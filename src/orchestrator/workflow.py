"""Workflow Manager — Defines and executes multi-step agent workflows."""

import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class CompensatingState(Enum):
    """Tracks whether a workflow is in compensation/rollback mode."""
    IDLE = "idle"
    ROLLING_BACK = "rolling_back"
    COMPLIANT = "compliant"  # Safe to proceed


class CompensationAction:
    """Represents a compensating action (rollback handler)."""
    
    def __init__(self, name: str, handler: Callable, target_step_id: Optional[str] = None):
        self.id = str(uuid4())
        self.name = name
        self.handler = handler
        self.target_step_id = target_step_id
        self.executed = False
        self.executed_at: Optional[float] = None
        self.success = False
    
    def execute(self) -> bool:
        """Execute the compensation action and track result."""
        try:
            self.handler()
            self.success = True
            self.executed = True
            self.executed_at = time.time()
            return True
        except Exception as e:
            logger.error(f"Compensation action {self.name} failed: {e}")
            self.executed = True
            self.executed_at = time.time()
            self.success = False
            return False


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStep:
    def __init__(self, name: str, handler: Callable, retries: int = 0, timeout: int = 300):
        self.id = str(uuid4())
        self.name = name
        self.handler = handler
        self.retries = retries
        self.timeout = timeout
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None


class Workflow:
    def __init__(self, name: str, description: str = ""):
        self.id = str(uuid4())
        self.name = name
        self.description = description
        self.steps: List[WorkflowStep] = []
        self._step_map: Dict[str, WorkflowStep] = {}
        self.status = StepStatus.PENDING
        self._compensation_state = CompensatingState.IDLE
        self._compensation_actions: List[CompensationAction] = []
        self._rollback_history: List[Dict[str, Any]] = []

    def add_step(self, step: WorkflowStep) -> "Workflow":
        self.steps.append(step)
        self._step_map[step.id] = step
        return self

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return self._step_map.get(step_id)
    
    def add_compensation(self, action: CompensationAction) -> None:
        """Add a compensation action for rollback."""
        self._compensation_actions.append(action)
    
    def get_compensation_state(self) -> CompensatingState:
        """Get the current compensation state."""
        return self._compensation_state
    
    def set_compensation_state(self, state: CompensatingState, reason: str = "") -> None:
        """Set the compensation state with audit log."""
        old_state = self._compensation_state
        self._compensation_state = state
        logger.info(
            f"Workflow {self.id} compensation state changed: {old_state.value} -> {state.value}. "
            f"Reason: {reason}"
        )
    
    def validate_transition(self, target_status: StepStatus) -> tuple[bool, str]:
        """
        Validate if a state transition is allowed given the compensation state.
        
        Returns (allowed, reason) tuple. If not allowed, reason explains why.
        """
        if self._compensation_state == CompensatingState.ROLLING_BACK:
            if target_status in (StepStatus.RUNNING, StepStatus.COMPLETED):
                return (
                    False,
                    f"Cannot transition to {target_status.value}: workflow is in rollback state"
                )
        return (True, "")
    
    def record_rollback(self, step_id: str, success: bool, error: Optional[str] = None) -> None:
        """Record a rollback attempt in history."""
        self._rollback_history.append({
            "step_id": step_id,
            "timestamp": time.time(),
            "success": success,
            "error": error
        })
    
    def can_proceed(self) -> bool:
        """Check if workflow can proceed to next step."""
        # Check compensation state is compliant
        if self._compensation_state == CompensatingState.ROLLING_BACK:
            return False
        return True


class WorkflowManager:
    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}

    def create_workflow(self, name: str, description: str = "") -> Workflow:
        workflow = Workflow(name, description)
        self._workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[Workflow]:
        return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        return self._workflows.pop(workflow_id, None) is not None

    def execute_workflow(self, workflow_id: str) -> bool:
        """
        Execute a workflow with compensation validation.
        
        Validates compensation state before allowing state transitions.
        Raises CompensationValidationError if transition violates invariants.
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False
        
        # Validate: Check if we can proceed given compensation state
        allowed, reason = workflow.validate_transition(StepStatus.RUNNING)
        if not allowed:
            logger.error(
                f"Workflow {workflow_id} transition blocked: {reason}"
            )
            from src.common.errors import CompensationValidationError
            raise CompensationValidationError(workflow_id, reason)
        
        workflow.status = StepStatus.RUNNING
        
        # Track completed steps for potential rollback
        completed_steps = []
        for step in workflow.steps:
            # Validate each step transition
            allowed, reason = workflow.validate_transition(StepStatus.RUNNING)
            if not allowed:
                # Trigger rollback for completed steps
                self._trigger_rollback(workflow, completed_steps)
                logger.error(
                    f"Workflow {workflow_id} step blocked: {reason}"
                )
                from src.common.errors import CompensationValidationError
                raise CompensationValidationError(workflow_id, f"Step {step.name}: {reason}")
            
            step.status = StepStatus.RUNNING
            try:
                result = step.handler()
                step.result = result
                step.status = StepStatus.COMPLETED
                completed_steps.append(step.id)
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                workflow.status = StepStatus.FAILED
                # Trigger rollback for previously completed steps
                self._trigger_rollback(workflow, completed_steps)
                return False

        workflow.status = StepStatus.COMPLETED
        # Mark as compliant - all compensation actions completed successfully
        workflow.set_compensation_state(CompensatingState.COMPLIANT, "All steps completed successfully")
        return True

    def _trigger_rollback(self, workflow: Workflow, completed_step_ids: List[str]) -> None:
        """Trigger rollback for completed steps using compensation actions."""
        workflow.set_compensation_state(
            CompensatingState.ROLLING_BACK,
            f"Initiating rollback for {len(completed_step_ids)} steps"
        )
        
        # Execute compensation actions in reverse order
        for comp_action in reversed(workflow._compensation_actions):
            # Find the corresponding completed step
            if comp_action.target_step_id in completed_step_ids:
                success = comp_action.execute()
                workflow.record_rollback(
                    comp_action.target_step_id,
                    success,
                    None if success else "Compensation action failed"
                )

# 2019-03-27T19:58:07 update

# 2019-05-09T09:42:56 update

# 2019-12-03T10:07:42 update

# 2020-01-16T18:43:28 update

# 2020-03-20T10:40:15 update

# 2020-04-17T15:36:50 update

# 2020-05-04T14:44:01 update

# 2020-06-16T13:17:31 update

# 2020-08-05T17:00:24 update

# 2020-09-04T08:29:23 update

# 2020-09-09T17:52:02 update

# 2020-10-23T10:57:44 update

# 2020-12-05T20:55:47 update

# 2021-01-15T19:23:40 update

# 2021-02-03T20:43:12 update

# 2021-03-16T12:26:47 update

# 2021-04-20T14:33:28 update

# 2021-10-14T15:03:32 update

# 2021-10-21T17:24:55 update

# 2021-11-16T17:01:08 update

# 2021-11-22T09:51:21 update

# 2021-12-21T16:15:47 update

# 2022-03-23T16:52:27 update

# 2022-12-21T09:25:50 update

# 2023-01-09T09:55:25 update

# 2023-01-13T11:06:15 update

# 2023-01-26T11:00:59 update

# 2023-02-23T08:56:54 update

# 2023-05-17T08:07:16 update

# 2023-06-06T17:09:34 update

# 2023-06-13T10:35:28 update

# 2023-08-24T20:36:06 update

# 2023-10-30T19:10:13 update

# 2024-01-02T08:27:25 update

# 2024-01-24T12:13:15 update

# 2024-02-08T13:35:49 update

# 2024-05-07T16:09:24 update

# 2024-05-11T09:48:46 update

# 2024-05-21T19:25:41 update

# 2024-06-05T12:00:30 update

# 2024-06-25T09:40:26 update

# 2024-09-17T13:49:39 update

# 2024-10-14T17:39:35 update

# 2024-11-27T20:14:35 update

# 2024-12-25T19:31:41 update

# 2025-01-16T13:15:09 update

# 2025-02-05T14:06:59 update

# 2025-02-17T20:55:11 update

# 2025-04-30T19:36:53 update

# 2025-07-17T10:14:40 update

# 2025-08-29T12:13:15 update

# 2025-09-03T13:51:11 update

# 2025-09-19T16:08:24 update

# 2025-11-27T08:38:12 update

# 2026-01-27T13:23:38 update

# 2026-01-28T11:22:50 update

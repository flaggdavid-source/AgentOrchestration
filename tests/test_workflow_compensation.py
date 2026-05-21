"""Tests for workflow compensation validation."""

import pytest
from unittest.mock import MagicMock

from src.orchestrator.workflow import (
    WorkflowManager,
    Workflow,
    WorkflowStep,
    CompensationAction,
    CompensatingState,
    StepStatus,
)
from src.common.errors import CompensationValidationError


class TestWorkflowCompensationValidation:
    """Test compensation validation in workflow execution."""

    def test_workflow_starts_with_idle_compensation_state(self):
        """Verify new workflows start with IDLE compensation state."""
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        assert wf.get_compensation_state() == CompensatingState.IDLE
        assert wf.can_proceed() is True

    def test_block_downstream_during_rollback(self):
        """
        Test that downstream transitions are blocked during rollback.
        
        This is the core bug being fixed: when rollback/compensation is triggered,
        the system should reject transitions like RUNNING or COMPLETED.
        """
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        # Simulate entering rollback state (as would happen after partial failure)
        wf.set_compensation_state(CompensatingState.ROLLING_BACK, "Partial failure detected")
        
        # Validation should now FAIL for RUNNING/COMPLETED transitions
        allowed, reason = wf.validate_transition(StepStatus.RUNNING)
        assert allowed is False
        assert "rollback" in reason.lower()
        
        # can_proceed should also return False
        assert wf.can_proceed() is False

    def test_transition_allowed_when_idle(self):
        """Verify transitions are allowed when compensation state is IDLE."""
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        # Should allow transitions when idle
        allowed, reason = wf.validate_transition(StepStatus.RUNNING)
        assert allowed is True
        assert reason == ""
        
        allowed, reason = wf.validate_transition(StepStatus.COMPLETED)
        assert allowed is True

    def test_transition_allowed_when_compliant(self):
        """Verify transitions are allowed when compensation state is compliant."""
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        # Set to compliant state (all compensation complete)
        wf.set_compensation_state(CompensatingState.COMPLIANT, "Rollback completed")
        
        allowed, reason = wf.validate_transition(StepStatus.RUNNING)
        assert allowed is True

    def test_exception_raised_on_invalid_transition(self):
        """
        Test that CompensationValidationError is raised on invalid transition.
        
        When execute_workflow encounters a workflow in rollback state,
        it should raise the validation error rather than proceeding.
        """
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        # Pre-set to rolling back state to simulate mid-execution rollback
        wf.set_compensation_state(CompensatingState.ROLLING_BACK, "Simulated rollback")
        
        # Execute should raise CompensationValidationError
        with pytest.raises(CompensationValidationError) as exc_info:
            wm.execute_workflow(wf.id)
        
        assert wf.id in str(exc_info.value)
        assert "rollback" in str(exc_info.value).lower()

    def test_rollback_triggered_on_step_failure(self):
        """
        Test that rollback is triggered when a step fails during execution.
        
        This tests the full flow: when a step fails, compensation state should
        be set to ROLLING_BACK and subsequent steps should be blocked.
        """
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        # Add steps - first succeeds, second fails
        step1 = WorkflowStep(
            name="success_step",
            handler=lambda: "ok"
        )
        step2 = WorkflowStep(
            name="fail_step", 
            handler=lambda: (_ for _ in ()).throw(Exception("Step failed"))
        )
        
        wf.add_step(step1)
        wf.add_step(step2)
        
        # Execute - should fail on step 2 and trigger rollback
        result = wm.execute_workflow(wf.id)
        
        assert result is False
        assert wf.status == StepStatus.FAILED
        # After failure, should be in rollback state
        assert wf.get_compensation_state() == CompensatingState.ROLLING_BACK

    def test_compensation_action_execution(self):
        """Test that compensation actions execute correctly during rollback."""
        mock_handler = MagicMock(return_value=True)
        comp_action = CompensationAction(
            name="compensate_step1",
            handler=mock_handler,
            target_step_id="step-1"
        )
        
        assert comp_action.execute() is True
        mock_handler.assert_called_once()
        assert comp_action.success is True
        assert comp_action.executed is True

    def test_compensation_action_failure_handled(self):
        """Test that compensation action failures are handled gracefully."""
        def failing_handler():
            raise Exception("Compensation failed")
        
        comp_action = CompensationAction(
            name="failing_comp",
            handler=failing_handler,
            target_step_id="step-1"
        )
        
        result = comp_action.execute()
        
        assert result is False
        assert comp_action.success is False
        assert comp_action.executed is True

    def test_rollback_history_recorded(self):
        """Test that rollback history is recorded."""
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        # Simulate recording rollback
        wf.record_rollback("step-1", True, None)
        wf.record_rollback("step-2", False, "Compensation failed")
        
        assert len(wf._rollback_history) == 2
        assert wf._rollback_history[0]["step_id"] == "step-1"
        assert wf._rollback_history[0]["success"] is True
        assert wf._rollback_history[1]["success"] is False

    def test_successful_workflow_marks_compliant(self):
        """
        Test that successful workflow completion marks compensation state as compliant.
        """
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow")
        
        step1 = WorkflowStep(
            name="success_step",
            handler=lambda: "ok"
        )
        wf.add_step(step1)
        
        result = wm.execute_workflow(wf.id)
        
        assert result is True
        assert wf.status == StepStatus.COMPLETED
        assert wf.get_compensation_state() == CompensatingState.COMPLIANT


class TestCompensationIntegration:
    """Integration tests for compensation validation."""

    def test_full_workflow_with_compensation(self):
        """Test a workflow with compensation actions defined."""
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Test workflow with compensation")
        
        # Add steps
        step1 = WorkflowStep(name="step1", handler=lambda: "result1")
        step2 = WorkflowStep(name="step2", handler=lambda: "result2")
        
        wf.add_step(step1)
        wf.add_step(step2)
        
        # Add compensation actions
        comp1 = CompensationAction(name="undo_step1", handler=lambda: None, target_step_id=step1.id)
        comp2 = CompensationAction(name="undo_step2", handler=lambda: None, target_step_id=step2.id)
        
        wf.add_compensation(comp1)
        wf.add_compensation(comp2)
        
        assert len(wf._compensation_actions) == 2
        assert wf.can_proceed() is True

    def test_workflow_with_failed_compensation_can_be_resumed_after_fix(self):
        """Test that a workflow can be retried after fixing compensation issues."""
        wm = WorkflowManager()
        wf = wm.create_workflow("test", "Retry test")
        
        # Start execution - fail on first step
        fail_step = WorkflowStep(name="fail", handler=lambda: (_ for _ in ()).throw(Exception("Fail")))
        wf.add_step(fail_step)
        
        result = wm.execute_workflow(wf.id)
        assert result is False
        assert wf.get_compensation_state() == CompensatingState.ROLLING_BACK
        
        # Now reset and retry - should be blocked until state is cleared
        # In practice, user would need to resolve compensation issues first
        # Here we simulate clearing the rollback state
        wf.set_compensation_state(CompensatingState.IDLE, "Manual reset after fix")
        
        allowed, _ = wf.validate_transition(StepStatus.RUNNING)
        assert allowed is True
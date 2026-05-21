"""Workflow Definition Parser — Parses YAML workflow definitions and validates structure."""

import logging
import re
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import yaml

from src.common.errors import ValidationError
from src.common.metrics import metrics

logger = logging.getLogger(__name__)


class DuplicateNodeError(ValidationError):
    """Raised when duplicate node identifiers are detected."""
    pass


class WorkflowNode:
    """Represents a node in a workflow graph."""
    
    def __init__(self, node_id: str, node_type: str, config: Dict[str, Any]):
        self.id = node_id
        self.type = node_type
        self.config = config
        self.dependencies: List[str] = []
    
    def __repr__(self):
        return f"WorkflowNode(id={self.id!r}, type={self.type!r})"


class WorkflowDefinition:
    """Represents a parsed workflow definition."""
    
    def __init__(self, name: str, version: str = "1.0"):
        self.id = str(uuid4())
        self.name = name
        self.version = version
        self.nodes: Dict[str, WorkflowNode] = {}
        self.imports: List[str] = []
    
    def add_node(self, node: WorkflowNode) -> None:
        self.nodes[node.id] = node
    
    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        return self.nodes.get(node_id)


class WorkflowParser:
    """Parses YAML workflow definitions and validates structure."""
    
    REQUIRED_FIELDS = ["name", "nodes"]
    VALID_NODE_TYPES = {"task", "handler", "agent", "queue", "router", "gateway"}
    
    def __init__(self):
        self._parsed_workflows: Dict[str, WorkflowDefinition] = {}
    
    def _check_duplicate_keys(self, yaml_content: str) -> None:
        """Check for duplicate node keys in YAML content before parsing."""
        lines = yaml_content.split('\n')
        in_nodes_section = False
        node_indent = 0
        node_keys: Set[str] = set()
        
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            
            # Detect start of nodes section
            if stripped.startswith('nodes:'):
                in_nodes_section = True
                node_indent = indent + 2  # Nodes are indented 2 more
                continue
            
            if not in_nodes_section:
                continue
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # Check if we've left the nodes section (less or equal indent, not a list item)
            if indent <= node_indent - 2 and not stripped.startswith('-'):
                break
            
            # Only check keys at the node level (exactly node_indent indent, not list items)
            if indent == node_indent and ':' in stripped and not stripped.startswith('-'):
                key = stripped.split(':')[0].strip()
                if key in node_keys:
                    logger.error(
                        f"Duplicate node identifier detected: {key}",
                        extra={"node_id": key}
                    )
                    metrics.increment("workflow.validation.duplicate_node")
                    raise DuplicateNodeError(
                        f"Duplicate node identifier: '{key}'. "
                        f"Each node must have a unique identifier."
                    )
                node_keys.add(key)
    
    def parse(self, yaml_content: str) -> WorkflowDefinition:
        """Parse YAML workflow definition and validate structure."""
        # First check for duplicate keys in raw YAML
        self._check_duplicate_keys(yaml_content)
        
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML: {e}")
            raise ValidationError(f"Invalid YAML syntax: {e}")
        
        if not isinstance(data, dict):
            raise ValidationError("Workflow definition must be a dictionary")
        
        # Validate required fields
        self._validate_required_fields(data)
        
        # Create workflow definition
        workflow = WorkflowDefinition(
            name=data.get("name", "unnamed"),
            version=data.get("version", "1.0")
        )
        
        # Process imports
        if "imports" in data:
            workflow.imports = self._process_imports(data["imports"])
        
        # Process nodes with duplicate detection
        self._process_nodes(data.get("nodes", {}), workflow)
        
        # Validate node dependencies
        self._validate_dependencies(workflow)
        
        # Store parsed workflow
        self._parsed_workflows[workflow.id] = workflow
        
        # Log successful parsing
        logger.info(
            f"Workflow '{workflow.name}' parsed successfully",
            extra={
                "workflow_id": workflow.id,
                "node_count": len(workflow.nodes),
                "import_count": len(workflow.imports)
            }
        )
        metrics.increment("workflow.parsed.total")
        metrics.increment(f"workflow.parsed.{workflow.name}.success")
        
        return workflow
    
    def _validate_required_fields(self, data: Dict[str, Any]) -> None:
        """Validate that required fields are present."""
        missing = [f for f in self.REQUIRED_FIELDS if f not in data]
        if missing:
            raise ValidationError(f"Missing required fields: {', '.join(missing)}")
    
    def _process_imports(self, imports: List[str]) -> List[str]:
        """Process workflow imports."""
        processed = []
        for imp in imports:
            if isinstance(imp, str):
                processed.append(imp)
                logger.debug(f"Processing import: {imp}")
            else:
                logger.warning(f"Ignoring invalid import: {imp}")
        return processed
    
    def _process_nodes(self, nodes_data: Dict[str, Any], workflow: WorkflowDefinition) -> None:
        """Process nodes with duplicate detection."""
        if not isinstance(nodes_data, dict):
            raise ValidationError("Nodes must be a dictionary")
        
        seen_ids: Set[str] = set()
        
        for node_id, node_config in nodes_data.items():
            # Check for duplicate node identifiers
            if node_id in seen_ids:
                logger.error(
                    f"Duplicate node identifier detected: {node_id}",
                    extra={
                        "node_id": node_id,
                        "workflow_name": workflow.name
                    }
                )
                metrics.increment("workflow.validation.duplicate_node")
                raise DuplicateNodeError(
                    f"Duplicate node identifier: '{node_id}'. "
                    f"Each node must have a unique identifier."
                )
            
            seen_ids.add(node_id)
            
            # Validate node configuration
            if not isinstance(node_config, dict):
                raise ValidationError(f"Node '{node_id}' config must be a dictionary")
            
            node_type = node_config.get("type")
            if not node_type:
                raise ValidationError(f"Node '{node_id}' missing 'type' field")
            
            if node_type not in self.VALID_NODE_TYPES:
                raise ValidationError(
                    f"Node '{node_id}' has invalid type '{node_type}'. "
                    f"Valid types: {', '.join(self.VALID_NODE_TYPES)}"
                )
            
            # Create node
            node = WorkflowNode(
                node_id=node_id,
                node_type=node_type,
                config=node_config
            )
            
            # Process dependencies
            if "depends_on" in node_config:
                deps = node_config["depends_on"]
                if isinstance(deps, list):
                    node.dependencies = deps
                elif isinstance(deps, str):
                    node.dependencies = [deps]
            
            workflow.add_node(node)
            logger.debug(f"Added node: {node_id} (type: {node_type})")
    
    def _validate_dependencies(self, workflow: WorkflowDefinition) -> None:
        """Validate that all dependencies reference existing nodes."""
        for node_id, node in workflow.nodes.items():
            for dep in node.dependencies:
                if dep not in workflow.nodes:
                    raise ValidationError(
                        f"Node '{node_id}' depends on non-existent node '{dep}'"
                    )
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get a parsed workflow by ID."""
        return self._parsed_workflows.get(workflow_id)
    
    def list_workflows(self) -> List[WorkflowDefinition]:
        """List all parsed workflows."""
        return list(self._parsed_workflows.values())


# Global parser instance
_parser = WorkflowParser()


def parse_workflow(yaml_content: str) -> WorkflowDefinition:
    """Parse a YAML workflow definition."""
    return _parser.parse(yaml_content)


def get_workflow(workflow_id: str) -> Optional[WorkflowDefinition]:
    """Get a parsed workflow by ID."""
    return _parser.get_workflow(workflow_id)


def list_workflows() -> List[WorkflowDefinition]:
    """List all parsed workflows."""
    return _parser.list_workflows()

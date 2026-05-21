"""Tests for workflow definition parser."""

import pytest

from src.common.errors import ValidationError
from src.orchestrator.workflow_parser import (
    DuplicateNodeError,
    WorkflowParser,
    parse_workflow,
)


class TestWorkflowParser:
    """Test cases for WorkflowParser."""

    def test_parse_valid_workflow(self):
        """Test parsing a valid workflow definition."""
        yaml_content = """
name: test-workflow
version: "1.0"
nodes:
  start:
    type: task
    handler: start_handler
  process:
    type: task
    handler: process_handler
    depends_on:
      - start
  end:
    type: task
    handler: end_handler
    depends_on:
      - process
"""
        workflow = parse_workflow(yaml_content)
        
        assert workflow.name == "test-workflow"
        assert workflow.version == "1.0"
        assert len(workflow.nodes) == 3
        assert "start" in workflow.nodes
        assert "process" in workflow.nodes
        assert "end" in workflow.nodes

    def test_parse_workflow_with_imports(self):
        """Test parsing workflow with imports."""
        yaml_content = """
name: workflow-with-imports
version: "1.0"
imports:
  - common-workflows/authentication
  - common-workflows/logging
nodes:
  task1:
    type: task
    handler: handler1
"""
        workflow = parse_workflow(yaml_content)
        
        assert workflow.name == "workflow-with-imports"
        assert len(workflow.imports) == 2
        assert "common-workflows/authentication" in workflow.imports

    def test_reject_duplicate_node_identifiers(self):
        """Test that duplicate node identifiers are rejected."""
        yaml_content = """
name: duplicate-nodes-workflow
version: "1.0"
nodes:
  task1:
    type: task
    handler: handler1
  task1:
    type: task
    handler: handler2
"""
        with pytest.raises(DuplicateNodeError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "Duplicate node identifier" in str(exc_info.value)
        assert "task1" in str(exc_info.value)

    def test_reject_duplicate_node_identifiers_complex(self):
        """Test duplicate detection with more complex duplicate scenario."""
        yaml_content = """
name: complex-duplicate-workflow
version: "1.0"
nodes:
  node_a:
    type: agent
    config: {}
  node_b:
    type: handler
    config: {}
  node_a:
    type: queue
    config: {}
"""
        with pytest.raises(DuplicateNodeError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "node_a" in str(exc_info.value)

    def test_reject_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        yaml_content = """
version: "1.0"
nodes:
  task1:
    type: task
"""
        with pytest.raises(ValidationError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "Missing required fields" in str(exc_info.value)
        assert "name" in str(exc_info.value)

    def test_reject_invalid_node_type(self):
        """Test that invalid node types are rejected."""
        yaml_content = """
name: invalid-type-workflow
version: "1.0"
nodes:
  task1:
    type: invalid_type
"""
        with pytest.raises(ValidationError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "invalid type" in str(exc_info.value).lower()

    def test_reject_missing_node_type(self):
        """Test that nodes without type are rejected."""
        yaml_content = """
name: no-type-workflow
version: "1.0"
nodes:
  task1:
    handler: some_handler
"""
        with pytest.raises(ValidationError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "missing 'type'" in str(exc_info.value)

    def test_reject_invalid_dependency(self):
        """Test that invalid dependencies are rejected."""
        yaml_content = """
name: invalid-dep-workflow
version: "1.0"
nodes:
  task1:
    type: task
    handler: handler1
    depends_on:
      - nonexistent
"""
        with pytest.raises(ValidationError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "non-existent node" in str(exc_info.value).lower()

    def test_reject_invalid_yaml(self):
        """Test that invalid YAML is rejected."""
        yaml_content = """
name: invalid-yaml
  invalid: indentation
"""
        with pytest.raises(ValidationError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "Invalid YAML" in str(exc_info.value)

    def test_reject_non_dict_nodes(self):
        """Test that non-dict nodes are rejected."""
        yaml_content = """
name: non-dict-nodes
version: "1.0"
nodes:
  - task1
  - task2
"""
        with pytest.raises(ValidationError) as exc_info:
            parse_workflow(yaml_content)
        
        assert "Nodes must be a dictionary" in str(exc_info.value)

    def test_workflow_parser_instance(self):
        """Test using WorkflowParser directly."""
        parser = WorkflowParser()
        
        yaml_content = """
name: direct-parser-test
version: "1.0"
nodes:
  node1:
    type: task
"""
        workflow = parser.parse(yaml_content)
        
        assert workflow.name == "direct-parser-test"
        assert len(workflow.nodes) == 1
        
        # Test get_workflow
        retrieved = parser.get_workflow(workflow.id)
        assert retrieved is not None
        assert retrieved.id == workflow.id
        
        # Test list_workflows
        workflows = parser.list_workflows()
        assert len(workflows) >= 1

    def test_node_dependencies(self):
        """Test that node dependencies are properly parsed."""
        yaml_content = """
name: dependencies-test
version: "1.0"
nodes:
  step1:
    type: task
  step2:
    type: task
    depends_on: step1
  step3:
    type: task
    depends_on:
      - step1
      - step2
"""
        workflow = parse_workflow(yaml_content)
        
        step1 = workflow.get_node("step1")
        step2 = workflow.get_node("step2")
        step3 = workflow.get_node("step3")
        
        assert step1.dependencies == []
        assert step2.dependencies == ["step1"]
        assert step3.dependencies == ["step1", "step2"]


class TestDuplicateNodeMetrics:
    """Test that metrics are properly recorded for duplicate detection."""

    def test_metrics_on_duplicate_detection(self):
        """Test that metrics are incremented on duplicate detection."""
        from src.common.metrics import metrics
        
        # Get initial count
        initial_count = metrics._counters.get("workflow.validation.duplicate_node", 0)
        
        yaml_content = """
name: metrics-test
version: "1.0"
nodes:
  dup_node:
    type: task
  dup_node:
    type: handler
"""
        with pytest.raises(DuplicateNodeError):
            parse_workflow(yaml_content)
        
        # Verify metric was incremented
        final_count = metrics._counters.get("workflow.validation.duplicate_node", 0)
        assert final_count == initial_count + 1
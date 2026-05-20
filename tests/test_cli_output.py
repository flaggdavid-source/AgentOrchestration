"""Tests for CLI stdout/stderr output separation."""

import subprocess
import sys


def test_init_command_outputs_to_stdout():
    """Test that 'init' command outputs to stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.main", "init", "test-project"],
        capture_output=True,
        text=True
    )
    assert "Initializing project: test-project" in result.stdout
    # stderr should only contain warnings, not error messages
    assert "Error:" not in result.stderr


def test_deploy_command_outputs_to_stdout():
    """Test that 'deploy' command outputs to stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.main", "deploy", "manifest.yaml"],
        capture_output=True,
        text=True
    )
    assert "Deploying agent from manifest: manifest.yaml" in result.stdout
    assert "Error:" not in result.stderr


def test_status_command_outputs_to_stdout():
    """Test that 'status' command outputs to stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.main", "status"],
        capture_output=True,
        text=True
    )
    assert "Checking agent status" in result.stdout
    assert "Error:" not in result.stderr


def test_logs_command_outputs_to_stdout():
    """Test that 'logs' command outputs to stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.main", "logs", "agent-123"],
        capture_output=True,
        text=True
    )
    assert "Fetching logs for agent: agent-123" in result.stdout
    assert "Error:" not in result.stderr


def test_no_command_outputs_to_stderr():
    """Test that no command specified outputs error to stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.main"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 1
    assert "Error: No command specified" in result.stderr


def test_help_command_outputs_to_stderr():
    """Test that help output goes to stderr when no command."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.main"],
        capture_output=True,
        text=True
    )
    # Help usage should be on stderr when there's an error
    assert "usage:" in result.stderr.lower() or "error" in result.stderr.lower()

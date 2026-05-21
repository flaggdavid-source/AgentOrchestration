import os
import tempfile
import pytest
from pathlib import Path
from src.agent.sandbox import AgentSandbox


class TestAgentSandbox:
    def test_base_path_resolved_from_relative(self):
        """Test that relative base_path is resolved to absolute path."""
        # Create a temporary directory to use as base
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a relative path from within tmpdir
            rel_path = "sandbox_dir"
            full_path = os.path.join(tmpdir, rel_path)
            os.makedirs(full_path, exist_ok=True)

            # Save current directory and change to tmpdir to test relative path resolution
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Create sandbox with relative path (resolved from tmpdir)
                sandbox = AgentSandbox(base_path=rel_path)

                # The base_path should be resolved to absolute path
                assert sandbox.base_path.is_absolute()
                assert sandbox.base_path == Path(full_path).resolve()
            finally:
                os.chdir(original_cwd)

    def test_base_path_resolved_from_symlink(self):
        """Test that symlinks in base_path are resolved to canonical path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a real directory
            real_dir = os.path.join(tmpdir, "real_sandbox")
            os.makedirs(real_dir, exist_ok=True)

            # Create a symlink to the real directory
            symlink_dir = os.path.join(tmpdir, "symlink_sandbox")
            os.symlink(real_dir, symlink_dir)

            # Create sandbox with symlink path
            sandbox = AgentSandbox(base_path=symlink_dir)

            # The base_path should be resolved to the canonical path (not the symlink)
            assert sandbox.base_path.is_absolute()
            assert sandbox.base_path == Path(real_dir).resolve()

    def test_base_path_default_is_resolved(self):
        """Test that default base_path (temp directory) is also resolved."""
        sandbox = AgentSandbox()

        # The default should also be an absolute resolved path
        assert sandbox.base_path.is_absolute()
        assert sandbox.base_path.exists()

    def test_create_sandbox_uses_resolved_base_path(self):
        """Test that created sandbox paths use the resolved base_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = AgentSandbox(base_path=tmpdir)

            # Create an agent sandbox
            agent_path = sandbox.create("test-agent")

            # The created path should be under the resolved base_path
            assert agent_path.is_absolute()
            assert agent_path.parent == sandbox.base_path

    def test_get_path_returns_resolved_path(self):
        """Test that get_path returns paths under resolved base_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = AgentSandbox(base_path=tmpdir)

            agent_id = "test-agent"
            sandbox.create(agent_id)

            path = sandbox.get_path(agent_id)
            assert path is not None
            assert path.is_absolute()
            assert path.parent == sandbox.base_path
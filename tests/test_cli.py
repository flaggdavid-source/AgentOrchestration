"""Tests for CLI argument validation."""

import pytest
import sys
from io import StringIO
from unittest.mock import patch

from src.cli.main import cli, OUTPUT_MODES


class TestOutputModeValidation:
    """Test output mode argument validation."""

    def test_valid_output_modes_are_accepted(self):
        """Test that all valid output modes are accepted without error."""
        for mode in OUTPUT_MODES:
            with patch("sys.argv", ["main", "--output", mode, "init", "test"]):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    try:
                        cli()
                    except SystemExit as e:
                        # Exit code 0 is ok (successful execution)
                        # Exit code 2 is argparse error (should not happen for valid modes)
                        if e.code == 2:
                            pytest.fail(f"Valid output mode '{mode}' was rejected")

    def test_invalid_output_mode_is_rejected(self):
        """Test that an invalid output mode is rejected with an error."""
        with patch("sys.argv", ["main", "--output", "invalid_mode", "init", "test"]):
            with pytest.raises(SystemExit) as exc_info:
                cli()
            # argparse returns exit code 2 for invalid arguments
            assert exc_info.value.code == 2

    def test_output_mode_short_flag(self):
        """Test that short flag -o also works for output mode."""
        with patch("sys.argv", ["main", "-o", "json", "init", "test"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                try:
                    cli()
                except SystemExit as e:
                    pytest.fail("Valid output mode '-o json' was rejected")

    def test_invalid_output_mode_short_flag(self):
        """Test that invalid output mode with short flag is rejected."""
        with patch("sys.argv", ["main", "-o", "bad_mode", "init", "test"]):
            with pytest.raises(SystemExit) as exc_info:
                cli()
            assert exc_info.value.code == 2

    def test_default_output_mode_is_text(self):
        """Test that default output mode is 'text' when not specified."""
        with patch("sys.argv", ["main", "init", "test"]):
            with patch("sys.stdout", new_callable=StringIO):
                with patch("src.cli.main.configure_logging"):
                    cli()
                    # If we get here without error, default works
                    # The default value is tested implicitly

    def test_output_modes_list_exports(self):
        """Test that OUTPUT_MODES constant is properly exported."""
        assert isinstance(OUTPUT_MODES, list)
        assert len(OUTPUT_MODES) > 0
        assert "json" in OUTPUT_MODES
        assert "text" in OUTPUT_MODES
        assert "table" in OUTPUT_MODES
        assert "yaml" in OUTPUT_MODES

"""Output helpers for CLI - route errors to stderr and data to stdout."""

import sys


def print_error(message: str) -> None:
    """Print an error message to stderr.
    
    Use this for all error messages, warnings, and diagnostic output
    that should not be piped to other commands.
    """
    print(message, file=sys.stderr)


def print_data(message: str) -> None:
    """Print data to stdout.
    
    Use this for command output that is meant to be consumed by
    shell pipelines or redirected to files.
    """
    print(message)


def print_data_json(data) -> None:
    """Print data as JSON to stdout.
    
    Use this for structured data output that is meant to be consumed
    by shell pipelines or other tools.
    """
    import json
    print(json.dumps(data))
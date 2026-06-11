"""Shared fixtures for the test suite."""
import pytest
import sys
import os

# Make the project root importable without installation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def in_memory_db_path(tmp_path):
    """Return a path inside a temp directory for each test (fresh DB)."""
    return str(tmp_path / "test.db")

"""Tests for installed package metadata."""

from lunchmoney_mcp.__about__ import __application__, __version__


def test_package_metadata_matches_project_configuration() -> None:
    """Expose the configured distribution name and installed version."""
    assert __application__ == "lunchmoney-mcp"
    assert __version__ == "0.4.0"

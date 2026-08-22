"""Proves the toolchain is wired up: package imports, pytest runs, async works.

This file exists so PR 2 has something for ruff, pyright, and pytest to act on.
It is deleted once real tests arrive in Phase 1.
"""

from app import __version__


def test_package_imports() -> None:
    assert __version__ == "0.1.0"


async def test_asyncio_mode_is_configured() -> None:
    """Fails to run at all if `asyncio_mode = "auto"` is not set."""
    assert True

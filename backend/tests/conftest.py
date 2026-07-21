"""Pytest config — session-scoped asyncio loop for Motor compatibility.

Motor's internal executor binds to the event loop on first use. Without a
session-scoped loop, every async test gets a fresh loop and Motor's cached
executor tries to `run_in_executor` on a closed loop. A session-scoped loop
keeps a single loop alive across all async tests in the file.
"""
import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Override pytest-asyncio's default function-scoped loop with a session loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

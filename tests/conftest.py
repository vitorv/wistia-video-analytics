"""Shared pytest fixtures."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    """Return a loader for the sanitized sample API responses in tests/fixtures/."""

    def _load(name: str) -> Any:
        return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))

    return _load

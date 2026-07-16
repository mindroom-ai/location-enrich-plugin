# ruff: noqa: INP001
"""Behavior tests for location-enrich plugin."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from importlib import util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from mindroom.hooks.decorators import get_hook_metadata


def _load_hooks_module() -> ModuleType:
    hooks_path = Path(__file__).resolve().parents[1] / "hooks.py"
    module_name = "mindroom_test_location_enrich_hooks"
    spec = util.spec_from_file_location(module_name, hooks_path)
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hooks = _load_hooks_module()


def test_hook_metadata_matches_manifest_contract() -> None:
    """Hook should stay registered for message enrichment."""
    metadata = get_hook_metadata(hooks.location_enrich)

    assert metadata is not None
    assert metadata.event_name == "message:enrich"
    assert metadata.hook_name == "location-enrich"
    assert metadata.timeout_ms == 1200


def test_fresh_driving_fix_builds_home_aware_enrichment() -> None:
    """Fresh fixes should expose movement and known-place context."""
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    fix = hooks.LocationFix(
        latitude=37.7749,
        longitude=-122.4194,
        velocity=20.0,
        altitude=15.2,
        timestamp=int((now - timedelta(seconds=12)).timestamp()),
    )
    places = [hooks.KnownPlace(name="Home", latitude=37.7749, longitude=-122.4194)]

    [item] = hooks.build_location_enrichment(fix=fix, places=places, now=now)

    assert item.key == "location"
    assert "status: fresh" in item.text
    assert "movement_state: driving" in item.text
    assert "nearby_place: Home" in item.text
    assert "at_home: true" in item.text
    assert "altitude_m: 15" in item.text
    assert "prefer voice replies" in item.text


def test_stale_fix_is_labeled_without_movement_advice() -> None:
    """Old fixes should warn callers instead of suggesting movement behavior."""
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    fix = hooks.LocationFix(
        latitude=37.7749,
        longitude=-122.4194,
        velocity=20.0,
        timestamp=int((now - timedelta(minutes=31)).timestamp()),
    )

    [item] = hooks.build_location_enrichment(fix=fix, places=[], now=now)

    assert "status: stale" in item.text
    assert "may be outdated" in item.text
    assert "movement_state" not in item.text
    assert "suggestion:" not in item.text


@pytest.mark.asyncio
async def test_hook_without_api_key_performs_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing credentials should make enrichment a clean no-op."""
    monkeypatch.delenv("DAWARICH_API_KEY", raising=False)
    ctx = SimpleNamespace()

    assert await hooks.location_enrich(ctx) == []

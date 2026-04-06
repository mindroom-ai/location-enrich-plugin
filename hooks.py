"""Dawarich-backed message enrichment hook."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from mindroom.constants import resolve_config_relative_path
from mindroom.hooks import EnrichmentItem, MessageEnrichContext, hook

DEFAULT_DAWARICH_URL = "http://localhost:3000"
DEFAULT_PLACES_PATH = Path.home() / ".mindroom/plugins/location-enrich/places.yaml"
HTTP_TIMEOUT_SECONDS = 5.0
STALE_AFTER_SECONDS = 30 * 60
NEARBY_THRESHOLD_M = 500.0
AT_HOME_THRESHOLD_M = 200.0


class KnownPlace(BaseModel):
    """One known place loaded from YAML."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(validation_alias=AliasChoices("name", "label"))
    latitude: float = Field(validation_alias=AliasChoices("latitude", "lat"))
    longitude: float = Field(validation_alias=AliasChoices("longitude", "lon"))


class NearbyPlace(BaseModel):
    """A known place matched against the current fix."""

    place: KnownPlace
    distance_m: int


class LocationFix(BaseModel):
    """One latest-location point returned by Dawarich."""

    model_config = ConfigDict(extra="ignore")

    latitude: float = Field(validation_alias=AliasChoices("latitude", "lat"))
    longitude: float = Field(validation_alias=AliasChoices("longitude", "lon"))
    velocity_mps: float = Field(default=0.0, validation_alias=AliasChoices("velocity", "speed"))
    altitude_m: float | None = Field(default=None, validation_alias="altitude")
    timestamp: int

    @property
    def recorded_at(self) -> datetime:
        timestamp_value = self.timestamp / 1000 if self.timestamp > 1_000_000_000_000 else self.timestamp
        return datetime.fromtimestamp(timestamp_value, tz=UTC)


class KnownPlacesDocument(BaseModel):
    """Known places file, accepting either a bare list or a locations wrapper."""

    model_config = ConfigDict(extra="ignore")

    locations: list[KnownPlace] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, value: object) -> dict[str, object]:
        if isinstance(value, list):
            return {"locations": value}
        if isinstance(value, dict):
            raw_locations = value.get("locations", value)
            if isinstance(raw_locations, list):
                return {"locations": raw_locations}
        return {"locations": []}

    @field_validator("locations", mode="before")
    @classmethod
    def parse_locations(cls, value: object) -> list[KnownPlace]:
        if not isinstance(value, list):
            return []
        places: list[KnownPlace] = []
        for item in value:
            try:
                places.append(KnownPlace.model_validate(item))
            except ValidationError:
                continue
        return places


class DawarichLatestResponse(BaseModel):
    """Latest-point response from Dawarich."""

    model_config = ConfigDict(extra="ignore")

    points: list[LocationFix] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, value: object) -> dict[str, object]:
        if isinstance(value, list):
            return {"points": value}
        if isinstance(value, dict):
            raw_points = value.get("points") or value.get("data")
            if isinstance(raw_points, list):
                return {"points": raw_points}
            if "latitude" in value or "lat" in value:
                return {"points": [value]}
        return {"points": []}

    @property
    def latest_fix(self) -> LocationFix | None:
        return self.points[0] if self.points else None


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two coordinates in meters."""
    earth_radius_m = 6_371_000.0
    lat1_rad = lat1 * 3.141592653589793 / 180.0
    lat2_rad = lat2 * 3.141592653589793 / 180.0
    dlat_rad = (lat2 - lat1) * 3.141592653589793 / 180.0
    dlon_rad = (lon2 - lon1) * 3.141592653589793 / 180.0
    a = (pow(math.sin(dlat_rad / 2.0), 2)) + math.cos(lat1_rad) * math.cos(lat2_rad) * pow(math.sin(dlon_rad / 2.0), 2)
    return earth_radius_m * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_movement(velocity_mps: float) -> str:
    """Classify one velocity into a coarse movement state."""
    if velocity_mps < 0.5:
        return "stationary"
    if velocity_mps < 2.0:
        return "walking"
    if velocity_mps < 5.0:
        return "jogging"
    if velocity_mps < 15.0:
        return "cycling"
    if velocity_mps < 40.0:
        return "driving"
    return "highway"


def _setting_str(settings: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = settings.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_places_path(ctx: MessageEnrichContext) -> Path:
    """Resolve the configured known-places YAML path."""
    configured_path = _setting_str(ctx.settings, "places_path", "known_places_path")
    if configured_path is None:
        return DEFAULT_PLACES_PATH
    return resolve_config_relative_path(configured_path, ctx.runtime_paths)


def load_known_places(path: Path) -> list[KnownPlace]:
    """Load known places from YAML."""
    try:
        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []

    try:
        return KnownPlacesDocument.model_validate(raw_data).locations
    except ValidationError:
        return []


def find_nearby_place(
    latitude: float,
    longitude: float,
    places: list[KnownPlace],
    *,
    threshold_m: float = NEARBY_THRESHOLD_M,
) -> NearbyPlace | None:
    """Return the nearest known place within the configured threshold."""
    best_match: NearbyPlace | None = None
    for place in places:
        distance_m = haversine_distance_m(latitude, longitude, place.latitude, place.longitude)
        if distance_m > threshold_m:
            continue
        rounded_distance = round(distance_m)
        if best_match is None or rounded_distance < best_match.distance_m:
            best_match = NearbyPlace(place=place, distance_m=rounded_distance)
    return best_match


def _home_place(places: list[KnownPlace]) -> KnownPlace | None:
    for place in places:
        if place.name.lower() == "home":
            return place
    return None


def age_seconds(fix: LocationFix, *, now: datetime | None = None) -> int:
    """Return point age in whole seconds."""
    effective_now = now or datetime.now(tz=UTC)
    return max(0, round((effective_now - fix.recorded_at).total_seconds()))


def build_location_enrichment(
    *,
    fix: LocationFix,
    places: list[KnownPlace],
    now: datetime | None = None,
) -> list[EnrichmentItem]:
    """Build the model-facing enrichment item for one latest fix."""
    age_s = age_seconds(fix, now=now)
    nearby = find_nearby_place(fix.latitude, fix.longitude, places)
    home = _home_place(places)
    home_distance_m = (
        round(haversine_distance_m(fix.latitude, fix.longitude, home.latitude, home.longitude)) if home is not None else None
    )
    at_home = home_distance_m is not None and home_distance_m <= AT_HOME_THRESHOLD_M

    if age_s > STALE_AFTER_SECONDS:
        lines = [
            "status: stale",
            f"latitude: {fix.latitude:.4f}",
            f"longitude: {fix.longitude:.4f}",
            f"location_age_seconds: {age_s}",
            f"nearby_place: {nearby.place.name if nearby is not None else 'unknown'}",
            f"at_home: {str(at_home).lower()}",
            "note: Location data is over 30 minutes old and may be outdated",
        ]
        if home_distance_m is not None:
            lines.append(f"distance_from_home_m: {home_distance_m}")
        return [EnrichmentItem(key="location", text="\n".join(lines))]

    movement_state = classify_movement(fix.velocity_mps)
    suggestion: str | None = None
    if movement_state in {"driving", "highway"}:
        suggestion = "User appears to be driving - prefer voice replies and keep text short"
    elif movement_state in {"walking", "jogging"}:
        suggestion = "User appears to be walking - keep replies concise"

    lines = [
        "status: fresh",
        f"latitude: {fix.latitude:.4f}",
        f"longitude: {fix.longitude:.4f}",
        f"velocity_mps: {fix.velocity_mps:.1f}",
        f"movement_state: {movement_state}",
        f"nearby_place: {nearby.place.name if nearby is not None else 'unknown'}",
        f"at_home: {str(at_home).lower()}",
        f"location_age_seconds: {age_s}",
    ]
    if fix.altitude_m is not None:
        lines.append(f"altitude_m: {round(fix.altitude_m)}")
    if home_distance_m is not None:
        lines.append(f"distance_from_home_m: {home_distance_m}")
    if suggestion is not None:
        lines.append(f"suggestion: {suggestion}")
    return [EnrichmentItem(key="location", text="\n".join(lines))]


async def fetch_latest_fix(api_key: str, *, dawarich_url: str = DEFAULT_DAWARICH_URL) -> LocationFix | None:
    """Fetch and parse the newest Dawarich point."""
    url = f"{dawarich_url.rstrip('/')}/api/v1/points"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(url, params={"api_key": api_key, "per_page": 1})
        response.raise_for_status()

    try:
        return DawarichLatestResponse.model_validate(response.json()).latest_fix
    except ValidationError:
        return None


@hook(event="message:enrich", name="location-enrich")
async def location_enrich(ctx: MessageEnrichContext) -> list[EnrichmentItem]:
    """Enrich inbound messages with the latest known location context."""
    api_key = os.getenv("DAWARICH_API_KEY", "").strip()
    if not api_key:
        return []

    dawarich_url = _setting_str(ctx.settings, "dawarich_url") or os.getenv("DAWARICH_URL", DEFAULT_DAWARICH_URL)
    places = load_known_places(resolve_places_path(ctx))

    try:
        fix = await fetch_latest_fix(api_key, dawarich_url=dawarich_url)
    except (httpx.HTTPError, ValueError) as exc:
        ctx.logger.warning("Failed to fetch Dawarich location", error=str(exc), correlation_id=ctx.correlation_id)
        return []

    if fix is None:
        return []
    return build_location_enrichment(fix=fix, places=places)

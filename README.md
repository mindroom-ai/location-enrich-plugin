# Location Enrich

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/mindroom-ai/location-enrich-plugin/actions/workflows/plugin-ci.yml/badge.svg)](https://github.com/mindroom-ai/location-enrich-plugin/actions/workflows/plugin-ci.yml)
[![Docs](https://img.shields.io/badge/docs-plugins-blue)](https://docs.mindroom.chat/plugins/)
[![Hooks](https://img.shields.io/badge/docs-hooks-blue)](https://docs.mindroom.chat/hooks/)

<picture>
  <source media="(prefers-reduced-motion: no-preference)" srcset="https://raw.githubusercontent.com/mindroom-ai/mindroom/main/assets/logo/logo-mark-animated.svg" />
  <img src="https://raw.githubusercontent.com/mindroom-ai/mindroom/main/assets/logo/logo-mark.svg" alt="MindRoom Logo" align="right" width="120" />
</picture>

A [MindRoom](https://github.com/mindroom-ai/mindroom) hook plugin that adds real-time location context from [Dawarich](https://dawarich.app/) to agent prompts, so agents know where you are and whether you are stationary, walking, or driving.

- **Movement-aware replies:** classifies speed (`stationary`, `walking`, `jogging`, `cycling`, `driving`, `highway`) and adds concise-reply guidance while walking or voice-first guidance while driving.
- **Known places:** matches GPS coordinates against a local YAML list of named places (`Home`, `Office`, etc.) and reports `nearby_place`, `at_home`, and `distance_from_home_m`.
- **Stale-fix protection:** flags fixes older than 30 minutes as `stale` and drops live movement hints so agents do not act on outdated coordinates.
- **Fast and fail-open:** stays silent when `DAWARICH_API_KEY` is unset, caches the latest fix for 15 seconds, and if Dawarich is unreachable reuses the last cached fix when one exists (staying silent when none is available).

On each incoming message, the plugin injects a transient `location` enrichment block for the model:

```text
status: fresh
latitude: 37.7749
longitude: -122.4194
velocity_mps: 1.4
movement_state: walking
nearby_place: Home
at_home: true
location_age_seconds: 12
altitude_m: 16
distance_from_home_m: 18
suggestion: User appears to be walking - keep replies concise
```

## Quick start

```bash
mindroom plugins install location-enrich-plugin
```

Set `DAWARICH_API_KEY` in MindRoom's environment, then add the plugin to `config.yaml`:

```yaml
plugins:
  - path: plugins/location-enrich-plugin
    settings:
      dawarich_url: "https://dawarich.example.com"  # optional; defaults to DAWARICH_URL or http://localhost:3000
      places_path: "places.yaml"                    # optional; defaults to ~/.mindroom/plugins/location-enrich/places.yaml
```

Note that `places_path` defaults to `~/.mindroom/plugins/location-enrich/places.yaml` (without the `-plugin` suffix) — either place your known-places file there or set `places_path` explicitly (relative paths resolve against your MindRoom config directory).

Update later with `mindroom plugins update location-enrich-plugin`.
Needs MindRoom v2026.11.180 or later (plugin API 1.0).

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `DAWARICH_API_KEY` (env) | required | Dawarich API key. If unset or blank, the hook is a silent no-op and makes no network requests. |
| `dawarich_url` (`DAWARICH_URL` env) | `http://localhost:3000` | Dawarich base URL. Precedence: `dawarich_url` > `DAWARICH_URL` > `http://localhost:3000`. |
| `places_path` (alias: `known_places_path`) | `~/.mindroom/plugins/location-enrich/places.yaml` | Known-places YAML file. Precedence: `places_path` > `known_places_path` > default path. Relative paths resolve against the active MindRoom config location. |

No agent tools are required; this plugin is hooks-only.

<details>
<summary><b>Known places file</b></summary>

Define your known locations as a bare YAML list:

```yaml
- name: Home
  latitude: 37.7749
  longitude: -122.4194
- name: Office
  latitude: 37.7897
  longitude: -122.4014
```

You can also wrap the list under a top-level `locations:` key, and use `label` instead of `name` or `lat` / `lon` instead of `latitude` / `longitude`:

```yaml
locations:
  - label: Home
    lat: 37.7749
    lon: -122.4194
```

- An entry named `Home` (case-insensitive) enables `at_home` and `distance_from_home_m`.
- Invalid entries are skipped; a missing or unreadable file falls back to an empty list.
- The file is cached in memory and reloaded automatically when its modification time changes.

</details>

<details>
<summary><b>How it works</b></summary>

1. If `DAWARICH_API_KEY` is missing or blank, the hook returns immediately with no I/O.
2. Otherwise, it fetches `GET <dawarich_url>/api/v1/points?per_page=1` with `api_key` under a `0.9 s` deadline (`1.0 s` HTTP timeout, `1200 ms` hook timeout).
3. The latest fix is cached per `(api_key, dawarich_url)` for `15 s`. On transient network errors or timeouts, the hook reuses the last cached fix if one exists; otherwise it logs a warning and returns no enrichment.
4. Distances are computed with the haversine formula: the closest known place within `500 m` sets `nearby_place` (otherwise `unknown`), and being within `200 m` of `Home` sets `at_home: true`.
5. For fixes up to `30` minutes old (`location_age_seconds <= 1800`), movement is classified from `velocity_mps`:
   - `< 0.5 m/s`: `stationary`
   - `< 2.0 m/s`: `walking` (adds concise-reply suggestion)
   - `< 5.0 m/s`: `jogging` (adds concise-reply suggestion)
   - `< 15.0 m/s`: `cycling`
   - `< 40.0 m/s`: `driving` (adds voice-first, short-text suggestion)
   - `>= 40.0 m/s`: `highway` (adds voice-first, short-text suggestion)
6. Fixes older than `30` minutes (`location_age_seconds > 1800`) switch to stale mode: `status: stale` with a staleness note, omitting `velocity_mps`, `movement_state`, `altitude_m`, and `suggestion`.
7. The hook emits one `location` enrichment item with `persist=False` (transient context for the current turn only, not saved onto the stored user message) and `minimal_required=True`.

</details>

## Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `location-enrich` | `message:enrich` | Fetch the latest Dawarich point and inject transient `location` context into the prompt |

# Location Enrich

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-plugins-blue)](https://docs.mindroom.chat/plugins/)
[![Hooks](https://img.shields.io/badge/docs-hooks-blue)](https://docs.mindroom.chat/hooks/)

<img src="https://media.githubusercontent.com/media/mindroom-ai/mindroom/refs/heads/main/frontend/public/logo.png" alt="MindRoom Logo" align="right" width="120" />

Enrich [MindRoom](https://github.com/mindroom-ai/mindroom) agent prompts with real-time location context from [Dawarich](https://dawarich.app/).

Agents see where the user is, how recent that fix is, whether it matches a known place, and whether they appear to be walking or driving. That lets the model adapt its behavior: shorter replies while in motion, voice-first when driving, and location-aware reasoning at home or other named places.

## Features

- Fetches the latest Dawarich point on every `message:enrich`
- Matches coordinates against a YAML file of known places
- Classifies movement as `stationary`, `walking`, `jogging`, `cycling`, `driving`, or `highway`
- Adds `nearby_place`, `at_home`, `distance_from_home_m`, `location_age_seconds`, and altitude when available
- Marks location data as stale after 30 minutes and warns the model that it may be outdated
- Adds concise reply guidance when the user appears to be driving or walking
- Caches the latest successful fix for 15 seconds and reuses it on transient fetch failures

## How It Works

1. The `location-enrich` hook runs on every `message:enrich`.
2. It fetches the latest GPS fix from Dawarich using `DAWARICH_API_KEY`.
3. The fix is compared against a local YAML file of known places such as home, office, or gym.
4. The plugin injects a compact location summary into the prompt for the active turn.
5. If the fix is stale, the plugin marks it as stale instead of presenting it as live context.

## Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `location-enrich` | `message:enrich` | Fetch the latest Dawarich point and inject location context into the prompt |

## Configuration

Set these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DAWARICH_API_KEY` | Yes | API key for your Dawarich instance |
| `DAWARICH_URL` | No | Dawarich base URL. Defaults to `http://localhost:3000` |

You can also configure plugin settings in `config.yaml`:

```yaml
plugins:
  - path: plugins/location-enrich
    settings:
      dawarich_url: "https://your-dawarich-instance.example.com"
      places_path: "path/to/places.yaml"
```

Supported plugin settings:

| Setting | Required | Description |
|---------|----------|-------------|
| `dawarich_url` | No | Overrides the Dawarich base URL |
| `places_path` | No | Path to the YAML known-places file |
| `known_places_path` | No | Alias for `places_path` |

Relative place-file paths are resolved against the active MindRoom config location. The default place-file path is `~/.mindroom/plugins/location-enrich/places.yaml`.

### Known Places File

Create a YAML file with your known locations:

```yaml
- name: Home
  latitude: 47.6062
  longitude: -122.3321
- name: Office
  latitude: 47.6205
  longitude: -122.3493
```

Each entry may also use `label` instead of `name`, and `lat` / `lon` instead of `latitude` / `longitude`.

## Setup

1. Copy this plugin to `~/.mindroom/plugins/location-enrich`.
2. Set the `DAWARICH_API_KEY` environment variable.
3. Create a `places.yaml` file with your known locations.
4. Add the plugin to `config.yaml`:
   ```yaml
   plugins:
     - path: plugins/location-enrich
   ```
5. Restart MindRoom.

No agent tools are required. This plugin is hooks-only.

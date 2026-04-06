# Location Enrich

[![License](https://img.shields.io/github/license/mindroom-ai/location-enrich-plugin)](https://github.com/mindroom-ai/location-enrich-plugin/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-plugins-blue)](https://docs.mindroom.chat/plugins/)
[![Hooks](https://img.shields.io/badge/docs-hooks-blue)](https://docs.mindroom.chat/hooks/)

<img src="https://media.githubusercontent.com/media/mindroom-ai/mindroom/refs/heads/main/frontend/public/logo.png" alt="MindRoom Logo" align="right" width="120" />

Enrich [MindRoom](https://github.com/mindroom-ai/mindroom) agent prompts with real-time location context from [Dawarich](https://dawarich.app/).

Agents see where the user is — at home, driving, walking — and adjust their behavior accordingly. When the user is driving, the agent keeps replies short and prefers voice. When at a known place, the agent knows which one.

## How it works

1. On every message, the `message:enrich` hook fetches the latest GPS fix from a Dawarich instance
2. The fix is matched against a YAML file of known places (home, office, gym, etc.)
3. Location metadata is injected into the prompt: coordinates, nearby place, movement state, at-home status
4. If the fix is older than 30 minutes, it's marked as stale

## Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `location-enrich` | `message:enrich` | Fetch GPS fix and inject location context into prompt |

## Configuration

Set these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DAWARICH_API_KEY` | Yes | API key for your Dawarich instance |
| `DAWARICH_URL` | No | Dawarich URL (default: `http://localhost:3000`) |

Or configure via plugin settings in `config.yaml`:

```yaml
plugins:
  - path: plugins/location-enrich
    settings:
      dawarich_url: "https://your-dawarich-instance.example.com"
      places_path: "path/to/places.yaml"
```

### Known places file

Create a YAML file with your known locations:

```yaml
- name: Home
  latitude: 47.6062
  longitude: -122.3321
- name: Office
  latitude: 47.6205
  longitude: -122.3493
```

Default path: `~/.mindroom/plugins/location-enrich/places.yaml` (configurable via `places_path` setting).

## Setup

1. Copy to `~/.mindroom/plugins/location-enrich`
2. Set the `DAWARICH_API_KEY` environment variable
3. Create a `places.yaml` with your known locations
4. Add to `config.yaml`:
   ```yaml
   plugins:
     - path: plugins/location-enrich
   ```
5. Restart MindRoom

No agent tools needed — this plugin is hooks only.
# location-enrich

MindRoom plugin that enriches messages with location context via [Dawarich](https://dawarich.app/) GPS tracking.

## What it does

Hooks into `message:enrich` to inject the user's current location as contextual metadata into agent conversations. Reads GPS coordinates from a Dawarich instance and resolves them against a YAML-based places database.

## Setup

1. Copy or symlink to `~/.mindroom-chat/plugins/location-enrich`
2. Add to `config.yaml`:
   ```yaml
   plugins:
     - path: plugins/location-enrich
   ```
3. Configure environment variables or defaults in `hooks.py`:
   - `DAWARICH_URL` — Dawarich API endpoint (default: `https://dawarich.lab.nijho.lt`)
   - Places YAML at `~/.mindroom-chat/mindroom_data/agents/openclaw/workspace/memory/facts/locations.yaml`
4. Restart MindRoom.
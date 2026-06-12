# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HaVassarr is a Home Assistant custom integration (HACS) that exposes HA services to add movies/TV shows to Radarr and Sonarr via voice commands or automations. It lives under `custom_components/havassarr/` and is installed into a Home Assistant instance via HACS.

There is no build step, test suite, or local dev server — this is a HA integration, so "running" it means deploying to a Home Assistant instance and testing there.

## Development Setup

For active development, clone the repo directly into the HA config directory and symlink the component — this avoids re-installing via HACS on every change:

```bash
# Remove any existing HACS-installed copy first
rm -rf /config/custom_components/havassarr

# Clone the repo
cd /config
git clone https://github.com/screamnAbdab/Havassarr.git

# Symlink the component into custom_components
ln -s /config/Havassarr/custom_components/havassarr /config/custom_components/havassarr
```

After editing files, reload the integration from HA's UI (Developer Tools → YAML → Reload All) or do a full restart (`ha core restart`). The integration supports `async_unload_entry` so it can be reloaded without a full restart via the Integrations UI.

**Testing service calls** via the HA REST API:
```bash
curl -X POST http://localhost:8123/api/services/havassarr/add_radarr_movie \
  -H "Authorization: Bearer <long-lived-token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Gladiator"}'
```

**Reading logs:**
```bash
ha logs | grep havassarr
# or tail the log file directly
tail -f /config/home-assistant.log | grep havassarr
```

## Architecture

All logic lives in five files under `custom_components/havassarr/`:

- **`const.py`** — domain name, service name constants, and `EVENT_STATUS_UPDATE`
- **`__init__.py`** — registers four HA services; starts background polling tasks after a successful add; fires `havassarr_status_update` events on state transitions; cancels tasks on unload via `async_unload_entry`
- **`config_flow.py`** — two-step UI config flow: user supplies Radarr & Sonarr URLs/API keys, then selects quality profiles fetched live from the APIs; supports reconfiguration
- **`services.py`** — synchronous HTTP logic using `requests` (always called via `async_add_executor_job`); `handle_add_media` searches lookup API, POSTs to add, returns internal ID; `handle_get_status` checks queue and library for on-demand status
- **`services.yaml`** — service schemas for the HA UI

### Four services

| Service | Input | Returns | Side effect |
|---|---|---|---|
| `havassarr.add_radarr_movie` | `title` | `{title, year}` | Starts background polling |
| `havassarr.add_sonarr_tv_show` | `title` | `{title, year}` | Starts background polling |
| `havassarr.get_radarr_movie_status` | `title` | status dict | None |
| `havassarr.get_sonarr_tv_show_status` | `title` | status dict | None |

All four services declare `supports_response: optional` and are registered with `SupportsResponse.OPTIONAL` so LLM assistants and automations can capture their return values.

### Status dict shape

```python
# On-demand status / event payload
{
    "title": "Gladiator",
    "year": 2000,
    "service": "radarr",           # add services include this in events only
    "status": "searching",         # searching | downloading | in_library | failed | not_found
    "progress": 45,                # only when downloading
    "time_remaining": "2:30:00",   # only when downloading
    "message": "...",              # only when failed
}
```

### Background polling

After each successful add, `_poll_status` (an `asyncio` coroutine using `aiohttp`) runs as a background task:
- Fires an initial `havassarr_status_update` event with `status: searching` immediately
- Polls every 60 seconds
- Fires events **only on state transitions** (not every tick)
- Exits on `completed` or `failed`
- Handles `asyncio.CancelledError` cleanly — tasks are cancelled in `async_unload_entry`
- Tasks are tracked in `hass.data[DOMAIN]["polling_tasks"]`

### LLM voice assistant integration

The services are designed to be called directly by an LLM-backed HA voice assistant:
- `add_radarr_movie` / `add_sonarr_tv_show` confirm TMDB metadata found and queuing — honest about what's confirmed (not whether a torrent was found or download started)
- `get_radarr_movie_status` / `get_sonarr_tv_show_status` can be called on demand for current state
- `havassarr_status_update` events enable proactive TTS notifications via a user automation:

```yaml
trigger:
  - platform: event
    event_type: havassarr_status_update
action:
  - service: tts.speak
    data:
      message: >
        {{ trigger.event.data.title }} is {{ trigger.event.data.status }}
        {%- if trigger.event.data.status == 'downloading' %}
          — {{ trigger.event.data.progress }}% complete
        {%- endif %}
```

## Key Constraints

- `services.py` uses synchronous `requests` — always call via `hass.async_add_executor_job`, never directly from an async context. `_poll_status` uses `aiohttp` because it runs directly in the async loop.
- All new network calls in `services.py` should use `requests` + executor. All new network calls in `__init__.py` async context should use `aiohttp`.
- `manifest.json` lists no `requirements` — `requests` and `aiohttp` are available because HA bundles them. Any new third-party dependency must be added there.
- Minimum HA version is `2024.12.5` (from `hacs.json`).
- The Radarr/Sonarr `POST /api/v3/{type}` returns `201` immediately after queuing — it does **not** confirm a torrent was found or is downloading. The background poller is the only way to track that.

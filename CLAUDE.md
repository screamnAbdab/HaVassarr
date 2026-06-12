# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HaVassarr is a Home Assistant custom integration (HACS) that exposes HA services to add movies/TV shows to Radarr and Sonarr via voice commands or automations. It lives under `custom_components/havassarr/` and is installed into a Home Assistant instance via HACS.

There is no build step, test suite, or local dev server — this is a HA integration, so "running" it means deploying to a Home Assistant instance and testing there.

## Architecture

All logic lives in four files under `custom_components/havassarr/`:

- **`const.py`** — domain name and service name constants
- **`__init__.py`** — registers four HA services; starts background polling tasks after a successful add; fires `havassarr_status_update` events on state transitions; cancels tasks on unload
- **`config_flow.py`** — multi-step UI config flow; user supplies Radarr & Sonarr URLs/API keys, then selects quality profiles fetched from the live APIs
- **`services.py`** — synchronous HTTP logic using `requests` (runs via `async_add_executor_job`); `handle_add_media` searches `api/v3/<type>/lookup`, picks first result, POSTs to `api/v3/<type>`, returns internal ID; `handle_get_status` checks queue and library for on-demand status

**Four services:**
- `havassarr.add_radarr_movie` / `havassarr.add_sonarr_tv_show` — add media, start background polling
- `havassarr.get_radarr_movie_status` / `havassarr.get_sonarr_tv_show_status` — on-demand status check

**Background polling:** after each add, a `_poll_status` asyncio task (using `aiohttp`) polls every 60s and fires `havassarr_status_update` events (`searching → downloading → completed/failed`). Tasks are stored in `hass.data[DOMAIN]["polling_tasks"]` and cancelled on `async_unload_entry`.

Config entry data stored in `hass.data[DOMAIN]` holds the URLs, API keys, quality profile IDs, and `polling_tasks` set — services read directly from there.

`services.yaml` declares the service schemas for the HA UI.

## Key Constraints

- `services.py` uses synchronous `requests` inside HA service handlers — HA is async, so these calls block the event loop. Any new service logic should either stay synchronous (acceptable for this small project) or be wrapped with `hass.async_add_executor_job`.
- `config_flow.py` correctly uses `aiohttp` for its async steps but `services.py` uses `requests` — keep these consistent if adding new network calls.
- The `manifest.json` lists no `requirements` — `requests` is available because HA bundles it, but any new third-party dependency must be added there.
- Minimum HA version is `2024.12.5` (from `hacs.json`).

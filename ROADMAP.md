# HaVassarr Roadmap

## Completed

- **Rename to HaVassarr** — component directory, domain, manifest, HACS config, README
- **Drop Overseerr support** — Radarr and Sonarr only; simplified config flow (no integration type picker)
- **Fix event loop blocking** — service handlers now run via `async_add_executor_job`; 30s timeout on all `requests` calls
- **Error surfacing** — all failure paths raise `HomeAssistantError` / `ServiceValidationError` instead of silently returning; errors appear in HA UI, automation traces, and LLM assistant responses
- **Service response data** — add services return `{title, year}` with `SupportsResponse.OPTIONAL` so LLM assistants receive structured confirmation
- **On-demand status services** — `get_radarr_movie_status` / `get_sonarr_tv_show_status` check the download queue and library; return `not_found | searching | downloading | in_library | failed`
- **Background polling + HA events** — after each add, a background asyncio task polls every 60s and fires `havassarr_status_update` events on state transitions (`searching → downloading → completed/failed`); user wires up a TTS automation to receive proactive voice updates

## Planned

- **Polling timeout with notification** — background polling currently runs until complete or failed with no upper bound. Add a configurable timeout (e.g. 24h) after which polling stops and fires a `status: timed_out` event so the user is notified rather than silently abandoned.
- **Already-in-library handling** — currently `add_radarr_movie` raises an error if Radarr returns 200 (movie already exists). Should detect this case and return a friendly `{status: "already_in_library"}` response instead.
- **Sonarr season/episode granularity** — status for TV shows currently reports at the series level (`percentOfEpisodes`). Could be extended to report per-season or per-episode status.
- **Config entry options flow** — allow changing quality profiles or URLs without going through full reconfiguration.

## Architecture notes for future contributors

See `CLAUDE.md` for full architecture details, development setup, and key constraints.

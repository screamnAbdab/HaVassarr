import asyncio
import logging
import voluptuous as vol
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv
from .services import handle_add_media, handle_get_status
from .const import (
    DOMAIN,
    SERVICE_ADD_RADARR_MOVIE,
    SERVICE_ADD_SONARR_TV_SHOW,
    SERVICE_GET_RADARR_STATUS,
    SERVICE_GET_SONARR_STATUS,
    EVENT_STATUS_UPDATE,
)

_LOGGER = logging.getLogger(__name__)

MEDIA_SCHEMA = vol.Schema({
    vol.Required("title"): cv.string,
})

async def _poll_status(hass: HomeAssistant, title: str, year: int, internal_id: int, service_name: str) -> None:
    """Background task: poll Radarr/Sonarr and fire status events on transitions."""
    config_data = hass.data[DOMAIN]
    url = config_data.get(f"{service_name}_url")
    api_key = config_data.get(f"{service_name}_api_key")
    headers = {"X-Api-Key": api_key}
    is_radarr = service_name == "radarr"
    queue_key = "movieId" if is_radarr else "seriesId"

    def _fire(status: str, extra: dict | None = None) -> None:
        payload = {"title": title, "year": year, "service": service_name, "status": status}
        if extra:
            payload.update(extra)
        hass.bus.async_fire(EVENT_STATUS_UPDATE, payload)

    _fire("searching")
    last_status = "searching"

    try:
        async with aiohttp.ClientSession() as session:
            while True:
                await asyncio.sleep(60)

                # Check queue
                queue_url = f"{url}/api/v3/queue?{queue_key}={internal_id}&includeUnknownMovieItems=false"
                try:
                    async with session.get(queue_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        queue_data = await resp.json()
                except Exception as err:
                    _LOGGER.warning(f"HaVassarr poll error for '{title}': {err}")
                    continue

                records = queue_data.get("records", []) if isinstance(queue_data, dict) else queue_data

                if records:
                    record = records[0]
                    queue_status = record.get("status", "")

                    if queue_status in ("failed", "warning"):
                        if last_status != "failed":
                            messages = [m.get("title", "") for m in record.get("statusMessages", [])]
                            _fire("failed", {"message": "; ".join(messages)})
                        break

                    size = record.get("size", 0)
                    sizeleft = record.get("sizeleft", 0)
                    progress = round((1 - sizeleft / size) * 100) if size else 0
                    new_status = "downloading"
                    if last_status != new_status:
                        _fire(new_status, {"progress": progress, "time_remaining": record.get("timeleft", "unknown")})
                        last_status = new_status
                    continue

                # Not in queue — check if file exists
                item_url = f"{url}/api/v3/{'movie' if is_radarr else 'series'}/{internal_id}"
                try:
                    async with session.get(item_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        item_data = await resp.json()
                except Exception as err:
                    _LOGGER.warning(f"HaVassarr poll error for '{title}': {err}")
                    continue

                if is_radarr:
                    done = item_data.get("hasFile", False)
                else:
                    done = item_data.get("statistics", {}).get("percentOfEpisodes", 0) == 100

                if done:
                    if last_status != "completed":
                        _fire("completed")
                    break

    except asyncio.CancelledError:
        _LOGGER.debug(f"HaVassarr polling cancelled for '{title}'")

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN] = {**config_entry.data, "polling_tasks": set()}

    async def async_add_radarr_movie(call: ServiceCall) -> dict:
        result = await hass.async_add_executor_job(handle_add_media, hass, call, "movie", "radarr")
        task = hass.async_create_background_task(
            _poll_status(hass, result["title"], result["year"], result["internal_id"], "radarr"),
            name=f"havassarr_poll_radarr_{result['internal_id']}",
        )
        hass.data[DOMAIN]["polling_tasks"].add(task)
        task.add_done_callback(hass.data[DOMAIN]["polling_tasks"].discard)
        return {"title": result["title"], "year": result["year"]}

    async def async_add_sonarr_tv_show(call: ServiceCall) -> dict:
        result = await hass.async_add_executor_job(handle_add_media, hass, call, "series", "sonarr")
        task = hass.async_create_background_task(
            _poll_status(hass, result["title"], result["year"], result["internal_id"], "sonarr"),
            name=f"havassarr_poll_sonarr_{result['internal_id']}",
        )
        hass.data[DOMAIN]["polling_tasks"].add(task)
        task.add_done_callback(hass.data[DOMAIN]["polling_tasks"].discard)
        return {"title": result["title"], "year": result["year"]}

    async def async_get_radarr_status(call: ServiceCall) -> dict:
        return await hass.async_add_executor_job(handle_get_status, hass, call, "radarr")

    async def async_get_sonarr_status(call: ServiceCall) -> dict:
        return await hass.async_add_executor_job(handle_get_status, hass, call, "sonarr")

    hass.services.async_register(DOMAIN, SERVICE_ADD_RADARR_MOVIE, async_add_radarr_movie, schema=MEDIA_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_ADD_SONARR_TV_SHOW, async_add_sonarr_tv_show, schema=MEDIA_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_GET_RADARR_STATUS, async_get_radarr_status, schema=MEDIA_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_GET_SONARR_STATUS, async_get_sonarr_status, schema=MEDIA_SCHEMA, supports_response=SupportsResponse.OPTIONAL)

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    for task in list(hass.data[DOMAIN].get("polling_tasks", set())):
        task.cancel()
    return True

async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    existing_tasks = hass.data[DOMAIN].get("polling_tasks", set())
    hass.data[DOMAIN] = {**config_entry.data, "polling_tasks": existing_tasks}

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv
from .services import handle_add_media
from .const import DOMAIN, SERVICE_ADD_RADARR_MOVIE, SERVICE_ADD_SONARR_TV_SHOW

ADD_RADARR_MOVIE_SCHEMA = vol.Schema({
    vol.Required("title"): cv.string,
})

ADD_SONARR_TV_SHOW_SCHEMA = vol.Schema({
    vol.Required("title"): cv.string,
})

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN] = config_entry.data

    async def async_add_radarr_movie(call: ServiceCall) -> dict:
        return await hass.async_add_executor_job(handle_add_media, hass, call, "movie", "radarr")

    async def async_add_sonarr_tv_show(call: ServiceCall) -> dict:
        return await hass.async_add_executor_job(handle_add_media, hass, call, "series", "sonarr")

    hass.services.async_register(DOMAIN, SERVICE_ADD_RADARR_MOVIE, async_add_radarr_movie, schema=ADD_RADARR_MOVIE_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_ADD_SONARR_TV_SHOW, async_add_sonarr_tv_show, schema=ADD_SONARR_TV_SHOW_SCHEMA, supports_response=SupportsResponse.OPTIONAL)

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    return True

async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    hass.data[DOMAIN] = config_entry.data
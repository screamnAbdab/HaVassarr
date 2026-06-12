from urllib.parse import urljoin
import voluptuous as vol
from homeassistant import config_entries
import aiohttp

from .const import DOMAIN

class HaVassarrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self.async_step_radarr_sonarr()

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of an existing entry."""
        return await self.async_step_reconfigure_radarr_sonarr()

    async def async_step_reconfigure_radarr_sonarr(self, user_input=None):
        """Handle reconfiguration for Radarr & Sonarr."""
        if user_input is not None:
            data = dict(self._get_reconfigure_entry().data)
            data.update(user_input)
            self.hass.config_entries.async_update_entry(
                self._get_reconfigure_entry(),
                data=data
            )
            return await self.async_step_reconfigure_radarr_sonarr_quality_profiles()

        existing_data = self._get_reconfigure_entry().data

        return self.async_show_form(
            step_id="reconfigure_radarr_sonarr",
            data_schema=vol.Schema({
                vol.Optional("radarr_url", default=existing_data.get("radarr_url", "")): str,
                vol.Optional("sonarr_url", default=existing_data.get("sonarr_url", "")): str,
                vol.Optional("radarr_api_key", default=existing_data.get("radarr_api_key", "")): str,
                vol.Optional("sonarr_api_key", default=existing_data.get("sonarr_api_key", "")): str,
            })
        )

    async def async_step_reconfigure_radarr_sonarr_quality_profiles(self, user_input=None):
        """Handle reconfiguration for Radarr & Sonarr quality profiles."""
        if user_input is not None:
            data = dict(self._get_reconfigure_entry().data)
            data.update(user_input)
            self.hass.config_entries.async_update_entry(
                self._get_reconfigure_entry(),
                data=data
            )
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates=user_input,
            )

        existing_data = self._get_reconfigure_entry().data
        radarr_url = existing_data.get("radarr_url")
        radarr_api_key = existing_data.get("radarr_api_key")
        sonarr_url = existing_data.get("sonarr_url")
        sonarr_api_key = existing_data.get("sonarr_api_key")

        radarr_profiles = await self._fetch_quality_profiles(radarr_url, radarr_api_key)
        sonarr_profiles = await self._fetch_quality_profiles(sonarr_url, sonarr_api_key)

        radarr_options = {profile["id"]: profile["name"] for profile in radarr_profiles}
        sonarr_options = {profile["id"]: profile["name"] for profile in sonarr_profiles}

        return self.async_show_form(
            step_id="reconfigure_radarr_sonarr_quality_profiles",
            data_schema=vol.Schema({
                vol.Required("radarr_quality_profile_id"): vol.In(radarr_options),
                vol.Required("sonarr_quality_profile_id"): vol.In(sonarr_options),
            })
        )

    async def async_step_radarr_sonarr(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="radarr_sonarr", data_schema=self._get_radarr_sonarr_schema())

        errors = {}
        if not user_input.get("radarr_url") or not user_input.get("radarr_api_key"):
            errors["base"] = "missing_radarr_info"
        if not user_input.get("sonarr_url") or not user_input.get("sonarr_api_key"):
            errors["base"] = "missing_sonarr_info"

        if errors:
            return self.async_show_form(step_id="radarr_sonarr", data_schema=self._get_radarr_sonarr_schema(), errors=errors)

        self.radarr_url = user_input["radarr_url"]
        self.radarr_api_key = user_input["radarr_api_key"]
        self.sonarr_url = user_input["sonarr_url"]
        self.sonarr_api_key = user_input["sonarr_api_key"]
        return await self.async_step_radarr_sonarr_quality_profiles()

    async def async_step_radarr_sonarr_quality_profiles(self, user_input=None):
        if user_input is None:
            radarr_profiles = await self._fetch_quality_profiles(self.radarr_url, self.radarr_api_key)
            sonarr_profiles = await self._fetch_quality_profiles(self.sonarr_url, self.sonarr_api_key)

            radarr_options = {profile["id"]: profile["name"] for profile in radarr_profiles}
            sonarr_options = {profile["id"]: profile["name"] for profile in sonarr_profiles}

            return self.async_show_form(
                step_id="radarr_sonarr_quality_profiles",
                data_schema=vol.Schema({
                    vol.Required("radarr_quality_profile_id"): vol.In(radarr_options),
                    vol.Required("sonarr_quality_profile_id"): vol.In(sonarr_options),
                })
            )

        user_input.update({
            "radarr_url": self.radarr_url,
            "radarr_api_key": self.radarr_api_key,
            "sonarr_url": self.sonarr_url,
            "sonarr_api_key": self.sonarr_api_key
        })
        return self.async_create_entry(title="HaVassarr", data=user_input)

    async def _fetch_quality_profiles(self, url, api_key):
        """Fetch quality profiles from the Radarr/Sonarr API."""
        async with aiohttp.ClientSession() as session:
            url = urljoin(url, "api/v3/qualityprofile")
            async with session.get(url, headers={"X-Api-Key": api_key}) as response:
                response.raise_for_status()
                data = await response.json()
                return data

    @staticmethod
    def _get_radarr_sonarr_schema():
        return vol.Schema({
            vol.Required("radarr_url"): str,
            vol.Required("radarr_api_key"): str,
            vol.Required("sonarr_url"): str,
            vol.Required("sonarr_api_key"): str,
        })

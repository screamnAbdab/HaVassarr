import logging
import requests
from urllib.parse import urljoin
from .const import DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

_LOGGER = logging.getLogger(__name__)

def fetch_data(url: str, headers: dict) -> dict:
    try:
        response = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.RequestException as err:
        raise HomeAssistantError(f"Connection error: {err}") from err
    if response.status_code != requests.codes.ok:
        raise HomeAssistantError(f"Failed to reach {url}: {response.text}")
    return response.json()

def get_root_folder_path(url: str, headers: dict) -> str:
    data = fetch_data(url, headers)
    if not data or not data[0].get("path"):
        raise HomeAssistantError("No root folder configured")
    return data[0]["path"]

def handle_add_media(hass: HomeAssistant, call: ServiceCall, media_type: str, service_name: str) -> None:
    title = call.data.get("title")
    if not title:
        raise ServiceValidationError("title is required")

    config_data = hass.data[DOMAIN]
    url = config_data.get(f"{service_name}_url")
    api_key = config_data.get(f"{service_name}_api_key")
    quality_profile_id = config_data.get(f"{service_name}_quality_profile_id")

    if not url or not api_key:
        raise HomeAssistantError(f"{service_name.capitalize()} is not configured")

    headers = {'X-Api-Key': api_key}

    search_url = urljoin(url, f"api/v3/{media_type}/lookup?term={title}")
    _LOGGER.info(f"Searching {service_name} for '{title}'")
    media_list = fetch_data(search_url, headers)

    if not media_list:
        raise HomeAssistantError(f"No results found for '{title}'")

    media_data = media_list[0]

    root_folder_path = get_root_folder_path(urljoin(url, "api/v3/rootfolder"), headers)

    payload = {
        'title': media_data['title'],
        'titleSlug': media_data['titleSlug'],
        'images': media_data['images'],
        'year': media_data['year'],
        'rootFolderPath': root_folder_path,
        'addOptions': {
            'searchForMovie' if media_type == 'movie' else 'searchForMissingEpisodes': True
        },
        'qualityProfileId': quality_profile_id,
    }
    if media_type == 'movie':
        payload['tmdbId'] = media_data['tmdbId']
    else:
        payload['tvdbId'] = media_data['tvdbId']

    add_url = urljoin(url, f"api/v3/{media_type}")
    _LOGGER.info(f"Adding '{title}' to {service_name.capitalize()}")
    try:
        add_response = requests.post(add_url, json=payload, headers=headers, timeout=30)
    except requests.exceptions.RequestException as err:
        raise HomeAssistantError(f"Connection error adding '{title}': {err}") from err

    if add_response.status_code != requests.codes.created:
        raise HomeAssistantError(f"Failed to add '{title}' to {service_name.capitalize()}: {add_response.text}")

    _LOGGER.info(f"Successfully added '{title}' to {service_name.capitalize()}")
    return {
        "title": media_data["title"],
        "year": media_data["year"],
    }

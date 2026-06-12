import logging
import requests
from urllib.parse import urljoin
from .const import DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)

def fetch_data(url: str, headers: dict) -> dict | None:
    """Fetch data from the given URL with headers.

    Args:
        url (str): The URL to fetch data from.
        headers (dict): The headers to include in the request.

    Returns:
        dict | None: The JSON response if successful, None otherwise.
    """
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == requests.codes.ok:
        return response.json()
    else:
        _LOGGER.error(f"Failed to fetch data from {url}: {response.text}")
        return None

def get_root_folder_path(url: str, headers: dict) -> str | None:
    """Get root folder path from the given URL.

    Args:
        url (str): The URL to fetch the root folder path from.
        headers (dict): The headers to include in the request.

    Returns:
        str | None: The root folder path if successful, None otherwise.
    """
    data = fetch_data(url, headers)
    if data:
        return data[0].get("path")
    return None

def handle_add_media(hass: HomeAssistant, call: ServiceCall, media_type: str, service_name: str) -> None:
    """Handle the service action to add a media (movie or TV show).

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        call (ServiceCall): The service call object.
        media_type (str): The type of media to add (e.g., "movie" or "series").
        service_name (str): The name of the service (e.g., "radarr" or "sonarr").
    """
    _LOGGER.info(f"Received call data: {call.data}")
    title = call.data.get("title")

    if not title:
        _LOGGER.error("Title is missing in the service call data")
        return

    _LOGGER.info(f"Title received: {title}")

    # Access stored configuration data
    config_data = hass.data[DOMAIN]

    url = config_data.get(f"{service_name}_url")
    api_key = config_data.get(f"{service_name}_api_key")
    quality_profile_id = config_data.get(f"{service_name}_quality_profile_id")

    if not url or not api_key:
        _LOGGER.error(f"{service_name.capitalize()} URL or API key is missing")
        return

    headers = {'X-Api-Key': api_key}

    # Fetch media list
    search_url = urljoin(url, f"api/v3/{media_type}/lookup?term={title}")
    _LOGGER.info(f"Fetching media list from URL: {search_url}")
    media_list = fetch_data(search_url, headers)

    if media_list:
        media_data = media_list[0]

        # Get root folder path
        root_folder_url = urljoin(url, "api/v3/rootfolder")
        root_folder_path = get_root_folder_path(root_folder_url, headers)
        if not root_folder_path:
            return

        # Prepare payload
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

        # Add media
        add_url = urljoin(url, f"api/v3/{media_type}")
        _LOGGER.info(f"Adding media to URL: {add_url} with payload: {payload}")
        add_response = requests.post(add_url, json=payload, headers=headers, timeout=30)

        if add_response.status_code == requests.codes.created:
            _LOGGER.info(f"Successfully added {media_type} '{title}' to {service_name.capitalize()}")
        else:
            _LOGGER.error(f"Failed to add {media_type} '{title}' to {service_name.capitalize()}: {add_response.text}")
    else:
        _LOGGER.info(f"No results found for {media_type} '{title}'")

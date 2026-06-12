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

def handle_add_media(hass: HomeAssistant, call: ServiceCall, media_type: str, service_name: str) -> dict:
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

    added = add_response.json()
    _LOGGER.info(f"Successfully added '{title}' to {service_name.capitalize()}")
    return {
        "title": added["title"],
        "year": added["year"],
        "internal_id": added["id"],
    }

def handle_get_status(hass: HomeAssistant, call: ServiceCall, service_name: str) -> dict:
    title = call.data.get("title")
    if not title:
        raise ServiceValidationError("title is required")

    config_data = hass.data[DOMAIN]
    url = config_data.get(f"{service_name}_url")
    api_key = config_data.get(f"{service_name}_api_key")

    if not url or not api_key:
        raise HomeAssistantError(f"{service_name.capitalize()} is not configured")

    headers = {'X-Api-Key': api_key}
    is_radarr = service_name == "radarr"
    media_type = "movie" if is_radarr else "series"
    id_field = "tmdbId" if is_radarr else "tvdbId"

    # Lookup metadata to get the external DB id
    lookup_url = urljoin(url, f"api/v3/{media_type}/lookup?term={title}")
    lookup_results = fetch_data(lookup_url, headers)
    if not lookup_results:
        return {"status": "not_found", "title": title}

    external_id = lookup_results[0].get(id_field)

    # Find the item in the library
    library_url = urljoin(url, f"api/v3/{media_type}")
    library = fetch_data(library_url, headers)
    item = next((m for m in library if m.get(id_field) == external_id), None)

    if not item:
        return {"status": "not_found", "title": lookup_results[0]["title"], "year": lookup_results[0].get("year")}

    internal_id = item["id"]
    found_title = item["title"]
    found_year = item.get("year")

    # Check if already in library
    if is_radarr:
        if item.get("hasFile"):
            return {"status": "in_library", "title": found_title, "year": found_year}
    else:
        stats = item.get("statistics", {})
        if stats.get("percentOfEpisodes", 0) == 100:
            return {"status": "in_library", "title": found_title, "year": found_year}

    # Check download queue
    queue_key = "movieId" if is_radarr else "seriesId"
    queue_url = urljoin(url, f"api/v3/queue?{queue_key}={internal_id}&includeUnknownMovieItems=false")
    queue_data = fetch_data(queue_url, headers)
    records = queue_data.get("records", []) if isinstance(queue_data, dict) else queue_data

    if records:
        record = records[0]
        queue_status = record.get("status", "")
        if queue_status in ("failed", "warning"):
            messages = [m.get("title", "") for m in record.get("statusMessages", [])]
            return {"status": "failed", "title": found_title, "year": found_year, "message": "; ".join(messages)}
        size = record.get("size", 0)
        sizeleft = record.get("sizeleft", 0)
        progress = round((1 - sizeleft / size) * 100) if size else 0
        return {
            "status": "downloading",
            "title": found_title,
            "year": found_year,
            "progress": progress,
            "time_remaining": record.get("timeleft", "unknown"),
        }

    return {"status": "searching", "title": found_title, "year": found_year}

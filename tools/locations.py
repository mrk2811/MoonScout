"""Location finding tool using OpenStreetMap Nominatim + Overpass API."""

import time
import requests
from typing import Optional


# Nominatim requires a User-Agent header
_HEADERS = {"User-Agent": "MoonScout/1.0 (crescent-moon-observation-app)"}
_NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
_OVERPASS_BASE = "https://overpass-api.de/api/interpreter"


def geocode_location(location_name: str) -> Optional[dict]:
    """
    Geocode a location name to lat/lon coordinates using Nominatim.

    Args:
        location_name: Natural language location (e.g., "New York City", "London")

    Returns:
        dict with lat, lon, display_name, or None if not found
    """
    try:
        url = f"{_NOMINATIM_BASE}/search"
        params = {
            "q": location_name,
            "format": "json",
            "limit": 1,
            "addressdetails": 1
        }

        response = requests.get(url, params=params, headers=_HEADERS, timeout=10)
        response.raise_for_status()
        results = response.json()

        if not results:
            return None

        result = results[0]
        return {
            "lat": float(result["lat"]),
            "lon": float(result["lon"]),
            "display_name": result.get("display_name", location_name)
        }
    except (requests.RequestException, ValueError, KeyError):
        return None


def find_candidate_locations(user_location: str, radius_miles: float = 50) -> dict:
    """
    Find candidate observation locations near the user's location.

    Searches for elevated points, viewpoints, parks, and open areas
    that are suitable for crescent moon observation (clear western horizon).

    Uses OpenStreetMap Nominatim for geocoding and Overpass API for
    finding nearby points of interest.

    Args:
        user_location: Location name or "lat,lon" string
        radius_miles: Search radius in miles (default 50)

    Returns:
        dict with candidates list and metadata
    """
    try:
        # Parse location
        if "," in user_location and _is_coordinate(user_location):
            parts = user_location.split(",")
            center_lat = float(parts[0].strip())
            center_lon = float(parts[1].strip())
            display_name = f"{center_lat:.4f}, {center_lon:.4f}"
        else:
            geo = geocode_location(user_location)
            if geo is None:
                return {
                    "error": f"Could not geocode location: {user_location}",
                    "candidates": [],
                    "center_lat": None,
                    "center_lon": None
                }
            center_lat = geo["lat"]
            center_lon = geo["lon"]
            display_name = geo["display_name"]
            time.sleep(1.1)  # Respect Nominatim rate limit

        radius_meters = radius_miles * 1609.34

        # Query Overpass API for suitable observation sites
        candidates = _query_overpass(center_lat, center_lon, radius_meters)

        if not candidates:
            # Fallback: try a broader search with just parks
            candidates = _query_overpass_fallback(center_lat, center_lon, radius_meters)

        # Deduplicate and limit to 10
        candidates = _deduplicate(candidates)[:10]

        # Get elevation for each candidate
        candidates = _enrich_with_elevation(candidates)

        return {
            "error": None,
            "candidates": candidates,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "center_name": display_name,
            "radius_miles": radius_miles,
            "count": len(candidates)
        }

    except Exception as e:
        return {
            "error": f"Location search failed: {str(e)}",
            "candidates": [],
            "center_lat": None,
            "center_lon": None
        }


def _is_coordinate(s: str) -> bool:
    """Check if a string looks like 'lat,lon' coordinates."""
    try:
        parts = s.split(",")
        if len(parts) == 2:
            float(parts[0].strip())
            float(parts[1].strip())
            return True
    except ValueError:
        pass
    return False


def _query_overpass(lat: float, lon: float, radius_meters: float) -> list:
    """Query Overpass API for observation-friendly locations."""
    # Search for viewpoints, peaks, hills, large parks, open areas
    query = (
        f'[out:json][timeout:30];'
        f'('
        f'node["tourism"="viewpoint"](around:{radius_meters},{lat},{lon});'
        f'node["natural"="peak"](around:{radius_meters},{lat},{lon});'
        f'node["natural"="hill"](around:{radius_meters},{lat},{lon});'
        f'node["natural"="saddle"](around:{radius_meters},{lat},{lon});'
        f'way["leisure"="park"]["name"](around:{radius_meters},{lat},{lon});'
        f'way["leisure"="nature_reserve"]["name"](around:{radius_meters},{lat},{lon});'
        f'way["natural"="heath"](around:{radius_meters},{lat},{lon});'
        f'node["man_made"="tower"]["tower:type"="observation"](around:{radius_meters},{lat},{lon});'
        f');'
        f'out center body 20;'
    )

    try:
        response = requests.post(
            _OVERPASS_BASE,
            data={"data": query},
            headers=_HEADERS,
            timeout=35
        )
        response.raise_for_status()
        data = response.json()

        candidates = []
        for element in data.get("elements", []):
            name = element.get("tags", {}).get("name")
            if not name:
                # Generate name from type
                tags = element.get("tags", {})
                etype = tags.get("tourism") or tags.get("natural") or tags.get("leisure") or "location"
                name = f"Unnamed {etype.replace('_', ' ').title()}"

            # Get coordinates (center for ways)
            if element.get("type") == "way":
                center = element.get("center", {})
                c_lat = center.get("lat")
                c_lon = center.get("lon")
            else:
                c_lat = element.get("lat")
                c_lon = element.get("lon")

            if c_lat is None or c_lon is None:
                continue

            candidates.append({
                "name": name,
                "lat": c_lat,
                "lon": c_lon,
                "type": _get_location_type(element.get("tags", {})),
                "elevation_m": element.get("tags", {}).get("ele"),
            })

        return candidates

    except (requests.RequestException, ValueError):
        return []


def _query_overpass_fallback(lat: float, lon: float, radius_meters: float) -> list:
    """Simpler fallback query for parks and open spaces."""
    query = (
        f'[out:json][timeout:25];'
        f'('
        f'way["leisure"="park"]["name"](around:{radius_meters},{lat},{lon});'
        f'relation["leisure"="park"]["name"](around:{radius_meters},{lat},{lon});'
        f'way["landuse"="recreation_ground"]["name"](around:{radius_meters},{lat},{lon});'
        f');'
        f'out center body 10;'
    )

    try:
        response = requests.post(
            _OVERPASS_BASE,
            data={"data": query},
            headers=_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        candidates = []
        for element in data.get("elements", []):
            name = element.get("tags", {}).get("name", "Unnamed Park")
            center = element.get("center", {})
            c_lat = center.get("lat", element.get("lat"))
            c_lon = center.get("lon", element.get("lon"))

            if c_lat is None or c_lon is None:
                continue

            candidates.append({
                "name": name,
                "lat": c_lat,
                "lon": c_lon,
                "type": "park",
                "elevation_m": None
            })

        return candidates

    except (requests.RequestException, ValueError):
        return []


def _get_location_type(tags: dict) -> str:
    """Determine a friendly location type from OSM tags."""
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    elif tags.get("natural") == "peak":
        return "peak"
    elif tags.get("natural") == "hill":
        return "hill"
    elif tags.get("leisure") == "nature_reserve":
        return "nature reserve"
    elif tags.get("leisure") == "park":
        return "park"
    elif tags.get("natural") == "heath":
        return "open heath"
    elif tags.get("man_made") == "tower":
        return "observation tower"
    else:
        return "open area"


def _deduplicate(candidates: list) -> list:
    """Remove duplicate locations based on proximity."""
    unique = []
    for c in candidates:
        is_dup = False
        for u in unique:
            dist = _approx_distance_km(c["lat"], c["lon"], u["lat"], u["lon"])
            if dist < 0.5:  # Within 500m = duplicate
                is_dup = True
                break
        if not is_dup:
            unique.append(c)
    return unique


def _approx_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two points in km (haversine)."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _enrich_with_elevation(candidates: list) -> list:
    """Add elevation data from Open-Meteo elevation API."""
    if not candidates:
        return candidates

    # Batch request for all candidates
    lats = ",".join(str(c["lat"]) for c in candidates)
    lons = ",".join(str(c["lon"]) for c in candidates)

    try:
        url = "https://api.open-meteo.com/v1/elevation"
        params = {"latitude": lats, "longitude": lons}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        elevations = data.get("elevation", [])
        for i, candidate in enumerate(candidates):
            if i < len(elevations) and elevations[i] is not None:
                candidate["elevation_m"] = elevations[i]
            elif candidate["elevation_m"] is None:
                candidate["elevation_m"] = 0

    except (requests.RequestException, ValueError, KeyError):
        # If elevation API fails, set defaults
        for c in candidates:
            if c["elevation_m"] is None:
                c["elevation_m"] = 0

    return candidates

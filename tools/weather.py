"""Weather tool using Open-Meteo API focused on sunset-time conditions."""

import requests
from datetime import datetime
from typing import Optional


def get_weather(lat: float, lon: float, date: str, sunset_hour: int = 19) -> dict:
    """
    Fetch weather conditions around sunset time for crescent moon observation.

    Uses Open-Meteo API (free, no key needed) to get cloud cover, humidity,
    visibility, and wind speed for the hours around sunset.

    Args:
        lat: Latitude of the location
        lon: Longitude of the location
        date: Date string in YYYY-MM-DD format
        sunset_hour: Approximate sunset hour in local time (will be refined)

    Returns:
        dict with cloud_cover_pct, humidity_pct, visibility_km, wind_speed_kmh,
        and a horizon_clarity score (0-1)
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        today = datetime.now()

        if (target_date - today).days > 16:
            return {
                "error": None,
                "cloud_cover_pct": None,
                "humidity_pct": None,
                "visibility_km": None,
                "wind_speed_kmh": None,
                "horizon_clarity": None,
                "forecast_available": False,
                "message": "Weather forecast not yet available for this date (>16 days ahead)."
            }

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloud_cover,cloud_cover_low,relative_humidity_2m,visibility,wind_speed_10m",
            "start_date": date,
            "end_date": date,
            "timezone": "auto"
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        hourly = data.get("hourly", {})
        cloud_cover = hourly.get("cloud_cover", [])
        cloud_cover_low = hourly.get("cloud_cover_low", [])
        humidity = hourly.get("relative_humidity_2m", [])
        visibility = hourly.get("visibility", [])
        wind_speed = hourly.get("wind_speed_10m", [])

        sunset_hours = list(range(max(0, sunset_hour - 1), min(24, sunset_hour + 2)))

        def avg_for_hours(values: list, hours: list) -> Optional[float]:
            if not values:
                return None
            selected = [values[h] for h in hours if h < len(values) and values[h] is not None]
            return sum(selected) / len(selected) if selected else None

        avg_cloud = avg_for_hours(cloud_cover, sunset_hours)
        avg_cloud_low = avg_for_hours(cloud_cover_low, sunset_hours)
        avg_humidity = avg_for_hours(humidity, sunset_hours)
        avg_visibility = avg_for_hours(visibility, sunset_hours)
        avg_wind = avg_for_hours(wind_speed, sunset_hours)

        # Convert visibility from meters to km
        if avg_visibility is not None:
            avg_visibility = avg_visibility / 1000.0

        # Horizon clarity score (0-1): penalizes low clouds and poor visibility most
        horizon_clarity = _calculate_horizon_clarity(avg_cloud, avg_cloud_low, avg_humidity, avg_visibility)

        return {
            "error": None,
            "cloud_cover_pct": round(avg_cloud, 1) if avg_cloud is not None else None,
            "cloud_cover_low_pct": round(avg_cloud_low, 1) if avg_cloud_low is not None else None,
            "humidity_pct": round(avg_humidity, 1) if avg_humidity is not None else None,
            "visibility_km": round(avg_visibility, 1) if avg_visibility is not None else None,
            "wind_speed_kmh": round(avg_wind, 1) if avg_wind is not None else None,
            "horizon_clarity": round(horizon_clarity, 3) if horizon_clarity is not None else None,
            "forecast_available": True,
            "message": None
        }

    except requests.RequestException as e:
        return {
            "error": f"Weather API request failed: {str(e)}",
            "cloud_cover_pct": None,
            "humidity_pct": None,
            "visibility_km": None,
            "wind_speed_kmh": None,
            "horizon_clarity": None,
            "forecast_available": False,
            "message": "Could not fetch weather data for this location."
        }
    except (ValueError, KeyError) as e:
        return {
            "error": f"Weather data parsing failed: {str(e)}",
            "cloud_cover_pct": None,
            "humidity_pct": None,
            "visibility_km": None,
            "wind_speed_kmh": None,
            "horizon_clarity": None,
            "forecast_available": False,
            "message": "Could not parse weather data."
        }


def _calculate_horizon_clarity(
    cloud_pct: Optional[float],
    cloud_low_pct: Optional[float],
    humidity_pct: Optional[float],
    visibility_km: Optional[float]
) -> Optional[float]:
    """
    Calculate a horizon clarity score from 0 (terrible) to 1 (perfect).

    Low clouds and poor visibility are penalized heavily since the crescent
    is observed very close to the horizon.
    """
    if all(v is None for v in [cloud_pct, cloud_low_pct, humidity_pct, visibility_km]):
        return None

    score = 1.0
    components = 0

    if cloud_pct is not None:
        score_cloud = (100 - cloud_pct) / 100.0
        score -= (1 - score_cloud) * 0.25
        components += 1

    if cloud_low_pct is not None:
        # Low clouds are especially bad for horizon viewing
        score_low_cloud = (100 - cloud_low_pct) / 100.0
        score -= (1 - score_low_cloud) * 0.35
        components += 1

    if humidity_pct is not None:
        score_humidity = (100 - humidity_pct) / 100.0
        score -= (1 - score_humidity) * 0.20
        components += 1

    if visibility_km is not None:
        # Normalize visibility: 0km=0, 20km+=1
        score_vis = min(visibility_km / 20.0, 1.0)
        score -= (1 - score_vis) * 0.20
        components += 1

    if components == 0:
        return None

    return max(0.0, min(1.0, score))

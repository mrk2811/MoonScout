"""Scoring module for MoonScout - normalized crescent visibility scoring."""


def score_location(
    moon_data: dict,
    weather_data: dict,
    elevation_m: float = 0,
    max_elevation_m: float = 1000
) -> dict:
    """
    Score a candidate location for crescent moon observation.

    All components are normalized to 0-1 range.

    Score = crescent_visibility * 0.40
          + horizon_clarity * 0.30
          + elevation_advantage * 0.15
          + lag_time_normalized * 0.15

    Args:
        moon_data: Output from get_moon_data tool
        weather_data: Output from get_weather tool
        elevation_m: Elevation of the location in meters
        max_elevation_m: Reference max elevation for normalization

    Returns:
        dict with total_score (0-1), component scores, and breakdown
    """
    # Component 1: Crescent visibility (from Yallop criterion)
    crescent_score = _crescent_visibility_score(moon_data)

    # Component 2: Horizon clarity (from weather)
    horizon_score = _horizon_clarity_score(weather_data)

    # Component 3: Elevation advantage
    elevation_score = _elevation_score(elevation_m, max_elevation_m)

    # Component 4: Lag time (more time = more opportunity)
    lag_score = _lag_time_score(moon_data)

    # Weighted total
    weights = {
        "crescent_visibility": 0.40,
        "horizon_clarity": 0.30,
        "elevation": 0.15,
        "lag_time": 0.15
    }

    total = (
        crescent_score * weights["crescent_visibility"]
        + horizon_score * weights["horizon_clarity"]
        + elevation_score * weights["elevation"]
        + lag_score * weights["lag_time"]
    )

    return {
        "total_score": round(total, 3),
        "components": {
            "crescent_visibility": round(crescent_score, 3),
            "horizon_clarity": round(horizon_score, 3),
            "elevation": round(elevation_score, 3),
            "lag_time": round(lag_score, 3),
        },
        "weights": weights,
        "scoreable": crescent_score > 0 or horizon_score > 0
    }


def _crescent_visibility_score(moon_data: dict) -> float:
    """
    Score based on Yallop visibility category.

    A (easily visible) = 1.0
    B (perfect conditions) = 0.8
    C (optical aid to find) = 0.6
    D (optical aid only) = 0.4
    E (not visible with telescope) = 0.1
    F (impossible) = 0.0
    """
    category = moon_data.get("visibility_category", "F")
    scores = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "E": 0.1, "F": 0.0, "X": 0.0}
    return scores.get(category, 0.0)


def _horizon_clarity_score(weather_data: dict) -> float:
    """
    Score based on weather/atmospheric conditions near the horizon.

    Uses pre-calculated horizon_clarity if available, otherwise computes
    from individual weather components.
    """
    if weather_data.get("forecast_available") is False:
        return 0.5  # Neutral score when forecast unavailable

    horizon_clarity = weather_data.get("horizon_clarity")
    if horizon_clarity is not None:
        return horizon_clarity

    # Fallback calculation from individual components
    score = 1.0
    cloud = weather_data.get("cloud_cover_pct")
    humidity = weather_data.get("humidity_pct")
    visibility = weather_data.get("visibility_km")

    if cloud is not None:
        score *= (100 - cloud) / 100.0
    if humidity is not None:
        score *= (100 - humidity * 0.3) / 100.0  # Humidity less penalizing
    if visibility is not None:
        score *= min(visibility / 20.0, 1.0)

    return max(0.0, min(1.0, score))


def _elevation_score(elevation_m: float, max_elevation_m: float) -> float:
    """
    Score based on elevation advantage.

    Higher locations have a clearer view to the horizon
    and less atmospheric extinction.

    Normalized: 0m = 0.2 (base), max_elevation = 1.0
    """
    if elevation_m is None:
        return 0.2

    # Even sea level has some base score
    base = 0.2
    if max_elevation_m <= 0:
        return base

    normalized = min(float(elevation_m) / max_elevation_m, 1.0)
    return base + (1.0 - base) * normalized


def _lag_time_score(moon_data: dict) -> float:
    """
    Score based on lag time (minutes between sunset and moonset).

    More lag time means more opportunity to observe the crescent.
    0 minutes = 0.0 (moon sets at/before sunset)
    20 minutes = 0.5 (minimum useful)
    40+ minutes = 1.0 (excellent opportunity)
    """
    lag = moon_data.get("lag_time_minutes")
    if lag is None or lag <= 0:
        return 0.0

    # Normalize: 0-40 minutes -> 0-1
    return min(lag / 40.0, 1.0)

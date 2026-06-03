"""Moon data tool using Skyfield for crescent visibility calculations."""

import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from skyfield.api import Loader, wgs84
from skyfield.almanac import find_discrete, moon_phases
from skyfield import almanac

# Singleton loader - downloads ephemeris to ./data directory
_DATA_DIR = Path(__file__).parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
_load = Loader(str(_DATA_DIR))

try:
    _eph = _load("de421.bsp")
    _ts = _load.timescale()
    _SKYFIELD_READY = True
except Exception:
    _eph = None
    _ts = None
    _SKYFIELD_READY = False


def is_skyfield_ready() -> bool:
    """Check if skyfield ephemeris is loaded and ready."""
    return _SKYFIELD_READY


def get_moon_data(lat: float, lon: float, date: str) -> dict:
    """
    Calculate crescent moon visibility data for a given location and date.

    Uses Skyfield with JPL DE421 ephemeris to compute:
    - Moon age (hours since last new moon)
    - Moon altitude at sunset
    - Lag time (minutes between sunset and moonset)
    - Arc of vision (ARCV)
    - Moon illumination percentage
    - Yallop criterion value and visibility category

    Args:
        lat: Latitude of the observation location
        lon: Longitude of the observation location
        date: Date string in YYYY-MM-DD format

    Returns:
        dict with moon data and visibility assessment
    """
    if not _SKYFIELD_READY:
        return {
            "error": "Skyfield ephemeris not loaded. Run: python scripts/setup.py",
            "visible": False,
            "visibility_category": "X",
            "message": "Moon calculation unavailable - ephemeris file not found."
        }

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        observer = wgs84.latlon(lat, lon)

        earth = _eph["earth"]
        moon = _eph["moon"]
        sun = _eph["sun"]

        # Find sunset time for the given date
        t0 = _ts.utc(target_date.year, target_date.month, target_date.day)
        t1 = _ts.utc(target_date.year, target_date.month, target_date.day + 1)

        f = almanac.risings_and_settings(_eph, sun, observer)
        times, events = find_discrete(t0, t1, f)

        sunset_time = None
        for t, e in zip(times, events):
            if not e:  # setting event
                sunset_time = t
                break

        if sunset_time is None:
            return {
                "error": None,
                "visible": False,
                "visibility_category": "X",
                "message": "Could not determine sunset time for this location and date.",
                "moon_age_hours": None,
                "moon_altitude_at_sunset": None,
                "lag_time_minutes": None,
                "arcv": None,
                "illumination_pct": None,
                "yallop_q": None,
                "next_new_moon": None
            }

        # Find moonset
        f_moon = almanac.risings_and_settings(_eph, moon, observer)
        moon_times, moon_events = find_discrete(t0, _ts.utc(target_date.year, target_date.month, target_date.day + 2), f_moon)

        moonset_time = None
        for t, e in zip(moon_times, moon_events):
            if not e and t.tt > sunset_time.tt:  # moonset after sunset
                moonset_time = t
                break

        # Calculate lag time
        lag_time_minutes = None
        if moonset_time is not None:
            lag_time_minutes = (moonset_time.tt - sunset_time.tt) * 24 * 60

        # Moon position at sunset
        location = earth + observer
        astrometric_moon = location.at(sunset_time).observe(moon)
        astrometric_sun = location.at(sunset_time).observe(sun)

        moon_alt, moon_az, _ = astrometric_moon.apparent().altaz()
        sun_alt, sun_az, _ = astrometric_sun.apparent().altaz()

        moon_altitude = moon_alt.degrees
        moon_azimuth = moon_az.degrees
        sun_azimuth = sun_az.degrees

        # Arc of vision (ARCV) - angular distance between moon and sun centers
        arcv = moon_altitude - sun_alt.degrees

        # Relative azimuth (DAZ)
        daz = abs(moon_azimuth - sun_azimuth)
        if daz > 180:
            daz = 360 - daz

        # Moon illumination
        illumination = _calculate_illumination(sunset_time, earth, moon, sun)

        # Moon age - find previous new moon
        moon_age_hours = _calculate_moon_age(sunset_time)

        # Yallop's criterion
        yallop_q = _calculate_yallop_q(arcv, daz, moon_altitude)
        visibility_category = _yallop_category(yallop_q)

        # Determine if crescent is potentially visible
        visible = (
            moon_altitude > 0
            and (lag_time_minutes is not None and lag_time_minutes > 0)
            and moon_age_hours is not None
            and moon_age_hours > 12
        )

        # Find next new moon for suggestion
        next_new_moon = _find_next_new_moon(target_date)

        return {
            "error": None,
            "visible": visible,
            "visibility_category": visibility_category,
            "moon_age_hours": round(moon_age_hours, 1) if moon_age_hours else None,
            "moon_altitude_at_sunset": round(moon_altitude, 2),
            "moon_azimuth_at_sunset": round(moon_azimuth, 1),
            "lag_time_minutes": round(lag_time_minutes, 1) if lag_time_minutes else None,
            "arcv": round(arcv, 2) if arcv else None,
            "daz": round(daz, 2),
            "illumination_pct": round(illumination * 100, 2) if illumination else None,
            "yallop_q": round(yallop_q, 3) if yallop_q else None,
            "next_new_moon": next_new_moon,
            "message": _generate_visibility_message(visibility_category, moon_age_hours, moon_altitude)
        }

    except Exception as e:
        return {
            "error": f"Moon calculation failed: {str(e)}",
            "visible": False,
            "visibility_category": "X",
            "message": "Could not calculate moon data for this location."
        }


def find_next_visible_date(lat: float, lon: float, from_date: str, max_days: int = 30) -> Optional[dict]:
    """
    Find the next date when the crescent moon might be visible from a location.

    Searches forward from from_date up to max_days looking for the first evening
    where the crescent has reasonable visibility potential.

    Args:
        lat: Latitude
        lon: Longitude
        from_date: Start date (YYYY-MM-DD)
        max_days: Maximum days to search ahead

    Returns:
        dict with the suggested date and moon data, or None if not found
    """
    if not _SKYFIELD_READY:
        return None

    start = datetime.strptime(from_date, "%Y-%m-%d")

    for day_offset in range(1, max_days + 1):
        check_date = start + timedelta(days=day_offset)
        date_str = check_date.strftime("%Y-%m-%d")
        result = get_moon_data(lat, lon, date_str)

        if result.get("visible") and result.get("visibility_category") in ("A", "B", "C", "D"):
            return {
                "date": date_str,
                "moon_data": result
            }

    return None


def _calculate_illumination(t, earth, moon, sun) -> Optional[float]:
    """Calculate the fraction of the moon's disk that is illuminated."""
    try:
        e = earth.at(t)
        m = e.observe(moon).apparent()
        s = e.observe(sun).apparent()

        moon_vec = m.position.au
        sun_vec = s.position.au

        # Elongation angle
        import numpy as np
        cos_elong = np.dot(moon_vec, sun_vec) / (
            np.linalg.norm(moon_vec) * np.linalg.norm(sun_vec)
        )
        cos_elong = np.clip(cos_elong, -1, 1)
        elongation = np.arccos(cos_elong)

        # Approximate illumination fraction
        illumination = (1 - np.cos(elongation)) / 2.0
        return float(illumination)
    except Exception:
        return None


def _calculate_moon_age(sunset_time) -> Optional[float]:
    """Calculate moon age in hours since the last new moon."""
    try:
        # Search backward up to 30 days for the last new moon
        t_start = _ts.tt_jd(sunset_time.tt - 30)
        t_end = sunset_time

        f = moon_phases(_eph)
        times, phases = find_discrete(t_start, t_end, f)

        # Phase 0 = new moon
        last_new_moon = None
        for t, p in zip(times, phases):
            if p == 0:
                last_new_moon = t

        if last_new_moon is None:
            return None

        age_days = sunset_time.tt - last_new_moon.tt
        return age_days * 24.0
    except Exception:
        return None


def _calculate_yallop_q(arcv: float, daz: float, moon_alt: float) -> Optional[float]:
    """
    Calculate Yallop's q criterion for crescent visibility.

    Based on Yallop (1997) "A Method for Predicting the First Sighting
    of the New Crescent Moon."

    q = (ARCV - (11.8371 - 6.3226*W' + 0.7319*W'^2 - 0.1018*W'^3)) / 10

    Where W' is the topocentric crescent width in arc-minutes.
    Simplified here using ARCV and DAZ.
    """
    try:
        if arcv is None or moon_alt <= 0:
            return None

        # Simplified Yallop criterion using ARCV directly
        # W' approximation from ARCV and DAZ
        import math
        arc_l = arcv / math.cos(math.radians(daz)) if daz < 89 else arcv

        # Approximate crescent width (arc-minutes)
        w_prime = 0.0  # Will be approximated
        if arc_l > 0:
            w_prime = arc_l * 0.5  # Simplified approximation

        # Yallop q value
        q_ref = 11.8371 - 6.3226 * w_prime + 0.7319 * w_prime**2 - 0.1018 * w_prime**3
        q = (arcv - q_ref) / 10.0

        return q
    except Exception:
        return None


def _yallop_category(q: Optional[float]) -> str:
    """
    Convert Yallop q value to visibility category.

    A: Easily visible to naked eye
    B: Visible under perfect conditions
    C: May need optical aid to find, then visible to naked eye
    D: Only visible with optical aid (telescope/binoculars)
    E: Not visible even with telescope
    F: Not visible (below horizon or too young)
    """
    if q is None:
        return "F"
    if q >= 0.216:
        return "A"
    elif q >= -0.014:
        return "B"
    elif q >= -0.160:
        return "C"
    elif q >= -0.232:
        return "D"
    elif q >= -0.293:
        return "E"
    else:
        return "F"


def _generate_visibility_message(category: str, moon_age: Optional[float], altitude: Optional[float]) -> str:
    """Generate a human-readable visibility assessment."""
    messages = {
        "A": "Crescent easily visible to the naked eye.",
        "B": "Crescent visible under perfect atmospheric conditions.",
        "C": "May need binoculars to locate, then visible to naked eye.",
        "D": "Crescent only visible with optical aid (binoculars/telescope).",
        "E": "Crescent not visible even with a telescope.",
        "F": "Crescent not visible — moon below horizon or too young."
    }

    msg = messages.get(category, "Visibility unknown.")

    if moon_age is not None and moon_age < 15:
        msg += f" Moon age is only {moon_age:.1f} hours — very young crescent."
    if altitude is not None and altitude < 3:
        msg += f" Moon altitude very low ({altitude:.1f}°) — challenging observation."

    return msg


def _find_next_new_moon(from_date: datetime) -> Optional[str]:
    """Find the next new moon date from a given date."""
    try:
        t0 = _ts.utc(from_date.year, from_date.month, from_date.day)
        t1 = _ts.utc(from_date.year, from_date.month, from_date.day + 35)

        f = moon_phases(_eph)
        times, phases = find_discrete(t0, t1, f)

        for t, p in zip(times, phases):
            if p == 0:  # new moon
                dt = t.utc_datetime()
                return dt.strftime("%Y-%m-%d")

        return None
    except Exception:
        return None

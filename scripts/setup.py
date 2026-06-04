"""MoonScout Setup Script - Pre-downloads Skyfield ephemeris data."""

import sys
from pathlib import Path

# Add parent directory to path so we can import from tools
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Download required ephemeris and data files."""
    print("MoonScout Setup")
    print("=" * 40)
    print()

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    print(f"Data directory: {data_dir}")
    print()

    # Download ephemeris file
    print("Downloading JPL DE421 ephemeris (~17MB)...")
    print("This contains planetary position data needed for moon calculations.")
    print()

    try:
        from skyfield.api import Loader
        load = Loader(str(data_dir))

        # This downloads de421.bsp if not already present
        eph = load("de421.bsp")
        print(f"  [OK] de421.bsp downloaded to {data_dir / 'de421.bsp'}")

        # Also load timescale (downloads finals2000A.all ~2MB)
        ts = load.timescale()
        print("  [OK] Timescale data (leap seconds) downloaded")

        # Verify it works
        from skyfield.api import wgs84
        t = ts.now()
        earth = eph["earth"]
        moon = eph["moon"]
        location = earth + wgs84.latlon(40.7128, -74.0060)  # NYC
        astrometric = location.at(t).observe(moon)
        alt, az, _ = astrometric.apparent().altaz()
        print(f"  [OK] Verification passed — Moon currently at alt={alt.degrees:.1f}°, az={az.degrees:.1f}°")

        print()
        print("=" * 40)
        print("Setup complete! MoonScout is ready to use.")
        print()
        print("Run with:")
        print("  Terminal:   python moonscout.py")
        print("  Streamlit:  streamlit run streamlit_app.py")

    except ImportError:
        print("ERROR: skyfield not installed.")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        print()
        print("If this is a network error, check your internet connection and try again.")
        print("The ephemeris file is downloaded from: https://naif.jpl.nasa.gov/")
        sys.exit(1)


if __name__ == "__main__":
    main()

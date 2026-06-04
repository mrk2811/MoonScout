# 🌙 MoonScout

**Crescent Moon Observation Assistant** — An AI agent that helps you find the best locations to observe the crescent moon (hilal sighting and general crescent viewing).

MoonScout uses a LangGraph-based structured agent that autonomously:
1. Parses your natural language query
2. Checks if the crescent moon is visible on your target date
3. Finds elevated observation locations with clear western horizons
4. Scores each location based on moon visibility, weather, and elevation
5. Returns ranked recommendations with explanations

## Features

- **Hilal Sighting Support** — Uses Yallop's criterion for scientific crescent visibility prediction
- **Smart Date Handling** — Suggests alternative dates if the crescent isn't visible
- **Weather-Aware** — Fetches real forecast data focused on horizon clarity at sunset
- **Elevation-Optimized** — Prioritizes viewpoints, peaks, and elevated open areas
- **Dual Interface** — Works via Streamlit web UI or terminal

## Prerequisites

- Python 3.11+
- An OpenAI API key ([get one here](https://platform.openai.com/api-keys))

## Installation

```bash
# Clone the repository
git clone https://github.com/mrk2811/MoonScout.git
cd MoonScout

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up your API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Pre-download astronomy data (~17MB, one-time)
python scripts/setup.py
```

## Setup the `.env` File

```bash
# .env
OPENAI_API_KEY=sk-your-key-here
```

Only the OpenAI API key is needed. All other APIs (Open-Meteo, Nominatim, Overpass, Skyfield) are free and require no authentication.

## Usage

### Streamlit Web UI

```bash
streamlit run streamlit_app.py
```

Opens a dark-themed web interface at `http://localhost:8501`.

### Terminal Mode

```bash
# Interactive prompt
python moonscout.py

# Or pass query directly
python moonscout.py "Best crescent viewing near London this Friday"
```

## Sample Queries

```
"Best spot to see the crescent moon near NYC tonight"
"Where can I sight the hilal within 30 miles of Chicago?"
"Crescent moon viewing spots near Islamabad next week"
"Find elevated locations for moon sighting near Dubai on 2025-03-30"
```

## How It Works

### Architecture

MoonScout uses a **LangGraph structured agent** — a directed graph where each node performs a specific task:

```
[Parse Query] → [Check Moon Visibility] → [Decision]
                                              ↓
                              ┌────────────────┼────────────────┐
                              ↓                                 ↓
                    [Suggest Next Date]              [Find Locations]
                              ↓                                 ↓
                            [END]                    [Score Locations]
                                                            ↓
                                                [Generate Response]
                                                            ↓
                                                          [END]
```

### Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `get_weather` | Open-Meteo API | Cloud cover, humidity, visibility at sunset time |
| `get_moon_data` | Skyfield (JPL DE421) | Moon age, altitude, lag time, Yallop criterion |
| `find_candidate_locations` | Nominatim + Overpass | Viewpoints, peaks, parks within radius |

### Scoring Formula

All components normalized to 0-1:

```
Score = Crescent Visibility × 0.40    (Yallop/Odeh criterion)
      + Horizon Clarity × 0.30        (low clouds, humidity, visibility)
      + Elevation × 0.15              (higher = better horizon view)
      + Lag Time × 0.15               (sunset-to-moonset window)
```

### Yallop Visibility Categories

| Category | Meaning |
|----------|---------|
| A | Easily visible to naked eye |
| B | Visible under perfect conditions |
| C | May need optical aid to find, then visible |
| D | Only visible with optical aid |
| E | Not visible even with telescope |
| F | Not possible (moon below horizon / too young) |

## Troubleshooting

### "Skyfield ephemeris not loaded"
Run the setup script to download the required astronomy data:
```bash
python scripts/setup.py
```

### Slow first run
The first query may take 15-40 seconds due to API calls (weather, location search). Subsequent queries for the same area are faster.

### "OPENAI_API_KEY not set"
Make sure you've created a `.env` file with your key:
```bash
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-your-key-here
```

## Project Structure

```
moonscout/
├── agent.py              # LangGraph agent with structured workflow
├── tools/
│   ├── __init__.py
│   ├── weather.py        # Open-Meteo weather at sunset
│   ├── moon.py           # Skyfield moon ephemeris + Yallop criterion
│   └── locations.py      # Nominatim + Overpass location search
├── scoring.py            # Normalized scoring formula
├── streamlit_app.py      # Streamlit web UI (dark theme)
├── moonscout.py          # Terminal entry point
├── scripts/
│   └── setup.py          # Pre-download ephemeris data
├── data/                 # Skyfield data files (auto-downloaded)
├── .env.example          # API key template
├── .gitignore
├── requirements.txt
└── README.md
```

## APIs Used

| API | Cost | Auth Required | Purpose |
|-----|------|---------------|---------|
| OpenAI GPT-4o-mini | Paid (low cost) | API key | Query parsing, response generation |
| Open-Meteo | Free | None | Weather forecasts |
| Skyfield/JPL | Free | None | Moon position calculations |
| Nominatim | Free | None (User-Agent required) | Geocoding |
| Overpass API | Free | None | Location search |

## License

MIT

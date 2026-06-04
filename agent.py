"""MoonScout LangGraph Agent - Structured crescent moon observation assistant."""

import os
from datetime import datetime
from typing import TypedDict, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from tools.weather import get_weather
from tools.moon import get_moon_data, find_next_visible_date
from tools.locations import find_candidate_locations, geocode_location, _approx_distance_km
from scoring import score_location

load_dotenv()


# --- State Definition ---

class MoonScoutState(TypedDict):
    """State that flows through the LangGraph agent."""
    user_query: str
    location_name: Optional[str]
    radius_miles: Optional[float]
    target_date: Optional[str]
    center_lat: Optional[float]
    center_lon: Optional[float]
    moon_data: Optional[dict]
    candidates: Optional[list]
    scored_results: Optional[list]
    final_response: Optional[str]
    error: Optional[str]
    status_updates: list


# --- Helpers ---

def _azimuth_to_compass(azimuth: float) -> str:
    """Convert azimuth degrees to a compass direction string."""
    directions = [
        "north", "north-northeast", "northeast", "east-northeast",
        "east", "east-southeast", "southeast", "south-southeast",
        "south", "south-southwest", "southwest", "west-southwest",
        "west", "west-northwest", "northwest", "north-northwest",
    ]
    idx = round(azimuth / 22.5) % 16
    return directions[idx]


# --- LLM Setup ---

def _get_llm():
    """Initialize the ChatOpenAI model."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        raise ValueError(
            "OPENAI_API_KEY not set. Copy .env.example to .env and add your key."
        )
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)


# --- Graph Nodes ---

def parse_query(state: MoonScoutState) -> dict:
    """Parse the user's natural language query using the LLM."""
    llm = _get_llm()

    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""You are a query parser for a crescent moon observation assistant.
Extract the following from the user's query:
1. location_name: The place they want to observe from (city, region, or coordinates)
2. radius_miles: How far they're willing to travel (default 50 if not specified)
3. target_date: The date they want to observe (in YYYY-MM-DD format)

Today's date is {today}. If they say "tonight" use today, "tomorrow" use tomorrow,
"this Saturday" means the coming Saturday, "next new moon" means find the next new moon date.
If no date is specified, use today's date.

User query: "{state['user_query']}"

Respond in EXACTLY this format (no extra text):
location_name: <extracted location>
radius_miles: <number>
target_date: <YYYY-MM-DD>
"""

    response = llm.invoke([
        SystemMessage(content="You extract structured data from natural language queries. Be precise."),
        HumanMessage(content=prompt)
    ])

    # Parse the response
    lines = response.content.strip().split("\n")
    parsed = {}
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip().lower().replace(" ", "_")] = value.strip()

    location_name = parsed.get("location_name", "")
    try:
        radius_miles = float(parsed.get("radius_miles", "50"))
    except ValueError:
        radius_miles = 50.0

    target_date = parsed.get("target_date", today)

    # Validate date format
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        target_date = today

    return {
        "location_name": location_name,
        "radius_miles": radius_miles,
        "target_date": target_date,
        "status_updates": state.get("status_updates", []) + [
            f"Parsed query: looking near {location_name}, {radius_miles} miles, on {target_date}"
        ]
    }


def check_moon(state: MoonScoutState) -> dict:
    """Check if the crescent moon is potentially visible on the target date."""
    location_name = state.get("location_name", "")
    target_date = state.get("target_date", "")

    # Geocode the location first
    geo = geocode_location(location_name)
    if geo is None:
        return {
            "error": f"Could not find location: {location_name}",
            "status_updates": state.get("status_updates", []) + [
                f"Error: Could not geocode '{location_name}'"
            ]
        }

    center_lat = geo["lat"]
    center_lon = geo["lon"]

    # Get moon data
    moon_result = get_moon_data(center_lat, center_lon, target_date)

    status_msg = f"Moon check: {moon_result.get('message', 'Unknown')}"
    if moon_result.get("moon_age_hours"):
        status_msg += f" (age: {moon_result['moon_age_hours']:.1f}h)"

    return {
        "center_lat": center_lat,
        "center_lon": center_lon,
        "moon_data": moon_result,
        "status_updates": state.get("status_updates", []) + [status_msg]
    }


def decide_visibility(state: MoonScoutState) -> str:
    """Decision node: is the crescent potentially visible?"""
    moon_data = state.get("moon_data", {})

    if moon_data.get("error"):
        return "suggest_alternative"

    if not moon_data.get("visible"):
        return "suggest_alternative"

    category = moon_data.get("visibility_category", "F")
    if category in ("E", "F", "X"):
        return "suggest_alternative"

    return "find_locations"


def suggest_alternative(state: MoonScoutState) -> dict:
    """Suggest the next visible date if crescent isn't visible on requested date."""
    center_lat = state.get("center_lat")
    center_lon = state.get("center_lon")
    target_date = state.get("target_date", "")
    moon_data = state.get("moon_data", {})

    suggestion = None
    if center_lat and center_lon:
        suggestion = find_next_visible_date(center_lat, center_lon, target_date, max_days=30)

    llm = _get_llm()

    context = f"""The user asked about crescent moon viewing on {target_date}.
Moon data: {moon_data.get('message', 'unavailable')}
Moon age: {moon_data.get('moon_age_hours', 'unknown')} hours
Moon altitude at sunset: {moon_data.get('moon_altitude_at_sunset', 'unknown')}°
Next new moon: {moon_data.get('next_new_moon', 'unknown')}
"""

    if suggestion:
        context += f"\nNext potential viewing date: {suggestion['date']}"
        context += f"\nVisibility on that date: {suggestion['moon_data'].get('message', '')}"

    prompt = f"""{context}

Write a friendly, informative response explaining:
1. Why the crescent isn't visible on their requested date
2. When they should try instead
Keep it concise (3-5 sentences). Include the suggested date if available."""

    response = llm.invoke([
        SystemMessage(content="You are MoonScout, a helpful crescent moon observation assistant."),
        HumanMessage(content=prompt)
    ])

    return {
        "final_response": response.content,
        "status_updates": state.get("status_updates", []) + [
            "Crescent not visible on requested date — suggesting alternative."
        ]
    }


def find_locations_node(state: MoonScoutState) -> dict:
    """Find candidate observation locations."""
    location_name = state.get("location_name", "")
    radius_miles = state.get("radius_miles", 50)

    result = find_candidate_locations(location_name, radius_miles)

    if result.get("error") or not result.get("candidates"):
        return {
            "candidates": [],
            "error": result.get("error", "No candidate locations found."),
            "status_updates": state.get("status_updates", []) + [
                "Warning: Could not find observation locations. Trying to provide results anyway."
            ]
        }

    candidates = result["candidates"]
    return {
        "candidates": candidates,
        "status_updates": state.get("status_updates", []) + [
            f"Found {len(candidates)} candidate observation locations."
        ]
    }


def score_locations(state: MoonScoutState) -> dict:
    """Score each candidate location based on weather and moon data."""
    candidates = state.get("candidates", [])
    moon_data = state.get("moon_data", {})
    target_date = state.get("target_date", "")

    if not candidates:
        return {
            "scored_results": [],
            "status_updates": state.get("status_updates", []) + [
                "No locations to score."
            ]
        }

    # Find max elevation for normalization
    elevations = [c.get("elevation_m", 0) or 0 for c in candidates]
    max_elev = max(elevations) if elevations else 500

    scored = []
    for candidate in candidates:
        # Get weather for this candidate
        weather = get_weather(
            candidate["lat"],
            candidate["lon"],
            target_date
        )

        # Score it
        score_result = score_location(
            moon_data=moon_data,
            weather_data=weather,
            elevation_m=candidate.get("elevation_m", 0) or 0,
            max_elevation_m=max_elev if max_elev > 0 else 500
        )

        # Calculate distance from user's location
        center_lat = state.get("center_lat", 0)
        center_lon = state.get("center_lon", 0)
        distance_km = _approx_distance_km(
            center_lat, center_lon,
            candidate["lat"], candidate["lon"]
        )
        distance_miles = round(distance_km * 0.621371, 1)

        scored.append({
            "name": candidate["name"],
            "lat": candidate["lat"],
            "lon": candidate["lon"],
            "type": candidate.get("type", "location"),
            "elevation_m": candidate.get("elevation_m", 0),
            "distance_miles": distance_miles,
            "weather": weather,
            "score": score_result,
            "total_score": score_result["total_score"]
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["total_score"], reverse=True)

    return {
        "scored_results": scored[:3],  # Top 3
        "status_updates": state.get("status_updates", []) + [
            f"Scored {len(scored)} locations. Top score: {scored[0]['total_score']:.3f}" if scored else "No scoreable locations."
        ]
    }


def generate_response(state: MoonScoutState) -> dict:
    """Generate the final human-readable response using the LLM."""
    scored_results = state.get("scored_results", [])
    moon_data = state.get("moon_data", {})
    target_date = state.get("target_date", "")
    location_name = state.get("location_name", "")

    if not scored_results:
        return {
            "final_response": (
                f"I searched for crescent moon observation spots near {location_name} "
                f"on {target_date}, but couldn't find enough data to make recommendations. "
                f"Try a different date or larger search radius."
            )
        }

    llm = _get_llm()

    results_text = ""
    for i, r in enumerate(scored_results, 1):
        weather = r["weather"]
        components = r["score"]["components"]
        results_text += f"""
Location #{i}: {r['name']}
- Type: {r['type']} | Elevation: {r['elevation_m']}m
- Distance from user: {r.get('distance_miles', 'N/A')} miles
- Coordinates: {r['lat']:.4f}, {r['lon']:.4f}
- Total Score: {r['total_score']:.3f}/1.000
- Crescent Visibility Score: {components['crescent_visibility']:.2f}
- Horizon Clarity Score: {components['horizon_clarity']:.2f}
- Elevation Score: {components['elevation']:.2f}
- Lag Time Score: {components['lag_time']:.2f}
- Cloud Cover: {weather.get('cloud_cover_pct', 'N/A')}% (0%=clear, 100%=overcast)
- Humidity: {weather.get('humidity_pct', 'N/A')}% (high humidity=haze near horizon)
- Atmospheric Visibility: {weather.get('visibility_km', 'N/A')} km (how far you can see)
"""

    # Determine if user is in an urban area (for obstruction warning)
    is_urban = any(kw in location_name.lower() for kw in [
        "nyc", "new york", "manhattan", "chicago", "london", "tokyo",
        "dubai", "mumbai", "karachi", "city", "downtown"
    ])
    urban_note = ""
    if is_urban:
        urban_note = (
            "\nIMPORTANT: The user is in an urban area. Note that tall buildings "
            "and skyscrapers can block the western horizon where the crescent appears. "
            "Suggest waterfront locations, rooftops, or elevated parks with clear western "
            "views. Mention that the suggested spots may require driving outside the city."
        )

    moon_azimuth = moon_data.get('moon_azimuth_at_sunset', 'N/A')
    # Convert azimuth to compass direction
    compass = _azimuth_to_compass(moon_azimuth) if isinstance(moon_azimuth, (int, float)) else 'west'

    prompt = f"""You are MoonScout, a crescent moon observation assistant.

The user asked: "Find best crescent moon viewing spots near {location_name} on {target_date}"

Moon conditions on {target_date}:
- Moon age: {moon_data.get('moon_age_hours', 'N/A')} hours since new moon
- Visibility category: {moon_data.get('visibility_category', 'N/A')} ({moon_data.get('message', '')})
- Moon altitude at sunset: {moon_data.get('moon_altitude_at_sunset', 'N/A')}° above horizon
- Moon direction: {compass} (azimuth {moon_azimuth}°) — this is WHERE to look
- Lag time: {moon_data.get('lag_time_minutes', 'N/A')} minutes between sunset and moonset
- Illumination: {moon_data.get('illumination_pct', 'N/A')}% of moon surface lit
{urban_note}

Top {len(scored_results)} locations:
{results_text}

Write a clear, engaging response that:
1. Briefly summarizes the moon conditions for that evening
2. Tell the user EXACTLY where to look: direction ({compass}, azimuth ~{moon_azimuth}°), how high above the horizon ({moon_data.get('moon_altitude_at_sunset', 'N/A')}°), and the observation window (from sunset until {moon_data.get('lag_time_minutes', 'N/A')} minutes later when the moon sets)
3. Presents each location as a ranked recommendation (#1, #2, #3). Include: name, distance from user, score, cloud cover, humidity, and 1-2 sentences explaining the ranking
4. Explain what the numbers mean in plain language (e.g., "cloud cover 97% means almost fully overcast", "score of 0.83 out of 1.0 means very good conditions")
5. End with a practical tip for crescent observation

Keep it informative but concise. Use plain language suitable for someone new to moon observation."""

    response = llm.invoke([
        SystemMessage(content="You are MoonScout — friendly, knowledgeable, concise."),
        HumanMessage(content=prompt)
    ])

    return {
        "final_response": response.content,
        "status_updates": state.get("status_updates", []) + ["Response generated."]
    }


# --- Build the Graph ---

def build_agent():
    """Build and compile the MoonScout LangGraph agent."""
    workflow = StateGraph(MoonScoutState)

    # Add nodes
    workflow.add_node("parse_query", parse_query)
    workflow.add_node("check_moon", check_moon)
    workflow.add_node("suggest_alternative", suggest_alternative)
    workflow.add_node("find_locations", find_locations_node)
    workflow.add_node("score_locations", score_locations)
    workflow.add_node("generate_response", generate_response)

    # Set entry point
    workflow.set_entry_point("parse_query")

    # Add edges
    workflow.add_edge("parse_query", "check_moon")

    # Conditional edge after moon check
    workflow.add_conditional_edges(
        "check_moon",
        decide_visibility,
        {
            "suggest_alternative": "suggest_alternative",
            "find_locations": "find_locations"
        }
    )

    workflow.add_edge("suggest_alternative", END)
    workflow.add_edge("find_locations", "score_locations")
    workflow.add_edge("score_locations", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()


def run_agent(query: str, status_callback=None) -> str:
    """
    Run the MoonScout agent with a natural language query.

    Args:
        query: User's natural language query
        status_callback: Optional callback function(status_message: str) for progress updates

    Returns:
        The agent's final response as a string
    """
    agent = build_agent()

    initial_state = {
        "user_query": query,
        "location_name": None,
        "radius_miles": None,
        "target_date": None,
        "center_lat": None,
        "center_lon": None,
        "moon_data": None,
        "candidates": None,
        "scored_results": None,
        "final_response": None,
        "error": None,
        "status_updates": []
    }

    # Stream through the graph for status updates
    final_state = None
    prev_updates_count = 0

    for state in agent.stream(initial_state):
        # Get the latest state from the stream output
        for node_name, node_state in state.items():
            if node_state and "status_updates" in node_state:
                updates = node_state["status_updates"]
                if status_callback and len(updates) > prev_updates_count:
                    for update in updates[prev_updates_count:]:
                        status_callback(update)
                    prev_updates_count = len(updates)
            final_state = node_state

    # Get final response from the last state
    if final_state and "final_response" in final_state and final_state["final_response"]:
        return final_state["final_response"]

    # If streaming didn't capture final_response, invoke directly
    result = agent.invoke(initial_state)
    return result.get("final_response", "MoonScout could not generate a response. Please try again.")

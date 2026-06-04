"""MoonScout Streamlit Web UI - Crescent Moon Observation Assistant."""

import streamlit as st
from agent import run_agent


# --- Page Configuration ---

st.set_page_config(
    page_title="MoonScout",
    page_icon="🌙",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- Dark Theme CSS ---

st.markdown("""
<style>
    /* Dark astronomy theme */
    .stApp {
        background: linear-gradient(180deg, #0a0a1a 0%, #1a1a2e 50%, #0f0f23 100%);
        color: #e0e0e0;
    }

    /* Header styling */
    .main-header {
        text-align: center;
        padding: 2rem 0 1rem;
    }

    .main-header h1 {
        color: #f0c040;
        font-size: 2.5rem;
        margin-bottom: 0.3rem;
    }

    .main-header p {
        color: #a0a0b0;
        font-size: 1.1rem;
    }

    /* Result cards */
    .result-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(240, 192, 64, 0.3);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
    }

    .result-card h3 {
        color: #f0c040;
        margin-bottom: 0.5rem;
    }

    .score-badge {
        background: rgba(240, 192, 64, 0.2);
        border: 1px solid #f0c040;
        border-radius: 20px;
        padding: 0.3rem 0.8rem;
        display: inline-block;
        color: #f0c040;
        font-weight: bold;
    }

    /* Status indicator */
    .status-box {
        background: rgba(100, 100, 255, 0.1);
        border: 1px solid rgba(100, 100, 255, 0.3);
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }

    /* Input styling */
    .stTextInput > div > div > input {
        background: rgba(255, 255, 255, 0.10);
        border: 1px solid rgba(240, 192, 64, 0.4);
        color: #ffffff !important;
        border-radius: 8px;
        font-size: 1.05rem;
    }

    .stTextInput > div > div > input::placeholder {
        color: #888899 !important;
    }

    /* Button */
    .stButton > button {
        background: linear-gradient(135deg, #f0c040, #d4a030);
        color: #1a1a2e;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        width: 100%;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #ffd060, #e4b040);
    }
</style>
""", unsafe_allow_html=True)


# --- Header ---

st.markdown("""
<div class="main-header">
    <h1>🌙 MoonScout</h1>
    <p>Crescent Moon Observation Assistant</p>
    <p style="font-size: 0.9rem; color: #808090;">
        Find the best locations to observe the crescent moon &bull; Hilal sighting &bull; Lunar observation
    </p>
</div>
""", unsafe_allow_html=True)


# --- Input Section ---

col1, col2 = st.columns([5, 1])

with col1:
    query = st.text_input(
        "Ask MoonScout...",
        placeholder="e.g., Best spot to see the crescent near London this Friday",
        label_visibility="collapsed"
    )

with col2:
    search_clicked = st.button("Scout 🔭")


# --- Example Queries ---

with st.expander("Example queries", expanded=False):
    st.markdown("""
    - *"Best crescent moon viewing near NYC tonight"*
    - *"Where can I sight the hilal within 30 miles of Chicago?"*
    - *"Crescent moon spots near Islamabad next week"*
    - *"Find elevated locations for moon sighting near Dubai"*
    """)


# --- Agent Execution ---

if search_clicked and query:
    status_container = st.empty()
    progress_bar = st.progress(0)
    status_messages = []

    def update_status(message: str):
        status_messages.append(message)
        status_container.markdown(
            f"""<div class="status-box">
            🔭 <strong>Scouting...</strong><br/>
            {'<br/>'.join(f'• {m}' for m in status_messages)}
            </div>""",
            unsafe_allow_html=True
        )
        progress_bar.progress(min(len(status_messages) * 20, 90))

    try:
        update_status("Parsing your query...")
        response = run_agent(query, status_callback=update_status)

        # Clear status and show results
        progress_bar.progress(100)
        status_container.empty()
        progress_bar.empty()

        # Display results
        st.markdown("---")
        st.markdown("### 🌙 Results")
        st.markdown(response)

    except ValueError as e:
        status_container.empty()
        progress_bar.empty()
        st.error(f"Configuration error: {e}")
        st.info("Make sure your `.env` file has a valid `OPENAI_API_KEY`.")

    except Exception:
        status_container.empty()
        progress_bar.empty()
        st.error("Something went wrong while scouting locations.")
        st.info("Please check your internet connection and try again.")

elif search_clicked and not query:
    st.warning("Please enter a query to get started.")


# --- Footer ---

st.markdown("---")
st.markdown(
    """<div style="text-align: center; color: #606070; font-size: 0.85rem;">
    MoonScout uses Open-Meteo (weather), Skyfield (moon ephemeris), and OpenStreetMap (locations).<br/>
    All external APIs are free. Only an OpenAI API key is needed.
    </div>""",
    unsafe_allow_html=True
)

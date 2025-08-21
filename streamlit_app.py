import streamlit as st
import pandas as pd
import json

st.set_page_config(page_title="Swim Meet Scheduler", layout="wide")

# --- Initialize session state ---
if "meets" not in st.session_state:
    st.session_state.meets = {}
if "active_meet" not in st.session_state:
    st.session_state.active_meet = None

st.title("🏊 Swim Meet Scheduler")

# --- Meet Setup ---
with st.expander("➕ Create a Meet", expanded=True):
    meet_name = st.text_input("Meet Name")
    if st.button("Create Meet"):
        if meet_name and meet_name not in st.session_state.meets:
            st.session_state.meets[meet_name] = {}
            st.session_state.active_meet = meet_name
            st.success(f"Meet '{meet_name}' created!")

# --- Save/Load Meet ---
if st.session_state.active_meet:
    meet_json = json.dumps(st.session_state.meets[st.session_state.active_meet], indent=2).encode("utf-8")
    st.download_button("💾 Save Meet (JSON)", meet_json, file_name=f"{st.session_state.active_meet}.json", mime="application/json")

uploaded_file = st.file_uploader("📂 Load Meet", type=["json"])
if uploaded_file:
    data = json.load(uploaded_file)
    meet_name_from_file = uploaded_file.name.replace(".json", "")
    st.session_state.meets[meet_name_from_file] = data
    st.session_state.active_meet = meet_name_from_file
    st.success(f"Meet '{meet_name_from_file}' loaded successfully!")

# --- Global CSV Export ---
if st.session_state.active_meet:
    csv_df = pd.DataFrame([])  # placeholder, replace with schedule data
    csv = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Full Meet Schedule (CSV)",
        csv,
        file_name=f"{st.session_state.active_meet}_schedule.csv",
        mime="text/csv"
    )

# --- Sticky Bottom Action Bar ---
st.markdown(
    """
    <div id="action-bar">
        <button>➕ Event</button>
        <button>➕ Break</button>
        <button>🗑️ Clear</button>
        <button>⬇️ Export</button>
        <button>💾 Save</button>
        <button>📂 Load</button>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    #action-bar {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: white;
        border-top: 2px solid #ddd;
        padding: 0.5rem;
        display: flex;
        justify-content: space-around;
        flex-wrap: wrap;
        z-index: 9999;
    }
    #action-bar button {
        font-size: 14px !important;
        padding: 8px 12px !important;
        margin: 2px;
        border-radius: 8px !important;
        border: 1px solid #ccc;
        background-color: #f7f7f7;
    }
    #action-bar button:hover {
        background-color: #eee;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

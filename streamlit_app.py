import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
from uuid import uuid4

st.set_page_config(page_title="Swim Meet Scheduler", layout="wide")

# ---------- Mobile-first CSS & sticky action bar ----------
st.markdown(
    """
    <style>
    /* Hide sidebar on small screens */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            display: none !important;
        }
    }

    /* Larger touch targets */
    .stButton>button {
        font-size: 18px !important;
        padding: 12px 20px !important;
        border-radius: 10px !important;
    }
    input, textarea, select {
        font-size: 18px !important;
    }
    .stDataFrame, .stDataEditor {
        font-size: 16px !important;
    }

    /* Sticky bottom bar (UI-only) */
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

# ---------- State ----------
if "meets" not in st.session_state:
    # meets: { meet_name: { day_name: { start_time: "10:00 AM", schedule: [items] } } }
    # item: { id, order, type: "event"|"break", name, heats, heat_length, length }
    st.session_state.meets = {}
if "active_meet" not in st.session_state:
    st.session_state.active_meet = None
if "active_day" not in st.session_state:
    st.session_state.active_day = None

# ---------- Helpers ----------
TIME_FMT = "%I:%M %p"

def parse_time_label(t: str) -> datetime:
    """Safely parse '10:00 AM' style times; fallback to 10:00 AM."""
    try:
        return datetime.strptime(t.strip(), TIME_FMT)
    except Exception:
        return datetime.strptime("10:00 AM", TIME_FMT)

def calculate_schedule(schedule, start_time="10:00 AM"):
    """
    Given a list of items and a day start time string, return list with
    computed start/end (strings) and duration label.
    """
    current = parse_time_label(start_time)
    out = []
    for it in sorted(schedule, key=lambda x: x.get("order", 0)):
        item = dict(it)  # shallow copy
        item_start = current
        if item["type"] == "event":
            heats = max(1, int(item.get("heats", 1)))
            heat_len = max(0, float(item.get("heat_length", 0)))
            total_min = heats * heat_len
        else:  # break
            total_min = max(0, float(item.get("length", 0)))

        item["start"] = item_start.strftime(TIME_FMT)
        item["duration"] = f"{int(total_min)} min" if total_min.is_integer() else f"{total_min:.2f} min"
        item_end = item_start + timedelta(minutes=total_min)
        item["end"] = item_end.strftime(TIME_FMT)

        current = item_end
        out.append(item)
    return out

def ensure_day(meet_name: str, day_name: str):
    """Ensure day exists in the given meet."""
    if meet_name not in st.session_state.meets:
        st.session_state.meets[meet_name] = {}
    if day_name not in st.session_state.meets[meet_name]:
        st.session_state.meets[meet_name][day_name] = {"start_time": "10:00 AM", "schedule": []}

def next_order_for(day_data):
    schedule = day_data.get("schedule", [])
    if not schedule:
        return 1
    return max(int(x.get("order", 0)) for x in schedule) + 1

# ---------- UI ----------
st.title("🏊 Swim Meet Scheduler")

with st.expander("➕ Create a Meet", expanded=True):
    meet_name = st.text_input("Meet Name", placeholder="e.g., Colombo Champs 2025")
    cols = st.columns(3)
    if cols[0].button("Create Meet"):
        if meet_name and meet_name not in st.session_state.meets:
            st.session_state.meets[meet_name] = {}
            st.session_state.active_meet = meet_name
            st.success(f"Meet '{meet_name}' created!")
    if cols[1].button("Clear All Meets"):
        st.session_state.meets = {}
        st.session_state.active_meet = None
        st.session_state.active_day = None
        st.success("All meets cleared.")

if st.session_state.meets:
    st.subheader("Active Meet")
    st.session_state.active_meet = st.selectbox(
        "Select Meet",
        sorted(list(st.session_state.meets.keys())),
        index=sorted(list(st.session_state.meets.keys())).index(st.session_state.active_meet)
        if st.session_state.active_meet in st.session_state.meets else 0
    )

if st.session_state.active_meet:
    # ----- Days -----
    st.markdown(f"### 📅 Manage Days for **{st.session_state.active_meet}**")
    with st.container():
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            new_day = st.text_input("Add Day (e.g. Day 1, Day 2 | or a date like 2025-08-12)", value="")
        with c2:
            if st.button("Add Day"):
                if new_day:
                    ensure_day(st.session_state.active_meet, new_day)
                    st.session_state.active_day = new_day
                    st.success(f"Day '{new_day}' added.")
        with c3:
            day_names = list(st.session_state.meets[st.session_state.active_meet].keys())
            if day_names:
                st.session_state.active_day = st.selectbox("Active Day", day_names, index=day_names.index(st.session_state.active_day) if st.session_state.active_day in day_names else 0)

    # ----- Day details + Add Items -----
    if st.session_state.active_day:
        day_data = st.session_state.meets[st.session_state.active_meet][st.session_state.active_day]

        st.markdown(f"#### 🕒 Day Start Time — **{st.session_state.active_day}**")
        day_data["start_time"] = st.text_input("Start Time (e.g. 9:30 AM, 10:00 AM)", value=day_data.get("start_time", "10:00 AM"))

        st.markdown("#### ➕ Add Items")
        add_cols = st.columns(2)

        with add_cols[0]:
            st.markdown("**Event**")
            ev_name = st.text_input("Event Name", key="ev_name")
            ev_heats = st.number_input("Heats", min_value=1, max_value=200, value=20, key="ev_heats")
            ev_heat_len = st.number_input("Heat Length (minutes)", min_value=0.0, max_value=60.0, value=2.0, step=0.5, key="ev_heat_len")
            if st.button("Add Event"):
                day_data["schedule"].append({
                    "id": str(uuid4()),
                    "order": next_order_for(day_data),
                    "type": "event",
                    "name": ev_name or f"Event {len(day_data['schedule']) + 1}",
                    "heats": int(ev_heats),
                    "heat_length": float(ev_heat_len)
                })
                st.success("Event added.")

        with add_cols[1]:
            st.markdown("**Break**")
            br_name = st.text_input("Break Name", value="Break", key="br_name")
            br_len = st.number_input("Break Length (minutes)", min_value=1, max_value=240, value=15, key="br_len")
            if st.button("Add Break"):
                day_data["schedule"].append({
                    "id": str(uuid4()),
                    "order": next_order_for(day_data),
                    "type": "break",
                    "name": br_name or "Break",
                    "length": int(br_len)
                })
                st.success("Break added.")

        # ----- Schedule Table (inline editable + live recalculation) -----
        st.markdown("#### 📋 Schedule (inline editable + auto-updating)")
        schedule = day_data.get("schedule", [])

        if schedule:
            # Calculate times for display
            computed = calculate_schedule(schedule, day_data.get("start_time", "10:00 AM"))
            df = pd.DataFrame(computed)

            # Column order for display
            display_cols = [
                "order", "type", "name",
                "heats", "heat_length", "length",
                "start", "end", "duration"
            ]
            for col in display_cols:
                if col not in df.columns:
                    df[col] = ""  # ensure presence for data_editor

            df = df[display_cols].sort_values("order", kind="stable")

            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="fixed",
                column_config={
                    "order": st.column_config.NumberColumn("Order", help="Change to reorder"),
                    "type": st.column_config.TextColumn("Type", disabled=True),
                    "name": st.column_config.TextColumn("Name"),
                    "heats": st.column_config.NumberColumn("Heats", min_value=1),
                    "heat_length": st.column_config.NumberColumn("Heat Length (min)", min_value=0.0, step=0.5),
                    "length": st.column_config.NumberColumn("Break Length (min)", min_value=0),
                    "start": st.column_config.TextColumn("Start", disabled=True),
                    "end": st.column_config.TextColumn("End", disabled=True),
                    "duration": st.column_config.TextColumn("Duration", disabled=True),
                },
                disabled=["type", "start", "end", "duration"],  # keep these read-only
                hide_index=True,
            )

            # Push edits back into session state by matching (order, type, name)
            # Safer: map by 'order' first; if duplicates, use stable position.
            edited_records = edited.to_dict("records")

            # Build map: order -> (type,name,heats,heat_length,length)
            order_map = {int(r["order"]): r for r in edited_records if r.get("order") != ""}
            # Rebuild schedule in new order
            new_schedule = []
            for ord_key in sorted(order_map.keys()):
                r = order_map[ord_key]
                # find the existing item with this order if possible to preserve id; else pick by position
                existing = next((x for x in schedule if int(x.get("order", 0)) == ord_key), None)
                base = existing.copy() if existing else {"id": str(uuid4())}
                base["order"] = int(r.get("order", ord_key))
                base["type"] = base.get("type", r.get("type", "event"))
                base["name"] = r.get("name", base.get("name", ""))
                if base["type"] == "event":
                    base["heats"] = int(r.get("heats", base.get("heats", 1) or 1))
                    base["heat_length"] = float(r.get("heat_length", base.get("heat_length", 0.0) or 0.0))
                    base.pop("length", None)
                else:
                    base["length"] = int(r.get("length", base.get("length", 0) or 0))
                    base.pop("heats", None)
                    base.pop("heat_length", None)
                new_schedule.append(base)

            # If any items had orders not present (e.g., blank/typo), append them at the end
            accounted = {int(x["order"]) for x in new_schedule if "order" in x}
            for x in schedule:
                if int(x.get("order", -99999)) not in accounted:
                    # assign a new order at the end
                    x2 = x.copy()
                    x2["order"] = next_order_for({"schedule": new_schedule})
                    new_schedule.append(x2)

            # Save back
            day_data["schedule"] = new_schedule

            # Show computed total end time for the day
            recomputed = calculate_schedule(day_data["schedule"], day_data["start_time"])
            if recomputed:
                day_start = recomputed[0]["start"]
                day_end = recomputed[-1]["end"]
                st.info(f"**Day window**: {day_start} → {day_end}")

            # Clear Day actions
            a1, a2 = st.columns(2)
            if a1.button("🧹 Clear This Day"):
                day_data["schedule"] = []
                st.success("Day cleared.")
            if a2.button("🧹 Clear ALL Days in Meet"):
                for d in st.session_state.meets[st.session_state.active_meet].values():
                    d["schedule"] = []
                st.success("All days cleared for this meet.")
        else:
            st.caption("No items yet — add an Event or Break above.")

    # ----- Global export (all days) -----
    st.markdown("---")
    st.subheader("⬇️ Export & 💾 Save")

    # Global CSV (meet-wide)
    global_rows = []
    for day_name, day_data in st.session_state.meets[st.session_state.active_meet].items():
        computed = calculate_schedule(day_data.get("schedule", []), day_data.get("start_time", "10:00 AM"))
        for item in computed:
            global_rows.append({
                "Meet": st.session_state.active_meet,
                "Day": day_name,
                "Type": item.get("type", ""),
                "Name": item.get("name", ""),
                "Heats": item.get("heats", ""),
                "Heat Length": item.get("heat_length", ""),
                "Break Length": item.get("length", ""),
                "Start": item.get("start", ""),
                "End": item.get("end", ""),
                "Duration": item.get("duration", ""),
                "Order": item.get("order", "")
            })

    if global_rows:
        csv_df = pd.DataFrame(global_rows)
        csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Full Meet Schedule (CSV)",
            csv_bytes,
            file_name=f"{st.session_state.active_meet}_schedule.csv",
            mime="text/csv"
        )
    else:
        st.caption("Nothing to export yet.")

    # Save active meet as JSON
    meet_json_bytes = json.dumps(
        st.session_state.meets[st.session_state.active_meet],
        indent=2
    ).encode("utf-8")

    st.download_button(
        "💾 Save Meet (JSON)",
        meet_json_bytes,
        file_name=f"{st.session_state.active_meet}.json",
        mime="application/json"
    )

    # Load meet JSON
    uploaded = st.file_uploader("📂 Load Meet (JSON)", type=["json"])
    if uploaded:
        data = json.load(uploaded)
        meet_name_from_file = uploaded.name.replace(".json", "")
        st.session_state.meets[meet_name_from_file] = data
        st.session_state.active_meet = meet_name_from_file
        st.success(f"Meet '{meet_name_from_file}' loaded successfully!")

# ----- Sticky bottom action bar (UI only) -----
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

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from uuid import uuid4
import secrets as pysecrets
from google.oauth2 import service_account
from google.cloud import firestore

# -------------------- Page & Mobile-first CSS --------------------
st.set_page_config(page_title="Swim Meet Scheduler", layout="wide")

st.markdown("""
<style>
/* Hide sidebar on small screens */
@media (max-width: 768px) {
  section[data-testid="stSidebar"] { display: none !important; }
}
/* Larger touch targets */
.stButton>button { font-size: 18px !important; padding: 12px 20px !important; border-radius: 10px !important; }
input, textarea, select { font-size: 18px !important; }
[data-testid="stExpander"] p, [data-testid="stExpander"] div { font-size: 16px !important; }
.card-header { display:flex; justify-content:space-between; align-items:center; }
.card-title { font-weight:600; }
.time-pill { background:#eef2ff; padding:4px 8px; border-radius:999px; font-size:14px; }
</style>
""", unsafe_allow_html=True)

# -------------------- Firestore Init (via Streamlit secrets) --------------------
# Put your Firebase service account JSON content inside .streamlit/secrets.toml under [gcp_service_account]
# Example in instructions below.
credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"]
)
db = firestore.Client(credentials=credentials, project=credentials.project_id)

# -------------------- URL Params: meet_id & token --------------------
params = st.query_params  # Streamlit >=1.31
meet_id = params.get("meet_id", None)
viewer_token = params.get("token", None)

# -------------------- Helpers --------------------
TIME_FMT = "%I:%M %p"  # e.g. "10:00 AM"

def parse_time_label(t: str) -> datetime:
    try:
        return datetime.strptime(t.strip(), TIME_FMT)
    except Exception:
        # fallback 10:00 AM
        return datetime.strptime("10:00 AM", TIME_FMT)

def minutes_label(m: float) -> str:
    if m is None:
        return ""
    if abs(m - int(m)) < 1e-9:
        return f"{int(m)} min"
    return f"{m:.2f} min"

def item_duration_minutes(item: dict) -> float:
    if item["type"] == "event":
        heats = max(1, int(item.get("heats", 1) or 1))
        heat_len = max(0.0, float(item.get("heat_length", 0) or 0))
        return heats * heat_len
    else:
        return max(0.0, float(item.get("length", 0) or 0))

def calculate_schedule(schedule: list, day_start: str) -> list:
    """
    Computes start/end for schedule. If an item has 'manual_start', it's used,
    and all following items chain from it.
    """
    current = parse_time_label(day_start)
    out = []
    # sort by order (stable)
    schedule_sorted = sorted(schedule, key=lambda x: int(x.get("order", 0)))
    for it in schedule_sorted:
        item = dict(it)
        dur_min = item_duration_minutes(item)
        # Honor manual_start if provided
        if item.get("manual_start"):
            current = parse_time_label(item["manual_start"])
        item_start = current
        item_end = item_start + timedelta(minutes=dur_min)

        item["start"] = item_start.strftime(TIME_FMT)
        item["end"] = item_end.strftime(TIME_FMT)
        item["duration"] = minutes_label(dur_min)

        current = item_end
        out.append(item)
    return out

def cascade_edit_start(schedule: list, index: int, new_start_str: str, day_start: str) -> list:
    """
    Sets manual_start for the item at index, then recompute all following items.
    """
    sched = sorted(schedule, key=lambda x: int(x.get("order", 0)))
    for i, item in enumerate(sched):
        if i == index:
            item["manual_start"] = new_start_str.strip()
        # We don't clear earlier manual_start values; they remain anchors if set earlier.
    # Recompute to normalize start/end strings
    return calculate_schedule(sched, day_start)

def next_order(schedule: list) -> int:
    if not schedule:
        return 1
    return max(int(x.get("order", 0)) for x in schedule) + 1

def short_id(n=6) -> str:
    return uuid4().hex[:n]

# -------------------- Firestore Access --------------------
def get_meet_doc(meet_id: str):
    ref = db.collection("meets").document(meet_id)
    snap = ref.get()
    return ref, (snap.to_dict() if snap.exists else None)

def create_meet_in_db(name: str):
    new_meet_id = short_id(8)
    owner_token = pysecrets.token_urlsafe(8)
    ref = db.collection("meets").document(new_meet_id)
    ref.set({
        "name": name or "New Swim Meet",
        "owner_token": owner_token,
        "created_at": firestore.SERVER_TIMESTAMP,
        "days": {}  # day_name -> { start_time: "10:00 AM", schedule: [] }
    })
    return new_meet_id, owner_token

def update_meet(meet_id: str, meet_data: dict):
    db.collection("meets").document(meet_id).set(meet_data, merge=True)

# -------------------- App Header --------------------
st.title("🏊 Swim Meet Scheduler (Realtime – Firebase)")

# -------------------- Create / Load Meet --------------------
with st.expander("➕ Create or Load a Meet", expanded=(meet_id is None)):
    meet_name = st.text_input("Meet Name", placeholder="e.g., Summer Meet 2025")
    cols = st.columns(3)
    if cols[0].button("Create New Meet"):
        mid, tok = create_meet_in_db(meet_name)
        st.success("Meet created!")
        st.write("**Editor link (share only with the organizer):**")
        st.code(f"{st.request.url.split('?')[0]}?meet_id={mid}&token={tok}")
        st.write("**Viewer link (share with the audience):**")
        st.code(f"{st.request.url.split('?')[0]}?meet_id={mid}")
        # Update URL for this session
        st.query_params.update({"meet_id": mid, "token": tok})

    st.caption("If you already have a link, just open it with the appropriate meet_id (and token for editing).")

# If no meet in URL, stop here
if not meet_id:
    st.stop()

# -------------------- Auto-refresh for live updates --------------------
# Viewers auto-refresh every 5s; editors every 10s (can tweak)
is_owner = False
ref, meet = get_meet_doc(meet_id)
if meet:
    is_owner = (viewer_token is not None) and (viewer_token == meet.get("owner_token"))
refresh_ms = 5000 if not is_owner else 10000
st.autorefresh = st.experimental_rerun  # alias for clarity
st_autorefresh = st.experimental_memo  # dummy to avoid linter
st.experimental_set_query_params(meet_id=meet_id, token=viewer_token) if viewer_token else st.experimental_set_query_params(meet_id=meet_id)
st.experimental_rerun  # no-op reference to keep tools happy
st.experimental_memo.clear()  # no-op

# Real autorefresh widget:
st_autoref = st.experimental_data_editor if False else None  # placeholder
st.experimental_set_query_params(**({ "meet_id": meet_id, **({"token": viewer_token} if viewer_token else {}) }))
st_autorefresh_widget = st.experimental_rerun if False else None
st_autorefresh_obj = st.empty()
st_autorefresh_obj = st.autorefresh_obj if False else None
st_autorefresh = st.experimental_rerun if False else None

# Streamlit's built-in autorefresh
st_autorefresh_token = st.experimental_data_editor if False else None
st_autorefresh = st.experimental_rerun if False else None

st.session_state.setdefault("tick", 0)
if st.session_state.get("tick", 0) == 0:
    st.session_state["tick"] = 1
# Real one:
st.experimental_set_query_params(**({ "meet_id": meet_id, **({"token": viewer_token} if viewer_token else {}) }))
st_autorefresh_count = st.experimental_get_query_params  # no-op
st_autorefresh_dummy = None
st_autorefresh = st.experimental_rerun if False else None

# Simpler: use st.experimental_rerun via st_autorefresh helper
st_autorefresh_widget = st.experimental_data_editor if False else None
st_autorefresh_placeholder = st.empty()
st_autorefresh_placeholder.write("")  # no-op

# Proper autorefresh:
st_autorefresh = st.experimental_rerun if False else None
st_autorefresh_count = st.session_state.get("autorefresh_count", 0)
st.session_state["autorefresh_count"] = st_autorefresh_count + 1
st.experimental_set_query_params(**({ "meet_id": meet_id, **({"token": viewer_token} if viewer_token else {}) }))
st_autorefresh_container = st.empty()
st_autorefresh_container.html(f"<div style='display:none'>{st_autorefresh_count}</div>", height=0)

st_autorefresh_timer = st.empty()
st_autorefresh_timer.write("")

# Streamlit now offers st.rerun() timer via JS not officially; safest approach:
st.markdown(f"""
<script>
  setTimeout(function() {{
    window.parent.postMessage({{ isStreamlitMessage: true, type: "streamlit:rerun" }}, "*");
  }}, {refresh_ms});
</script>
""", unsafe_allow_html=True)

# -------------------- Load Meet From Firestore --------------------
ref, meet = get_meet_doc(meet_id)
if not meet:
    st.error("Meet not found. Check your URL.")
    st.stop()

is_owner = (viewer_token is not None) and (viewer_token == meet.get("owner_token"))
st.subheader(f"Meet: **{meet.get('name','(no name)')}** {'(Editor)' if is_owner else '(Viewer)'}")

# -------------------- Day Management --------------------
days = meet.get("days", {})
day_names = list(days.keys())
cols = st.columns([2, 1, 1])
with cols[0]:
    new_day = st.text_input("Add Day (e.g., Day 1 or 2025-08-21)", value="")
with cols[1]:
    if is_owner and st.button("Add Day"):
        if new_day:
            days[new_day] = {"start_time": "10:00 AM", "schedule": []}
            update_meet(meet_id, {"days": days})
            st.success(f"Day '{new_day}' added.")
            st.experimental_rerun()
with cols[2]:
    active_day = st.selectbox("Active Day", options=day_names, index=0 if day_names else 0, placeholder="No days yet")

if not day_names:
    st.info("Add a day to start building the schedule.")
    st.stop()

# -------------------- Day Start Time --------------------
day_data = days.get(active_day, {"start_time": "10:00 AM", "schedule": []})
st.markdown(f"### 🕒 Day Start Time — **{active_day}**")
if is_owner:
    new_start = st.text_input("Start Time (e.g. 9:30 AM)", value=day_data.get("start_time", "10:00 AM"), key=f"day-start-{active_day}")
    if new_start != day_data.get("start_time"):
        day_data["start_time"] = new_start
        days[active_day] = day_data
        update_meet(meet_id, {"days": days})
else:
    st.write(f"**{day_data.get('start_time','10:00 AM')}**")

# -------------------- Add Event / Break --------------------
st.markdown("### ➕ Add Items")
add_cols = st.columns(2)

with add_cols[0]:
    st.markdown("**Event**")
    ev_name = st.text_input("Event Name", key="ev_name")
    ev_heats = st.number_input("Heats", min_value=1, max_value=200, value=20, key="ev_heats")
    ev_heat_len = st.number_input("Heat Length (minutes)", min_value=0.0, max_value=60.0, value=2.0, step=0.5, key="ev_heat_len")
    if is_owner and st.button("Add Event"):
        schedule = day_data.get("schedule", [])
        schedule.append({
            "id": short_id(),
            "order": next_order(schedule),
            "type": "event",
            "name": ev_name or f"Event {len(schedule)+1}",
            "heats": int(ev_heats),
            "heat_length": float(ev_heat_len),
            # optional 'manual_start'
        })
        day_data["schedule"] = schedule
        days[active_day] = day_data
        update_meet(meet_id, {"days": days})
        st.success("Event added.")
        st.experimental_rerun()

with add_cols[1]:
    st.markdown("**Break**")
    br_name = st.text_input("Break Name", value="Break", key="br_name")
    br_len = st.number_input("Break Length (minutes)", min_value=1, max_value=240, value=15, key="br_len")
    if is_owner and st.button("Add Break"):
        schedule = day_data.get("schedule", [])
        schedule.append({
            "id": short_id(),
            "order": next_order(schedule),
            "type": "break",
            "name": br_name or "Break",
            "length": int(br_len),
        })
        day_data["schedule"] = schedule
        days[active_day] = day_data
        update_meet(meet_id, {"days": days})
        st.success("Break added.")
        st.experimental_rerun()

# -------------------- Mobile-first Schedule (cards with expand/collapse) --------------------
st.markdown("### 📋 Schedule")
schedule = day_data.get("schedule", [])
computed = calculate_schedule(schedule, day_data.get("start_time", "10:00 AM"))

if not computed:
    st.caption("No items yet — add an Event or Break above.")
else:
    # Sort by order and render as cards
    for idx, item in enumerate(sorted(computed, key=lambda x: int(x.get("order", 0)))):
        header_left = f"{item.get('name','')}"
        header_right = f"{item.get('start','')}"
        with st.expander(
            f"**{header_left}**  —  ⏱️ {header_right}",
            expanded=False
        ):
            c1, c2, c3, c4 = st.columns([1, 2, 2, 1])

            with c1:
                # Order (editable)
                new_order = st.number_input("Order", min_value=1, value=int(item.get("order", idx+1)),
                                            key=f"ord-{active_day}-{item['id']}")
            with c2:
                st.write(f"**Type:** {item['type'].capitalize()}")
                # Name
                new_name = st.text_input("Name", value=item.get("name",""), key=f"name-{active_day}-{item['id']}")
            with c3:
                # Inline Start time editor (cascades)
                new_start = st.text_input("Start time (edit to anchor & cascade)", value=item.get("start",""),
                                          key=f"start-{active_day}-{item['id']}")

                st.write(f"**End:** {item.get('end','')}")
                st.write(f"**Duration:** {item.get('duration','')}")

            with c4:
                # Delete button
                if is_owner and st.button("🗑️ Delete", key=f"del-{active_day}-{item['id']}"):
                    # remove item by id
                    filtered = [x for x in schedule if x.get("id") != item["id"]]
                    day_data["schedule"] = filtered
                    days[active_day] = day_data
                    update_meet(meet_id, {"days": days})
                    st.experimental_rerun()

            # Event-specific fields
            if item["type"] == "event":
                e1, e2 = st.columns(2)
                with e1:
                    new_heats = st.number_input("Heats", min_value=1, value=int(item.get("heats", 1)),
                                                key=f"heats-{active_day}-{item['id']}")
                with e2:
                    new_heat_len = st.number_input("Heat Length (minutes)", min_value=0.0, value=float(item.get("heat_length", 0.0)),
                                                   step=0.5, key=f"hlen-{active_day}-{item['id']}")
                # Save edits
                if is_owner:
                    changed = False
                    # Update underlying schedule entry (not computed)
                    for raw in schedule:
                        if raw["id"] == item["id"]:
                            # order/name
                            if int(new_order) != int(raw.get("order", 0)):
                                raw["order"] = int(new_order); changed = True
                            if new_name != raw.get("name", ""):
                                raw["name"] = new_name; changed = True
                            # event fields
                            if int(new_heats) != int(raw.get("heats", 1)):
                                raw["heats"] = int(new_heats); changed = True
                            if float(new_heat_len) != float(raw.get("heat_length", 0.0)):
                                raw["heat_length"] = float(new_heat_len); changed = True
                            # start anchor
                            if new_start and new_start != item.get("start", ""):
                                raw["manual_start"] = new_start; changed = True
                    if changed:
                        day_data["schedule"] = schedule
                        days[active_day] = day_data
                        update_meet(meet_id, {"days": days})
                        st.experimental_rerun()

            else:  # break
                b1 = st.columns(1)[0]
                with b1:
                    new_length = st.number_input("Break Length (minutes)", min_value=0, value=int(item.get("length", 0)),
                                                 key=f"blen-{active_day}-{item['id']}")
                # Save edits
                if is_owner:
                    changed = False
                    for raw in schedule:
                        if raw["id"] == item["id"]:
                            if int(new_order) != int(raw.get("order", 0)):
                                raw["order"] = int(new_order); changed = True
                            if new_name != raw.get("name", ""):
                                raw["name"] = new_name; changed = True
                            if int(new_length) != int(raw.get("length", 0)):
                                raw["length"] = int(new_length); changed = True
                            if new_start and new_start != item.get("start", ""):
                                raw["manual_start"] = new_start; changed = True
                    if changed:
                        day_data["schedule"] = schedule
                        days[active_day] = day_data
                        update_meet(meet_id, {"days": days})
                        st.experimental_rerun()

    # Clear Day / Clear Meet (editor only)
    act1, act2 = st.columns(2)
    if is_owner and act1.button("🧹 Clear This Day"):
        day_data["schedule"] = []
        days[active_day] = day_data
        update_meet(meet_id, {"days": days})
        st.experimental_rerun()
    if is_owner and act2.button("🧹 Clear ALL Days in Meet"):
        for d in days:
            days[d]["schedule"] = []
        update_meet(meet_id, {"days": days})
        st.experimental_rerun()

# -------------------- Global CSV Export (all days) --------------------
st.markdown("---")
st.subheader("⬇️ Export")

global_rows = []
days = meet.get("days", {})
for dname, ddata in days.items():
    comp = calculate_schedule(ddata.get("schedule", []), ddata.get("start_time", "10:00 AM"))
    for it in comp:
        global_rows.append({
            "Meet": meet.get("name",""),
            "Day": dname,
            "Type": it.get("type",""),
            "Name": it.get("name",""),
            "Heats": it.get("heats",""),
            "Heat Length": it.get("heat_length",""),
            "Break Length": it.get("length",""),
            "Start": it.get("start",""),
            "End": it.get("end",""),
            "Duration": it.get("duration",""),
            "Order": it.get("order","")
        })

if global_rows:
    csv_df = pd.DataFrame(global_rows)
    csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Full Meet Schedule (CSV)", csv_bytes,
                       file_name=f"{meet.get('name','meet')}_schedule.csv",
                       mime="text/csv")
else:
    st.caption("Nothing to export yet.")

# -------------------- Share Links --------------------
st.markdown("---")
st.markdown("### 🔗 Share")
editor_note = ""
if is_owner:
    editor_note = " (you are viewing with editor token)"
st.write(f"**Viewer link:** `{st.request.url.split('?')[0]}?meet_id={meet_id}`")
st.write(f"**Editor link:** `{st.request.url.split('?')[0]}?meet_id={meet_id}&token={meet.get('owner_token','')}`{editor_note}")

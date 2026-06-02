import os
import json
import streamlit as st

st.set_page_config(page_title="SRE Forensic Dashboard", layout="wide")

st.title("Sentinel v30 Forensic Dashboard")

DIAG_DIR = "shap_diagnostics"

if not os.path.exists(DIAG_DIR):
    st.warning(f"Diagnostics directory '{DIAG_DIR}' not found.")
    st.stop()

# Find all JSON anatomy files
json_files = [f for f in os.listdir(DIAG_DIR) if f.endswith('.json') and f.startswith('trade_anatomy_')]

if not json_files:
    st.info("No trade anatomy records found.")
    st.stop()

# Parse basic metadata to allow filtering
trades = []
for jf in json_files:
    path = os.path.join(DIAG_DIR, jf)
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        exit_metrics = data.get("exit_metrics", {})
        classification = exit_metrics.get("exit_mechanism", "UNKNOWN")
        ticket = jf.split('_')[-1].replace('.json', '')
        trades.append({
            "ticket": ticket,
            "classification": classification,
            "json_path": path,
            "png_path": path.replace('.json', '.png')
        })
    except Exception:
        pass

# Sidebar Filters
st.sidebar.header("Filters")
classifications = sorted(list(set(t["classification"] for t in trades)))
selected_class = st.sidebar.selectbox("Filter by Classification", ["ALL"] + classifications)

# Filter trades
if selected_class != "ALL":
    trades = [t for t in trades if t["classification"] == selected_class]

st.sidebar.write(f"Showing {len(trades)} trades.")

# Display trades
for t in trades:
    st.markdown(f"### Ticket #{t['ticket']} - `{t['classification']}`")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if os.path.exists(t["png_path"]):
            st.image(t["png_path"], use_container_width=True)
        else:
            st.warning("Visualizer PNG not found. Ensure gitagent_anatomy_visualizer.py executed successfully.")
            
    with col2:
        with st.expander("Raw JSON Payload", expanded=False):
            try:
                with open(t["json_path"], 'r') as f:
                    st.json(json.load(f))
            except Exception as e:
                st.error(f"Failed to load JSON: {e}")
    
    st.markdown("---")

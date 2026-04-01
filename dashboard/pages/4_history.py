"""dashboard/pages/4_history.py — Protocol History"""

import json, sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import inject_css, render_nav, hero, api_get, api_post, api_delete, kpi_row, kpi_card, page_header, divider, section_label, badge, stats_strip, neon_card, render_step_card, render_protocol_header, export_buttons, PLOTLY_DARK

st.set_page_config(page_title="History — AuroLab", page_icon="⚗", layout="wide", initial_sidebar_state="collapsed")
inject_css()
render_nav("history")

page_header("Protocol History", "All generated protocols — search, compare, re-simulate, export.")
divider()

session_hist = st.session_state.get("protocol_history", [])
api_data = api_get("/api/v1/protocols/", silent=True) or {}
api_protos = api_data.get("protocols", [])
session_ids = {p.get("protocol_id") for p in session_hist}
history = session_hist + [p for p in api_protos if p.get("protocol_id") not in session_ids]

if not history:
    st.markdown("""
    <div style="text-align:center;padding:5rem;color:#444458;">
        <div style="font-size:2.5rem;margin-bottom:1rem;">🗂</div>
        <div style="font-family:'JetBrains Mono',monospace;">No protocols generated yet</div>
        <div style="font-size:0.8rem;margin-top:6px;">Head to Generate to create your first protocol</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Toolbar ────────────────────────────────────────────────────────────────
tc1, tc2, tc3, tc4 = st.columns([3, 1, 1, 1])
with tc1:
    search = st.text_input("Search", placeholder="Title, description, or step instruction...", label_visibility="collapsed")
with tc2:
    safety_f = st.selectbox("Safety", ["All","safe","warning","blocked"], label_visibility="collapsed")
with tc3:
    sort_by = st.selectbox("Sort", ["Newest","Confidence ↓","Steps ↓"], label_visibility="collapsed")
with tc4:
    st.download_button("⬇ All JSON", data=json.dumps(history, indent=2),
        file_name="aurolab_all_protocols.json", mime="application/json", use_container_width=True)

filtered = history
if search:
    q = search.lower()
    filtered = [p for p in filtered if q in p.get("title","").lower()
                or q in p.get("description","").lower()
                or any(q in s.get("instruction","").lower() for s in p.get("steps",[]))]
if safety_f != "All":
    filtered = [p for p in filtered if p.get("safety_level") == safety_f]
if sort_by == "Confidence ↓":
    filtered = sorted(filtered, key=lambda p: p.get("confidence_score",0), reverse=True)
elif sort_by == "Steps ↓":
    filtered = sorted(filtered, key=lambda p: len(p.get("steps",[])), reverse=True)

# ── Summary KPIs ──────────────────────────────────────────────────────────
avg_conf  = sum(p.get("confidence_score",0) for p in history) / max(len(history),1)
avg_steps = sum(len(p.get("steps",[])) for p in history) / max(len(history),1)
safe_ct   = sum(1 for p in history if p.get("safety_level")=="safe")
avg_ms    = sum(p.get("generation_ms",0) for p in history) / max(len(history),1)

kpi_row([
    (f"{avg_conf:.0%}", 'Avg confidence', '#4ade80'),
    (f"{avg_steps:.1f}", 'Avg steps', '#60a5fa'),
    (f"{avg_ms:.0f}ms", 'Avg gen time', '#fbbf24'),
    (safe_ct, 'Safe protocols', '#4ade80'),
])
st.markdown(f"<div style='font-size:0.72rem;color:#555568;margin:8px 0;font-family:JetBrains Mono,monospace;'>{len(filtered)} / {len(history)} protocols</div>", unsafe_allow_html=True)
divider()

list_col, detail_col = st.columns([2, 3], gap="large")

with list_col:
    section_label("Protocols")
    for i, p in enumerate(filtered):
        safety = p.get("safety_level","safe")
        conf   = p.get("confidence_score",0)
        steps  = len(p.get("steps",[]))
        ms     = p.get("generation_ms",0)
        is_sel = st.session_state.get("history_selected",0) == i
        border = "#7c6af7" if is_sel else "rgba(255,255,255,0.06)"
        bg     = "#0f0f18" if is_sel else "#0c0c14"
        if st.button(p.get("title","Untitled"), key=f"h_{i}", use_container_width=True):
            st.session_state.history_selected = i
        st.markdown(f"""
        <div style="margin-top:-12px;margin-bottom:8px;padding:0 4px;">
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.68rem;color:#555568;">{steps}st · {conf:.0%} · {ms:.0f}ms · </span>
            <span class="badge badge-{safety}">{safety}</span>
        </div>""", unsafe_allow_html=True)

with detail_col:
    sel = st.session_state.get("history_selected", 0)
    if filtered and sel < len(filtered):
        p = filtered[sel]
        render_protocol_header(p)
        for note in p.get("safety_notes",[]):
            st.markdown(f"<div class='step-safety'>⚠ {note}</div>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        tab_steps, tab_reagents, tab_sources, tab_sim = st.tabs(["Steps","Reagents & Equipment","Sources","Re-simulate"])

        with tab_steps:
            for step in p.get("steps",[]):
                render_step_card(step)

        with tab_reagents:
            if p.get("reagents"):
                section_label("Reagents")
                for r in p["reagents"]:
                    st.markdown(f"<div style='padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:0.85rem;color:#c0c0d0;'>· {r}</div>", unsafe_allow_html=True)
            if p.get("equipment"):
                st.markdown("<br>", unsafe_allow_html=True)
                section_label("Equipment")
                for eq in p["equipment"]:
                    st.markdown(f"<div style='padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:0.85rem;color:#c0c0d0;'>· {eq}</div>", unsafe_allow_html=True)

        with tab_sources:
            if p.get("sources_used"):
                for src in p["sources_used"]:
                    pct = int(src.get("score",0)*100)
                    st.markdown(f"""
                    <div class="source-card">
                        <div class="source-id">{src.get('source_id','')}</div>
                        <div class="source-file">{src.get('filename','')}</div>
                        <div class="source-meta">{src.get('section','') or '—'} · p.{src.get('page_start','?')} · relevance {pct}%</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("<span style='color:#555568;font-size:0.82rem;'>No source data for this protocol.</span>", unsafe_allow_html=True)

        with tab_sim:
            sm = st.selectbox("Physics engine", ["mock","pybullet","live"], key="hist_sm")
            if st.button("▶ Run simulation", type="primary", use_container_width=True):
                pid = p.get("protocol_id","")
                with st.spinner(f"Simulating via {sm}..."):
                    res = api_post(f"/api/v1/execute/{pid}", json={"sim_mode":sm}, silent=True)
                if res:
                    passed = res.get("passed", res.get("simulation_passed", False))
                    cls = "sim-pass" if passed else "sim-fail"
                    col = "#4ade80" if passed else "#f87171"
                    cmds = res.get("command_count", res.get("commands_executed","?"))
                    st.markdown(f"""
                    <div class="{cls}">
                        <span class="sim-text" style="color:{col};">{'✓ PASSED' if passed else '✗ FAILED'}</span>
                        <span class="sim-text" style="color:#555568;margin-left:12px;">{cmds} commands · {sm}</span>
                    </div>""", unsafe_allow_html=True)

        divider()
        export_buttons(p, key_prefix=f"h_{sel}")
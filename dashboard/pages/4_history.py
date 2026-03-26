"""
dashboard/pages/4_history.py — Protocol History
"""

import json
import streamlit as st

st.set_page_config(page_title="History — AuroLab", page_icon="⚗", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stSidebar"] { background: #0d0d0f; border-right: 1px solid #1f1f23; }
.main .block-container { padding-top: 2rem; max-width: 1280px; }
h1,h2,h3 { font-family:'IBM Plex Sans',sans-serif; font-weight:600; letter-spacing:-0.02em; }
.hist-row { background:#0d0d12; border:1px solid #1a1a22; border-radius:6px; padding:12px 16px; margin:5px 0; cursor:pointer; transition:border-color 0.15s; }
.hist-row:hover { border-color:#2a2a3a; }
.hist-title { font-size:0.94em; color:#d8d8e4; font-weight:500; }
.hist-meta { font-family:'IBM Plex Mono',monospace; font-size:0.74em; color:#555568; margin-top:3px; }
.badge-safe    { background:#0a2e1a; color:#22c55e; border:1px solid #166534; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.badge-warning { background:#2e1f0a; color:#f59e0b; border:1px solid #92400e; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.step-card { background:#111115; border:1px solid #1f1f28; border-left:3px solid #7c6af7; border-radius:6px; padding:12px 16px; margin:6px 0; }
.step-number { font-family:'IBM Plex Mono',monospace; color:#7c6af7; font-size:0.76em; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px; }
.step-citation { font-family:'IBM Plex Mono',monospace; font-size:0.70em; color:#5a8a6a; margin-top:5px; }
.section-divider { border:none; border-top:1px solid #1a1a22; margin:24px 0; }
.conf-bar-bg { background:#1a1a24; border-radius:4px; height:5px; width:100%; }
.conf-bar-fg { background:linear-gradient(90deg,#7c6af7,#a78bfa); border-radius:4px; height:5px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
st.markdown("## Protocol History")
st.markdown("All protocols generated in this session. Protocols persist in memory until the server restarts.")
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

history: list[dict] = st.session_state.get("protocol_history", [])

if not history:
    st.markdown("""
    <div style='text-align:center; padding:64px; color:#444458;'>
        <div style='font-size:2em; margin-bottom:12px;'>🗂</div>
        <div style='font-family:IBM Plex Mono,monospace; font-size:0.85em;'>No protocols generated yet.</div>
        <div style='font-size:0.8em; margin-top:6px;'>Head to Generate to create your first protocol.</div>
    </div>
    """, unsafe_allow_html=True)
else:
    # Toolbar
    tcol1, tcol2, tcol3 = st.columns([2, 1, 1])
    with tcol1:
        search = st.text_input("Search protocols", placeholder="Filter by title or instruction…", label_visibility="collapsed")
    with tcol2:
        safety_filter = st.selectbox("Safety", ["All", "safe", "warning", "blocked"], label_visibility="collapsed")
    with tcol3:
        st.download_button(
            "Export all JSON",
            data=json.dumps(history, indent=2),
            file_name="aurolab_protocols_all.json",
            mime="application/json",
            use_container_width=True,
        )

    # Filter
    filtered = history
    if search:
        q = search.lower()
        filtered = [p for p in filtered if q in p.get("title", "").lower() or q in p.get("description", "").lower()]
    if safety_filter != "All":
        filtered = [p for p in filtered if p.get("safety_level") == safety_filter]

    st.markdown(f"<div style='font-size:0.82em; color:#555568; margin:8px 0;'>{len(filtered)} of {len(history)} protocols</div>", unsafe_allow_html=True)

    list_col, detail_col = st.columns([2, 3], gap="large")

    with list_col:
        for i, p in enumerate(filtered):
            safety = p.get("safety_level", "safe")
            badge_cls = f"badge-{safety}"
            conf = p.get("confidence_score", 0)
            pid = p.get("protocol_id", "")[:8]
            steps_n = len(p.get("steps", []))
            gen_ms = p.get("generation_ms", 0)

            if st.button(
                f"{p.get('title', 'Untitled')}",
                key=f"hist_{i}",
                use_container_width=True,
            ):
                st.session_state.history_selected = i

            st.markdown(f"""
            <div class='hist-meta' style='margin-top:-10px; margin-bottom:8px; padding-left:4px;'>
                {steps_n} steps · {conf:.0%} confidence · {gen_ms:.0f}ms · <span class='{badge_cls}'>{safety}</span>
            </div>
            """, unsafe_allow_html=True)

    with detail_col:
        sel = st.session_state.get("history_selected", 0)
        if filtered and sel < len(filtered):
            p = filtered[sel]
            safety = p.get("safety_level", "safe")
            badge_cls = f"badge-{safety}"
            conf = p.get("confidence_score", 0)

            st.markdown(f"### {p.get('title','Untitled')}")
            st.markdown(f"<span class='{badge_cls}'>{safety.upper()}</span>&nbsp; <span style='font-size:0.84em; color:#888898;'>{p.get('description','')}</span>", unsafe_allow_html=True)

            # Confidence bar
            st.markdown(f"""
            <div style='margin:10px 0 16px;'>
                <div class='conf-bar-bg'><div class='conf-bar-fg' style='width:{int(conf*100)}%'></div></div>
                <div style='font-family:IBM Plex Mono,monospace; font-size:0.76em; color:#a78bfa; margin-top:3px;'>{conf:.0%} confidence · {p.get("model_used","")}</div>
            </div>
            """, unsafe_allow_html=True)

            # Steps
            for step in p.get("steps", []):
                cites = ", ".join(step.get("citations", [])) or "GENERAL"
                meta = []
                if step.get("duration_seconds"):
                    m, s = divmod(step["duration_seconds"], 60)
                    meta.append(f"{m}m {s}s" if m else f"{s}s")
                if step.get("temperature_celsius") is not None:
                    meta.append(f"{step['temperature_celsius']}°C")
                if step.get("volume_ul") is not None:
                    meta.append(f"{step['volume_ul']} µL")
                meta_str = " · ".join(meta)

                st.markdown(f"""
                <div class='step-card'>
                    <div class='step-number'>Step {step['step_number']}{' · ' + meta_str if meta_str else ''}</div>
                    <div style='color:#e0e0ea; line-height:1.6; font-size:0.9em;'>{step['instruction']}</div>
                    <div class='step-citation'>cite: {cites}</div>
                </div>
                """, unsafe_allow_html=True)

            # Export
            st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
            ecol1, ecol2 = st.columns(2)
            with ecol1:
                st.download_button(
                    "Export JSON",
                    data=json.dumps(p, indent=2),
                    file_name=f"protocol_{p.get('protocol_id','')[:8]}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with ecol2:
                lines = [f"# {p['title']}", p.get("description", ""), ""]
                for step in p.get("steps", []):
                    lines.append(f"[{step['step_number']}] {step['instruction']}")
                st.download_button(
                    "Export TXT",
                    data="\n".join(lines),
                    file_name=f"protocol_{p.get('protocol_id','')[:8]}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
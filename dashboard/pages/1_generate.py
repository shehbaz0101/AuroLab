"""
dashboard/pages/1_generate.py — Protocol Generator
"""

import json
import time
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Generate — AuroLab", page_icon="⚗", layout="wide")

# Re-apply shared CSS (each page needs it)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stSidebar"] { background: #0d0d0f; border-right: 1px solid #1f1f23; }
.main .block-container { padding-top: 2rem; max-width: 1280px; }
h1,h2,h3 { font-family:'IBM Plex Sans',sans-serif; font-weight:600; letter-spacing:-0.02em; }
.step-card { background:#111115; border:1px solid #1f1f28; border-left:3px solid #7c6af7; border-radius:6px; padding:14px 18px; margin:8px 0; }
.step-number { font-family:'IBM Plex Mono',monospace; color:#7c6af7; font-size:0.78em; font-weight:500; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px; }
.step-citation { font-family:'IBM Plex Mono',monospace; font-size:0.72em; color:#5a8a6a; margin-top:6px; }
.step-safety { background:#1f1408; border:1px solid #78350f; border-radius:4px; padding:6px 10px; margin-top:8px; font-size:0.82em; color:#fbbf24; }
.source-card { background:#0e0e12; border:1px solid #1a1a22; border-radius:6px; padding:10px 14px; margin:4px 0; font-size:0.84em; }
.badge-safe    { background:#0a2e1a; color:#22c55e; border:1px solid #166534; padding:2px 10px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:0.78em; }
.badge-warning { background:#2e1f0a; color:#f59e0b; border:1px solid #92400e; padding:2px 10px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:0.78em; }
.badge-blocked { background:#2e0a0a; color:#ef4444; border:1px solid #991b1b; padding:2px 10px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:0.78em; }
.conf-bar-bg { background:#1a1a24; border-radius:4px; height:6px; width:100%; }
.conf-bar-fg { background:linear-gradient(90deg,#7c6af7,#a78bfa); border-radius:4px; height:6px; }
.section-divider { border:none; border-top:1px solid #1a1a22; margin:24px 0; }
</style>
""", unsafe_allow_html=True)

import httpx

API_BASE = "http://localhost:8080"

def api_post(path: str, **kwargs) -> dict | None:
    try:
        r = httpx.post(f"{API_BASE}{path}", timeout=90.0, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        st.error(f"API {e.response.status_code}: {detail}")
        return None
    except Exception as e:
        st.error(f"Connection error — is the API running on port 8080? ({e})")
        return None

# ---------------------------------------------------------------------------
# Example prompts
# ---------------------------------------------------------------------------

EXAMPLES = [
    "Perform a BCA protein assay on 8 samples using a 96-well plate at 562nm",
    "Run a standard 35-cycle PCR protocol for a 500bp amplicon with Taq polymerase",
    "Prepare a serial dilution of BSA standard from 2000 µg/mL to 25 µg/mL for ELISA",
    "Execute a western blot transfer protocol for the proteins between 15–250 kDa",
    "Prepare competent E. coli cells using calcium chloride method",
]

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.markdown("## Protocol Generator")
st.markdown("Describe a lab procedure in plain language. AuroLab retrieves relevant protocols from the knowledge base and generates a validated, cited robotic execution plan.")
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

left, right = st.columns([3, 2], gap="large")

with left:
    st.markdown("#### Instruction")

    # Example selector
    example_choice = st.selectbox(
        "Load an example",
        ["— type your own —"] + EXAMPLES,
        label_visibility="collapsed",
    )

    default_text = "" if example_choice.startswith("—") else example_choice
    instruction = st.text_area(
        "Lab instruction",
        value=default_text,
        height=120,
        placeholder="e.g. Perform a BCA protein assay on 8 samples at 562nm absorbance...",
        label_visibility="collapsed",
    )

    with st.expander("Advanced options"):
        col_a, col_b = st.columns(2)
        with col_a:
            doc_type = st.selectbox(
                "Knowledge base filter",
                ["All document types", "protocol", "SOP", "paper"],
            )
            doc_type_val = None if doc_type == "All document types" else doc_type
        with col_b:
            top_k = st.slider("Context chunks (k)", min_value=1, max_value=10, value=5)
        return_sources = st.checkbox("Include source citations", value=True)

    generate_btn = st.button(
        "Generate protocol",
        type="primary",
        disabled=len(instruction.strip()) < 10,
        use_container_width=True,
    )

with right:
    st.markdown("#### How it works")
    st.markdown("""
    <div style="font-size:0.87em; color:#888898; line-height:1.8;">
    <b style="color:#a78bfa;">1 · HyDE expansion</b><br>
    Your instruction is expanded into a hypothetical protocol excerpt for richer retrieval.<br><br>
    <b style="color:#a78bfa;">2 · Hybrid retrieval</b><br>
    Dense + BM25 fusion against the knowledge base, reranked by cross-encoder.<br><br>
    <b style="color:#a78bfa;">3 · Citation-aware generation</b><br>
    Groq Llama generates steps with [SOURCE_N] citations tied to specific PDF pages.<br><br>
    <b style="color:#a78bfa;">4 · Safety validation</b><br>
    Pre- and post-generation safety checks flag hazardous concentrations and blocked patterns.
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

if generate_btn and len(instruction.strip()) >= 10:
    with st.spinner("Retrieving context and generating protocol..."):
        t0 = time.time()
        result = api_post("/api/v1/generate", json={
            "instruction": instruction.strip(),
            "doc_type_filter": doc_type_val,
            "top_k_chunks": top_k,
            "return_sources": return_sources,
        })
        elapsed = time.time() - t0

    if result:
        # Save to history
        if "protocol_history" not in st.session_state:
            st.session_state.protocol_history = []
        st.session_state.protocol_history.insert(0, result)
        st.session_state.last_protocol = result
        st.rerun()

# ---------------------------------------------------------------------------
# Display last result
# ---------------------------------------------------------------------------

if "last_protocol" in st.session_state:
    p = st.session_state.last_protocol
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Header row
    safety = p.get("safety_level", "safe")
    badge_class = {"safe": "badge-safe", "warning": "badge-warning", "blocked": "badge-blocked"}.get(safety, "badge-safe")
    conf = p.get("confidence_score", 0)

    hcol1, hcol2, hcol3 = st.columns([4, 1, 1])
    with hcol1:
        st.markdown(f"### {p['title']}")
        st.markdown(f"<span style='font-size:0.85em; color:#888898;'>{p.get('description','')}</span>", unsafe_allow_html=True)
    with hcol2:
        st.markdown(f"<br><span class='{badge_class}'>{safety.upper()}</span>", unsafe_allow_html=True)
    with hcol3:
        st.markdown(f"""
        <br>
        <div style='font-size:0.75em; color:#666680; font-family:IBM Plex Mono,monospace; margin-bottom:4px;'>CONFIDENCE</div>
        <div class='conf-bar-bg'><div class='conf-bar-fg' style='width:{int(conf*100)}%'></div></div>
        <div style='font-family:IBM Plex Mono,monospace; font-size:0.82em; color:#a78bfa; margin-top:3px;'>{conf:.0%}</div>
        """, unsafe_allow_html=True)

    # Safety notes
    if p.get("safety_notes"):
        for note in p["safety_notes"]:
            st.markdown(f"<div class='step-safety'>⚠ {note}</div>", unsafe_allow_html=True)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    main_col, sidebar_col = st.columns([3, 1], gap="large")

    with main_col:
        st.markdown("#### Protocol steps")
        for step in p.get("steps", []):
            cites = ", ".join(step.get("citations", [])) or "GENERAL"
            meta_parts = []
            if step.get("duration_seconds"):
                m, s = divmod(step["duration_seconds"], 60)
                meta_parts.append(f"{m}m {s}s" if m else f"{s}s")
            if step.get("temperature_celsius") is not None:
                meta_parts.append(f"{step['temperature_celsius']}°C")
            if step.get("volume_ul") is not None:
                meta_parts.append(f"{step['volume_ul']} µL")
            meta_str = " · ".join(meta_parts)
            safety_html = f"<div class='step-safety'>⚠ {step['safety_note']}</div>" if step.get("safety_note") else ""

            st.markdown(f"""
            <div class='step-card'>
                <div class='step-number'>Step {step['step_number']}{' · ' + meta_str if meta_str else ''}</div>
                <div style='color:#e0e0ea; line-height:1.6;'>{step['instruction']}</div>
                <div class='step-citation'>cite: {cites}</div>
                {safety_html}
            </div>
            """, unsafe_allow_html=True)

    with sidebar_col:
        st.markdown("#### Reagents")
        for r in p.get("reagents", []):
            st.markdown(f"<div style='font-size:0.84em; color:#c0c0cc; padding:3px 0; border-bottom:1px solid #18181f;'>· {r}</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Equipment")
        for eq in p.get("equipment", []):
            st.markdown(f"<div style='font-size:0.84em; color:#c0c0cc; padding:3px 0; border-bottom:1px solid #18181f;'>· {eq}</div>", unsafe_allow_html=True)

        if p.get("sources_used"):
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### Sources")
            for src in p["sources_used"]:
                score_pct = int(src.get("score", 0) * 100)
                st.markdown(f"""
                <div class='source-card'>
                    <div style='font-family:IBM Plex Mono,monospace; color:#7c6af7; font-size:0.78em;'>{src.get('source_id','')}</div>
                    <div style='color:#c0c0cc; margin-top:2px;'>{src.get('filename','')}</div>
                    <div style='color:#666680; font-size:0.78em;'>{src.get('section','')or'—'} · p.{src.get('page_start','?')} · {score_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Export
    ecol1, ecol2, ecol3 = st.columns([1, 1, 4])
    with ecol1:
        st.download_button(
            "Export JSON",
            data=json.dumps(p, indent=2),
            file_name=f"protocol_{p.get('protocol_id','')[:8]}.json",
            mime="application/json",
        )
    with ecol2:
        # Plain-text export for robot execution handoff
        lines = [f"# {p['title']}", p.get("description", ""), ""]
        for step in p.get("steps", []):
            lines.append(f"[{step['step_number']}] {step['instruction']}")
        st.download_button(
            "Export TXT",
            data="\n".join(lines),
            file_name=f"protocol_{p.get('protocol_id','')[:8]}.txt",
            mime="text/plain",
        )
    with ecol3:
        pid = p.get("protocol_id", "")
        st.markdown(f"<span style='font-family:IBM Plex Mono,monospace; font-size:0.78em; color:#444458;'>ID: {pid}</span>", unsafe_allow_html=True)
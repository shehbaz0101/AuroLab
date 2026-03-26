"""
dashboard/pages/5_health.py — System Health
"""

import time
import streamlit as st
import httpx
import plotly.graph_objects as go

st.set_page_config(page_title="Health — AuroLab", page_icon="⚗", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stSidebar"] { background: #0d0d0f; border-right: 1px solid #1f1f23; }
.main .block-container { padding-top: 2rem; max-width: 1280px; }
h1,h2,h3 { font-family:'IBM Plex Sans',sans-serif; font-weight:600; letter-spacing:-0.02em; }
.health-row { display:flex; align-items:center; gap:12px; padding:10px 14px; background:#0d0d12; border:1px solid #1a1a22; border-radius:6px; margin:5px 0; }
.health-label { font-family:'IBM Plex Mono',monospace; font-size:0.84em; color:#888898; flex:1; }
.health-value { font-family:'IBM Plex Mono',monospace; font-size:0.84em; color:#d0d0dc; }
.dot-green { width:8px;height:8px;background:#22c55e;border-radius:50%;flex-shrink:0; }
.dot-red   { width:8px;height:8px;background:#ef4444;border-radius:50%;flex-shrink:0; }
.dot-amber { width:8px;height:8px;background:#f59e0b;border-radius:50%;flex-shrink:0; }
.section-divider { border:none; border-top:1px solid #1a1a22; margin:24px 0; }
.metric-box { background:#0d0d0f; border:1px solid #1f1f2a; border-radius:8px; padding:16px 20px; text-align:center; }
.metric-value { font-family:'IBM Plex Mono',monospace; font-size:1.8em; font-weight:500; color:#a78bfa; line-height:1.1; }
.metric-label { font-size:0.75em; color:#666680; text-transform:uppercase; letter-spacing:0.1em; margin-top:4px; }
.flag-on  { background:#0a2e1a; color:#22c55e; border:1px solid #166534; padding:2px 10px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.76em; }
.flag-off { background:#1a1a1a; color:#444458; border:1px solid #2a2a2a; padding:2px 10px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.76em; }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8080"
PLOTLY_TEMPLATE = dict(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0a0a0e",
        font=dict(family="IBM Plex Mono, monospace", color="#888898", size=11),
        xaxis=dict(gridcolor="#1a1a22", linecolor="#2a2a38"),
        yaxis=dict(gridcolor="#1a1a22", linecolor="#2a2a38"),
        margin=dict(l=0, r=0, t=28, b=0),
    )
)

# ---------------------------------------------------------------------------

def probe_endpoint(path: str) -> tuple[bool, float, dict | None]:
    t0 = time.perf_counter()
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=5.0)
        latency = (time.perf_counter() - t0) * 1000
        return r.status_code == 200, latency, r.json() if r.status_code == 200 else None
    except Exception:
        return False, -1.0, None

# ---------------------------------------------------------------------------

st.markdown("## System Health")
st.markdown("Live diagnostics for all AuroLab services.")
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

auto_refresh = st.checkbox("Auto-refresh every 10s", value=False)

# Run probes
endpoints = [
    ("/health",           "API health"),
    ("/api/v1/documents/","Document registry"),
]

probe_results = {}
for path, label in endpoints:
    ok, latency, data = probe_endpoint(path)
    probe_results[label] = {"ok": ok, "latency_ms": latency, "data": data}

# Track latency history
if "latency_history" not in st.session_state:
    st.session_state.latency_history = []
api_ok = probe_results["API health"]["ok"]
api_lat = probe_results["API health"]["latency_ms"]
if api_ok:
    history = st.session_state.latency_history
    history.append(api_lat)
    if len(history) > 60:
        history.pop(0)

# ---------------------------------------------------------------------------
# Status overview
# ---------------------------------------------------------------------------

col1, col2 = st.columns([1, 2], gap="large")

with col1:
    st.markdown("#### Service status")

    for label, res in probe_results.items():
        dot = "dot-green" if res["ok"] else "dot-red"
        lat_str = f"{res['latency_ms']:.1f} ms" if res["latency_ms"] >= 0 else "timeout"
        st.markdown(f"""
        <div class='health-row'>
            <div class='{dot}'></div>
            <div class='health-label'>{label}</div>
            <div class='health-value'>{lat_str}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### RAG configuration")

    health_data = probe_results["API health"].get("data") or {}
    rag = health_data.get("rag", {})

    hyde_on = rag.get("hyde_enabled", False)
    rerank_on = rag.get("reranker_enabled", False)
    collection = rag.get("collection", "—")
    embed_model = rag.get("embed_model", "—").split("/")[-1]
    total_chunks = rag.get("total_chunks", 0)

    flags = [
        ("HyDE expansion",    hyde_on),
        ("Cross-encoder rerank", rerank_on),
    ]
    for name, enabled in flags:
        cls = "flag-on" if enabled else "flag-off"
        label = "ON" if enabled else "OFF"
        st.markdown(f"""
        <div class='health-row'>
            <div class='health-label'>{name}</div>
            <span class='{cls}'>{label}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Vector store")
    for k, v in [("Collection", collection), ("Embed model", embed_model), ("Total chunks", f"{total_chunks:,}")]:
        st.markdown(f"""
        <div class='health-row'>
            <div class='health-label'>{k}</div>
            <div class='health-value'>{v}</div>
        </div>
        """, unsafe_allow_html=True)

with col2:
    st.markdown("#### Summary metrics")
    docs_data = probe_results["Document registry"].get("data") or {}
    docs = docs_data.get("documents", [])
    ready_docs = sum(1 for d in docs if d.get("status") == "ready")
    history_len = len(st.session_state.get("protocol_history", []))

    m1, m2, m3, m4 = st.columns(4)
    for col, val, label in [
        (m1, f"{total_chunks:,}", "Chunks"),
        (m2, str(ready_docs),      "Docs ready"),
        (m3, str(history_len),     "Protocols"),
        (m4, f"{api_lat:.0f}ms" if api_ok else "—", "API latency"),
    ]:
        col.markdown(f"""
        <div class='metric-box'>
            <div class='metric-value'>{val}</div>
            <div class='metric-label'>{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### API latency history")

    lat_hist = st.session_state.latency_history
    if len(lat_hist) >= 2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=lat_hist,
            mode="lines",
            line=dict(color="#7c6af7", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(124,106,247,0.08)",
        ))
        fig.update_layout(
            **PLOTLY_TEMPLATE["layout"],
            title=dict(text="Response time (ms)", font=dict(color="#888898", size=11)),
            yaxis=dict(title="", **PLOTLY_TEMPLATE["layout"]["yaxis"]),
            xaxis=dict(title="Recent requests", **PLOTLY_TEMPLATE["layout"]["xaxis"]),
            height=220,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style='text-align:center; padding:32px; color:#444458; font-family:IBM Plex Mono,monospace; font-size:0.8em;'>
        No latency data yet — make some API requests first.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Document type breakdown")

    if docs:
        from collections import Counter
        import plotly.express as px
        type_counts = Counter(d.get("doc_type", "unknown") for d in docs)
        fig3 = go.Figure(go.Bar(
            x=list(type_counts.keys()),
            y=list(type_counts.values()),
            marker_color=["#7c6af7", "#22c55e", "#f59e0b", "#555568"][:len(type_counts)],
            marker_line_color="rgba(0,0,0,0)",
        ))
        fig3.update_layout(
            **PLOTLY_TEMPLATE["layout"],
            height=200,
            showlegend=False,
            title=dict(text="Documents by type", font=dict(color="#888898", size=11)),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.markdown("""
        <div style='text-align:center; padding:24px; color:#444458; font-family:IBM Plex Mono,monospace; font-size:0.8em;'>
        No documents ingested yet.
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------

if auto_refresh:
    time.sleep(10)
    st.rerun()
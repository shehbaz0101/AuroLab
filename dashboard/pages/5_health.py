"""dashboard/pages/5_health.py — System Health"""

import time, sys
from pathlib import Path
from collections import Counter
import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import inject_css, render_nav, hero, api_get, api_post, api_delete, kpi_row, kpi_card, page_header, divider, section_label, badge, stats_strip, neon_card, render_step_card, render_protocol_header, export_buttons, PLOTLY_DARK

st.set_page_config(page_title="Health — AuroLab", page_icon="⚗", layout="wide", initial_sidebar_state="collapsed")
inject_css()
render_nav("health")

def probe(path):
    import httpx
    t0 = time.perf_counter()
    try:
        r = httpx.get(f"http://localhost:8080{path}", timeout=4.0)
        ms = (time.perf_counter()-t0)*1000
        return r.status_code==200, ms, (r.json() if r.status_code==200 else None)
    except:
        return False, -1.0, None

page_header("System Health", "Live diagnostics — service status, RAG configuration, latency history.")

auto = st.checkbox("Auto-refresh every 10s", value=False)
if st.button("⟳ Refresh now"): st.rerun()
divider()

PROBES = [
    ("/health",               "API gateway"),
    ("/api/v1/documents/",    "Document registry"),
    ("/api/v1/fleet/status",  "Fleet orchestrator"),
    ("/api/v1/rl/overview",   "RL service"),
]
results = {}
for path, label in PROBES:
    ok, ms, data = probe(path)
    results[label] = {"ok":ok, "ms":ms, "data":data}

# ── KPIs ───────────────────────────────────────────────────────────────────
api_ms  = results["API gateway"]["ms"]
health_d = results["API gateway"].get("data") or {}
rag = health_d.get("rag",{})
chunks = rag.get("total_chunks",0)
docs_d = (results["Document registry"].get("data") or {})
docs   = docs_d.get("documents",[]) if isinstance(docs_d,dict) else []
protocols_n = len(st.session_state.get("protocol_history",[]))

# Track latency
if "lat_hist" not in st.session_state: st.session_state.lat_hist = []
if results["API gateway"]["ok"]:
    st.session_state.lat_hist.append(api_ms)
    if len(st.session_state.lat_hist) > 80: st.session_state.lat_hist.pop(0)

all_ok = all(r["ok"] for r in results.values())
status_val = "ALL SYSTEMS GO" if all_ok else f"{sum(1 for r in results.values() if r['ok'])}/{len(results)} ONLINE"
status_col = "#4ade80" if all_ok else "#fbbf24"

st.markdown(f"""
<div style="background:#0c0c14;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:1.1rem 1.4rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:16px;">
    <div class="{'dot-green' if all_ok else 'dot-amber'}"></div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.85rem;font-weight:500;color:{status_col};">{status_val}</div>
    <div style="flex:1;"></div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.72rem;color:#444458;">{time.strftime('%H:%M:%S')}</div>
</div>""", unsafe_allow_html=True)

kpi_row([
    (f"{api_ms:.0f}ms" if api_ms>0 else "—", "API latency",         "#00f0c8"),
    (f"{chunks:,}",                            "Chunks indexed",      "#6c4cdc"),
    (len(docs),                                "Documents ready",     "#00b8ff"),
    (protocols_n,                              "Protocols generated", "#ffd33d"),
])

left, right = st.columns([1, 2], gap="large")

with left:
    section_label("Service status")
    for label, res in results.items():
        dot = "dot-green" if res["ok"] else "dot-red"
        ms_str = f"{res['ms']:.1f}ms" if res["ms"]>=0 else "timeout"
        st.markdown(f"""
        <div class="health-row">
            <div class="{dot}"></div>
            <div class="health-label">{label}</div>
            <div class="health-value">{ms_str}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    section_label("RAG configuration")
    flags = [
        ("HyDE expansion",      rag.get("hyde_enabled",False)),
        ("Cross-encoder rerank", rag.get("reranker_enabled",False)),
        ("Hybrid BM25",          rag.get("hybrid_enabled",True)),
    ]
    for name, on in flags:
        cls = "flag-on" if on else "flag-off"
        st.markdown(f"""
        <div class="health-row">
            <div class="health-label">{name}</div>
            <span class="{cls}">{'ON' if on else 'OFF'}</span>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    section_label("Vector store")
    for k, v in [
        ("Collection",   rag.get("collection","—")),
        ("Embed model",  rag.get("embed_model","—").split("/")[-1]),
        ("Total chunks", f"{chunks:,}"),
        ("Sim mode",     health_d.get("sim_mode","—")),
    ]:
        st.markdown(f"""
        <div class="health-row">
            <div class="health-label">{k}</div>
            <div class="health-value">{v}</div>
        </div>""", unsafe_allow_html=True)

with right:
    section_label("API latency history")
    lat = st.session_state.lat_hist
    if len(lat) >= 2:
        avg = sum(lat)/len(lat)
        p95 = sorted(lat)[int(len(lat)*0.95)]
        col_line = "#4ade80" if avg < 200 else ("#fbbf24" if avg < 500 else "#f87171")
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=lat, mode="lines",
            line=dict(color=col_line, width=1.5),
            fill="tozeroy", fillcolor=f"rgba({','.join(str(int(x)) for x in bytes.fromhex(col_line[1:]))},0.07)"))
        fig.add_hline(y=avg, line=dict(color="#7c6af7", width=1, dash="dot"),
            annotation_text=f"avg {avg:.0f}ms", annotation_font_color="#7c6af7")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="JetBrains Mono, monospace", color="rgba(160,185,205,0.5)", size=10), legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="rgba(160,185,205,0.6)", size=10)), margin=dict(l=8, r=8, t=36, b=8), hoverlabel=dict(bgcolor="#0a1018", bordercolor="rgba(0,240,200,0.3)", font=dict(family="JetBrains Mono, monospace", color="#d0e4f0")), height=200, showlegend=False,
            title=dict(text=f"Response time · p95={p95:.0f}ms", font=dict(color="#555568",size=11)))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("<div style='color:#444458;font-size:0.8rem;text-align:center;padding:2rem;'>No latency data — make API requests first</div>", unsafe_allow_html=True)

    if docs:
        section_label("Document types")
        counts = Counter(d.get("doc_type","unknown") for d in docs)
        colors = ["#7c6af7","#4ade80","#60a5fa","#fbbf24","#f87171"]
        fig2 = go.Figure(go.Bar(
            x=list(counts.keys()), y=list(counts.values()),
            marker_color=colors[:len(counts)], marker_line_width=0))
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="JetBrains Mono, monospace", color="rgba(160,185,205,0.5)", size=10), legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="rgba(160,185,205,0.6)", size=10)), margin=dict(l=8, r=8, t=36, b=8), hoverlabel=dict(bgcolor="#0a1018", bordercolor="rgba(0,240,200,0.3)", font=dict(family="JetBrains Mono, monospace", color="#d0e4f0")), height=180, showlegend=False,
            title=dict(text="Docs by type", font=dict(color="#555568",size=11)))
        st.plotly_chart(fig2, use_container_width=True)

    if len(lat) >= 2:
        section_label("Latency distribution")
        fig3 = go.Figure(go.Histogram(x=lat, nbinsx=15,
            marker_color="#7c6af7", marker_line_width=0, opacity=0.8))
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="JetBrains Mono, monospace", color="rgba(160,185,205,0.5)", size=10), legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="rgba(160,185,205,0.6)", size=10)), margin=dict(l=8, r=8, t=36, b=8), hoverlabel=dict(bgcolor="#0a1018", bordercolor="rgba(0,240,200,0.3)", font=dict(family="JetBrains Mono, monospace", color="#d0e4f0")), height=160, showlegend=False,
            title=dict(text="Response time distribution (ms)", font=dict(color="#555568",size=11)))
        st.plotly_chart(fig3, use_container_width=True)

if auto:
    time.sleep(10); st.rerun()
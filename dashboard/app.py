"""dashboard/app.py — AuroLab Home · Futuristic UI"""
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from shared import inject_css, render_nav, hero, api_get, kpi_row, divider, section_label, badge, stats_strip, neon_card, PLOTLY_DARK

st.set_page_config(page_title="AuroLab", page_icon="⚗", layout="wide",
                   initial_sidebar_state="collapsed")
inject_css()
render_nav("app")

hero("AUROLAB",
     "Autonomous physical AI — natural language to validated robotic protocols in under 3 seconds",
     accent="#00f0c8", tag="Autonomous Physical AI · v2.0")

health_data = api_get("/health", silent=True) or {}
rag     = health_data.get("rag", {})
docs_d  = api_get("/api/v1/documents/", silent=True) or {}
history = st.session_state.get("protocol_history", [])

kpi_row([
    (f"{rag.get('total_chunks',0):,}", "Chunks indexed",      "#00f0c8"),
    (str(docs_d.get("total",0)),        "Documents",           "#6c4cdc"),
    (str(len(history)),                  "Protocols generated", "#ffd33d"),
    (rag.get("embed_model","—").split("/")[-1][:14], "Embed model", "#00b8ff"),
    (health_data.get("sim_mode","—"),    "Sim mode",            "#a89ef8"),
])
divider()

# Feature cards with neon accent bars
section_label("Capabilities")
cols = st.columns(3, gap="large")
features = [
    ("⚗",  "RAG + LLM Generation",
     "ChromaDB · BM25 · HyDE · cross-encoder reranking · Groq Llama 3.3-70B with [SOURCE_N] citation injection",
     "linear-gradient(90deg,#6c4cdc,#00f0c8)"),
    ("🔬", "Physics Simulation",
     "PyBullet CPU · OT-2 deck geometry · 12 slots · collision detection · mock / pybullet / live modes",
     "linear-gradient(90deg,#00f0c8,#00b8ff)"),
    ("🧠", "RL Optimisation",
     "Q-learning agent · SQLite telemetry · reward = speed×0.30 + accuracy×0.35 + waste×0.20 + safety×0.15",
     "linear-gradient(90deg,#f87171,#ffd33d)"),
    ("🤖", "Fleet Orchestration",
     "EDF scheduler · resource conflict detection and resolution · Gantt timeline · multi-robot parallelism",
     "linear-gradient(90deg,#00b8ff,#6c4cdc)"),
    ("👁", "Vision Layer",
     "Lab state detection · mock / Groq LLaVA / NVIDIA Cosmos backends · live deck layout inspection",
     "linear-gradient(90deg,#ffd33d,#f87171)"),
    ("📡", "Digital Twin",
     "Three.js 3D OT-2 · liquid particle FX · centrifuge spin · incubate glow · plate reader scan beam",
     "linear-gradient(90deg,#00f0c8,#6c4cdc)"),
]
for i, (icon, title, desc, grad) in enumerate(features):
    with cols[i % 3]:
        st.markdown(f"""
        <div style="
            background:rgba(0,240,200,0.015);
            border:1px solid rgba(0,240,200,0.08);
            border-radius:12px;padding:1.4rem 1.5rem;
            margin-bottom:12px;min-height:158px;
            position:relative;overflow:hidden;
            transition:border-color 0.2s;
        ">
            <div style="position:absolute;top:0;left:8px;right:8px;height:2px;background:{grad};border-radius:0 0 2px 2px;opacity:0.8;"></div>
            <div style="position:absolute;top:8px;left:8px;width:8px;height:8px;border-top:1px solid rgba(0,240,200,0.3);border-left:1px solid rgba(0,240,200,0.3);"></div>
            <div style="position:absolute;top:8px;right:8px;width:8px;height:8px;border-top:1px solid rgba(0,240,200,0.3);border-right:1px solid rgba(0,240,200,0.3);"></div>
            <div style="position:absolute;bottom:8px;left:8px;width:8px;height:8px;border-bottom:1px solid rgba(0,240,200,0.3);border-left:1px solid rgba(0,240,200,0.3);"></div>
            <div style="position:absolute;bottom:8px;right:8px;width:8px;height:8px;border-bottom:1px solid rgba(0,240,200,0.3);border-right:1px solid rgba(0,240,200,0.3);"></div>
            <div style="font-size:1.5rem;margin-bottom:0.65rem;margin-top:0.2rem;">{icon}</div>
            <div style="font-family:'Orbitron',monospace;font-size:0.72rem;font-weight:600;color:#e8f4ff;letter-spacing:0.06em;margin-bottom:7px;text-transform:uppercase;">{title}</div>
            <div style="font-size:0.75rem;color:rgba(160,185,205,0.45);line-height:1.65;">{desc}</div>
        </div>""", unsafe_allow_html=True)

divider()
stats_strip([
    ("Phases", "7/7"), ("Tests", "243"), ("Endpoints", "28"),
    ("Dashboard", "10 pages"), ("Latency", "<3s"),
    ("Model", "Llama-3.3-70B"), ("Physics", "PyBullet"), ("Version", "2.0.0"),
])

if history:
    divider()
    section_label("Recent protocols")
    for p in history[:5]:
        safety = p.get("safety_level","safe")
        conf   = p.get("confidence_score",0)
        steps  = len(p.get("steps",[]))
        glow   = "#00f0c8" if conf > 0.8 else "#ffd33d"
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:14px;padding:10px 14px;
            background:rgba(0,240,200,0.015);border:1px solid rgba(0,240,200,0.07);
            border-radius:8px;margin:5px 0;transition:background 0.15s;">
            <div style="width:3px;height:36px;background:linear-gradient(180deg,#00f0c8,transparent);border-radius:2px;flex-shrink:0;"></div>
            <div style="flex:1;">
                <div style="font-family:'Orbitron',monospace;font-size:0.78rem;font-weight:600;color:#e8f4ff;margin-bottom:3px;letter-spacing:0.03em;">{p.get('title','Untitled')}</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.62rem;color:rgba(160,185,205,0.35);">{steps} steps · {conf:.0%} confidence</div>
            </div>
            <div style="font-family:'Orbitron',monospace;font-size:0.85rem;font-weight:700;color:{glow};text-shadow:0 0 10px {glow};">{conf:.0%}</div>
            {badge(safety.upper(), safety)}
        </div>""", unsafe_allow_html=True)
"""dashboard/pages/9_rl_optimiser.py — RL Protocol Optimiser"""

import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import inject_css, render_nav, hero, api_get, api_post, api_delete, kpi_row, kpi_card, page_header, divider, section_label, badge, stats_strip, neon_card, render_step_card, render_protocol_header, export_buttons, PLOTLY_DARK

st.set_page_config(page_title="RL Optimiser — AuroLab", page_icon="⚗", layout="wide", initial_sidebar_state="collapsed")
inject_css()
render_nav("rl_optimizer")

page_header("RL Protocol Optimiser",
    "Q-learning agent learns from execution history to suggest protocol parameter improvements")
divider()

history = st.session_state.get("protocol_history",[])
if not history:
    st.info("Generate and execute protocols first, then return here.")
    st.stop()

opts = {f"{p.get('title','?')} — {p.get('protocol_id','')[:8]}": p.get("protocol_id","") for p in history}
ca, cb, cc = st.columns([3,1,1])
with ca:
    sel_label = st.selectbox("Protocol", list(opts.keys()), label_visibility="collapsed")
    pid = opts[sel_label]
with cb:
    if st.button("⟳ Refresh", use_container_width=True): st.rerun()
with cc:
    if st.button("⚡ Generate suggestions", type="primary", use_container_width=True):
        with st.spinner("Analysing execution history..."):
            res = api_post(f"/api/v1/rl/optimise/{pid}")
        if res:
            st.success(f"{res.get('count',0)} suggestions generated")
            st.rerun()

divider()

stats = api_get(f"/api/v1/rl/stats/{pid}", silent=True) or {}
trend = (api_get(f"/api/v1/rl/trend/{pid}", silent=True) or {}).get("trend",[])
suggs = (api_get(f"/api/v1/rl/suggestions/{pid}", silent=True) or {}).get("suggestions",[])

# ── KPIs ───────────────────────────────────────────────────────────────────
runs    = stats.get("total_runs",0)
avg_r   = stats.get("avg_reward",0)
best_r  = stats.get("best_reward",0)
pass_r  = stats.get("pass_rate",0)
q_states= stats.get("q_states",0)
pending = sum(1 for s in suggs if s.get("status","pending")=="pending")

kpi_row([
    (runs, 'Execution runs', '#7c6af7'),
    (f"{avg_r:.3f}", 'Avg reward', '#4ade80" if avg_r>0.7 else "#fbbf24'),
    (f"{best_r:.3f}", 'Best reward', '#4ade80'),
    (f"{pass_r:.0%}", 'Pass rate', '#4ade80" if pass_r>0.8 else "#fbbf24'),
    (q_states, 'Q-states', '#60a5fa'),
    (pending, 'Pending suggestions', '#a89ef8'),
])

left, right = st.columns([3, 2], gap="large")

with left:
    section_label("Reward trend")
    if trend:
        rewards = [r["reward"] for r in trend]
        passed  = [r.get("passed",True) for r in trend]
        x = list(range(1, len(rewards)+1))
        window = min(5, max(2, len(rewards)//4))
        ma = [sum(rewards[max(0,i-window):i+1])/min(i+1,window) for i in range(len(rewards))]

        fig = go.Figure()
        # Background fill
        fig.add_trace(go.Scatter(x=x, y=rewards, mode="none",
            fill="tozeroy", fillcolor="rgba(124,106,247,0.05)", showlegend=False))
        # Reward line
        fig.add_trace(go.Scatter(x=x, y=rewards, mode="lines+markers",
            line=dict(color="#7c6af7", width=1.5),
            marker=dict(color=["#4ade80" if p else "#f87171" for p in passed],
                size=7, line=dict(color="#070709",width=1.5)),
            name="Reward",
            hovertemplate="Run %{x}<br>Reward: %{y:.4f}<extra></extra>"))
        # Moving average
        fig.add_trace(go.Scatter(x=x, y=ma, mode="lines",
            line=dict(color="#fbbf24", width=1.5, dash="dot"),
            name=f"{window}-run avg"))
        # Target line
        fig.add_hline(y=0.85, line=dict(color="#4ade80", width=1, dash="dash"),
            annotation_text="target 0.85", annotation_font_color="#4ade80")

        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="JetBrains Mono, monospace", color="rgba(160,185,205,0.5)", size=10), legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="rgba(160,185,205,0.6)", size=10)), margin=dict(l=8, r=8, t=36, b=8), hoverlabel=dict(bgcolor="#0a1018", bordercolor="rgba(0,240,200,0.3)", font=dict(family="JetBrains Mono, monospace", color="#d0e4f0")), height=300,
            yaxis=dict(gridcolor="rgba(0,240,200,0.06)", linecolor="rgba(0,240,200,0.08)", tickfont=dict(color="rgba(160,185,205,0.4)"), range=[0,1.05], title="Reward"),
            xaxis=dict(gridcolor="rgba(0,240,200,0.06)", linecolor="rgba(0,240,200,0.08)", tickfont=dict(color="rgba(160,185,205,0.4)"), title="Run"),
            title=dict(text="Reward per execution", font=dict(color="#555568",size=11)))
        st.plotly_chart(fig, use_container_width=True)

        # Reward components breakdown (if available)
        if trend and "speed" in trend[-1]:
            section_label("Reward components (latest run)")
            last = trend[-1]
            comps = {"Speed":last.get("speed",0),"Accuracy":last.get("accuracy",0),
                     "Waste":last.get("waste",0),"Safety":last.get("safety",0)}
            comp_colors = {"Speed":"#60a5fa","Accuracy":"#4ade80","Waste":"#fbbf24","Safety":"#f87171"}
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=list(comps.keys()), y=list(comps.values()),
                marker_color=[comp_colors[k] for k in comps], marker_line_width=0))
            fig2.add_hline(y=1.0, line=dict(color="rgba(255,255,255,0.1)",width=1))
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="JetBrains Mono, monospace", color="rgba(160,185,205,0.5)", size=10), legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="rgba(160,185,205,0.6)", size=10)), margin=dict(l=8, r=8, t=36, b=8), hoverlabel=dict(bgcolor="#0a1018", bordercolor="rgba(0,240,200,0.3)", font=dict(family="JetBrains Mono, monospace", color="#d0e4f0")), height=180, showlegend=False,
                yaxis=dict(gridcolor="rgba(0,240,200,0.06)", linecolor="rgba(0,240,200,0.08)", tickfont=dict(color="rgba(160,185,205,0.4)"), range=[0,1.1]),
                title=dict(text="Component scores (weights: speed×0.30, acc×0.35, waste×0.20, safety×0.15)", font=dict(color="#555568",size=10)))
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#444458;">
            <div style="font-size:2rem;margin-bottom:0.8rem;">📈</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;">No execution data yet</div>
            <div style="font-size:0.75rem;margin-top:4px;">Generate + Simulate protocols to populate the reward trend</div>
        </div>""", unsafe_allow_html=True)

with right:
    section_label("Q-agent state")
    if stats:
        health_cell = api_get("/health", silent=True) or {}
        sim_m = health_cell.get("sim_mode","mock")
        st.markdown(f"""
        <div style="background:#0c0c14;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:1rem 1.2rem;margin-bottom:1rem;">
            <div class="section-label" style="margin-bottom:8px;">Isaac Sim status</div>
            <div class="health-row">
                <div class="health-label">Sim mode</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.8rem;color:#a89ef8;">{sim_m}</div>
            </div>
            <div class="health-row">
                <div class="health-label">Epsilon (ε)</div>
                <div class="health-value">{stats.get('epsilon',0.1):.3f}</div>
            </div>
            <div class="health-row">
                <div class="health-label">Q-states explored</div>
                <div class="health-value">{q_states:,}</div>
            </div>
            <div class="health-row">
                <div class="health-label">Convergence</div>
                <div class="health-value">{stats.get('convergence_pct',0):.0f}%</div>
            </div>
        </div>""", unsafe_allow_html=True)

    section_label(f"Parameter suggestions ({len(suggs)})")
    if not suggs:
        st.markdown("<div style='color:#444458;font-size:0.82rem;'>No suggestions yet — click Generate suggestions above.</div>", unsafe_allow_html=True)
    else:
        for sug in suggs:
            sid    = sug.get("suggestion_id","")[:8]
            status = sug.get("status","pending")
            param  = sug.get("parameter","?")
            curr   = sug.get("current_value","?")
            sugg_v = sug.get("suggested_value","?")
            delta  = sug.get("expected_reward_delta",0)
            ratio  = sug.get("rationale","")
            delta_col = "#4ade80" if delta>0 else "#f87171"

            st.markdown(f"""
            <div class="sug-card">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                    <div class="sug-param">{param}</div>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-family:'JetBrains Mono',monospace;font-size:0.72rem;color:{delta_col};">+Δ{delta:+.3f}</span>
                        <span class="badge badge-{status}">{status}</span>
                    </div>
                </div>
                <div class="sug-vals">{curr} → <span style="color:#a89ef8;">{sugg_v}</span></div>
                <div class="sug-rationale">{ratio}</div>
            </div>""", unsafe_allow_html=True)

            if status == "pending":
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("✓ Accept", key=f"acc_{sid}", use_container_width=True):
                        api_post(f"/api/v1/rl/suggestions/{sug.get('suggestion_id','')}/accept", silent=True)
                        st.rerun()
                with bc2:
                    if st.button("✗ Reject", key=f"rej_{sid}", use_container_width=True):
                        api_post(f"/api/v1/rl/suggestions/{sug.get('suggestion_id','')}/reject", silent=True)
                        st.rerun()
"""
dashboard/pages/9_rl_optimiser.py — RL Protocol Optimiser
"""

import streamlit as st
import httpx
import plotly.graph_objects as go

st.set_page_config(page_title="RL Optimiser — AuroLab", page_icon="⚗", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stSidebar"] { background: #0d0d0f; border-right: 1px solid #1f1f23; }
.main .block-container { padding-top: 2rem; max-width: 1280px; }
h1,h2,h3 { font-family:'IBM Plex Sans',sans-serif; font-weight:600; letter-spacing:-0.02em; }
.section-divider { border:none; border-top:1px solid #1a1a22; margin:24px 0; }
.metric-box { background:#0d0d0f; border:1px solid #1f1f2a; border-radius:8px; padding:14px 18px; text-align:center; }
.metric-value { font-family:'IBM Plex Mono',monospace; font-size:1.8em; font-weight:500; color:#a78bfa; line-height:1.1; }
.metric-label { font-size:0.72em; color:#666680; text-transform:uppercase; letter-spacing:0.1em; margin-top:4px; }
.suggestion-card { background:#0d0d12; border:1px solid #1a1a22; border-left:3px solid #7c6af7; border-radius:6px; padding:12px 16px; margin:6px 0; }
.suggestion-param { font-family:'IBM Plex Mono',monospace; color:#7c6af7; font-size:0.82em; font-weight:500; }
.suggestion-values { font-family:'IBM Plex Mono',monospace; font-size:0.78em; color:#888898; margin-top:3px; }
.suggestion-rationale { font-size:0.84em; color:#c0c0cc; margin-top:6px; line-height:1.6; }
.reward-delta-positive { color:#22c55e; font-family:'IBM Plex Mono',monospace; font-size:0.78em; }
.badge-pending  { background:#1a1a2e; color:#a78bfa; border:1px solid #534AB7; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.badge-accepted { background:#0a2e1a; color:#22c55e; border:1px solid #166534; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.badge-rejected { background:#2e0a0a; color:#ef4444; border:1px solid #991b1b; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8080"

def api_get(path):
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def api_post(path, **kwargs):
    try:
        r = httpx.post(f"{API_BASE}{path}", timeout=15.0, **kwargs)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(str(e))
        return None

PLOTLY_DARK = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a0a0e",
    font=dict(family="IBM Plex Mono, monospace", color="#888898", size=11),
    xaxis=dict(gridcolor="#1a1a22"), yaxis=dict(gridcolor="#1a1a22"),
    margin=dict(l=0, r=0, t=28, b=0),
)

# ---------------------------------------------------------------------------
st.markdown("## RL Protocol Optimiser")
st.markdown("Analyses execution history to suggest protocol parameter improvements. More runs = smarter suggestions.")
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

history = st.session_state.get("protocol_history", [])
if not history:
    st.info("No protocols generated yet. Generate and execute some protocols first, then return here.")
    st.stop()

# Protocol selector
options = {f"{p.get('title','Untitled')} — {p.get('protocol_id','')[:8]}": p.get("protocol_id","")
           for p in history}
selected_label = st.selectbox("Select protocol", list(options.keys()), label_visibility="collapsed")
pid = options[selected_label]

col_run, col_opt = st.columns([1, 1])
with col_run:
    if st.button("Refresh stats", use_container_width=True):
        st.rerun()
with col_opt:
    if st.button("Generate suggestions", type="primary", use_container_width=True):
        with st.spinner("Analysing execution history..."):
            result = api_post(f"/api/v1/rl/optimise/{pid}")
        if result:
            st.success(f"{result.get('count', 0)} suggestions generated")
            st.rerun()

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

stats_data = api_get(f"/api/v1/rl/stats/{pid}")
trend_data = api_get(f"/api/v1/rl/trend/{pid}")
suggestions_data = api_get(f"/api/v1/rl/suggestions/{pid}")

left_col, right_col = st.columns([3, 2], gap="large")

with left_col:
    st.markdown("#### Reward trend")

    trend = (trend_data or {}).get("trend", [])
    if trend:
        rewards = [r["reward"] for r in trend]
        passed  = [r["passed"] for r in trend]
        x       = list(range(1, len(rewards) + 1))

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x, y=rewards,
            mode="lines+markers",
            line=dict(color="#7c6af7", width=2),
            marker=dict(
                color=["#22c55e" if p else "#ef4444" for p in passed],
                size=8,
                line=dict(color="#0a0a0e", width=1.5),
            ),
            name="Reward",
            hovertemplate="Run %{x}<br>Reward: %{y:.4f}<extra></extra>",
        ))
        # Moving average
        if len(rewards) >= 3:
            window = 3
            ma = [sum(rewards[max(0,i-window):i+1]) / min(i+1, window) for i in range(len(rewards))]
            fig.add_trace(go.Scatter(
                x=x, y=ma,
                mode="lines",
                line=dict(color="#f59e0b", width=1, dash="dash"),
                name="3-run avg",
            ))
        fig.update_layout(
            **PLOTLY_DARK,
            title=dict(text="Reward per execution run", font=dict(color="#888898", size=12)),
            yaxis=dict(range=[0, 1.05], title="Reward", **PLOTLY_DARK["yaxis"]),
            xaxis=dict(title="Run number", **PLOTLY_DARK["xaxis"]),
            height=280,
            legend=dict(font=dict(size=10)),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style='text-align:center; padding:48px; color:#444458; font-family:IBM Plex Mono,monospace; font-size:0.82em;'>
        No execution runs recorded yet.<br>Execute a protocol to start collecting telemetry.
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("#### Parameter suggestions")

    suggestions = (suggestions_data or {}).get("suggestions", [])
    if not suggestions:
        st.markdown("<span style='font-size:0.84em; color:#555568;'>No pending suggestions — click Generate suggestions above.</span>", unsafe_allow_html=True)
    else:
        for s in suggestions:
            badge_cls = f"badge-{s.get('status','pending')}"
            delta = s.get("expected_reward_delta", 0)
            delta_str = f"+{delta:.3f}" if delta > 0 else f"{delta:.3f}"
            st.markdown(f"""
            <div class='suggestion-card'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span class='suggestion-param'>{s.get('parameter','')}</span>
                    <span class='{badge_cls}'>{s.get('status','pending').upper()}</span>
                </div>
                <div class='suggestion-values'>
                    {s.get('current_value',0):.1f} → {s.get('suggested_value',0):.1f}
                    &nbsp;·&nbsp; <span class='reward-delta-positive'>{delta_str} reward</span>
                </div>
                <div class='suggestion-rationale'>{s.get('rationale','')}</div>
            </div>
            """, unsafe_allow_html=True)

            sid = s.get("suggestion_id", "")
            bcol1, bcol2 = st.columns(2)
            with bcol1:
                if st.button("Accept", key=f"accept_{sid}", use_container_width=True):
                    api_post(f"/api/v1/rl/suggestions/{sid}/accept")
                    st.rerun()
            with bcol2:
                if st.button("Reject", key=f"reject_{sid}", use_container_width=True):
                    api_post(f"/api/v1/rl/suggestions/{sid}/reject")
                    st.rerun()

with right_col:
    st.markdown("#### Execution stats")
    if stats_data:
        exec_stats = stats_data.get("execution_stats", {})
        agent_info = stats_data.get("rl_agent", {})

        total     = exec_stats.get("total_runs", 0)
        success   = exec_stats.get("success_rate", 0)
        avg_rew   = exec_stats.get("avg_reward", 0) or 0
        best_rew  = exec_stats.get("best_reward", 0) or 0
        episodes  = agent_info.get("episodes", 0)
        states    = agent_info.get("states_visited", 0)
        epsilon   = agent_info.get("epsilon", 0.3)

        m1, m2 = st.columns(2)
        m1.markdown(f'<div class="metric-box"><div class="metric-value">{total}</div><div class="metric-label">Total runs</div></div>', unsafe_allow_html=True)
        m2.markdown(f'<div class="metric-box"><div class="metric-value" style="color:#22c55e">{success:.0%}</div><div class="metric-label">Success rate</div></div>', unsafe_allow_html=True)
        m3, m4 = st.columns(2)
        m3.markdown(f'<div class="metric-box"><div class="metric-value">{avg_rew:.3f}</div><div class="metric-label">Avg reward</div></div>', unsafe_allow_html=True)
        m4.markdown(f'<div class="metric-box"><div class="metric-value" style="color:#f59e0b">{best_rew:.3f}</div><div class="metric-label">Best reward</div></div>', unsafe_allow_html=True)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("#### Q-agent state")

        agent_items = [
            ("Episodes", str(episodes), "#a78bfa"),
            ("States explored", str(states), "#a78bfa"),
            ("Exploration ε", f"{epsilon:.3f}", "#f59e0b"),
        ]
        for label, value, color in agent_items:
            st.markdown(f"""
            <div style='display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #13131a; font-size:0.84em;'>
                <span style='color:#888898;'>{label}</span>
                <span style='font-family:IBM Plex Mono,monospace; color:{color};'>{value}</span>
            </div>
            """, unsafe_allow_html=True)

        # Epsilon gauge
        if total > 0:
            st.markdown("<br>", unsafe_allow_html=True)
            fig2 = go.Figure(go.Indicator(
                mode="gauge+number",
                value=epsilon,
                title=dict(text="Exploration rate (ε)", font=dict(color="#888898", size=11)),
                number=dict(font=dict(color="#a78bfa", size=24), suffix=""),
                gauge=dict(
                    axis=dict(range=[0, 0.3], tickcolor="#555568"),
                    bar=dict(color="#7c6af7"),
                    bgcolor="#111118",
                    bordercolor="#1a1a22",
                    steps=[
                        dict(range=[0, 0.1], color="#0a2e1a"),
                        dict(range=[0.1, 0.2], color="#1a1a0a"),
                        dict(range=[0.2, 0.3], color="#1a0a0a"),
                    ],
                ),
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="IBM Plex Mono", color="#888898"),
                height=200,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("#### Isaac Sim status")

        # Read sim mode from backend health endpoint
        health = api_get("/health") or {}
        sim_mode = health.get("sim_mode", "mock")
        st.markdown(f"""
        <div style='font-size:0.84em; color:#888898; line-height:1.9;'>
        <b style='color:#a78bfa;'>Sim mode:</b>
        <span style='font-family:IBM Plex Mono,monospace;'>AUROLAB_SIM_MODE={sim_mode}</span><br>
        <b style='color:#a78bfa;'>Extension:</b> isaac_extension/aurolab_isaac_extension.py<br>
        <b style='color:#a78bfa;'>Port:</b> tcp://localhost:5555<br><br>
        See <code>isaac_extension/SETUP.md</code> to activate live mode.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<span style='color:#555568;'>Select a protocol and refresh stats.</span>", unsafe_allow_html=True)
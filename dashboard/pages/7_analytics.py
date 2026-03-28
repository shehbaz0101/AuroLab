"""
dashboard/pages/7_analytics.py — Analytics & Sustainability
"""

import streamlit as st
import httpx
import plotly.graph_objects as go

st.set_page_config(page_title="Analytics — AuroLab", page_icon="⚗", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stSidebar"] { background: #0d0d0f; border-right: 1px solid #1f1f23; }
.main .block-container { padding-top: 2rem; max-width: 1280px; }
h1,h2,h3 { font-family:'IBM Plex Sans',sans-serif; font-weight:600; letter-spacing:-0.02em; }
.section-divider { border:none; border-top:1px solid #1a1a22; margin:24px 0; }
.metric-box { background:#0d0d0f; border:1px solid #1f1f2a; border-radius:8px; padding:16px 20px; text-align:center; }
.metric-value { font-family:'IBM Plex Mono',monospace; font-size:1.8em; font-weight:500; color:#a78bfa; line-height:1.1; }
.metric-value-green { font-family:'IBM Plex Mono',monospace; font-size:1.8em; font-weight:500; color:#22c55e; line-height:1.1; }
.metric-value-amber { font-family:'IBM Plex Mono',monospace; font-size:1.8em; font-weight:500; color:#f59e0b; line-height:1.1; }
.metric-label { font-size:0.72em; color:#666680; text-transform:uppercase; letter-spacing:0.1em; margin-top:4px; }
.rating-A { background:#0a2e1a; color:#22c55e; border:1px solid #166534; padding:3px 12px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-weight:500; }
.rating-B { background:#0a2416; color:#4ade80; border:1px solid #166534; padding:3px 12px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-weight:500; }
.rating-C { background:#2e2a0a; color:#facc15; border:1px solid #854d0e; padding:3px 12px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-weight:500; }
.rating-D { background:#2e1508; color:#fb923c; border:1px solid #9a3412; padding:3px 12px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-weight:500; }
.rating-F { background:#2e0a0a; color:#ef4444; border:1px solid #991b1b; padding:3px 12px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-weight:500; }
.line-row { display:flex; align-items:center; padding:7px 14px; border-bottom:1px solid #13131a; font-size:0.84em; }
.line-category { font-family:'IBM Plex Mono',monospace; font-size:0.72em; color:#555568; width:120px; flex-shrink:0; }
.line-desc { color:#c0c0cc; flex:1; }
.line-cost { font-family:'IBM Plex Mono',monospace; color:#a78bfa; min-width:80px; text-align:right; }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8080"
PLOTLY_DARK = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a0a0e",
    font=dict(family="IBM Plex Mono, monospace", color="#888898", size=11),
    xaxis=dict(gridcolor="#1a1a22", linecolor="#2a2a38"),
    yaxis=dict(gridcolor="#1a1a22", linecolor="#2a2a38"),
    margin=dict(l=0, r=0, t=28, b=0),
)

def api_get(path):
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def api_post(path, **kwargs):
    try:
        r = httpx.post(f"{API_BASE}{path}", timeout=15.0, **kwargs)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def rating_badge(r: str) -> str:
    return f"<span class='rating-{r}'>{r}</span>"

# ---------------------------------------------------------------------------
st.markdown("## Analytics & Sustainability")
st.markdown("Cost breakdown, environmental impact, and ROI vs manual execution for every generated protocol.")
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# Protocol selector
history = st.session_state.get("protocol_history", [])
if not history:
    st.info("No protocols generated yet. Head to Generate to create your first protocol, then come back here.")
    st.stop()

protocol_options = {f"{p.get('title','Untitled')} — {p.get('protocol_id','')[:8]}": p
                   for p in history}
selected_label = st.selectbox("Select protocol", list(protocol_options.keys()),
                               label_visibility="collapsed")
protocol = protocol_options[selected_label]
pid = protocol.get("protocol_id", "")

# Fetch analytics
if st.button("Compute analytics", use_container_width=False) or f"analytics_{pid}" in st.session_state:
    if f"analytics_{pid}" not in st.session_state:
        with st.spinner("Computing analytics..."):
            data = api_get(f"/api/v1/analytics/{pid}")
        if data:
            st.session_state[f"analytics_{pid}"] = data
    data = st.session_state.get(f"analytics_{pid}")
else:
    data = None

if not data:
    st.markdown("""
    <div style='text-align:center; padding:48px; color:#444458;'>
        <div style='font-size:1.5em; margin-bottom:8px;'>Select a protocol and click Compute analytics</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------------------
# Summary metrics row
# ---------------------------------------------------------------------------

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

m1, m2, m3, m4, m5 = st.columns(5)
cost_saved  = data.get("cost_saved_usd", 0)
time_saved  = data.get("time_saved_min", 0)
robot_cost  = data.get("robot_cost_usd", 0)
plastic_g   = data.get("plastic_g", 0)
co2_g       = data.get("co2_g", 0)
p_rating    = data.get("plastic_rating", "?")
e_rating    = data.get("energy_rating", "?")

m1.markdown(f'<div class="metric-box"><div class="metric-value-green">${cost_saved:.2f}</div><div class="metric-label">Cost saved vs manual</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="metric-box"><div class="metric-value-green">{time_saved:.0f}m</div><div class="metric-label">Time saved</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="metric-box"><div class="metric-value">${robot_cost:.4f}</div><div class="metric-label">Robot execution cost</div></div>', unsafe_allow_html=True)
m4.markdown(f'<div class="metric-box"><div class="metric-value-amber">{plastic_g:.1f}g</div><div class="metric-label">Plastic waste</div></div>', unsafe_allow_html=True)
m5.markdown(f'<div class="metric-box"><div class="metric-value-amber">{co2_g:.1f}g</div><div class="metric-label">CO₂ equivalent</div></div>', unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

left_col, right_col = st.columns([3, 2], gap="large")

with left_col:
    st.markdown("#### Cost breakdown")

    line_items = data.get("line_items", [])
    if line_items:
        rows_html = "".join(
            f"<div class='line-row'>"
            f"<div class='line-category'>{item['category']}</div>"
            f"<div class='line-desc'>{item['description']}</div>"
            f"<div class='line-cost'>${item['total_usd']:.4f}</div>"
            f"</div>"
            for item in line_items
        )
        total_html = (
            f"<div class='line-row' style='border-top:1px solid #2a2a38; margin-top:4px;'>"
            f"<div class='line-category'></div>"
            f"<div class='line-desc' style='font-weight:500; color:#d0d0dc;'>Total</div>"
            f"<div class='line-cost' style='color:#d0d0dc; font-weight:500;'>${robot_cost:.4f}</div>"
            f"</div>"
        )
        st.markdown(rows_html + total_html, unsafe_allow_html=True)

    # Cost breakdown donut chart
    if line_items:
        st.markdown("<br>", unsafe_allow_html=True)
        labels = [i["category"] for i in line_items]
        values = [i["total_usd"] for i in line_items]
        colors = ["#7c6af7", "#22c55e", "#f59e0b", "#60a5fa", "#f87171"][:len(labels)]

        fig = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.55,
            marker=dict(colors=colors, line=dict(color="#0a0a0e", width=2)),
            textfont=dict(size=10, color="#888898"),
            showlegend=True,
        ))
        fig.update_layout(**PLOTLY_DARK, height=240,
                          legend=dict(font=dict(size=10), orientation="h", y=-0.15))
        st.plotly_chart(fig, use_container_width=True)

with right_col:
    st.markdown("#### Sustainability ratings")
    st.markdown(f"""
    <div style='display:flex; gap:16px; margin-bottom:16px;'>
        <div>
            <div style='font-size:0.72em; color:#666680; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.08em;'>Plastic</div>
            {rating_badge(p_rating)}
        </div>
        <div>
            <div style='font-size:0.72em; color:#666680; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.08em;'>Energy</div>
            {rating_badge(e_rating)}
        </div>
    </div>
    """, unsafe_allow_html=True)

    sustain_items = [
        ("Tip plastic",    f"{data.get('tip_plastic_g', plastic_g):.2f} g",  "#f59e0b"),
        ("Total plastic",  f"{plastic_g:.2f} g",                              "#fb923c"),
        ("Energy",         f"{data.get('energy_kwh', 0)*1000:.2f} Wh",       "#60a5fa"),
        ("CO₂",            f"{co2_g:.2f} g",                                  "#f87171"),
    ]
    for label, value, color in sustain_items:
        st.markdown(f"""
        <div style='display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #13131a; font-size:0.84em;'>
            <span style='color:#888898;'>{label}</span>
            <span style='font-family:IBM Plex Mono,monospace; color:{color};'>{value}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### ROI vs manual")

    robot_dur   = data.get("robot_duration_min", 0)
    manual_dur  = data.get("manual_duration_min", 0)
    manual_cost = data.get("manual_cost_usd", 0)
    annual      = data.get("annual_savings_usd_250runs", 0)

    comparison_items = [
        ("Robot time",    f"{robot_dur:.1f} min",  "#7c6af7"),
        ("Manual time",   f"{manual_dur:.1f} min", "#555568"),
        ("Robot cost",    f"${robot_cost:.4f}",    "#7c6af7"),
        ("Manual cost",   f"${manual_cost:.4f}",   "#555568"),
        ("Annual saving", f"${annual:,.0f}",        "#22c55e"),
    ]
    for label, value, color in comparison_items:
        st.markdown(f"""
        <div style='display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #13131a; font-size:0.84em;'>
            <span style='color:#888898;'>{label}</span>
            <span style='font-family:IBM Plex Mono,monospace; color:{color};'>{value}</span>
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Fleet aggregate
# ---------------------------------------------------------------------------

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown("#### Session aggregate")

agg = api_get("/api/v1/analytics/")
if agg and agg.get("total_protocols", 0) > 0:
    a1, a2, a3, a4 = st.columns(4)
    a1.markdown(f'<div class="metric-box"><div class="metric-value">{agg["total_protocols"]}</div><div class="metric-label">Protocols</div></div>', unsafe_allow_html=True)
    a2.markdown(f'<div class="metric-box"><div class="metric-value-green">${agg["total_cost_saved_usd"]:.2f}</div><div class="metric-label">Total cost saved</div></div>', unsafe_allow_html=True)
    a3.markdown(f'<div class="metric-box"><div class="metric-value-amber">{agg["total_plastic_g"]:.1f}g</div><div class="metric-label">Total plastic</div></div>', unsafe_allow_html=True)
    a4.markdown(f'<div class="metric-box"><div class="metric-value-green">${agg["annual_savings_usd"]:,.0f}</div><div class="metric-label">Annual saving (250 runs)</div></div>', unsafe_allow_html=True)
else:
    st.markdown("<span style='font-size:0.84em; color:#555568;'>Compute analytics for multiple protocols to see aggregate metrics.</span>", unsafe_allow_html=True)
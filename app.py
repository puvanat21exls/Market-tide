import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv
from fredapi import Fred
import os

# --- Configuration & Caching ---
load_dotenv()
# Local: .env file. Streamlit Community Cloud: app secrets.
FRED_API_KEY = os.getenv("FRED_API_KEY")
if not FRED_API_KEY:
    try:
        FRED_API_KEY = st.secrets["FRED_API_KEY"]
    except Exception:
        FRED_API_KEY = None

# One color per lever, used everywhere
C_FED, C_TGA, C_RRP, C_NET = "#2ca02c", "#d62728", "#ff7f0e", "#1f77b4"
C_SPY, C_RATE = "#7fd17f", "#b07cd8"

@st.cache_data(ttl=3600)
def get_data(start_date):
    fred = Fred(api_key=FRED_API_KEY)

    # Fetch FRED series
    s_walcl = fred.get_series('WALCL', observation_start=start_date) / 1000
    s_wtregen = fred.get_series('WTREGEN', observation_start=start_date) / 1000
    s_rrp = fred.get_series('RRPONTSYD', observation_start=start_date)
    s_dff = fred.get_series('DFF', observation_start=start_date).dropna()
    # HY spread is fetched from 2008 regardless of chart range — the stress light is a fixed gauge and its historical context shouldn't recalibrate when the user zooms.
    s_hy = fred.get_series('BAMLH0A0HYM2', observation_start="2008-01-01").dropna()

    # Resample to weekly Wednesday
    df = pd.concat([
        s_walcl.resample('W-WED').last().rename('WALCL'),
        s_wtregen.resample('W-WED').last().rename('WTREGEN'),
        s_rrp.resample('W-WED').mean().rename('RRPONTSYD'),
        s_dff.resample('W-WED').mean().rename('DFF')
    ], axis=1)
    df['RRPONTSYD'] = df['RRPONTSYD'].fillna(0)
    df = df.dropna(subset=['WALCL', 'WTREGEN'])

    df['Net Liquidity (T)'] = (df['WALCL'] - df['WTREGEN'] - df['RRPONTSYD']) / 1000

    # Fetch SPY/QQQ/BTC/GLD
    tickers = {'SPY': 'SPY', 'QQQ': 'QQQ', 'BTC': 'BTC-USD', 'GLD': 'GLD'}
    assets = {}
    for name, ticker in tickers.items():
        hist = yf.Ticker(ticker).history(start=start_date)
        if not hist.empty:
            assets[name] = hist['Close'].tz_localize(None).resample('W-WED').last()

    df_assets = pd.DataFrame(assets)
    df = pd.concat([df, df_assets], axis=1)

    return df, s_dff.iloc[-1], s_hy

# --- Page setup & styling ---
st.set_page_config(page_title="Market Tide", page_icon="🌊", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] p { font-family: 'Inter', sans-serif !important; }
.block-container { padding-top: 3.5rem; padding-bottom: 3rem; max-width: 1400px; }
.stApp h2, .stApp h3 { letter-spacing: -0.02em; }
div.hero-title { font-size: 2.2rem !important; font-weight: 700; line-height: 1.15; letter-spacing: -0.03em; }
div.hero-sub { color: rgba(250,250,250,0.6); margin-top: 0.3rem; font-size: 0.95rem; }
div.verdict-line { font-size: 1.15rem; font-weight: 500; margin: 0.6rem 0 0.4rem 0; }
[data-testid="stMetric"] { background: rgba(255,255,255,0.03); }
[data-testid="stTabs"] button p { font-size: 1rem !important; font-weight: 600; }
@media (max-width: 640px) {
  div.hero-title { font-size: 1.6rem !important; }
  div.verdict-line { font-size: 1rem; }
  .block-container { padding-left: 1rem; padding-right: 1rem; }
}
</style>
""", unsafe_allow_html=True)

def style_fig(fig, height=None):
    """Shared look for new charts: transparent background, tight margins, horizontal legend."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif"),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    if height:
        fig.update_layout(height=height)
    return fig

# --- Chart Formatting Helper ---
def apply_time_gridlines(fig):
    fig.update_xaxes(
        dtick="M12",
        tickformat="%Y",
        showgrid=True,
        gridcolor="rgba(128, 128, 128, 0.4)",
        gridwidth=1.5,
        minor=dict(
            dtick="M1",
            showgrid=True,
            gridcolor="rgba(128, 128, 128, 0.1)",
            gridwidth=1
        )
    )

# --- Sidebar: date range only ---
st.sidebar.header("Date Range")
def set_range(years):
    if years == 'All':
        st.session_state.start_date_widget = pd.to_datetime("2008-01-01").date()
    else:
        st.session_state.start_date_widget = (pd.Timestamp.today() - pd.DateOffset(years=years)).date()

c1, c2, c3, c4 = st.sidebar.columns(4)
c1.button("1Y", on_click=set_range, args=(1,))
c2.button("5Y", on_click=set_range, args=(5,))
c3.button("10Y", on_click=set_range, args=(10,))
c4.button("All", on_click=set_range, args=('All',))

start_date_val = pd.to_datetime("2008-01-01").date()
start_date = st.sidebar.date_input("Start Date", value=start_date_val, key="start_date_widget")
start_date = pd.to_datetime(start_date)
st.sidebar.caption("Applies to every chart. The credit-stress gauge always uses history since 2008.")

# --- Load data ---
if not FRED_API_KEY:
    st.error("FRED_API_KEY not found. Add it to a local `.env` file (FRED_API_KEY=...) or to the app's Secrets when deployed. Free key: https://fred.stlouisfed.org/docs/api/api_key.html")
    st.stop()

try:
    with st.spinner("Loading Fed and market data..."):
        df, latest_dff, s_hy = get_data(start_date)
except Exception as e:
    st.error(f"Could not load data (check your internet connection and API key). Details: {e}")
    st.info("Try refreshing the page in a moment.")
    st.stop()

if df['Net Liquidity (T)'].dropna().shape[0] < 5:
    st.warning("Not enough data in this date range. Pick an earlier start date.")
    st.stop()

valid_liq = df['Net Liquidity (T)'].dropna()
latest_liq_date = valid_liq.index[-1]
latest_liq = valid_liq.iloc[-1]
delta_liq = latest_liq - valid_liq.iloc[-2]
latest_hy = s_hy.iloc[-1]
liq_df = df.loc[valid_liq.index]

# --- Shared calculations ---
def fmt_b(v):
    """Format $ billions with a sign, without showing '-0B'."""
    v = round(v)
    return "0B" if v == 0 else f"{v:+,.0f}B"

def attribution(weeks):
    """Change in each lever over the last `weeks` ($ billions). TGA/RRP flipped: rising = drain."""
    recent = liq_df.iloc[-(weeks + 1):]
    d_fed = recent['WALCL'].iloc[-1] - recent['WALCL'].iloc[0]
    d_tga = -(recent['WTREGEN'].iloc[-1] - recent['WTREGEN'].iloc[0])
    d_rrp = -(recent['RRPONTSYD'].iloc[-1] - recent['RRPONTSYD'].iloc[0])
    return d_fed, d_tga, d_rrp, d_fed + d_tga + d_rrp

def regime_for(weeks, confirm_weeks):
    d_net = attribution(weeks)[3]
    threshold = 50 * weeks / 13  # scale the +/-$50B quarterly rule to the window
    chg_confirm = (valid_liq.iloc[-1] - valid_liq.iloc[-(confirm_weeks + 1)]) * 1000
    if d_net > threshold and chg_confirm > 0:
        return "Expanding", "green", threshold, chg_confirm
    if d_net < -threshold and chg_confirm < 0:
        return "Draining", "red", threshold, chg_confirm
    return "Flat / Mixed", "orange", threshold, chg_confirm

if latest_hy < 4:
    credit_label, credit_color, credit_text = "Calm", "green", "Credit markets are calm; little stress priced in."
elif latest_hy < 6:
    credit_label, credit_color, credit_text = "Caution", "orange", "Spreads are widening; markets are pricing in moderate risk or uncertainty."
else:
    credit_label, credit_color, credit_text = "Stress", "red", "Credit is tight; significant distress or recession risk is being priced in."
higher_pct = (s_hy > latest_hy).mean() * 100

has_quarter = len(valid_liq) > 13
q_regime, q_color, _, _ = regime_for(13, 4) if has_quarter else ("Not enough data", "gray", 0, 0)

# --- Hero ---
st.markdown('<div class="hero-title">🌊 Market Tide</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hero-sub">Fed net liquidity and what it means for markets · Fed data as of {latest_liq_date.strftime("%b %d, %Y")}</div>', unsafe_allow_html=True)

with st.container(horizontal=True, gap="small"):
    st.badge(f"Liquidity (13w): {q_regime}", color=q_color)
    st.badge(f"Credit: {credit_label}", color=credit_color)
    st.badge(f"Fed funds: {latest_dff:.2f}%", color="violet")

if has_quarter:
    d_fed, d_tga, d_rrp, d_net = attribution(13)
    parts = {"the Fed balance sheet": d_fed, "the Treasury account (TGA)": d_tga, "reverse repo (RRP)": d_rrp}
    biggest = max(parts, key=lambda k: abs(parts[k]))
    st.markdown(f'<div class="verdict-line">Net liquidity moved <b>{d_net:+,.0f}B</b> over the last 13 weeks, driven mostly by {biggest} ({parts[biggest]:+,.0f}B).</div>', unsafe_allow_html=True)

# --- Status cards with sparklines ---
spark_n = 26  # last ~6 months of weekly points
m1, m2, m3, m4 = st.columns(4)
m1.metric("Net Liquidity", f"${latest_liq:.2f}T", f"{delta_liq * 1000:+,.0f}B WoW", border=True,
          chart_data=valid_liq.tail(spark_n).round(3).tolist(), chart_type="area",
          help="Fed assets minus the Treasury General Account minus reverse repo. Sparkline: last 6 months.")
m2.metric("Fed Funds Rate", f"{latest_dff:.2f}%", border=True,
          chart_data=df['DFF'].dropna().tail(spark_n).round(3).tolist(),
          help="Effective federal funds rate, weekly average.")
hy_week_ago = s_hy.iloc[-6] if len(s_hy) > 5 else latest_hy
m3.metric("High-Yield Spread", f"{latest_hy:.2f}%", f"{latest_hy - hy_week_ago:+.2f} pts (1w)", delta_color="inverse", border=True,
          chart_data=s_hy.tail(spark_n * 5).round(3).tolist(),
          help=f"Extra yield on junk bonds over Treasuries. Higher = more credit stress. Lower than {higher_pct:.0f}% of readings since {s_hy.index[0].year}.")
if 'SPY' in df.columns and df['SPY'].dropna().shape[0] > 1:
    spy = df['SPY'].dropna()
    m4.metric("S&P 500 (SPY)", f"${spy.iloc[-1]:,.2f}", f"{(spy.iloc[-1] / spy.iloc[-2] - 1) * 100:+.1f}% WoW", border=True,
              chart_data=spy.tail(spark_n).round(2).tolist(), chart_type="area")

st.write("")

# --- Main sections ---
tab_over, tab_liq, tab_assets, tab_lead, tab_about = st.tabs(
    ["Overview", "Liquidity", "Assets", "Lead / Lag", "About"])

# ===================== OVERVIEW =====================
with tab_over:
    st.subheader("Liquidity Verdict")
    st.caption("Did the money in the financial system go up or down, and who moved it?")
    WINDOWS = {"1M": (4, 2, "month"), "3M": (13, 4, "3 months"), "6M": (26, 8, "6 months"), "1Y": (52, 13, "year")}
    period = st.segmented_control("Window", list(WINDOWS), default="3M",
                                  label_visibility="collapsed", key="verdict_period") or "3M"
    weeks, confirm, span_text = WINDOWS[period]

    if len(valid_liq) <= weeks:
        st.info("Not enough history in this date range for this view. Pick an earlier start date.")
    else:
        d_fed, d_tga, d_rrp, d_net = attribution(weeks)
        regime, r_color, threshold, chg_confirm = regime_for(weeks, confirm)

        def lever_phrase(name, v):
            v = round(v)
            if abs(v) < 5:
                return f"{name} barely moved"
            return f"{name} {'added' if v > 0 else 'drained'} ${abs(v):,.0f}B"

        if regime == "Flat / Mixed":
            if abs(d_net) > threshold:
                # Big move over the window, but the recent weeks disagree
                regime = (f"Mixed: {'up' if d_net > 0 else 'down'} over the {span_text}, "
                          f"{'falling' if chg_confirm < 0 else 'rising'} in the last {confirm} weeks")
            else:
                regime = f"Flat: smaller than the ±${threshold:,.0f}B that counts as a big move for this window"
        st.badge(regime, color=r_color)
        net_word = "up" if round(d_net) > 0 else "down" if round(d_net) < 0 else "flat"
        st.markdown(f'<div class="verdict-line">Net liquidity is <b>{net_word} ${abs(round(d_net)):,.0f}B</b> over the past {span_text}.</div>',
                    unsafe_allow_html=True)
        phrases = [lever_phrase("The Fed", d_fed), lever_phrase("the Treasury (TGA)", d_tga), lever_phrase("reverse repo (RRP)", d_rrp)]
        st.write(" · ".join(phrases).replace("$", "\\$"))

        left, right = st.columns([1.25, 1])
        with left:
            sw = '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:{};margin:0 6px -1px 14px"></span>'
            st.markdown('<div style="font-size:0.85rem;color:rgba(250,250,250,0.75)">'
                        + sw.format(C_FED) + 'Added money'
                        + sw.format(C_TGA) + 'Drained money'
                        + sw.format(C_NET) + 'Net result (all three combined)</div>',
                        unsafe_allow_html=True)
            # Tug-of-war: right = added money, left = drained money
            names = ["Fed balance sheet", "Treasury account (TGA)", "Reverse repo (RRP)"]
            vals = [d_fed, d_tga, d_rrp]
            labels = [("added " if round(v) > 0 else "drained " if round(v) < 0 else "") + f"${abs(round(v)):,.0f}B" for v in vals]
            span = max(abs(v) for v in vals + [d_net]) * 1.6 or 1
            fig_tw = go.Figure()
            biggest_abs = max(abs(v) for v in vals + [d_net]) or 1
            positions = ['inside' if abs(v) >= 0.4 * biggest_abs else 'outside' for v in vals]
            fig_tw.add_trace(go.Bar(
                y=names, x=vals, orientation='h', text=labels, textposition=positions, cliponaxis=False,
                insidetextanchor='middle', insidetextfont=dict(color='white', size=13),
                marker=dict(color=[C_FED if v >= 0 else C_TGA for v in vals]),
                hovertemplate="%{y}: %{x:+,.0f}B<extra></extra>"))
            fig_tw.add_trace(go.Bar(
                y=["Net result"], x=[d_net], orientation='h', text=[fmt_b(d_net)],
                textposition='inside' if abs(d_net) >= 0.4 * biggest_abs else 'outside', cliponaxis=False,
                insidetextanchor='middle', insidetextfont=dict(color='white', size=13),
                marker=dict(color=C_NET), hovertemplate="Net result: %{x:+,.0f}B<extra></extra>"))
            fig_tw.add_vline(x=0, line_width=2, line_color="rgba(200,200,200,0.6)")
            fig_tw.add_annotation(x=-span, y=1.1, yref="paper", text="◀ drained", showarrow=False,
                                  xanchor="left", font=dict(color=C_TGA, size=12))
            fig_tw.add_annotation(x=span, y=1.1, yref="paper", text="added ▶", showarrow=False,
                                  xanchor="right", font=dict(color=C_FED, size=12))
            style_fig(fig_tw, 300)
            fig_tw.update_layout(showlegend=False, hovermode="closest", bargap=0.35, margin=dict(l=10, r=10, t=40, b=10))
            fig_tw.update_xaxes(range=[-span, span], showgrid=False, zeroline=False, showticklabels=False)
            fig_tw.update_yaxes(categoryorder="array", categoryarray=["Net result"] + names[::-1], showgrid=False)
            st.plotly_chart(fig_tw, width='stretch', key=f"tug_{weeks}", config={"displayModeBar": False})

        with right:
            # Context: is this move big or normal? Shade the selected window on a longer trend.
            look = min(len(valid_liq), max(52, weeks * 2))
            trend = valid_liq.tail(look)
            win_start = valid_liq.index[-(weeks + 1)]
            fig_tr = go.Figure()
            fig_tr.add_vrect(x0=win_start, x1=trend.index[-1], fillcolor=C_NET, opacity=0.15, line_width=0)
            fig_tr.add_trace(go.Scatter(x=trend.index, y=trend, mode="lines", line=dict(color=C_NET, width=2.5),
                                        hovertemplate="%{x|%b %d, %Y}: $%{y:.2f}T<extra></extra>"))
            fig_tr.add_trace(go.Scatter(x=[win_start, trend.index[-1]], y=[valid_liq.loc[win_start], trend.iloc[-1]],
                                        mode="markers", marker=dict(color="white", size=8, line=dict(color=C_NET, width=2)),
                                        hoverinfo="skip"))
            trend_label = "2 years" if look >= 104 else "year"
            style_fig(fig_tr, 300)
            fig_tr.update_layout(showlegend=False, hovermode="closest", yaxis_title="Net liquidity ($T)",
                                 title=dict(text=f"Net liquidity over the last {trend_label} · shaded = selected window",
                                            font=dict(size=12)))
            st.plotly_chart(fig_tr, width='stretch', key=f"trend_{weeks}", config={"displayModeBar": False})

        with st.expander("Month by month (last 12 months)"):
            monthly = pd.DataFrame({
                'Fed': liq_df['WALCL'].diff(),
                'TGA': -liq_df['WTREGEN'].diff(),
                'RRP': -liq_df['RRPONTSYD'].diff(),
            }).resample('ME').sum().tail(12)
            if len(monthly) >= 2:
                monthly['Net'] = monthly['Fed'] + monthly['TGA'] + monthly['RRP']
                mlabels = monthly.index.strftime('%b %y')
                fig_m = go.Figure()
                for col, color in (('Fed', C_FED), ('TGA', C_TGA), ('RRP', C_RRP)):
                    fig_m.add_trace(go.Bar(x=mlabels, y=monthly[col], name=col, marker_color=color))
                fig_m.add_trace(go.Scatter(x=mlabels, y=monthly['Net'], name="Net", mode='lines+markers',
                                           line=dict(color=C_NET, width=3)))
                style_fig(fig_m, 300)
                fig_m.update_layout(barmode='relative', yaxis_title="$ Billions")
                st.plotly_chart(fig_m, width='stretch', key="monthly_hist")
                st.caption("Bars above zero added money that month, bars below drained it. The line is the net result. The first month may be partial.")

        with st.expander("How to read this"):
            st.write("Net liquidity = Fed assets − Treasury account (TGA) − reverse repo (RRP). "
                     "The Fed adds money when its balance sheet grows. The TGA and RRP drain money when they grow, because that cash is "
                     "sitting at the Fed instead of circulating. Each bar shows how much that lever pushed liquidity up (right) or down (left) "
                     f"over the past {span_text}; the blue bar is the total. "
                     f"Badge rule: net change beyond ±${threshold:,.0f}B, with the last {confirm} weeks pointing the same way. "
                     "Short windows can be swung by tax dates (mid-April, June, September, December), so check 6M or 1Y for the trend. Not a forecast.")

    st.divider()
    st.subheader("Net Liquidity vs S&P 500")
    fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                         row_heights=[0.72, 0.28], specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
    fig1.add_trace(go.Scatter(x=df.index, y=df['Net Liquidity (T)'], name="Net Liquidity (T$)", line=dict(color=C_NET, width=2)), row=1, col=1, secondary_y=False)
    fig1.add_trace(go.Scatter(x=df.index, y=df['SPY'], name="SPY", line=dict(color=C_SPY, width=1.5)), row=1, col=1, secondary_y=True)
    fig1.add_trace(go.Scatter(x=df.index, y=df['DFF'].ffill(), name="Fed Funds (%)", line=dict(color=C_RATE, width=1.5)), row=2, col=1)

    show_events = st.toggle("Show policy events", value=True)
    if show_events:
        try:
            events_df = pd.read_csv(os.path.join(os.path.dirname(__file__), "events.csv"))
            events_df['date'] = pd.to_datetime(events_df['date'])
            category_colors = {"QE": "rgba(44,160,44,0.6)", "QT": "rgba(214,39,40,0.6)",
                               "Crisis": "rgba(214,39,40,0.9)", "RateHike": "rgba(176,124,216,0.6)"}
            for _, row in events_df[events_df['date'] >= start_date].iterrows():
                fig1.add_vline(x=row['date'], line_dash="dash", line_color=category_colors.get(row['category'], "gray"), opacity=0.8, row=1, col=1)
                fig1.add_annotation(x=row['date'], y=0, text=row['label'], showarrow=False, textangle=-90,
                                    yref="y domain", yshift=-10, font=dict(size=10), row=1, col=1)
        except Exception as e:
            st.warning(f"Could not load events.csv: {e}")

    style_fig(fig1, 620)
    fig1.update_yaxes(title_text="Net Liquidity (T$)", row=1, col=1, secondary_y=False)
    fig1.update_yaxes(title_text="SPY ($)", row=1, col=1, secondary_y=True, showgrid=False)
    fig1.update_yaxes(title_text="Rate (%)", row=2, col=1)
    apply_time_gridlines(fig1)
    st.plotly_chart(fig1, width='stretch')
    st.caption("Dashed lines mark policy events: green = QE, red = QT / crisis, purple = rate hikes.")

    st.divider()
    st.subheader("Credit Stress")
    cs1, cs2 = st.columns([1, 2])
    with cs1:
        st.badge(credit_label, color=credit_color)
        st.write(f"**{credit_text}**")
        st.write(f"The high-yield spread is **{latest_hy:.2f}%**, lower than **{higher_pct:.0f}%** of readings since {s_hy.index[0].year}.")
        st.caption("Bands: below 4% calm · 4–6% caution · above 6% stress.")
    with cs2:
        hy_view = s_hy[s_hy.index >= start_date] if (s_hy.index >= start_date).sum() > 10 else s_hy
        fig_hy = go.Figure(go.Scatter(x=hy_view.index, y=hy_view, name="HY spread", line=dict(color="#e8e8e8", width=1.5)))
        fig_hy.add_hrect(y0=0, y1=4, fillcolor=C_FED, opacity=0.08, line_width=0)
        fig_hy.add_hrect(y0=4, y1=6, fillcolor=C_RRP, opacity=0.08, line_width=0)
        fig_hy.add_hrect(y0=6, y1=max(hy_view.max(), 6.5) * 1.05, fillcolor=C_TGA, opacity=0.08, line_width=0)
        style_fig(fig_hy, 260)
        fig_hy.update_layout(yaxis_title="Spread (%)", showlegend=False)
        st.plotly_chart(fig_hy, width='stretch')

# ===================== LIQUIDITY =====================
with tab_liq:
    st.subheader("Liquidity Levers — Levels (the bathtub)")
    fig_levels = go.Figure()
    fig_levels.add_trace(go.Scatter(x=df.index, y=df['Net Liquidity (T)'], name="Net Liquidity", stackgroup='one', line=dict(color=C_NET)))
    fig_levels.add_trace(go.Scatter(x=df.index, y=df['WTREGEN']/1000, name="TGA Drain", stackgroup='one', line=dict(color=C_TGA)))
    fig_levels.add_trace(go.Scatter(x=df.index, y=df['RRPONTSYD']/1000, name="RRP Drain", stackgroup='one', line=dict(color=C_RRP)))
    fig_levels.add_trace(go.Scatter(x=df.index, y=df['WALCL']/1000, name="Fed Assets (WALCL)", line=dict(color='#98FB98', width=3, dash='dot')))
    style_fig(fig_levels, 480)
    fig_levels.update_layout(yaxis_title="Trillions ($)")
    apply_time_gridlines(fig_levels)
    st.plotly_chart(fig_levels, width='stretch')
    with st.expander("How to read this"):
        st.write("The stacked total equals total Fed Assets (WALCL). The blue band is Net Liquidity — the money that actually reaches markets — "
                 "and the red/orange bands are the TGA and RRP drains.")

    st.divider()

    # --- Liquidity Flows: copied verbatim from app.py ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.subheader("Liquidity Flows — What Moved It")
    with c2:
        flow_period = st.selectbox("Period:", ["Monthly", "Quarterly"], label_visibility="collapsed")

    fig_flows = go.Figure()
    contrib_fed = df['WALCL'].diff()
    contrib_tga = -df['WTREGEN'].diff()
    contrib_rrp = -df['RRPONTSYD'].diff()

    rule = 'ME' if flow_period == "Monthly" else 'QE'
    df_flows = pd.DataFrame({
        'Fed': contrib_fed,
        'TGA': contrib_tga,
        'RRP': contrib_rrp
    }).resample(rule).sum()

    df_flows['Net Change'] = df_flows['Fed'] + df_flows['TGA'] + df_flows['RRP']

    fig_flows.add_trace(go.Bar(x=df_flows.index, y=df_flows['Fed'], name="Fed Contribution", marker_color='green'))
    fig_flows.add_trace(go.Bar(x=df_flows.index, y=df_flows['TGA'], name="TGA Contribution", marker_color='red'))
    fig_flows.add_trace(go.Bar(x=df_flows.index, y=df_flows['RRP'], name="RRP Contribution", marker_color='orange'))
    fig_flows.add_trace(go.Scatter(x=df_flows.index, y=df_flows['Net Change'], name="Net Change", mode='lines+markers', line=dict(color='white', width=2), marker=dict(color='white', size=6)))

    fig_flows.update_layout(barmode='relative', yaxis_title="Change ($ Billions)", hovermode="x unified", legend=dict(orientation="h"))
    fig_flows.add_hline(y=0, line_width=1, line_color="white", opacity=0.3)

    apply_time_gridlines(fig_flows)
    st.plotly_chart(fig_flows, width='stretch')
    st.caption("Each bar shows how much that lever added (+) or drained (−) from Net Liquidity that period. TGA and RRP are inverted — when they rise, they drain, so their bars point down. The line is the net result. Big opposing bars = levers fighting each other (e.g. 2023: QT pulling down while the RRP drain pushed up).")

# ===================== ASSETS =====================
with tab_assets:
    st.subheader("Asset Race (Indexed Performance)")
    available = [a for a in ['SPY', 'QQQ', 'BTC', 'GLD'] if a in df.columns and df[a].notna().any()]
    names = {'SPY': 'S&P 500', 'QQQ': 'Nasdaq-100', 'BTC': 'Bitcoin', 'GLD': 'Gold'}
    ac1, ac2 = st.columns([3, 1])
    with ac1:
        picked = st.pills("Assets", available, default=available, selection_mode="multi",
                          format_func=lambda a: f"{names[a]} ({a})", label_visibility="collapsed")
    with ac2:
        use_log = st.toggle("Log scale", value=True)

    if not picked:
        st.info("Pick at least one asset.")
    else:
        first_valid_prices = df[available].apply(lambda x: x.loc[x.first_valid_index()])
        df_race = (df[available] / first_valid_prices) * 100
        asset_colors = {'SPY': C_SPY, 'QQQ': '#4fc3f7', 'BTC': '#f7931a', 'GLD': '#d4af37'}
        fig3 = go.Figure()
        for a in picked:
            fig3.add_trace(go.Scatter(x=df.index, y=df_race[a], name=a, line=dict(color=asset_colors[a], width=2)))
        style_fig(fig3, 520)
        fig3.update_layout(yaxis_type="log" if use_log else "linear", yaxis_title="Index (start = 100)")
        apply_time_gridlines(fig3)
        st.plotly_chart(fig3, width='stretch')

        rows = []
        for a in picked:
            s = df[a].dropna()
            rows.append({"Asset": f"{names[a]} ({a})", "Since start": f"{(s.iloc[-1] / s.iloc[0] - 1) * 100:+,.0f}%",
                         "Last 13w": f"{(s.iloc[-1] / s.iloc[-14] - 1) * 100:+.1f}%" if len(s) > 13 else "—",
                         "Last 4w": f"{(s.iloc[-1] / s.iloc[-5] - 1) * 100:+.1f}%" if len(s) > 4 else "—"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    st.caption("Each asset is indexed to 100 at its first available date in the selected range; assets that began later (e.g. Bitcoin) start their line later.")

# ===================== LEAD / LAG =====================
with tab_lead:
    st.subheader("Does Liquidity Lead Prices?")
    lc1, lc2 = st.columns([1, 1])
    lag_asset = lc1.selectbox("Asset:", [a for a in ['SPY', 'QQQ', 'BTC', 'GLD'] if a in df.columns])
    win = lc2.selectbox("Window (weeks):", [4, 13], index=0)

    liq_chg = df['Net Liquidity (T)'].pct_change(win)
    asset_ret = df[lag_asset].pct_change(win)
    lags = list(range(0, 13))
    corrs = [liq_chg.shift(l).corr(asset_ret) for l in lags]
    n_obs = pd.concat([liq_chg, asset_ret], axis=1).dropna().shape[0]

    if n_obs < 30:
        st.info("Not enough overlapping history in this date range. Widen the start date (try 'All').")
    else:
        best = max(range(len(corrs)), key=lambda i: abs(corrs[i]) if pd.notna(corrs[i]) else -1)
        fig_lag = go.Figure(go.Bar(x=lags, y=corrs, marker_color=[C_NET if i != best else C_RRP for i in range(len(lags))]))
        style_fig(fig_lag, 350)
        fig_lag.update_layout(xaxis_title="Liquidity change measured N weeks BEFORE the asset move",
                              yaxis_title="Correlation", yaxis_range=[-1, 1], showlegend=False)
        fig_lag.add_hline(y=0, line_width=1, line_color="white", opacity=0.3)
        st.plotly_chart(fig_lag, width='stretch')
        st.write(f"Strongest link: liquidity change **{best} weeks earlier**, correlation **{corrs[best]:+.2f}** ({n_obs} weekly observations).")
        with st.expander("How to read this"):
            st.write(f"Each bar compares the {win}-week change in net liquidity (shifted back N weeks) with the {lag_asset} {win}-week return. "
                     "Bars far from zero at higher N suggest liquidity leads the asset. Caution: windows overlap, so the effective sample size is much smaller "
                     "than the count shown, and correlations shift across eras. Treat this as context, not a trading signal.")

# ===================== ABOUT =====================
with tab_about:
    st.subheader("What this dashboard tracks")
    st.write("""
The Fed's balance sheet is like a bathtub. The water level (**Net Liquidity**) is fed by the Fed's assets,
but drained by the Treasury (TGA) and money market funds (RRP). This dashboard tracks that water level
and how it relates to asset prices.
""")
    st.latex(r"\text{Net Liquidity} = \text{Fed Assets (WALCL)} - \text{TGA} - \text{RRP}")
    st.markdown("""
- **Fed Assets (WALCL):** total liquidity supplied by the Fed.
- **TGA:** the Treasury's cash account at the Fed. When it grows, money leaves the banking system.
- **RRP:** cash money-market funds park at the Fed overnight. When it grows, that cash isn't circulating.
""")
    st.subheader("Data sources & freshness")
    fresh = pd.DataFrame([
        {"Series": "Fed assets (WALCL)", "Source": "FRED", "Latest": liq_df['WALCL'].index[-1].strftime('%Y-%m-%d'), "Updates": "Weekly (Thu, Wed level)"},
        {"Series": "Treasury account (WTREGEN)", "Source": "FRED", "Latest": liq_df['WTREGEN'].index[-1].strftime('%Y-%m-%d'), "Updates": "Weekly (Thu, Wed level)"},
        {"Series": "Reverse repo (RRPONTSYD)", "Source": "FRED", "Latest": latest_liq_date.strftime('%Y-%m-%d'), "Updates": "Daily, averaged weekly"},
        {"Series": "Fed funds (DFF)", "Source": "FRED", "Latest": df['DFF'].dropna().index[-1].strftime('%Y-%m-%d'), "Updates": "Daily, averaged weekly"},
        {"Series": "High-yield spread", "Source": "FRED (ICE BofA)", "Latest": s_hy.index[-1].strftime('%Y-%m-%d'), "Updates": "Daily"},
        {"Series": "SPY / QQQ / BTC / GLD", "Source": "Yahoo Finance", "Latest": df[available].dropna(how='all').index[-1].strftime('%Y-%m-%d') if available else "—", "Updates": "Daily, weekly close shown"},
    ])
    st.dataframe(fresh, hide_index=True, width='stretch')
    st.caption("Data is cached for 1 hour. Weekly dates are Wednesdays.")

st.divider()
st.caption("_This is a personal context tool, not financial advice. Liquidity is one input among many and the link to prices is loose and can break._")

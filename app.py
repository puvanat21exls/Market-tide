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

RATE_SERIES = {
    'DGS3MO': '3-month', 'DGS2': '2-year', 'DGS10': '10-year',
    'T10Y3M': '10Y − 3M', 'T10Y2Y': '10Y − 2Y', 'DFII10': '10Y real',
}

@st.cache_data(ttl=3600)
def get_rates(start_date):
    """Daily Treasury yields and curve spreads. Always reaches back at least ~13 months for the 1-year-ago curve."""
    fred = Fred(api_key=FRED_API_KEY)
    fetch_from = min(pd.Timestamp(start_date), pd.Timestamp.today() - pd.DateOffset(months=13))
    rates = pd.DataFrame({code: fred.get_series(code, observation_start=fetch_from) for code in RATE_SERIES})
    return rates.dropna(how='all')

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

try:
    rates = get_rates(start_date)
except Exception as e:
    rates, rates_error = None, str(e)

def curve_status(spread):
    """Label the 10Y−3M spread: below 0 inverted, under 0.5 flat, else normal."""
    if spread < 0:
        return "Inverted", "red"
    if spread < 0.5:
        return "Flat", "orange"
    return "Normal", "green"

if rates is not None and rates['T10Y3M'].notna().any():
    curve_label, curve_color = curve_status(rates['T10Y3M'].dropna().iloc[-1])
else:
    curve_label, curve_color = None, None
q_regime, q_color, _, _ = regime_for(13, 4) if has_quarter else ("Not enough data", "gray", 0, 0)

# --- Hero ---
st.markdown('<div class="hero-title">🌊 Market Tide</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hero-sub">Fed net liquidity and what it means for markets · Fed data as of {latest_liq_date.strftime("%b %d, %Y")}</div>', unsafe_allow_html=True)

with st.container(horizontal=True, gap="small"):
    st.badge(f"Liquidity (13w): {q_regime}", color=q_color)
    st.badge(f"Credit: {credit_label}", color=credit_color)
    st.badge(f"Fed funds: {latest_dff:.2f}%", color="violet")
    if curve_label:
        st.badge(f"Yield curve: {curve_label}", color=curve_color)

if has_quarter:
    d_fed, d_tga, d_rrp, d_net = attribution(13)
    parts = {"the Fed balance sheet": d_fed, "the Treasury account (TGA)": d_tga, "reverse repo (RRP)": d_rrp}
    biggest = max(parts, key=lambda k: abs(parts[k]))
    st.markdown(f'<div class="verdict-line">Net liquidity moved <b>{d_net:+,.0f}B</b> over the last 13 weeks, driven mostly by {biggest} ({parts[biggest]:+,.0f}B).</div>', unsafe_allow_html=True)

# --- Status cards with sparklines ---
SPARK_MONTHS = 24  # sparklines: one point per month, last 2 years

def monthly_spark(series, how="mean"):
    """Monthly points (average, or month-end value for prices/levels) over the last SPARK_MONTHS months."""
    m = series.dropna().resample('ME')
    m = m.last() if how == "last" else m.mean()
    return m.dropna().tail(SPARK_MONTHS).round(3).tolist()

spark_help = " Sparkline: monthly, last 2 years."
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Net Liquidity", f"${latest_liq:.2f}T", f"{delta_liq * 1000:+,.0f}B WoW", border=True,
          chart_data=monthly_spark(valid_liq, "last"), chart_type="area",
          help="Fed assets minus the Treasury General Account minus reverse repo." + spark_help)
m2.metric("Fed Funds Rate", f"{latest_dff:.2f}%", border=True,
          chart_data=monthly_spark(df['DFF']),
          help="Effective federal funds rate: the overnight rate the Fed targets." + spark_help)
hy_week_ago = s_hy.iloc[-6] if len(s_hy) > 5 else latest_hy
m3.metric("High-Yield Spread", f"{latest_hy:.2f}%", f"{latest_hy - hy_week_ago:+.2f} pts (1w)", delta_color="inverse", border=True,
          chart_data=monthly_spark(s_hy),
          help=f"Extra yield on junk bonds over Treasuries. Higher = more credit stress. Lower than {higher_pct:.0f}% of readings since {s_hy.index[0].year}." + spark_help)
if rates is not None and rates['DGS10'].notna().sum() > 5:
    y10 = rates['DGS10'].dropna()
    y10_week_ago = y10.iloc[-6]
    m4.metric("10-Year Treasury", f"{y10.iloc[-1]:.2f}%", f"{y10.iloc[-1] - y10_week_ago:+.2f} pts (1w)", delta_color="off", border=True,
              chart_data=monthly_spark(y10),
              help="What the US government pays to borrow for 10 years. Sets mortgage and long-term borrowing costs; a key input for stock valuations. See the Rates tab." + spark_help)
else:
    m4.metric("10-Year Treasury", "—", border=True, help="Treasury yields could not be loaded.")
if 'SPY' in df.columns and df['SPY'].dropna().shape[0] > 1:
    spy = df['SPY'].dropna()
    m5.metric("S&P 500 (SPY)", f"${spy.iloc[-1]:,.2f}", f"{(spy.iloc[-1] / spy.iloc[-2] - 1) * 100:+.1f}% WoW", border=True,
              chart_data=monthly_spark(spy, "last"), chart_type="area", help="Month-end prices." + spark_help)

st.write("")

# --- Main sections ---
tab_over, tab_liq, tab_rates, tab_assets, tab_lead, tab_about = st.tabs(
    ["Overview", "Liquidity", "Rates", "Assets", "Lead / Lag", "About"])

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
    st.subheader("Liquidity Levers — Where the Fed's Money Goes")
    st.caption("The Fed's balance sheet is the total. Part of it reaches markets (net liquidity); the rest sits in two drains.")

    # --- Idea 2: today's split in one bar ---
    lv = liq_df.iloc[-1]
    fed_t, tga_t, rrp_t = lv['WALCL'] / 1000, lv['WTREGEN'] / 1000, lv['RRPONTSYD'] / 1000
    net_t = fed_t - tga_t - rrp_t
    parts_split = [("Reaches markets (net liquidity)", net_t, C_NET),
                   ("Treasury account (TGA)", tga_t, C_TGA),
                   ("Reverse repo (RRP)", rrp_t, C_RRP)]

    def amt_text(v_t):
        """$ amount from trillions: '$5.75T', or '$4B' when under $1T."""
        v_b = v_t * 1000
        if round(v_b) >= 1000:
            return f"${v_t:.2f}T"
        return f"${v_b:.1f}B" if v_b < 10 else f"${v_b:,.0f}B"

    def pct_text(v):
        p = v / fed_t * 100
        return f"{p:.0f}%" if p >= 1 else "<1%"

    st.markdown(f'<div class="verdict-line">Of the Fed\'s <b>${fed_t:.2f}T</b>, <b>{pct_text(net_t)}</b> reaches markets.</div>',
                unsafe_allow_html=True)
    fig_split = go.Figure()
    for label, v, color in parts_split:
        share = v / fed_t * 100
        fig_split.add_trace(go.Bar(
            y=["Today"], x=[share], orientation='h', name=label, marker=dict(color=color),
            text=[f"{label.split(' (')[0]}<br>{amt_text(v)} · {pct_text(v)}" if share >= 8 else ""],
            textposition='inside', insidetextanchor='middle', insidetextfont=dict(color='white', size=13),
            textangle=0, constraintext='inside',
            hovertemplate=f"{label}: {amt_text(v)} ({share:.1f}%)<extra></extra>"))
    style_fig(fig_split, 150)
    fig_split.update_layout(barmode='stack', hovermode="closest", margin=dict(l=10, r=10, t=10, b=10),
                            legend=dict(orientation="h", yanchor="top", y=-0.15, x=0, traceorder="normal"))
    fig_split.update_xaxes(range=[0, 100], showticklabels=False, showgrid=False, zeroline=False)
    fig_split.update_yaxes(showticklabels=False, showgrid=False)
    st.plotly_chart(fig_split, width='stretch', key="lever_split", config={"displayModeBar": False})
    st.write(" · ".join(f"{label}: {amt_text(v)} ({pct_text(v)})" for label, v, _ in parts_split).replace("$", "\\$"))
    st.caption(f"Fed data as of {latest_liq_date.strftime('%b %d, %Y')}. Slices under 8% are labelled in the line above, not in the bar.")

    # --- Idea 1: each lever on its own scale ---
    st.markdown("#### Each lever on its own scale")
    st.caption("Separate charts so small moves are visible. For the Fed, up = more money. For the TGA and RRP, up = more money drained.")
    year_ago = liq_df.iloc[-53] if len(liq_df) > 52 else liq_df.iloc[0]
    year_label = "1y" if len(liq_df) > 52 else "range"
    levers = [
        ("Fed assets", 'WALCL', C_FED, "up = adds money"),
        ("Treasury account (TGA)", 'WTREGEN', C_TGA, "up = drains money"),
        ("Reverse repo (RRP)", 'RRPONTSYD', C_RRP, "up = drains money"),
    ]
    cols = st.columns(3)
    for col, (title, field, color, meaning) in zip(cols, levers):
        series = liq_df[field]
        now_v, then_v = series.iloc[-1], year_ago[field]
        chg = now_v - then_v
        value_text = amt_text(now_v / 1000)
        chg_text = f"{chg / 1000:+.2f}T" if abs(chg) >= 1000 else f"{chg:+,.0f}B"
        with col:
            st.metric(title, value_text, f"{chg_text} ({year_label})", border=True,
                      delta_color="normal" if field == 'WALCL' else "inverse", help=meaning.capitalize() + ".")
            r_, g_, b_ = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            fill = f"rgba({r_},{g_},{b_},0.2)"  # same color, 20% opacity
            fig_l = go.Figure(go.Scatter(x=series.index, y=series / 1000, mode="lines", fill="tozeroy",
                                         line=dict(color=color, width=2), fillcolor=fill,
                                         hovertemplate="%{x|%b %d, %Y}: $%{y:.2f}T<extra></extra>"))
            style_fig(fig_l, 220)
            fig_l.update_layout(showlegend=False, hovermode="closest", margin=dict(l=10, r=10, t=10, b=10))
            fig_l.update_yaxes(title_text="$T", rangemode="tozero")
            fig_l.update_xaxes(nticks=6, showgrid=False)
            st.plotly_chart(fig_l, width='stretch', key=f"lever_{field}", config={"displayModeBar": False})
            st.caption(meaning.capitalize())

    with st.expander("Classic stacked view (the bathtub)"):
        fig_levels = go.Figure()
        fig_levels.add_trace(go.Scatter(x=df.index, y=df['Net Liquidity (T)'], name="Net Liquidity", stackgroup='one', line=dict(color=C_NET)))
        fig_levels.add_trace(go.Scatter(x=df.index, y=df['WTREGEN']/1000, name="TGA Drain", stackgroup='one', line=dict(color=C_TGA)))
        fig_levels.add_trace(go.Scatter(x=df.index, y=df['RRPONTSYD']/1000, name="RRP Drain", stackgroup='one', line=dict(color=C_RRP)))
        fig_levels.add_trace(go.Scatter(x=df.index, y=df['WALCL']/1000, name="Fed Assets (WALCL)", line=dict(color='#98FB98', width=3, dash='dot')))
        style_fig(fig_levels, 420)
        fig_levels.update_layout(yaxis_title="Trillions ($)")
        apply_time_gridlines(fig_levels)
        st.plotly_chart(fig_levels, width='stretch')
        st.caption("The stacked total equals total Fed Assets (WALCL). The blue band is Net Liquidity — the money that actually reaches markets — "
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

# ===================== RATES =====================
with tab_rates:
    st.subheader("Treasury Yields & the Yield Curve")
    st.caption("What the US government pays to borrow, from 3 months to 10 years. The gap between short and long rates is the yield curve.")
    if rates is None:
        st.error(f"Could not load Treasury yields. Details: {rates_error}")
    else:
        r = rates.ffill()
        last = r.iloc[-1]
        ago_idx = r.index.searchsorted(r.index[-1] - pd.DateOffset(years=1))
        year_ago = r.iloc[min(ago_idx, len(r) - 1)]

        # --- Cards ---
        k1, k2, k3, k4 = st.columns(4)
        for col, code, tip in (
            (k1, 'DGS3MO', "Tracks the Fed's policy rate almost exactly: the 'cash' rate."),
            (k2, 'DGS2', "What markets expect the Fed to do over the next 2 years. Moves first when cuts or hikes get priced in."),
            (k3, 'DGS10', "Sets mortgage and long-term borrowing costs; a key input for stock valuations."),
        ):
            col.metric(f"{RATE_SERIES[code]} yield", f"{last[code]:.2f}%", f"{last[code] - year_ago[code]:+.2f} pts (1y)",
                       delta_color="off", border=True, chart_data=monthly_spark(r[code]), help=tip + spark_help)
        k4.metric("Curve: 10Y − 3M", f"{last['T10Y3M']:+.2f} pts", curve_label, delta_color="off", border=True,
                  chart_data=monthly_spark(r['T10Y3M']),
                  help="10-year yield minus 3-month yield. Below zero = inverted, which has come before most US recessions.")

        st.badge(f"Yield curve: {curve_label}", color=curve_color)
        curve_text = {
            "Inverted": "Short-term rates are above long-term rates. Markets expect rates to fall, often because they expect the economy to slow.",
            "Flat": "Short- and long-term rates are close together. A transition zone: the curve is either un-inverting or flattening.",
            "Normal": "Long-term rates are above short-term rates, the usual shape when growth is expected to continue.",
        }[curve_label]
        st.write(curve_text)

        # --- 1. Yield curve snapshot: today vs a year ago ---
        st.markdown("#### The curve today vs a year ago")
        maturities = ['DGS3MO', 'DGS2', 'DGS10']
        mat_labels = ['3 months', '2 years', '10 years']
        fig_curve = go.Figure()
        fig_curve.add_trace(go.Scatter(x=mat_labels, y=[year_ago[m] for m in maturities], name=f"A year ago ({r.index[min(ago_idx, len(r) - 1)]:%b %Y})",
                                       mode="lines+markers", line=dict(color="rgba(200,200,200,0.6)", width=2, dash="dot"), marker=dict(size=9)))
        fig_curve.add_trace(go.Scatter(x=mat_labels, y=[last[m] for m in maturities], name=f"Today ({r.index[-1]:%b %d, %Y})",
                                       mode="lines+markers+text", line=dict(color=C_NET, width=3), marker=dict(size=11),
                                       text=[f"{last[m]:.2f}%" for m in maturities], textposition="top center"))
        style_fig(fig_curve, 320)
        curve_vals = [year_ago[m] for m in maturities] + [last[m] for m in maturities]
        fig_curve.update_layout(yaxis_title="Yield (%)", hovermode="x unified")
        fig_curve.update_yaxes(range=[min(curve_vals) - 0.3, max(curve_vals) + 0.35])
        st.plotly_chart(fig_curve, width='stretch', key="curve_snapshot", config={"displayModeBar": False})
        st.caption("Upward slope = normal. Downward slope = inverted. Comparing the two lines shows how the shape has changed.")

        # --- 2. History ---
        st.markdown("#### Yields over time")
        show_real = st.toggle("Add the 10-year real yield (after expected inflation)", value=False,
                              help="Often the best single rate for explaining gold and Bitcoin, which pay no interest.")
        hist = r[r.index >= start_date]
        fig_y = go.Figure()
        for code, color in (('DGS3MO', '#4fc3f7'), ('DGS2', C_RRP), ('DGS10', '#f0f0f0')):
            fig_y.add_trace(go.Scatter(x=hist.index, y=hist[code], name=RATE_SERIES[code], line=dict(color=color, width=1.8)))
        fig_y.add_trace(go.Scatter(x=df.index, y=df['DFF'].ffill(), name="Fed funds", line=dict(color=C_RATE, width=1.5, dash="dot")))
        if show_real:
            fig_y.add_trace(go.Scatter(x=hist.index, y=hist['DFII10'], name="10Y real", line=dict(color="#d4af37", width=1.8)))
        style_fig(fig_y, 420)
        fig_y.update_layout(yaxis_title="Yield (%)")
        apply_time_gridlines(fig_y)
        st.plotly_chart(fig_y, width='stretch', key="yields_history", config={"displayModeBar": False})

        # --- 3. Spreads with the inverted zone shaded ---
        st.markdown("#### Is the curve inverted?")
        fig_s = go.Figure()
        low = min(hist['T10Y3M'].min(), hist['T10Y2Y'].min(), -0.5)
        fig_s.add_hrect(y0=low * 1.1, y1=0, fillcolor=C_TGA, opacity=0.12, line_width=0)
        fig_s.add_annotation(x=0.01, y=low * 0.55, xref="paper", text="Inverted zone", showarrow=False,
                             xanchor="left", font=dict(color=C_TGA, size=12))
        fig_s.add_trace(go.Scatter(x=hist.index, y=hist['T10Y3M'], name="10Y − 3M", line=dict(color=C_NET, width=2)))
        fig_s.add_trace(go.Scatter(x=hist.index, y=hist['T10Y2Y'], name="10Y − 2Y", line=dict(color=C_RRP, width=1.6)))
        fig_s.add_hline(y=0, line_width=1, line_color="rgba(200,200,200,0.6)")
        style_fig(fig_s, 360)
        fig_s.update_layout(yaxis_title="Spread (percentage points)")
        apply_time_gridlines(fig_s)
        st.plotly_chart(fig_s, width='stretch', key="spreads_history", config={"displayModeBar": False})

        with st.expander("How to read this"):
            st.write("A Treasury yield is the interest rate the US government pays to borrow for that length of time. "
                     "Normally longer loans pay more, so the curve slopes up. When short rates rise above long rates, the curve is "
                     "'inverted': markets expect the Fed to cut later, often because they expect a slowdown. The 10Y − 3M inversion has "
                     "come before most US recessions, but the timing varies a lot (often 6–18 months) and it has given false alarms. "
                     "Link to liquidity: when 3-month T-bills pay more than the Fed's reverse repo rate, money-market funds move cash out "
                     "of RRP into T-bills, which is a big part of why RRP drained from over $2T to near zero. Context, not a forecast.")

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
        {"Series": "Treasury yields & spreads (DGS3MO, DGS2, DGS10, T10Y3M, T10Y2Y, DFII10)", "Source": "FRED",
         "Latest": rates.dropna(how='all').index[-1].strftime('%Y-%m-%d') if rates is not None else "unavailable", "Updates": "Daily (business days)"},
        {"Series": "SPY / QQQ / BTC / GLD", "Source": "Yahoo Finance", "Latest": df[available].dropna(how='all').index[-1].strftime('%Y-%m-%d') if available else "—", "Updates": "Daily, weekly close shown"},
    ])
    st.dataframe(fresh, hide_index=True, width='stretch')
    st.caption("Data is cached for 1 hour. Weekly dates are Wednesdays.")

st.divider()
st.caption("_This is a personal context tool, not financial advice. Liquidity is one input among many and the link to prices is loose and can break._")

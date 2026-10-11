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

# --- UI Setup ---
st.set_page_config(page_title="Market Liquidity Dashboard", layout="wide")

st.sidebar.header("Dashboard Settings")

# Quick Range Buttons
st.sidebar.write("### Quick Range")
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
# Ensure start_date is a pandas Timestamp for get_data
start_date = pd.to_datetime(start_date)

st.sidebar.markdown("---")
st.sidebar.write("### Asset Race Settings")
show_spy = st.sidebar.checkbox("S&P 500 (SPY)", value=True)
show_qqq = st.sidebar.checkbox("Nasdaq-100 (QQQ)", value=True)
show_btc = st.sidebar.checkbox("Bitcoin (BTC)", value=True)
show_gld = st.sidebar.checkbox("Gold (GLD)", value=True)
use_log = st.sidebar.checkbox("Use Logarithmic Scale", value=True)

if not FRED_API_KEY:
    st.error("FRED_API_KEY not found. Add it to a local `.env` file (FRED_API_KEY=...) or to the app's Secrets when deployed. Free key: https://fred.stlouisfed.org/docs/api/api_key.html")
    st.stop()

try:
    df, latest_dff, s_hy = get_data(start_date)
except Exception as e:
    st.error(f"Could not load data (check your internet connection and API key). Details: {e}")
    st.info("Try refreshing the page in a moment.")
    st.stop()

if df['Net Liquidity (T)'].dropna().shape[0] < 5:
    st.warning("Not enough data in this date range. Pick an earlier start date.")
    st.stop()
latest_hy = s_hy.iloc[-1]

# Calculate valid latest liquidity dates before the Title
valid_liq = df['Net Liquidity (T)'].dropna()
latest_liq_date = valid_liq.index[-1]

# --- Title & Intro ---
st.title("Market Liquidity Dashboard")
st.write(f"**As of:** {latest_liq_date.strftime('%Y-%m-%d')}")
st.write("""
The Fed's balance sheet is like a bathtub. The water level (Net Liquidity) is fed by the Fed's assets, 
but drained by the Treasury (TGA) and money market funds (RRP). This dashboard tracks that water 
level and how it influences asset prices.
""")
st.caption("_This is a personal context tool, not financial advice. Liquidity is one input among many and the link to prices is loose and can break._")
st.markdown("---")

# --- Status Strip ---
latest_liq = valid_liq.iloc[-1]
delta_liq = latest_liq - valid_liq.iloc[-2]

c1, c2, c3 = st.columns(3)
c1.metric("Net Liquidity", f"${latest_liq:.2f}T", f"{delta_liq:.2f}T (WoW)")
c2.metric("Fed Funds Rate", f"{latest_dff:.2f}%")
c3.metric("High-Yield Spread", f"{latest_hy:.2f}%")

# Deepened Stress-Light explanation
higher_pct = (s_hy > latest_hy).mean() * 100
start_year = s_hy.index[0].year

if latest_hy < 4:
    status_icon, status_title = "🟢 Calm", "Credit markets are calm; little stress priced in."
elif latest_hy < 6:
    status_icon, status_title = "🟡 Caution", "Spreads are widening; markets are pricing in moderate risk or uncertainty."
else:
    status_icon, status_title = "🔴 Stress", "Credit is tight; significant distress or recession risk is being priced in."

st.subheader(status_icon)
st.write(f"**{status_title}**")
st.write(f"The high-yield spread is currently **{latest_hy:.2f}%**, which is lower than **{higher_pct:.0f}%** of readings since {start_year}.")
st.markdown("---")

# --- Liquidity Verdict & Flow Attribution (what moved it lately) ---
st.subheader("Liquidity Verdict")
ATTR_WEEKS = 13
if len(valid_liq) > ATTR_WEEKS:
    recent = df.loc[valid_liq.index].iloc[-(ATTR_WEEKS + 1):]
    d_fed = recent['WALCL'].iloc[-1] - recent['WALCL'].iloc[0]
    d_tga = -(recent['WTREGEN'].iloc[-1] - recent['WTREGEN'].iloc[0])
    d_rrp = -(recent['RRPONTSYD'].iloc[-1] - recent['RRPONTSYD'].iloc[0])
    d_net = d_fed + d_tga + d_rrp  # $ billions

    chg4 = (valid_liq.iloc[-1] - valid_liq.iloc[-5]) * 1000 if len(valid_liq) > 4 else 0
    if d_net > 50 and chg4 > 0:
        regime = "🟢 Expanding"
    elif d_net < -50 and chg4 < 0:
        regime = "🔴 Draining"
    else:
        regime = "🟡 Flat / Mixed"

    parts = {"Fed balance sheet": d_fed, "Treasury (TGA)": d_tga, "Reverse repo (RRP)": d_rrp}
    biggest = max(parts, key=lambda k: abs(parts[k]))
    st.write(f"**{regime}** — net liquidity changed **{d_net:+,.0f}B** over the last {ATTR_WEEKS} weeks "
             f"({chg4:+,.0f}B over the last 4). The biggest driver was **{biggest}** ({parts[biggest]:+,.0f}B).")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric(f"Fed assets ({ATTR_WEEKS}w)", f"{d_fed:+,.0f}B")
    a2.metric(f"TGA ({ATTR_WEEKS}w)", f"{d_tga:+,.0f}B")
    a3.metric(f"RRP ({ATTR_WEEKS}w)", f"{d_rrp:+,.0f}B")
    a4.metric(f"Net ({ATTR_WEEKS}w)", f"{d_net:+,.0f}B")

    fig_attr = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "relative", "total"],
        x=["Fed assets", "TGA", "RRP", "Net change"],
        y=[d_fed, d_tga, d_rrp, d_net],
        text=[f"{v:+,.0f}B" for v in (d_fed, d_tga, d_rrp, d_net)],
        increasing=dict(marker=dict(color="#2ca02c")),
        decreasing=dict(marker=dict(color="#d62728")),
        totals=dict(marker=dict(color="#1f77b4")),
    ))
    fig_attr.update_layout(height=320, yaxis_title="Change ($ Billions)", showlegend=False, margin=dict(t=20))
    st.plotly_chart(fig_attr, width='stretch')
    st.caption(f"How the last {ATTR_WEEKS} weeks added up. Green = added liquidity, red = drained it. TGA and RRP are flipped: a rising TGA/RRP drains liquidity, so it shows as negative. "
               "The regime label is a simple rule (net change beyond ±$50B and the last 4 weeks pointing the same way), not a forecast.")
st.markdown("---")

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

# --- Charts ---
st.subheader("Net Liquidity, SPY & Fed Funds Rate")
fig1 = make_subplots(
    rows=2, cols=1, 
    shared_xaxes=True, 
    vertical_spacing=0.08, 
    row_heights=[0.7, 0.3], 
    specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
)

# Top row: Net Liquidity vs SPY
fig1.add_trace(go.Scatter(x=df.index, y=df['Net Liquidity (T)'], name="Net Liquidity (T$)", line=dict(color='#1f77b4')), row=1, col=1, secondary_y=False)
fig1.add_trace(go.Scatter(x=df.index, y=df['SPY'], name="SPY Price", line=dict(color='#2ca02c')), row=1, col=1, secondary_y=True)

# Bottom row: Fed Funds Rate
fig1.add_trace(go.Scatter(x=df.index, y=df['DFF'].ffill(), name="Fed Funds Rate (%)", line=dict(color='#800080')), row=2, col=1)

# Add annotations to top row from events.csv
try:
    events_path = os.path.join(os.path.dirname(__file__), "events.csv")
    events_df = pd.read_csv(events_path)
    events_df['date'] = pd.to_datetime(events_df['date'])
    
    category_colors = {
        "QE": "rgba(44, 160, 44, 0.6)",       # Greenish
        "QT": "rgba(214, 39, 40, 0.6)",       # Reddish
        "Crisis": "rgba(214, 39, 40, 0.9)",   # Darker Red
        "RateHike": "rgba(148, 103, 189, 0.6)" # Purple
    }
    
    for _, row in events_df.iterrows():
        date_obj = row['date']
        label = row['label']
        cat = row['category']
        
        # Only draw if within the current chart's view roughly
        if date_obj >= pd.Timestamp(start_date):
            line_color = category_colors.get(cat, "gray")
            fig1.add_vline(x=date_obj, line_dash="dash", line_color=line_color, opacity=0.8, row=1, col=1)
            fig1.add_annotation(x=date_obj, y=0, text=label, showarrow=False, textangle=-90, yref="y domain", yshift=-10, row=1, col=1)
except Exception as e:
    st.warning(f"Could not load events.csv: {e}")

fig1.update_layout(height=650, hovermode="x unified", legend=dict(orientation="h"))
fig1.update_yaxes(title_text="Rate (%)", row=2, col=1)
apply_time_gridlines(fig1)

st.plotly_chart(fig1, width='stretch')

st.subheader("Liquidity Levers — Levels (the bathtub)")
fig_levels = go.Figure()
fig_levels.add_trace(go.Scatter(x=df.index, y=df['Net Liquidity (T)'], name="Net Liquidity", stackgroup='one', line=dict(color='#1f77b4')))
fig_levels.add_trace(go.Scatter(x=df.index, y=df['WTREGEN']/1000, name="TGA Drain", stackgroup='one', line=dict(color='#d62728')))
fig_levels.add_trace(go.Scatter(x=df.index, y=df['RRPONTSYD']/1000, name="RRP Drain", stackgroup='one', line=dict(color='#ff7f0e')))
fig_levels.add_trace(go.Scatter(x=df.index, y=df['WALCL']/1000, name="Fed Assets (WALCL)", line=dict(color='#98FB98', width=3, dash='dot')))
fig_levels.update_layout(yaxis_title="Trillions ($)", hovermode="x unified", legend=dict(orientation="h"))

apply_time_gridlines(fig_levels)
st.plotly_chart(fig_levels, width='stretch')
st.caption("Levels (the bathtub): The stacked total equals total Fed Assets (WALCL). The blue band is Net Liquidity — the money that actually reaches markets — and the red/orange bands are the TGA and RRP drains.")

st.markdown("---")

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

st.subheader("Asset Race (Indexed Performance)")
# Rebase each asset to 100 based on its first available valid price
first_valid_prices = df[['SPY', 'QQQ', 'BTC', 'GLD']].apply(lambda x: x.loc[x.first_valid_index()])
df_race = (df[['SPY', 'QQQ', 'BTC', 'GLD']] / first_valid_prices) * 100 
fig3 = go.Figure()
if show_spy: fig3.add_trace(go.Scatter(x=df.index, y=df_race['SPY'], name="SPY"))
if show_qqq: fig3.add_trace(go.Scatter(x=df.index, y=df_race['QQQ'], name="QQQ"))
if show_btc: fig3.add_trace(go.Scatter(x=df.index, y=df_race['BTC'], name="BTC"))
if show_gld: fig3.add_trace(go.Scatter(x=df.index, y=df_race['GLD'], name="GLD"))
fig3.update_layout(yaxis_type="log" if use_log else "linear", hovermode="x unified", legend=dict(orientation="h"))
apply_time_gridlines(fig3)
st.plotly_chart(fig3, width='stretch')
st.caption("Each asset is indexed to 100 at its first available date in the selected range; assets that began later (e.g. Bitcoin) start their line later.")

# --- Does liquidity lead prices? (flow vs returns, lagged correlation) ---
st.markdown("---")
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
    fig_lag = go.Figure(go.Bar(x=lags, y=corrs, marker_color=['#1f77b4' if i != best else '#ff7f0e' for i in range(len(lags))]))
    fig_lag.update_layout(height=350, xaxis_title="Liquidity change measured N weeks BEFORE the asset move",
                          yaxis_title="Correlation", yaxis_range=[-1, 1], showlegend=False)
    fig_lag.add_hline(y=0, line_width=1, line_color="white", opacity=0.3)
    st.plotly_chart(fig_lag, width='stretch')
    st.write(f"Strongest link: liquidity change **{best} weeks earlier**, correlation **{corrs[best]:+.2f}** ({n_obs} weekly observations).")
    st.caption(f"Each bar compares the {win}-week change in net liquidity (shifted back N weeks) with the {lag_asset} {win}-week return. "
               "Bars far from zero at higher N suggest liquidity leads the asset. Caution: windows overlap, so effective sample size is much smaller than the count shown, "
               "and correlations shift across eras. Treat this as context, not a trading signal.")

# 🌊 Market Tide: Federal Reserve Net Liquidity & Asset Performance Dashboard

An interactive macro-financial dashboard built in Python to track Federal Reserve balance sheet liquidity dynamics and analyze their impact on major asset classes (S&P 500, Nasdaq, Bitcoin, Gold).

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.58-red.svg)
![Plotly](https://img.shields.io/badge/Plotly-6.8-FF6F00.svg)

---

## 📌 Executive Summary

Central bank liquidity acts as the primary "water level" for asset prices. **Market Tide** quantifies real-time Federal Reserve liquidity injections and drains using economic data from FRED (Federal Reserve Economic Data) and historical market prices from Yahoo Finance.

### **The Net Liquidity Equation**
$$\text{Net Liquidity} = \text{Fed Total Assets (WALCL)} - \text{Treasury General Account (TGA)} - \text{Reverse Repo Facility (RRP)}$$

- **WALCL (Fed Assets):** Total liquidity supplied.
- **TGA (Treasury Drain):** Cash held by the US Treasury that is kept out of the banking system.
- **RRP (Money Market Drain):** Capital parked at the Fed by institutional money funds.

---

## 🔑 Key Features & Analytics

* **Interactive Liquidity Drivers:** Visualizes stacked balance sheet levels and net flow contributions (Monthly / Quarterly) to evaluate driver shifts (e.g., Quantitative Tightening vs. RRP drain).
* **Credit Stress Monitor:** Real-time High-Yield Credit Spread ($BAMLH0A0HYM2$) gauge displaying percentile rankings relative to post-2008 historical distributions.
* **Asset Race Benchmarking:** Indexed performance tracking (Rebased to 100) comparing Net Liquidity trends across SPY, QQQ, BTC, and Gold on linear and logarithmic scales.
* **Macro Event Annotations:** Overlay of historical policy shocks (QE, QT, Repo Market Stress, Rate Hike Cycles).

---

## 🛠️ Tech Stack & API Dependencies

* **Language & Frameworks:** Python, Streamlit
* **Data Pipelines & Wrangling:** `pandas`, `yfinance`, `fredapi`
* **Visualization:** `plotly` (Subplots, dual-y axis, custom time grids)
* **API Integration:** FRED API (Federal Reserve Economic Data)

---

## 🚀 Quickstart & Setup

1. **Get a free FRED API key:** https://fred.stlouisfed.org/docs/api/api_key.html
2. **Create the environment and install dependencies:**
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows (Mac/Linux: source venv/bin/activate)
   pip install -r requirements.txt
   ```
3. **Add your key** to a file named `.env` in this folder:
   ```
   FRED_API_KEY=your_key_here
   ```
4. **Run:**
   ```bash
   streamlit run app.py
   ```

## ☁️ Free Deployment (Streamlit Community Cloud)

1. Push this folder to a GitHub repo (`.env` and `venv/` are git-ignored).
2. At https://share.streamlit.io choose **New app**, select the repo, main file `app.py`.
3. In **Settings > Secrets** add: `FRED_API_KEY = "your_key_here"` (see `.streamlit/secrets.toml.example`).

## 🆕 Verdict & Lead/Lag sections

- **Liquidity Verdict:** 13-week attribution of net liquidity change to Fed assets, TGA and RRP, with a simple regime label.
- **Does Liquidity Lead Prices?:** lagged correlation between net-liquidity change and SPY/QQQ/BTC/GLD returns. Windows overlap, so treat it as context, not a signal.

_Personal context tool, not financial advice._

# Team 95 - Xin Jong Bao
### SG vs HK Quant Trading Hackathon 2026

This repository contains an autonomous quantitative trading engine developed for the **Roostoo 2026 Hackathon**. The strategy is engineered to maximize risk-adjusted returns (Sharpe and Sortino Ratios) by dynamically shifting between aggressive momentum capture and defensive capital preservation.

## 📈 Strategy Architecture

The bot employs a **Dual-Momentum Framework** to navigate the volatile crypto landscape:

1.  **Macro Regime Filter (Absolute Momentum):** The system uses real-world BTC/USDT data from Binance to determine the global market state. By calculating a **48-hour Moving Average**, the bot identifies the "Master Trend." If Bitcoin trades below this average, the system enters "Capital Preservation Mode," liquidating all risky assets to USD.
2.  **Top-5 Asset Selection (Relative Momentum):** When the macro regime is Bullish, the engine scans the 66+ Roostoo assets to identify the top 5 coins with the strongest 24h momentum.
3.  **Anti-Churn Rebalancing:** The engine rebalances every 4 hours to rotate capital into the strongest performers while maintaining existing winners to minimize unnecessary transaction fees.

---

## 🛡️ Risk Management & Mathematics

To protect the **Calmar Ratio** and minimize **Max Drawdown**, the bot utilizes a multi-layered defensive stack:

### 1. The 48-Hour Macro Switch
The bot calculates a Simple Moving Average ($SMA$) over 12 periods of 4-hour candles ($48$ total hours):

$$SMA_{48} = \frac{\sum_{i=1}^{12} Close_{i}}{12}$$

* **Risk-On:** $Current Price > SMA_{48}$ (Deploy Capital)
* **Risk-Off:** $Current Price < SMA_{48}$ (100% Cash/USD)

This filter was instrumental in successfully navigating the **March 22, 2026, market downturn**, where Bitcoin dipped from $76k to sub-$69k. By detecting the trend break early, the system avoided the heavy drawdowns faced by "buy-and-hold" participants.

### 2. Micro-Level Stop-Loss
A dedicated "Fast Loop" monitors all held positions every 5 minutes. If any individual asset drops **3%** from its entry price, it is immediately liquidated, protecting the portfolio from "Black Swan" events in specific altcoins.

---

## ⚙️ Operational Compliance: Tactical "Ping" Trade

To satisfy the **8-day active trading requirement** without taking unnecessary risk during bearish periods, the system includes an automated **Compliance Module**:

* **Logic:** If no organic trades occur by **11:50 AM UTC (7:50 PM SGT/HKT)**, the bot triggers a minimal, low-cost "Ping Trade" (10 units of ZEN).
* **Purpose:** This guarantees 100% daily activity compliance for the leaderboard metrics while maintaining a 99.9%+ cash position during high-volatility regimes.

---

## 🛠️ Tech Stack
* **Language:** Python 3.10
* **Infrastructure:** AWS EC2 (t2.micro)
* **Data Sources:** Binance REST API (Macro) & Roostoo API (Execution)
* **Deployment:** Managed via `tmux` for 24/7 uptime

---

**Current Status:** Successfully navigated the March 2026 geopolitical volatility to secure a **Rank #1 position** on the global leaderboard by prioritizing capital preservation and mathematical trend-following. CAA 1624H 22/3/2026

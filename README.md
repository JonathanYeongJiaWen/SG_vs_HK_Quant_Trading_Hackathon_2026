# Team 95 - Xin Jong Bao
**SG vs HK Quant Trading Hackathon 2026**

# Quantitative Momentum Trading Engine
An automated, data-driven algorithmic trading system optimized for high-volatility crypto environments. The engine utilizes **Relative Strength Momentum** across a dynamic lookback window, integrated with a macro-regime filter to protect capital during bearish cycles.

---

## 🔄 System Update (March 24, 2026)
**Strategic Pivot:** The engine was upgraded from a standard 24-hour momentum tracker to a **4-Hour "News Cycle" Momentum Strategy**. 
* *Reasoning:* Relying solely on exchange-provided 24h rolling data created a "laggard effect," missing sudden macro catalysts. 
* *Implementation:* We integrated the Binance API to fetch live K-line (candlestick) data, calculating custom 4-hour percentage changes. This allows the bot to capture real-time breakouts while outperforming standard 24h-reliant algorithms.

---

## 🚀 Strategy Architecture & Logic

### 1. Macro Regime Filter (The Shield)
Before any trades are executed, the bot assesses the overall market health by checking the **Bitcoin (BTC) 4-Hour Moving Average**.
* **Bullish Regime:** BTC is holding above its moving average. The bot actively scans for momentum leaders.
* **Bearish Regime:** BTC falls below the moving average. The bot executes a hard stop, liquidating all altcoin positions into USD or PAXG (Gold) to preserve capital until the storm passes.

### 2. Cross-Sectional Momentum (Alpha Generation)
Instead of looking for absolute gains, the engine scans the top 15 highest-volume assets and ranks them by **Relative 4-Hour Strength**. It dynamically identifies and purchases the **Top 5** performing assets, ensuring the portfolio is always positioned in the market's fastest-moving vehicles.

### 3. The Buffer Zone (Churn Reduction)
To optimize for trading fees and prevent "whipsawing" (buying and selling the same coin repeatedly due to micro-volatility), the system employs a **Dual-Threshold Buffer**:
* **Entry:** An asset must break into the **Top 5** momentum rankings to be purchased.
* **Exit:** The asset is held loosely and is only sold if it falls out of the **Top 10**. This allows temporary pullbacks without triggering unnecessary taxable/fee-heavy events.

### 4. Hard Stop-Loss (Risk Management)
Every individual asset in the portfolio is protected by a strict **3% Trailing Stop-Loss** relative to its entry price. Even if the macro market remains bullish, idiosyncratic crashes (e.g., a specific coin dumping) are instantly severed.

### 5. Autonomous State Management
The bot features an `auto_heal_memory` function. It constantly cross-references its local JSON memory with the actual exchange wallet balances. This prevents "ghost orders," handles manual interventions gracefully, and ensures exact synchronization without rate-limiting the exchange API.

---

## 🛠️ Technical Stack
* **Language:** Python 3
* **Execution:** AWS EC2 instance running via `tmux` for 24/7 uptime.
* **Frequency:** 5-minute cron-style loop (288 evaluations per day).
* **Data Sources:** Roostoo API (Execution & Balances), Binance API (Real-time K-lines & Pricing logic).

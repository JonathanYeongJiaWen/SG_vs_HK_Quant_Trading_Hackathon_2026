# Team 95 - Xin Jong Bao

## SG vs HK Quant Trading Hackathon 2026
### Quantitative Momentum Trading Engine

An automated, data-driven algorithmic trading system optimized for high-volatility crypto environments. The engine utilizes Relative Strength Momentum across a dynamic lookback window, integrated with a macro-regime filter to protect capital during bearish cycles.

---

### 🔄 System Update (March 25, 2026)

* **Strategic Pivot:** The engine was upgraded from a standard absolute momentum tracker to a **Risk-Adjusted Momentum Strategy**.
* **Reasoning:** The previous iteration suffered from "cash drag" during optimal purchasing windows and was susceptible to whipsawing during sideways market chop.
* **Implementation:** We integrated a Golden Cross moving average crossover for systemic risk detection, True Proportional Allocation for capital efficiency, and a High-Water Mark memory system to actively protect floating profits.

---

### 🚀 Strategy Architecture & Logic

#### 1. Macro Regime Filter (Systemic Risk Mitigation)
Before any trades are executed, the bot assesses overall market health by checking a **Golden Cross Moving Average (20-hour vs. 60-hour SMA)** on Bitcoin (BTC) using 4H K-lines.
* **Bullish Regime:** The fast SMA crosses above the slow SMA. The bot actively scans for momentum leaders and fully deploys capital.
* **Bearish Regime:** The fast SMA crosses below the slow SMA. The bot executes a hard stop, liquidating all altcoin positions and re-allocating 95% of the portfolio into a PAXG (Gold) hedge to preserve capital and reduce beta exposure until the cycle shifts.

#### 2. Cross-Sectional Momentum & Dynamic Sizing (Alpha Generation)
The engine scans a predefined blue-chip whitelist and ranks assets by **Relative 24-Hour Strength**. It dynamically identifies the **Top 5** performing assets. 
* **True Proportional Allocation:** Instead of dividing cash equally, the system applies a rank-based mathematical weighting (Rank 1 receives a higher multiplier than Rank 5). This scales capital directly into the assets proving the highest real-time momentum, while ensuring 100% capital efficiency (zero cash drag).

#### 3. The Buffer Zone (Churn Reduction)
To optimize for trading fees and prevent "whipsawing" (buying and selling the same coin repeatedly due to micro-volatility), the system employs a **Dual-Threshold Buffer**:
* **Entry:** An asset must break into the **Top 5** momentum rankings to be purchased.
* **Exit:** The asset is held loosely and is only sold if it falls out of the **Top 7 Safe Zone**. This allows for temporary pullbacks without triggering unnecessary fee-heavy liquidation events.

#### 4. High-Water Mark Trailing Stop-Loss (Drawdown Protection)
Every individual asset in the portfolio is protected by a strict **6% Trailing Stop-Loss**.
* The system actively records the highest price an asset reaches post-purchase (the High-Water Mark). If an asset drops 6% from its absolute peak, the bot severs the position to lock in floating gains or cap the maximum downside on a false breakout.
* Liquidated assets are placed in a 60-minute penalty timeout to prevent immediate re-entry (revenge trading) during flash crashes.

#### 5. Autonomous State Management & Network Integrity
The bot features an `auto_heal_memory` function, constantly cross-referencing its local JSON memory with actual exchange wallet balances. 
* **API Blackout Safety:** To prevent "Phantom Sells" caused by dropped network packets, the bot verifies the integrity of the data payload. If the Binance API fails to return data for the entire universe, the bot aborts the cycle rather than executing trades on incomplete data.

---

### 🛠️ Technical Stack

* **Language:** Python 3
* **Execution:** AWS EC2 instance running via `tmux` for 24/7 uptime.
* **Frequency:** Dual-Loop Architecture (5-minute fast loop for risk management; 4-hour slow loop for rebalancing).
* **Data Sources:** Roostoo API (Execution & Balances), Binance API (Real-time K-lines & Pricing logic).

---

Note: I changed to this strategy at 25 March 12pm where I was -5% down.

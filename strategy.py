import math
import requests
import datetime
import json
import os

STATE_FILE = "state.json"
STOP_LOSS_THRESHOLD = 0.06 

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                if state.get("last_trade_date"):
                    state["last_trade_date"] = datetime.datetime.strptime(state["last_trade_date"], "%Y-%m-%d").date()
                if "cooldowns" not in state:
                    state["cooldowns"] = {}
                return state
        except: pass
    return {"held_coins": {}, "last_trade_date": None, "cooldowns": {}}

def save_state(state):
    state_copy = state.copy()
    if state_copy.get("last_trade_date"):
        if isinstance(state_copy["last_trade_date"], datetime.date):
            state_copy["last_trade_date"] = state_copy["last_trade_date"].strftime("%Y-%m-%d")
    with open(STATE_FILE, "w") as f:
        json.dump(state_copy, f)

STATE = load_state()

def format_qty(usd_amount, price):
    raw_qty = usd_amount / price
    if price > 1000: return math.floor(raw_qty * 10000) / 10000.0
    elif price > 10: return math.floor(raw_qty * 100) / 100.0
    else: return float(math.floor(raw_qty))

def auto_heal_memory(balance_data, market_data):
    global STATE
    actual_balances = balance_data.get("SpotWallet", {})
    ghosts = [c for c in list(STATE["held_coins"].keys()) if actual_balances.get(c, {}).get("Free", 0) <= 0.001]
    for g in ghosts: del STATE["held_coins"][g]
    for coin, info in actual_balances.items():
        if coin != "USD" and info.get("Free", 0) > 0.001 and coin not in STATE["held_coins"]:
            pair = f"{coin}/USD"
            if pair in market_data:
                price = market_data[pair]["LastPrice"]
                # Save as dict for Trailing Stop-Loss compatibility
                STATE["held_coins"][coin] = {"buy": price, "high": price}
                print(f"Auto-Healed: Synced {coin} bag to memory.")

def get_24h_momentum(coin):
    try:
        symbol = f"{coin}USDT"
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": "4h", "limit": 6}
        data = requests.get(url, params=params, timeout=2).json()
        
        price_24h_ago = float(data[0][4]) 
        current_price = float(data[-1][4]) 
        return (current_price - price_24h_ago) / price_24h_ago
    except: return -999 

def get_real_world_regime():
    """Golden Cross Macro Filter (20-hour vs 60-hour average)"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "4h", "limit": 20} 
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        closes = [float(candle[4]) for candle in data]
        
        fast_ma = sum(closes[-5:]) / 5   # Last 20 hours
        slow_ma = sum(closes[-15:]) / 15 # Last 60 hours
        return fast_ma > slow_ma
    except: 
        return None # PATCH: Return None instead of False on API crash

def check_stop_loss(client):
    """Evaluates the 6% Trailing Stop-Loss against the High Water Mark."""
    global STATE
    if not STATE["held_coins"]: return False
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    if not ticker_data or not balance_data: return False
    
    market_data = ticker_data.get("Data", ticker_data)
    auto_heal_memory(balance_data, market_data)
    
    coins_to_remove = []
    triggered = False
    state_updated = False
    
    for coin, record in list(STATE["held_coins"].items()):
        if coin == "PAXG": continue # DO NOT apply trailing stop-loss to the Macro Hedge
        
        pair = f"{coin}/USD"
        if pair not in market_data: continue
        
        # Backward compatibility: Convert old float formats to dict
        if isinstance(record, (float, int)):
            STATE["held_coins"][coin] = {"buy": float(record), "high": float(record)}
            record = STATE["held_coins"][coin]
            state_updated = True

        current_price = market_data[pair]["LastPrice"]
        
        # Update High Water Mark if the price has gone up
        if current_price > record["high"]:
            STATE["held_coins"][coin]["high"] = current_price
            state_updated = True
            
        drop_percentage = (record["high"] - current_price) / record["high"]
        
        if drop_percentage >= STOP_LOSS_THRESHOLD:
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0:
                resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                if resp and resp.get("Success"):
                    print(f"TRAILING STOP LOSS: {pair} liquidated. Imposing 60-minute ban on {coin}.")
                    coins_to_remove.append(coin)
                    STATE["cooldowns"][coin] = datetime.datetime.utcnow().timestamp() + 3600
                    triggered = True
            
    for coin in coins_to_remove:
        del STATE["held_coins"][coin]
    
    if triggered or state_updated: save_state(STATE)
    return triggered

def run_rebalance(client):
    global STATE
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    if not ticker_data or not balance_data: return

    market_data = ticker_data.get("Data", ticker_data)
    auto_heal_memory(balance_data, market_data)

    current_utc_time = datetime.datetime.utcnow()
    current_utc_date = current_utc_time.date()
    is_bullish = get_real_world_regime()
    
    # PATCH: The Nuclear API Timeout Protector
    if is_bullish is None:
        print("WARNING: Binance API failed to return macro data. Aborting rebalance to prevent false liquidation.")
        return
    
    # --- COOLDOWN CLEANUP ---
    current_ts = current_utc_time.timestamp()
    expired_cooldowns = [c for c, exp in STATE.get("cooldowns", {}).items() if current_ts > exp]
    for c in expired_cooldowns:
        del STATE["cooldowns"][c]
        print(f"Cooldown expired for {c}. Eligible for momentum re-entry.")
        save_state(STATE)

    # --- THE BEARISH SHIELD ---
    if not is_bullish:
        print(f"[{current_utc_time}] Macro: BEARISH. Hedging.")
        traded_today = False
        for coin in list(STATE["held_coins"].keys()):
            if coin != "PAXG":
                pair = f"{coin}/USD"
                held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
                if held_amount > 0.001:
                    resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                    if resp and resp.get("Success"):
                        print(f"Liquidated {coin}.")
                        traded_today = True
                        del STATE["held_coins"][coin]
        
        # Unrestricted Hedge Entry (95% Capital Deployment)
        usd_balance = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
        if "PAXG/USD" in market_data and usd_balance > 10 and "PAXG" not in STATE["held_coins"]:
            price = market_data["PAXG/USD"]["LastPrice"]
            qty = format_qty(usd_balance * 0.95, price)
            resp = client.place_order(pair="PAXG/USD", side="BUY", order_type="MARKET", quantity=qty)
            if resp and resp.get("Success"):
                print("Hedged into PAXG (Gold).")
                STATE["held_coins"]["PAXG"] = {"buy": price, "high": price}
                traded_today = True
        
        if traded_today: save_state(STATE)
        return

    # --- THE BULLISH OFFENSE ---
    print(f"[{current_utc_time}] Macro: BULLISH. Ranking Blue-Chips by 24H Momentum...")
    
    # LIQUIDATE HEDGE ON BULLISH FLIP
    if "PAXG" in STATE["held_coins"]:
        held_amount = balance_data.get("SpotWallet", {}).get("PAXG", {}).get("Free", 0)
        if held_amount > 0.001:
            resp = client.place_order(pair="PAXG/USD", side="SELL", order_type="MARKET", quantity=held_amount)
            if resp and resp.get("Success"):
                print("Macro turned BULLISH. Sold PAXG hedge to re-deploy capital.")
                del STATE["held_coins"]["PAXG"] # Safe deletion
        else:
            del STATE["held_coins"]["PAXG"] # Clean up dust

    WHITELIST = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK"]
    
    candidates = []
    for pair, info in market_data.items():
        if type(info) == dict and "/USD" in pair:
            coin_name = pair.split('/')[0]
            if coin_name in WHITELIST:
                candidates.append((coin_name, info.get("Change", 0)))
    
    # Network Vulnerability Patch: Abort if API fails to return data
    if not candidates:
        print("WARNING: API failed to return data. Aborting rebalance to prevent false liquidations.")
        return

    candidates.sort(key=lambda x: x[1], reverse=True)
    
    momentum_list = []
    for coin, _ in candidates:
        m24 = get_24h_momentum(coin)
        if m24 != -999:
            momentum_list.append((coin, m24))

    # --- THE PHANTOM SELL PROTECTOR ---
    if len(momentum_list) < len(candidates):
        dropped_count = len(candidates) - len(momentum_list)
        print(f"WARNING: Binance API dropped data for {dropped_count} coin(s). Aborting rebalance to prevent phantom liquidations.")
        return

    momentum_list.sort(key=lambda x: x[1], reverse=True)
    
    top_5_names = [x[0] for x in momentum_list[:5]]
    safe_zone_names = [x[0] for x in momentum_list[:7]]

    traded_today = False
    for coin in list(STATE["held_coins"].keys()):
        if coin not in safe_zone_names and coin != "PAXG":
            pair = f"{coin}/USD"
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0.001:
                resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                if resp and resp.get("Success"):
                    print(f"24H Exit: {coin} hit the lowest momentum rank. Liquidating.")
                    traded_today = True
                    del STATE["held_coins"][coin]
            
    balance_data = client.get_balance()
    current_usd = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
    open_slots = 5 - len([c for c in STATE["held_coins"] if c != "PAXG"])
    
    to_buy_candidates = [c for c in top_5_names if c not in STATE["held_coins"] and c not in STATE.get("cooldowns", {})]
    
    if open_slots > 0 and to_buy_candidates and current_usd > 10:
        to_buy = to_buy_candidates[:open_slots]
        
        # 1. Determine exactly how much of our total USD is allowed to be spent right now
        usd_to_spend = (current_usd * 0.95) * (len(to_buy) / open_slots)
        
        # 2. Sum the weights of ONLY the coins we are actually buying
        total_weight = sum([5 - top_5_names.index(c) for c in to_buy])
        
        for coin in to_buy:
            coin_weight = 5 - top_5_names.index(coin)
            
            # 3. True Proportional Allocation: Distribute the exact spendable cash by weight
            usd_allocated = usd_to_spend * (coin_weight / total_weight)
            
            pair = f"{coin}/USD"
            price = market_data[pair]["LastPrice"]
            qty = format_qty(usd_allocated, price)
            
            resp = client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=qty)
            if resp and resp.get("Success"):
                weight_percent = (coin_weight / total_weight) * 100
                print(f"Entry: Purchased {coin} (Allocated {weight_percent:.1f}% of available spend).")
                STATE["held_coins"][coin] = {"buy": price, "high": price}
                traded_today = True
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
        save_state(STATE)
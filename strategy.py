import math
import requests
import datetime
import json
import os

STATE_FILE = "state.json"
STOP_LOSS_THRESHOLD = 0.06 # Loosened to 6% to prevent whipsawing

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
                STATE["held_coins"][coin] = market_data[pair]["LastPrice"]
                print(f"Auto-Healed: Synced {coin} bag to memory.")

def get_24h_momentum(coin):
    """Fetches real-world 24h performance from Binance."""
    try:
        symbol = f"{coin}USDT"
        if coin in ["PEPE", "SHIB", "BONK", "CHEEMS"]: symbol = f"1000{coin}USDT"
        
        url = "https://api.binance.com/api/v3/klines"
        # 6 candles of 4 hours = 24 hours of data
        params = {"symbol": symbol, "interval": "4h", "limit": 6}
        data = requests.get(url, params=params, timeout=2).json()
        
        price_24h_ago = float(data[0][4]) 
        current_price = float(data[-1][4]) 
        return (current_price - price_24h_ago) / price_24h_ago
    except: return -999 

def get_real_world_regime():
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "4h", "limit": 6} 
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        closes = [float(candle[4]) for candle in data]
        return closes[-1] > (sum(closes) / len(closes))
    except: return False

def check_stop_loss(client):
    global STATE
    if not STATE["held_coins"]: return False
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    if not ticker_data or not balance_data: return False
    
    market_data = ticker_data.get("Data", ticker_data)
    auto_heal_memory(balance_data, market_data)
    
    coins_to_remove = []
    triggered = False
    
    for coin, buy_price in STATE["held_coins"].items():
        pair = f"{coin}/USD"
        if pair not in market_data: continue
        current_price = market_data[pair]["LastPrice"]
        drop_percentage = (buy_price - current_price) / buy_price
        
        if drop_percentage >= STOP_LOSS_THRESHOLD:
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0:
                resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                if resp and resp.get("Success"):
                    print(f"STOP LOSS: {pair} liquidated. Imposing 60-minute ban on {coin}.")
                    coins_to_remove.append(coin)
                    # Add to cooldowns: Current UTC Timestamp + 3600 seconds
                    STATE["cooldowns"][coin] = datetime.datetime.utcnow().timestamp() + 3600
                    triggered = True
            
    for coin in coins_to_remove:
        del STATE["held_coins"][coin]
    
    if triggered: save_state(STATE)
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
    
    # --- COOLDOWN CLEANUP ---
    current_ts = current_utc_time.timestamp()
    expired_cooldowns = [c for c, exp in STATE.get("cooldowns", {}).items() if current_ts > exp]
    for c in expired_cooldowns:
        del STATE["cooldowns"][c]
        print(f"Cooldown expired for {c}. Eligible for momentum re-entry.")
        save_state(STATE)

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
        
        if STATE["last_trade_date"] != current_utc_date:
            if current_utc_time.hour in [11, 14, 15]: 
                usd_balance = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
                if "PAXG/USD" in market_data and usd_balance > 10:
                    price = market_data["PAXG/USD"]["LastPrice"]
                    qty = format_qty(usd_balance * 0.05, price)
                    resp = client.place_order(pair="PAXG/USD", side="BUY", order_type="MARKET", quantity=qty)
                    if resp and resp.get("Success"):
                        STATE["held_coins"]["PAXG"] = price
                        STATE["last_trade_date"] = current_utc_date
                        traded_today = True
        
        if traded_today: save_state(STATE)
        return

    print(f"[{current_utc_time}] Macro: BULLISH. Ranking by 24H Momentum...")
    
    candidates = []
    for pair, info in market_data.items():
        if type(info) == dict and "/USD" in pair and pair not in ["USDT/USD", "USDC/USD", "PAXG/USD"]:
            candidates.append((pair.split('/')[0], info.get("Change", 0)))
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    momentum_list = []
    for coin, _ in candidates[:15]:
        m24 = get_24h_momentum(coin)
        if m24 != -999:
            momentum_list.append((coin, m24))

    momentum_list.sort(key=lambda x: x[1], reverse=True)
    top_5_names = [x[0] for x in momentum_list[:5]]
    top_10_names = [x[0] for x in momentum_list[:10]]

    traded_today = False
    for coin in list(STATE["held_coins"].keys()):
        if coin not in top_10_names:
            pair = f"{coin}/USD"
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0.001:
                resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                if resp and resp.get("Success"):
                    print(f"24H Exit: {coin} faded.")
                    traded_today = True
                    del STATE["held_coins"][coin]
            
    balance_data = client.get_balance()
    current_usd = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
    open_slots = 5 - len(STATE["held_coins"])
    
    # --- FILTER OUT COOLDOWN COINS ---
    to_buy_candidates = [c for c in top_5_names if c not in STATE["held_coins"] and c not in STATE.get("cooldowns", {})]
    
    if open_slots > 0 and to_buy_candidates and current_usd > 10:
        to_buy = to_buy_candidates[:open_slots]
        usd_per_coin = (current_usd * 0.95) / len(to_buy)
        for coin in to_buy:
            pair = f"{coin}/USD"
            price = market_data[pair]["LastPrice"]
            qty = format_qty(usd_per_coin, price)
            resp = client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=qty)
            if resp and resp.get("Success"):
                print(f"24H Entry: Purchased {coin}.")
                STATE["held_coins"][coin] = price
                traded_today = True
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
        save_state(STATE)
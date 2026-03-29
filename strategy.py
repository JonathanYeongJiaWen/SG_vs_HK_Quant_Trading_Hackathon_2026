import math
import requests
import datetime
import json
import os

STATE_FILE = "state.json"
STOP_LOSS_THRESHOLD = 0.15 

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
    """Updated to track both Free and Locked balances for Limit Orders."""
    global STATE
    actual_balances = balance_data.get("SpotWallet", {})
    
    ghosts = []
    for c in list(STATE["held_coins"].keys()):
        free_bal = actual_balances.get(c, {}).get("Free", 0)
        locked_bal = actual_balances.get(c, {}).get("Locked", 0)
        if (free_bal + locked_bal) <= 0.001:
            ghosts.append(c)
            
    for g in ghosts: del STATE["held_coins"][g]
    
    for coin, info in actual_balances.items():
        if coin != "USD":
            total_bal = info.get("Free", 0) + info.get("Locked", 0)
            if total_bal > 0.001 and coin not in STATE["held_coins"]:
                pair = f"{coin}/USD"
                if pair in market_data:
                    price = market_data[pair]["LastPrice"]
                    STATE["held_coins"][coin] = {"buy": price, "high": price}
                    print(f"Auto-Healed: Synced {coin} bag to memory (includes locked funds).")

def get_fast_momentum(coin):
    try:
        symbol = f"{coin}USDT"
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": "1h", "limit": 4} 
        data = requests.get(url, params=params, timeout=2).json()
        
        price_start = float(data[0][4]) 
        price_end = float(data[-1][4]) 
        return (price_end - price_start) / price_start
    except: 
        return -999 

def get_real_world_regime():
    return True

def sweep_open_orders(client):
    """Cancels all open limit orders so locked funds return to the Free balance."""
    try:
        open_orders_resp = client.get_open_orders()
        if not open_orders_resp: return
        
        # Handle dict or list depending on Roostoo API response format
        orders = open_orders_resp.get("Data", open_orders_resp) if isinstance(open_orders_resp, dict) else open_orders_resp
        
        if isinstance(orders, list) and len(orders) > 0:
            print(f"Sweeping {len(orders)} hanging open order(s)...")
            for order in orders:
                # APIs usually return 'order_id' or 'id'
                order_id = order.get("order_id") or order.get("id")
                pair = order.get("pair")
                if order_id:
                    client.cancel_order(order_id=order_id, pair=pair)
                    print(f"Cancelled hanging order {order_id} for {pair}.")
    except Exception as e:
        print(f"WARNING: Failed to sweep open orders. Error: {e}")
        
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
    state_updated = False
    
    for coin, record in list(STATE["held_coins"].items()):
        if coin == "PAXG": continue 
        
        pair = f"{coin}/USD"
        if pair not in market_data: continue
        
        if isinstance(record, (float, int)):
            STATE["held_coins"][coin] = {"buy": float(record), "high": float(record)}
            record = STATE["held_coins"][coin]
            state_updated = True

        current_price = market_data[pair]["LastPrice"]
        
        if current_price > record["high"]:
            STATE["held_coins"][coin]["high"] = current_price
            state_updated = True
            
        drop_percentage = (record["high"] - current_price) / record["high"]
        
        if drop_percentage >= STOP_LOSS_THRESHOLD:
            # We only sell the "Free" balance. If it's already in a pending limit order, it will be in "Locked".
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0:
                resp = client.place_order(pair=pair, side="SELL", order_type="LIMIT", quantity=held_amount, price=current_price)
                if resp and resp.get("Success"):
                    print(f"TRAILING STOP LOSS: {pair} limit sell placed at {current_price}. Imposing 60-minute ban on {coin}.")
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
    
    current_ts = current_utc_time.timestamp()
    expired_cooldowns = [c for c, exp in STATE.get("cooldowns", {}).items() if current_ts > exp]
    for c in expired_cooldowns:
        del STATE["cooldowns"][c]
        print(f"Cooldown expired for {c}. Eligible for re-entry.")
        save_state(STATE)

    print(f"[{current_utc_time}] Scanning ALL assets for extreme momentum...")

    candidates = []
    for pair, info in market_data.items():
        if type(info) == dict and "/USD" in pair:
            coin_name = pair.split('/')[0]
            if coin_name not in ["USDT", "USDC", "PAXG"]:
                candidates.append((coin_name, info.get("Change", 0)))
    
    if not candidates:
        print("WARNING: API failed to return data. Aborting.")
        return

    candidates.sort(key=lambda x: x[1], reverse=True)
    top_20_candidates = candidates[:20]

    momentum_list = []
    for coin, _ in top_20_candidates:
        m_fast = get_fast_momentum(coin)
        if m_fast != -999:
            momentum_list.append((coin, m_fast))

    # The strict Binance Mismatch abort check has been removed.
    # The bot will proceed with whatever coins it successfully pulled.

    momentum_list.sort(key=lambda x: x[1], reverse=True)
    
    top_5_names = [x[0] for x in momentum_list[:5]]
    safe_zone_names = [x[0] for x in momentum_list[:7]]

    traded_today = False
    for coin in list(STATE["held_coins"].keys()):
        if coin not in safe_zone_names and coin != "PAXG":
            pair = f"{coin}/USD"
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0.001:
                current_price = market_data.get(pair, {}).get("LastPrice", 0)
                if current_price > 0:
                    resp = client.place_order(pair=pair, side="SELL", order_type="LIMIT", quantity=held_amount, price=current_price)
                    if resp and resp.get("Success"):
                        print(f"Exit: {coin} fell out of top momentum. Limit sell placed at {current_price}.")
                        traded_today = True
                        del STATE["held_coins"][coin]
            
    balance_data = client.get_balance()
    current_usd = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
    open_slots = 5 - len([c for c in STATE["held_coins"] if c != "PAXG"])
    
    to_buy_candidates = [c for c in top_5_names if c not in STATE["held_coins"] and c not in STATE.get("cooldowns", {})]
    
    if open_slots > 0 and to_buy_candidates and current_usd > 10:
        to_buy = to_buy_candidates[:open_slots]
        
        usd_to_spend = (current_usd * 0.95) * (len(to_buy) / open_slots)
        total_weight = sum([5 - top_5_names.index(c) for c in to_buy])
        
        for coin in to_buy:
            coin_weight = 5 - top_5_names.index(coin)
            usd_allocated = usd_to_spend * (coin_weight / total_weight)
            
            pair = f"{coin}/USD"
            price = market_data[pair]["LastPrice"]
            qty = format_qty(usd_allocated, price)
            
            resp = client.place_order(pair=pair, side="BUY", order_type="LIMIT", quantity=qty, price=price)
            if resp and resp.get("Success"):
                weight_percent = (coin_weight / total_weight) * 100
                print(f"Entry: Limit buy placed for {coin} at {price} (Allocated {weight_percent:.1f}%).")
                STATE["held_coins"][coin] = {"buy": price, "high": price}
                traded_today = True
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
        save_state(STATE)
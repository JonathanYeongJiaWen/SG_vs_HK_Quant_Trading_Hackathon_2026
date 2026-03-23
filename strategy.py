import math
import requests
import datetime
import json
import os

STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                if state.get("last_trade_date"):
                    state["last_trade_date"] = datetime.datetime.strptime(state["last_trade_date"], "%Y-%m-%d").date()
                return state
        except: pass
    return {"held_coins": {}, "last_trade_date": None}

def save_state(state):
    state_copy = state.copy()
    if state_copy.get("last_trade_date"):
        if isinstance(state_copy["last_trade_date"], datetime.date):
            state_copy["last_trade_date"] = state_copy["last_trade_date"].strftime("%Y-%m-%d")
    with open(STATE_FILE, "w") as f:
        json.dump(state_copy, f)

STATE = load_state()
STOP_LOSS_THRESHOLD = 0.03 

def format_qty(usd_amount, price):
    """Smart rounding to bypass Roostoo step size errors."""
    raw_qty = usd_amount / price
    if price > 1000: return math.floor(raw_qty * 10000) / 10000.0
    elif price > 10: return math.floor(raw_qty * 100) / 100.0
    else: return float(math.floor(raw_qty))

def auto_heal_memory(balance_data, market_data):
    """Syncs the bot's memory with actual exchange balances."""
    global STATE
    actual_balances = balance_data.get("SpotWallet", {})
    
    # Remove ghost coins (in memory but 0 balance)
    ghosts = [c for c in list(STATE["held_coins"].keys()) if actual_balances.get(c, {}).get("Free", 0) <= 0.001]
    for g in ghosts: del STATE["held_coins"][g]
        
    # Add real unrecorded coins (like the massive WIF bag)
    for coin, info in actual_balances.items():
        if coin != "USD" and info.get("Free", 0) > 0.001 and coin not in STATE["held_coins"]:
            pair = f"{coin}/USD"
            if pair in market_data:
                STATE["held_coins"][coin] = market_data[pair]["LastPrice"]
                print(f"Auto-Healed Memory: Found {info.get('Free')} of {coin}")

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
                if resp and resp.get("Success") is True:
                    print(f"STOP LOSS: {pair} liquidated successfully.")
                    coins_to_remove.append(coin)
                    triggered = True
            
    for coin in coins_to_remove:
        del STATE["held_coins"][coin]
    
    if triggered: save_state(STATE)
    return triggered

def get_real_world_regime():
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "4h", "limit": 6} 
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        closes = [float(candle[4]) for candle in data]
        return closes[-1] > (sum(closes) / len(closes))
    except:
        return False

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
    
    if not is_bullish:
        print(f"[{current_utc_time}] Macro: BEARISH. Protecting capital.")
        traded_today = False
        
        for coin in list(STATE["held_coins"].keys()):
            if coin != "PAXG":
                pair = f"{coin}/USD"
                held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
                if held_amount > 0.001:
                    resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                    if resp and resp.get("Success") is True:
                        print(f"Liquidated {coin} to USD.")
                        traded_today = True
                        del STATE["held_coins"][coin]
        
        if STATE["last_trade_date"] != current_utc_date:
            if current_utc_time.hour in [11, 14, 15]: 
                usd_balance = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
                if "PAXG/USD" in market_data and usd_balance > 0:
                    gold_price = market_data["PAXG/USD"]["LastPrice"]
                    buy_qty = format_qty(usd_balance * 0.05, gold_price)
                    resp = client.place_order(pair="PAXG/USD", side="BUY", order_type="MARKET", quantity=buy_qty)
                    if resp and resp.get("Success") is True:
                        print("Daily activity trade: Bought PAXG Hedge.")
                        STATE["held_coins"]["PAXG"] = gold_price
                        STATE["last_trade_date"] = current_utc_date
                        traded_today = True
        
        if traded_today: save_state(STATE)
        return

    print(f"[{current_utc_time}] Macro: BULLISH. Aggressive mode.")
    valid_pairs = []
    for pair, info in market_data.items():
        if type(info) == dict and "/USD" in pair and pair not in ["USDT/USD", "USDC/USD", "PAXG/USD"]:
            if info.get("Change", 0) > 0:
                valid_pairs.append((pair, info.get("Change", 0)))
            
    valid_pairs.sort(key=lambda x: x[1], reverse=True)
    top_5_coins = [x[0].split('/')[0] for x in valid_pairs[:5]]

    traded_today = False
    
    # Sell losers
    for coin in list(STATE["held_coins"].keys()):
        if coin not in top_5_coins:
            pair = f"{coin}/USD"
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0.001:
                resp = client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                if resp and resp.get("Success") is True:
                    print(f"Liquidated {coin} (fell out of Top 5).")
                    traded_today = True
                    del STATE["held_coins"][coin]
            
    # Buy winners
    balance_data = client.get_balance()
    current_usd = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
    coins_to_buy = [c for c in top_5_coins if c not in STATE["held_coins"]]
    
    if coins_to_buy and current_usd > 10:
        usd_per_coin = (current_usd * 0.95) / len(coins_to_buy)
        for coin in coins_to_buy:
            pair = f"{coin}/USD"
            if pair in market_data:
                price = market_data[pair]["LastPrice"]
                qty = format_qty(usd_per_coin, price)
                resp = client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=qty)
                if resp and resp.get("Success") is True:
                    print(f"Successfully purchased {coin}.")
                    STATE["held_coins"][coin] = price
                    traded_today = True
                else:
                    print(f"FAILED to buy {coin}. Reason: {resp.get('ErrMsg', 'Unknown')}")
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
        save_state(STATE)
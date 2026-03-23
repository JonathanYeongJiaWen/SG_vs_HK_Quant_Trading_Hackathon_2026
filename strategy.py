import math
import requests
import datetime
import json
import os

# --- PERSISTENCE LOGIC ---
STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                if state.get("last_trade_date"):
                    state["last_trade_date"] = datetime.datetime.strptime(state["last_trade_date"], "%Y-%m-%d").date()
                return state
        except Exception as e:
            print(f"Error loading state: {e}")
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

def check_stop_loss(client):
    """Restored Stop-Loss Function"""
    global STATE
    if not STATE["held_coins"]: return False
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    if not ticker_data or not balance_data: return False
    
    market_data = ticker_data["Data"]
    coins_to_remove = []
    triggered = False
    
    for coin, buy_price in STATE["held_coins"].items():
        pair = f"{coin}/USD"
        if pair not in market_data: continue
        current_price = market_data[pair]["LastPrice"]
        drop_percentage = (buy_price - current_price) / buy_price
        
        if drop_percentage >= STOP_LOSS_THRESHOLD:
            print(f"STOP LOSS: {pair} liquidated.")
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
            coins_to_remove.append(coin)
            triggered = True
            
    for coin in coins_to_remove:
        del STATE["held_coins"][coin]
    
    if triggered: save_state(STATE)
    return triggered

def get_real_world_regime():
    """24-Hour Moving Average Filter (6 candles * 4 hours)"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "4h", "limit": 6} 
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        closes = [float(candle[4]) for candle in data]
        current_price = closes[-1]
        moving_avg = sum(closes) / len(closes)
        return current_price > moving_avg
    except Exception as e:
        print(f"Binance API Error: {e}")
        return False

def run_rebalance(client):
    global STATE
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    if not ticker_data or not balance_data: return

    market_data = ticker_data["Data"]
    current_utc_time = datetime.datetime.utcnow()
    current_utc_date = current_utc_time.date()

    # ==========================================
    # STEP 1: Macro Filter & Defensive Hedge
    # ==========================================
    is_bullish = get_real_world_regime()
    
    if not is_bullish:
        print(f"[{current_utc_time}] Macro: BEARISH (24h MA). Protecting capital.")
        traded_today = False
        
        for coin in list(STATE["held_coins"].keys()):
            if coin != "PAXG":
                pair = f"{coin}/USD"
                held_amount = balance_data["SpotWallet"][coin]["Free"]
                if held_amount > 0.001:
                    print(f"Liquidating {coin} to USD...")
                    client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                    traded_today = True
                del STATE["held_coins"][coin]
        
        # Extended window to Hours 11, 14, and 15 UTC to guarantee execution right now
        if STATE["last_trade_date"] != current_utc_date:
            if current_utc_time.hour in [11, 14, 15]: 
                print("Daily activity trade triggered: Buying PAXG Hedge.")
                usd
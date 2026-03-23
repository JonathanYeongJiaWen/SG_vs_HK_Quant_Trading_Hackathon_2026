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
                # Convert string date back to date object
                if state.get("last_trade_date"):
                    state["last_trade_date"] = datetime.datetime.strptime(state["last_trade_date"], "%Y-%m-%d").date()
                return state
        except Exception as e:
            print(f"Error loading state: {e}")
    return {"held_coins": {}, "last_trade_date": None}

def save_state(state):
    state_copy = state.copy()
    if state_copy.get("last_trade_date"):
        # Convert date object to string for JSON
        if isinstance(state_copy["last_trade_date"], datetime.date):
            state_copy["last_trade_date"] = state_copy["last_trade_date"].strftime("%Y-%m-%d")
    with open(STATE_FILE, "w") as f:
        json.dump(state_copy, f)

STATE = load_state()
STOP_LOSS_THRESHOLD = 0.03 

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
        
        # Liquidate everything except safe-haven PAXG
        for coin in list(STATE["held_coins"].keys()):
            if coin != "PAXG":
                pair = f"{coin}/USD"
                held_amount = balance_data["SpotWallet"][coin]["Free"]
                if held_amount > 0.001:
                    print(f"Liquidating {coin} to USD...")
                    client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                    traded_today = True
                del STATE["held_coins"][coin]
        
        # ACTIVITY RULE: Buy PAXG if no trades yet.
        # Window set to 11 (7PM SGT) or 14 (10PM SGT) to fix today's miss.
        if STATE["last_trade_date"] != current_utc_date:
            if current_utc_time.hour in [11, 14, 15]: 
                print("Daily activity trade triggered: Buying PAXG Hedge.")
                usd_balance = balance_data["SpotWallet"]["USD"]["Free"]
                gold_price = market_data["PAXG/USD"]["LastPrice"]
                buy_qty = (usd_balance * 0.05) / gold_price
                
                client.place_order(pair="PAXG/USD", side="BUY", order_type="MARKET", quantity=buy_qty)
                STATE["held_coins"]["PAXG"] = gold_price
                STATE["last_trade_date"] = current_utc_date
                traded_today = True
        
        if traded_today: save_state(STATE)
        return

    # ==========================================
    # STEP 2: Momentum Logic (Bullish)
    # ==========================================
    print(f"[{current_utc_time}] Macro: BULLISH. Aggressive mode.")
    valid_pairs = []
    for pair, info in market_data.items():
        if "/USD" in pair and pair not in ["USDT/USD", "USDC/USD", "PAXG/USD"]:
            if info.get("Change", 0) > 0:
                valid_pairs.append((pair, info.get("Change", 0)))
            
    valid_pairs.sort(key=lambda x: x[1], reverse=True)
    top_5_coins = [x[0].split('/')[0] for x in valid_pairs[:5]]

    traded_today = False
    # Sell losers
    for coin in list(STATE["held_coins"].keys()):
        if coin not in top_5_coins:
            pair = f"{coin}/USD"
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            if held_amount > 0.001:
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                traded_today = True
            del STATE["held_coins"][coin]
            
    # Buy winners
    balance_data = client.get_balance()
    current_usd = balance_data["SpotWallet"]["USD"]["Free"]
    coins_to_buy = [c for c in top_5_coins if c not in STATE["held_coins"]]
    
    if coins_to_buy:
        usd_per_coin = (current_usd * 0.95) / len(coins_to_buy)
        for coin in coins_to_buy:
            pair = f"{coin}/USD"
            price = market_data[pair]["LastPrice"]
            qty = math.floor((usd_per_coin / price) * 100) / 100.0
            client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=qty)
            STATE["held_coins"][coin] = price
            traded_today = True
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
        save_state(STATE)
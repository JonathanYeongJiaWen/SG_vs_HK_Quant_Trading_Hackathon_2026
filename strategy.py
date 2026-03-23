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
        except:
            pass
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
    global STATE
    if not STATE["held_coins"]: return False
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    if not ticker_data or not balance_data: return False
    
    # API Crash Fix 1: Safe fallback
    market_data = ticker_data.get("Data", ticker_data)
    coins_to_remove = []
    triggered = False
    
    for coin, buy_price in STATE["held_coins"].items():
        pair = f"{coin}/USD"
        if pair not in market_data: continue
        current_price = market_data[pair]["LastPrice"]
        drop_percentage = (buy_price - current_price) / buy_price
        
        if drop_percentage >= STOP_LOSS_THRESHOLD:
            # API Crash Fix 2: Safe dictionary navigation
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0:
                print(f"STOP LOSS: {pair} liquidated.")
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
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

    # API Crash Fix 1: Safe fallback
    market_data = ticker_data.get("Data", ticker_data)

    current_utc_time = datetime.datetime.utcnow()
    current_utc_date = current_utc_time.date()

    is_bullish = get_real_world_regime()
    
    if not is_bullish:
        print(f"[{current_utc_time}] Macro: BEARISH (24h MA). Protecting capital.")
        traded_today = False
        
        for coin in list(STATE["held_coins"].keys()):
            if coin != "PAXG":
                pair = f"{coin}/USD"
                # API Crash Fix 2: Safe dictionary navigation
                held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
                if held_amount > 0.001:
                    print(f"Liquidating {coin} to USD...")
                    client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                    traded_today = True
                del STATE["held_coins"][coin]
        
        if STATE["last_trade_date"] != current_utc_date:
            if current_utc_time.hour in [11, 14, 15]: 
                print("Daily activity trade triggered: Buying PAXG Hedge.")
                usd_balance = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
                if "PAXG/USD" in market_data and usd_balance > 0:
                    gold_price = market_data["PAXG/USD"]["LastPrice"]
                    buy_qty = (usd_balance * 0.05) / gold_price
                    client.place_order(pair="PAXG/USD", side="BUY", order_type="MARKET", quantity=buy_qty)
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
    for coin in list(STATE["held_coins"].keys()):
        if coin not in top_5_coins:
            pair = f"{coin}/USD"
            held_amount = balance_data.get("SpotWallet", {}).get(coin, {}).get("Free", 0)
            if held_amount > 0.001:
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                traded_today = True
            del STATE["held_coins"][coin]
            
    balance_data = client.get_balance()
    current_usd = balance_data.get("SpotWallet", {}).get("USD", {}).get("Free", 0)
    coins_to_buy = [c for c in top_5_coins if c not in STATE["held_coins"]]
    
    if coins_to_buy and current_usd > 0:
        usd_per_coin = (current_usd * 0.95) / len(coins_to_buy)
        for coin in coins_to_buy:
            pair = f"{coin}/USD"
            if pair in market_data:
                price = market_data[pair]["LastPrice"]
                
                # Round quantity to handle precision errors on meme coins
                qty = round((usd_per_coin / price), 4) 
                
                print(f"Attempting to buy {qty} of {coin}...")
                order_response = client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=qty)
                
                print(f"Roostoo API Response: {order_response}")
                
                # ONLY save to memory if the exchange confirms the trade
                if order_response and order_response.get("Success") is True:
                    STATE["held_coins"][coin] = price
                    traded_today = True
                    print(f"Successfully purchased {coin}.")
                else:
                    print(f"FAILED to buy {coin}. Reason: {order_response.get('ErrMsg', 'Unknown')}")
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
        save_state(STATE)
import math
import requests
import datetime

STATE = {
    "held_coins": {},
    "last_trade_date": None 
}

STOP_LOSS_THRESHOLD = 0.03 

def check_stop_loss(client):
    """The Fast Loop (Defense): Checks all currently held assets."""
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
            print(f"STOP LOSS ALERT! {pair} dropped {drop_percentage*100:.2f}%.")
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
            coins_to_remove.append(coin)
            triggered = True
            
    for coin in coins_to_remove:
        del STATE["held_coins"][coin]
        
    return triggered

def get_real_world_regime():
    """Fetches real-world BTC data from Binance (48-Hour Macro Filter)."""
    try:
        url = "https://api.binance.com/api/v3/klines"
        # Adjusted to 12 periods of 4H candles = 48 hours
        params = {"symbol": "BTCUSDT", "interval": "4h", "limit": 12} 
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        closes = [float(candle[4]) for candle in data]
        current_price = closes[-1]
        moving_average = sum(closes) / len(closes)
        
        return current_price > moving_average
    except Exception as e:
        print(f"External Data Error: {e}. Defaulting to safe mode.")
        return False

def run_rebalance(client):
    """The Slow Loop (Offense): Top-5 Momentum & Activity Logging."""
    global STATE
    
    print("Fetching market data for rebalance...")
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    
    if not ticker_data or not balance_data:
        print("API Error: Failed to fetch data.")
        return

    market_data = ticker_data["Data"]
    
    # Grab current UTC time to sync with the 8:00 PM HKT reset (12:00 PM UTC)
    current_utc_time = datetime.datetime.utcnow()
    current_utc_date = current_utc_time.date()

    # ==========================================
    # STEP 1: The Macro Regime Filter & Ping Trade
    # ==========================================
    is_bullish = get_real_world_regime()
    
    if not is_bullish:
        print("Macro Regime is BEARISH. Checking for needed liquidations...")
        traded_today = False
        
        for coin in list(STATE["held_coins"].keys()):
            pair = f"{coin}/USD"
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            if held_amount > 0.001:
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                traded_today = True
                
        STATE["held_coins"].clear()
        
        if traded_today:
            STATE["last_trade_date"] = current_utc_date
            
        # The Ping Trade: Triggers only if no trades happened today, 
        # and only between 11:00 AM and 11:59 AM UTC (7:00 PM - 7:59 PM HKT)
        if STATE["last_trade_date"] != current_utc_date:
            if current_utc_time.hour == 11: 
                print("Approaching daily cutoff. Executing minimal ping trade...")
                client.place_order(pair="ZEN/USD", side="BUY", order_type="MARKET", quantity=10.0)
                client.place_order(pair="ZEN/USD", side="SELL", order_type="MARKET", quantity=10.0)
                STATE["last_trade_date"] = current_utc_date
                print("Ping trade complete. Daily activity logged.")
            else:
                print(f"Standing by safely in cash. Will check ping logic closer to cutoff.")
        return

    # ==========================================
    # STEP 2: Find the Top 5 Momentum Coins
    # ==========================================
    print("Macro Regime is BULLISH. Scanning for top 5 momentum assets...")
    exclude_list = ["USDT/USD", "USDC/USD"]
    valid_pairs = []
    
    for pair, info in market_data.items():
        if pair not in exclude_list and info.get("Change", 0) > 0:
            valid_pairs.append((pair, info.get("Change", 0)))
            
    valid_pairs.sort(key=lambda x: x[1], reverse=True)
    top_5_pairs = [x[0] for x in valid_pairs[:5]]
    top_5_coins = [p.split('/')[0] for p in top_5_pairs]

    if not top_5_pairs:
        print("No positive momentum assets today. Staying in USD.")
        return

    # ==========================================
    # STEP 3: Liquidate Losers (Anti-Churn)
    # ==========================================
    traded_today = False
    for coin in list(STATE["held_coins"].keys()):
        if coin not in top_5_coins:
            pair = f"{coin}/USD"
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            print(f"{coin} fell out of the Top 5. Liquidating...")
            if held_amount > 0.001:
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
                traded_today = True
            del STATE["held_coins"][coin]
            
    balance_data = client.get_balance()
    current_usd = balance_data["SpotWallet"]["USD"]["Free"]

    # ==========================================
    # STEP 4: Buy the New Winners
    # ==========================================
    coins_to_buy = [coin for coin in top_5_coins if coin not in STATE["held_coins"]]
    
    if not coins_to_buy:
        print("Holding the optimal portfolio. No action needed.")
        if traded_today: STATE["last_trade_date"] = current_utc_date
        return
        
    usd_per_coin = (current_usd * 0.98) / len(coins_to_buy)
    
    for coin in coins_to_buy:
        pair = f"{coin}/USD"
        buy_price = market_data[pair]["LastPrice"]
        quantity_to_buy = math.floor((usd_per_coin / buy_price) * 100) / 100.0
        
        print(f"Adding to portfolio: {coin} at {buy_price} per unit...")
        order_response = client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=quantity_to_buy)
        
        if order_response and order_response.get("Success"):
            STATE["held_coins"][coin] = buy_price
            traded_today = True
            
    if traded_today:
        STATE["last_trade_date"] = current_utc_date
import math
import requests

# Upgraded to a dictionary to hold multiple assets at once
STATE = {
    "held_coins": {} # Format: {"ZEN": 5.833, "BTC": 60000.0}
}

STOP_LOSS_THRESHOLD = 0.03 

def check_stop_loss(client):
    """
    The Fast Loop (Defense): Checks all currently held assets.
    Sells individual coins if they drop 3% below their specific entry price.
    """
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
            
    # Clean up the state dictionary
    for coin in coins_to_remove:
        del STATE["held_coins"][coin]
        
    return triggered

def get_real_world_regime():
    """Fetches real-world BTC data from Binance's public API."""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "4h", "limit": 20}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        closes = [float(candle[4]) for candle in data]
        current_price = closes[-1]
        moving_average = sum(closes) / len(closes)
        
        return current_price > moving_average
    except Exception as e:
        print(f"External Data Error: {e}. Defaulting to safe mode (Bearish).")
        return False

def run_rebalance(client):
    """
    The Slow Loop (Offense): Maintains a diversified Top-5 Momentum portfolio 
    to optimize Sharpe/Sortino ratios.
    """
    global STATE
    
    print("Fetching market data for rebalance...")
    ticker_data = client.get_ticker()
    balance_data = client.get_balance()
    
    if not ticker_data or not balance_data:
        print("API Error: Failed to fetch data. Aborting rebalance.")
        return

    market_data = ticker_data["Data"]

    # ==========================================
    # STEP 1: The Macro Regime Filter
    # ==========================================
    is_bullish = get_real_world_regime()
    
    if not is_bullish:
        print("Macro Regime is BEARISH. Liquidating all positions to USD.")
        for coin in list(STATE["held_coins"].keys()):
            pair = f"{coin}/USD"
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            if held_amount > 0.001:
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
        STATE["held_coins"].clear()
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
            
    # Sort by highest momentum descending and grab the top 5
    valid_pairs.sort(key=lambda x: x[1], reverse=True)
    top_5_pairs = [x[0] for x in valid_pairs[:5]]
    top_5_coins = [p.split('/')[0] for p in top_5_pairs]

    if not top_5_pairs:
        print("No assets have positive momentum today. Staying in USD.")
        return

    # ==========================================
    # STEP 3: Liquidate Losers (Anti-Churn Logic)
    # ==========================================
    for coin in list(STATE["held_coins"].keys()):
        if coin not in top_5_coins:
            pair = f"{coin}/USD"
            held_amount = balance_data["SpotWallet"][coin]["Free"]
            print(f"{coin} fell out of the Top 5. Liquidating to free up cash...")
            if held_amount > 0.001:
                client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
            del STATE["held_coins"][coin]
            
    # Refresh balance data so we know exactly how much cash we freed up
    balance_data = client.get_balance()
    current_usd = balance_data["SpotWallet"]["USD"]["Free"]

    # ==========================================
    # STEP 4: Buy the New Winners
    # ==========================================
    # Find which of the top 5 we don't already own
    coins_to_buy = [coin for coin in top_5_coins if coin not in STATE["held_coins"]]
    
    if not coins_to_buy:
        print("Already holding the optimal Top 5 portfolio. No action needed.")
        return
        
    # Divide available cash evenly among the new coins we need to buy
    usd_per_coin = (current_usd * 0.98) / len(coins_to_buy)
    
    for coin in coins_to_buy:
        pair = f"{coin}/USD"
        buy_price = market_data[pair]["LastPrice"]
        quantity_to_buy = math.floor((usd_per_coin / buy_price) * 100) / 100.0
        
        print(f"Adding to portfolio: {coin} at {buy_price} per unit...")
        order_response = client.place_order(pair=pair, side="BUY", order_type="MARKET", quantity=quantity_to_buy)
        
        if order_response and order_response.get("Success"):
            STATE["held_coins"][coin] = buy_price
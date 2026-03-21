import math

# A simple in-memory state tracker so the bot remembers what it bought
# In a full enterprise system, you'd save this to a database, but for a 10-day hackathon, memory is fine.
STATE = {
    "held_coin": None,
    "buy_price": 0.0
}

# The risk tolerance: Sell immediately if the coin drops 3% from our entry price
STOP_LOSS_THRESHOLD = 0.03 

def check_stop_loss(client):
    """
    The Fast Loop (Defense): Checks if the currently held asset has crashed.
    Returns True if the stop-loss was triggered, False otherwise.
    """
    global STATE
    
    # If we are sitting in USD, there is no risk to manage.
    if STATE["held_coin"] is None:
        return False
        
    pair = f"{STATE['held_coin']}/USD"
    
    # Fetch current price
    ticker_data = client.get_ticker(pair)
    if not ticker_data or not ticker_data.get("Success"):
        print("API Error: Could not fetch ticker for stop-loss check.")
        return False
        
    current_price = ticker_data["Data"][pair]["LastPrice"]
    drop_percentage = (STATE["buy_price"] - current_price) / STATE["buy_price"]
    
    if drop_percentage >= STOP_LOSS_THRESHOLD:
        print(f"STOP LOSS ALERT! {pair} dropped {drop_percentage*100:.2f}%. Current Price: {current_price}")
        
        # 1. Fetch exact balance to know how much to sell
        balance_data = client.get_balance()
        held_amount = balance_data["Wallet"][STATE["held_coin"]]["Free"]
        
        # 2. Execute Market Sell to get out immediately
        client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
        
        # 3. Reset state to USD
        STATE["held_coin"] = None
        STATE["buy_price"] = 0.0
        return True
        
    return False

def run_rebalance(client):
    """
    The Slow Loop (Offense): Sells current holdings, evaluates the macro regime, 
    and buys the highest momentum coin.
    """
    global STATE
    
    print("Fetching market data for rebalance...")
    ticker_data = client.get_ticker() # Calling without a pair returns ALL coins
    balance_data = client.get_balance()
    
    if not ticker_data or not balance_data:
        print("API Error: Failed to fetch data. Aborting rebalance.")
        return

    # ==========================================
    # STEP 1: Sell Current Holdings (Go to Cash)
    # ==========================================
    if STATE["held_coin"] is not None:
        coin = STATE["held_coin"]
        pair = f"{coin}/USD"
        held_amount = balance_data["Wallet"][coin]["Free"]
        
        # Only sell if we have a meaningful amount (ignoring dust)
        if held_amount > 0.001: 
            print(f"Liquidating current position: Selling {held_amount} {coin}")
            client.place_order(pair=pair, side="SELL", order_type="MARKET", quantity=held_amount)
            
        STATE["held_coin"] = None
        STATE["buy_price"] = 0.0
        
        # Refresh balance data after selling to know our exact USD cache
        balance_data = client.get_balance()

    # ==========================================
    # STEP 2: The Macro Regime Filter
    # ==========================================
    market_data = ticker_data["Data"]
    btc_change = market_data.get("BTC/USD", {}).get("Change", 0)
    
    if btc_change < 0:
        print(f"Macro Regime is BEARISH (BTC 24h Change: {btc_change*100:.2f}%).")
        print("Staying safely in USD. Will check again in 4 hours.")
        return # Abort buying. We successfully protected the portfolio.

    # ==========================================
    # STEP 3: Cross-Sectional Momentum Selection
    # ==========================================
    print("Macro Regime is BULLISH. Scanning for top momentum asset...")
    
    best_pair = None
    highest_change = -999.0
    
    # Exclude stablecoins or coins we don't want to trade
    exclude_list = ["USDT/USD", "USDC/USD"] 
    
    for pair, info in market_data.items():
        if pair in exclude_list:
            continue
            
        change = info.get("Change", 0)
        if change > highest_change:
            highest_change = change
            best_pair = pair

    if not best_pair or highest_change <= 0:
        print("No assets have positive momentum today. Staying in USD.")
        return

    # ==========================================
    # STEP 4: Execute the Buy
    # ==========================================
    current_usd = balance_data["Wallet"]["USD"]["Free"]
    buy_price = market_data[best_pair]["LastPrice"]
    
    # Calculate how much we can buy. 
    # We use 98% of our USD to leave room for the 0.1% Taker Fee and avoid "Insufficient Funds" errors.
    usable_usd = current_usd * 0.98 
    quantity_to_buy = usable_usd / buy_price
    
    # Round down to 4 decimal places to avoid API precision errors
    quantity_to_buy = math.floor(quantity_to_buy * 10000) / 10000.0

    print(f"Winner selected: {best_pair} (24h Change: {highest_change*100:.2f}%).")
    print(f"Buying {quantity_to_buy} at {buy_price} per unit...")
    
    order_response = client.place_order(pair=best_pair, side="BUY", order_type="MARKET", quantity=quantity_to_buy)
    
    if order_response and order_response.get("Success"):
        # Update our internal state so the Fast Loop can start protecting it
        coin_name = best_pair.split('/')[0]
        STATE["held_coin"] = coin_name
        STATE["buy_price"] = buy_price
        print("Trade successful! Position locked and Stop-Loss activated.")
    else:
        print(f"Trade failed. API Response: {order_response}")
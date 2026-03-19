import os
import time
from dotenv import load_dotenv
from api_client import RoostooClient
# from strategy import generate_signal  # We will uncomment this once we write strategy.py

def setup():
    """Loads environment variables and initializes the API client."""
    # This automatically finds your .env file and loads the variables
    load_dotenv()
    
    # Fetch the exact keys you defined
    api_key = os.getenv("RST_API_KEY")
    secret_key = os.getenv("RST_SECRET_KEY")
    
    if not api_key or not secret_key:
        raise ValueError("Missing API keys! Please check your .env file.")
        
    print("Keys loaded successfully. Initializing client...")
    return RoostooClient(api_key=api_key, secret_key=secret_key)

def run_bot():
    """The main execution loop that keeps the bot running 24/7."""
    client = setup()
    
    print("Bot is starting up...")
    
    # Infinite loop to keep the bot alive on your cloud server
    while True:
        try:
            print(f"\n--- New Cycle: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            
            # 1. Fetch Market Data
            # ticker_data = client.get_ticker("BTC/USD")
            
            # 2. Fetch Account Balance
            # balance = client.get_balance()
            
            # 3. Run Strategy Logic (To be built)
            # action, quantity = generate_signal(ticker_data, balance)
            
            # 4. Execute Trade
            # if action in ['BUY', 'SELL']:
            #     print(f"Executing {action} for {quantity} BTC")
            #     client.place_order(pair="BTC/USD", side=action, order_type="MARKET", quantity=quantity)
            # else:
            #     print("Holding position. No action taken.")

            print("Cycle complete. Sleeping for 5 minutes...")
            
            # Sleep for 300 seconds (5 minutes) before checking the market again
            # This prevents rate-limiting and keeps the logic simple
            time.sleep(300)

        except Exception as e:
            # This catch-all prevents the bot from dying if an unexpected error occurs
            print(f"CRITICAL ERROR in main loop: {e}")
            print("Sleeping for 60 seconds before retrying...")
            time.sleep(60)

if __name__ == "__main__":
    run_bot()
import os
import time
from dotenv import load_dotenv
from api_client import RoostooClient
from strategy import run_rebalance, check_stop_loss 

def setup():
    """Loads environment variables and initializes the API client."""
    load_dotenv()
    
    api_key = os.getenv("RST_API_KEY")
    secret_key = os.getenv("RST_SECRET_KEY")
    
    if not api_key or not secret_key:
        raise ValueError("Missing API keys! Please check your .env file.")
        
    print("Keys loaded successfully. Initializing client...")
    return RoostooClient(api_key=api_key, secret_key=secret_key)

def run_bot():
    """The Relentless 5-Minute Execution Engine."""
    client = setup()
    print("Bot initialized. Starting execution loops...")
    
    while True:
        print(f"\n--- System Check: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        try:
            # 1. DEFENSE: Check Stop-Loss (strategy.py will automatically impose the 60-min penalty if triggered)
            check_stop_loss(client)
            
            # 2. OFFENSE: Momentum Rebalance (strategy.py will ignore any coin currently in penalty)
            run_rebalance(client)
                    
        except Exception as e:
            # The Ultimate Safety Net: Catches any weird math or network errors
            print(f"SYSTEM ERROR in main loop: {e}")
            print("Sleeping for 60 seconds before retrying...")
            time.sleep(60)
            continue # Skip the normal sleep and retry immediately

        # Sleep for exactly 5 minutes before waking up to do the next check
        print("Cycle complete. Sleeping for 5 minutes...")
        time.sleep(300)

if __name__ == "__main__":
    run_bot()
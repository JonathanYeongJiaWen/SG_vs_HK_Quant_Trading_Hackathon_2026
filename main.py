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
    """The Dual-Loop Execution Engine."""
    client = setup()
    print("Bot initialized. Restoring Dual-Loop Execution...")
    
    # Timing Constants (in seconds)
    FAST_LOOP_INTERVAL = 300      # 5 minutes for Defense (Stop-Loss)
    SLOW_LOOP_INTERVAL = 14400    # 4 hours for Offense (Momentum Rebalance)
    
    last_slow_loop_time = 0
    
    while True:
        current_time = time.time()
        print(f"\n--- System Check: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        try:
            # ==========================================
            # 1. DEFENSE: Check Stop-Loss (Every 5 mins)
            # ==========================================
            check_stop_loss(client)
            
            # ==========================================
            # 2. OFFENSE: Momentum Rebalance (Every 4 hours)
            # ==========================================
            time_since_last_slow = current_time - last_slow_loop_time
            
            if time_since_last_slow >= SLOW_LOOP_INTERVAL:
                print("Initiating 4-Hour Macro Regime & Rebalance Sequence...")
                run_rebalance(client)
                last_slow_loop_time = current_time
            else:
                minutes_left = int((SLOW_LOOP_INTERVAL - time_since_last_slow) / 60)
                print(f"Holding positions. Next momentum rebalance in {minutes_left} minutes.")
                    
        except Exception as e:
            print(f"SYSTEM ERROR in main loop: {e}")
            print("Sleeping for 60 seconds before retrying...")
            time.sleep(60)
            continue 

        # Sleep for 5 minutes before waking up to do the next check
        print("Cycle complete. Sleeping for 5 minutes...")
        time.sleep(FAST_LOOP_INTERVAL)

if __name__ == "__main__":
    run_bot()
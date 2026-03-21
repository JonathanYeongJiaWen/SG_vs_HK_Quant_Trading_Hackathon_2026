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
    print("Bot initialized. Starting execution loops...")
    
    # Timing Constants (in seconds)
    FAST_LOOP_INTERVAL = 300      # 5 minutes for risk checks
    SLOW_LOOP_INTERVAL = 14400    # 4 hours for strategy rebalancing
    COOLDOWN_PERIOD = 14400       # 4 hour penalty if stop-loss is hit
    
    # State Trackers
    last_slow_loop_time = 0
    cooldown_until = 0
    
    while True:
        current_time = time.time()
        print(f"\n--- System Check: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        try:
            # ==========================================
            # 1. THE FAST LOOP (Defense - Every 5 mins)
            # ==========================================
            # This function will return True if it had to sell an asset to save capital
            stop_loss_triggered = check_stop_loss(client)
            
            if stop_loss_triggered:
                print("CRITICAL: Stop-loss triggered! Liquidated position into USD.")
                cooldown_until = current_time + COOLDOWN_PERIOD
                print(f"Entering cooldown mode until {time.strftime('%H:%M:%S', time.localtime(cooldown_until))}.")
            
            # ==========================================
            # 2. THE SLOW LOOP (Offense - Every 4 hours)
            # ==========================================
            time_since_last_slow_loop = current_time - last_slow_loop_time
            
            if time_since_last_slow_loop >= SLOW_LOOP_INTERVAL:
                # Check if we are currently serving a cooldown penalty
                if current_time < cooldown_until:
                    print("Skipping strategy rebalance. System is in cooldown to prevent whipsaw losses.")
                else:
                    print("Initiating 4-Hour Macro Regime & Rebalance Sequence...")
                    run_rebalance(client)
                    
                # Reset the slow loop clock whether we traded or skipped due to cooldown
                last_slow_loop_time = current_time
            else:
                minutes_left = int((SLOW_LOOP_INTERVAL - time_since_last_slow_loop) / 60)
                print(f"Next strategy rebalance in {minutes_left} minutes.")

        except Exception as e:
            # The Ultimate Safety Net: Catches any weird math or network errors
            print(f"SYSTEM ERROR in main loop: {e}")
            print("Sleeping for 60 seconds before retrying...")
            time.sleep(60)
            continue # Skip the normal sleep and retry immediately

        # Sleep for 5 minutes before waking up to do the next Fast Loop check
        print("Cycle complete. Sleeping for 5 minutes...")
        time.sleep(FAST_LOOP_INTERVAL)

if __name__ == "__main__":
    run_bot()
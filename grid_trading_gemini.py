import requests
import pandas as pd
import pandas_ta as ta
import json
import time
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv # For loading credentials from .env file

# --- Configuration ---

# --- Part 1: Suggestion Parameters ---
SYMBOL = "BTCUSDT"      # Trading pair (Binance example)
INTERVAL = "1d"         # Candlestick interval for historical data ('1h', '4h', '1d')
HISTORY_LIMIT = 90      # Number of historical candles (e.g., 90 days for '1d')

# Method preference: 'ATR' or 'Historical'. Will use this method's suggested range.
PREFERRED_METHOD = 'ATR' # Use 'ATR' first, fallback to 'Historical' if ATR fails

# Historical Range Parameters (Used as fallback or if preferred)
HISTORICAL_LOOKBACK = 30 # Days/Periods to consider for historical min/max

# ATR Parameters (Used if preferred)
ATR_PERIOD = 14          # Period for ATR calculation
ATR_FACTOR = 2.0         # Multiplier for ATR to set range width

# Grid Density Calculation Parameters
TARGET_PROFIT_PER_GRID_PCT = 0.8  # Target gross profit % per grid step (e.g., 0.8%)
FEE_PCT = 0.1                     # Trading fee PER trade (e.g., 0.1%)

# --- Part 2: Monitoring & Notification Parameters ---
# Price API Endpoint for real-time price
CURRENT_PRICE_API_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"

# Email Configuration (Load from .env file or set directly)
load_dotenv() # Load variables from .env file into environment
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', 'fengkuang33@gmail.com') # Takes from .env or default
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '362580Lv') # Takes from .env or default
EMAIL_RECEIVER = 'fengkuang33@gmail.com' # !!! CHANGE THIS TO YOUR EMAIL !!!

# Monitoring Interval
CHECK_INTERVAL_SECONDS = 60 # Check price every 60 seconds

# --- End Configuration ---

# --- Grid Trading Explanation Template ---
# Will be formatted later with calculated values
GRID_EXPLANATION_TEMPLATE = """
网格交易 (Grid Trading) 提醒:

当前监控基于以下自动建议参数:
方法: {method}
范围: {min_p:.2f} - {max_p:.2f}
网格数: {num_g}

原理: 在上述预设范围内，设置了一系列买卖线。当价格下跌触及线时视为潜在买入信号；上涨触及线时视为潜在卖出信号。
(注意：此脚本仅发送通知，不执行实际交易)

优点: 自动化程度高（指真实交易机器人），适合震荡行情。
缺点: 若价格突破范围，可能导致损失或错过趋势行情。参数基于历史数据，需谨慎使用。
"""

# --- Global Variables ---
triggered_levels = set() # Keep track of levels that sent a notification
last_price = None        # Store the previous price to detect crossing direction

# --- Functions (Suggestion Part) ---

def get_historical_data(symbol, interval, limit):
    """Fetches historical candlestick data from Binance."""
    KLINE_API_URL = "https://api.binance.com/api/v3/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        response = requests.get(KLINE_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'Open time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close time', 'Quote asset volume', 'Number of trades',
            'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'
        ])
        df['Open time'] = pd.to_datetime(df['Open time'], unit='ms')
        num_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
        df.set_index('Open time', inplace=True)
        # Ensure data is sorted chronologically if needed (usually is from API)
        df.sort_index(inplace=True)
        return df
    except requests.exceptions.RequestException as e:
        print(f"Error fetching historical data: {e}")
    except Exception as e:
        print(f"An error occurred processing historical data: {e}")
    return None

def suggest_params_historical(df, lookback_period):
    """Suggests grid range based on historical High/Low."""
    if df is None or len(df) < lookback_period:
        print(f"Not enough historical data ({len(df)} points) for lookback {lookback_period}")
        return None, None
    recent_data = df.iloc[-lookback_period:]
    min_price = recent_data['Low'].min()
    max_price = recent_data['High'].max()
    print(f"[Suggestion] Based on Historical Range ({lookback_period} {INTERVAL}s): Min={min_price:.2f}, Max={max_price:.2f}")
    return min_price, max_price

def suggest_params_atr(df, atr_period, atr_factor):
    """Suggests grid range based on ATR."""
    if df is None or len(df) < atr_period + 1: # Need enough data for ATR calc
        print(f"Not enough historical data ({len(df)} points) for ATR period {atr_period}")
        return None, None
    try:
        # Calculate ATR using pandas_ta - check if column exists before using
        atr_col_name = f'ATRr_{atr_period}'
        df.ta.atr(length=atr_period, append=True)

        if atr_col_name not in df.columns or df[atr_col_name].isnull().all():
             print(f"Could not calculate ATR column '{atr_col_name}'.")
             return None, None

        latest_atr = df[atr_col_name].iloc[-1]
        latest_close = df['Close'].iloc[-1]

        if pd.isna(latest_atr) or pd.isna(latest_close):
            print("Could not retrieve latest ATR or Close price from historical data.")
            return None, None

        min_price = latest_close - atr_factor * latest_atr
        max_price = latest_close + atr_factor * latest_atr
        print(f"[Suggestion] Based on ATR ({atr_period} {INTERVAL}s, Factor={atr_factor}): Min={min_price:.2f}, Max={max_price:.2f} (ATR={latest_atr:.2f}, Close={latest_close:.2f})")
        return min_price, max_price
    except Exception as e:
        print(f"Error calculating ATR suggestion: {e}")
        return None, None


def suggest_num_grids(min_price, max_price, target_profit_pct, fee_pct):
    """Suggests number of grids based on target profit per grid."""
    if min_price is None or max_price is None or min_price >= max_price:
        print("Invalid price range for grid density calculation.")
        return None
    if target_profit_pct <= 0: print("Target profit percentage must be positive."); return None

    min_profitable_step_pct = 2 * fee_pct
    if target_profit_pct <= min_profitable_step_pct:
        print(f"Warning: Target profit per grid ({target_profit_pct}%) might be too low to cover fees ({min_profitable_step_pct}%).")

    approx_grid_step_value = min_price * (target_profit_pct / 100.0)
    if approx_grid_step_value <= 0: print("Calculated approximate grid step is zero or negative."); return None

    num_grids = int((max_price - min_price) / approx_grid_step_value) - 1
    if num_grids < 1: num_grids = 1 # Ensure at least 1 grid

    actual_step = (max_price - min_price) / (num_grids + 1)
    actual_profit_pct = (actual_step / min_price) * 100
    net_profit_pct = actual_profit_pct - (2 * fee_pct)

    print(f"[Suggestion] Based on Target Profit ≈{target_profit_pct}% & Fee ≈{fee_pct}%:")
    print(f"  > Suggested Number of Grids: {num_grids} (Net Profit/Grid ≈ {net_profit_pct:.2f}%)")
    if net_profit_pct <= 0: print("  > WARNING: Estimated net profit per grid is zero or negative!")
    return num_grids

# --- Functions (Monitoring Part) ---

def get_current_btc_price():
    """Fetches the current BTC price from the specified API."""
    try:
        response = requests.get(CURRENT_PRICE_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = float(data['price'])
        return price
    except requests.exceptions.RequestException as e:
        print(f"Error fetching current price: {e}")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error processing current price data: {e}")
    return None

def calculate_monitoring_grid_levels(min_p, max_p, num_grids):
    """Calculates the actual grid price levels for monitoring."""
    if num_grids <= 0: return []
    if min_p >= max_p: return []
    step = (max_p - min_p) / (num_grids + 1)
    levels = [min_p + (i + 1) * step for i in range(num_grids)]
    return sorted(levels)

def send_email(subject, body):
    """Sends an email notification."""
    if not EMAIL_SENDER or '@' not in EMAIL_SENDER or not EMAIL_PASSWORD or EMAIL_PASSWORD == 'YOUR_APP_PASSWORD' or not EMAIL_RECEIVER:
         print("Email configuration incomplete or using placeholders. Skipping email.")
         return

    message = MIMEText(body)
    message['Subject'] = subject
    message['From'] = EMAIL_SENDER
    message['To'] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, message.as_string())
        print(f"Email sent successfully to {EMAIL_RECEIVER}")
    except smtplib.SMTPAuthenticationError:
        print("Email Authentication Error: Check sender email/password (use App Password for Gmail). Ensure 'less secure apps' OR App Password is set.")
    except Exception as e:
        print(f"Error sending email: {e}")

# --- Main Execution ---

if __name__ == "__main__":
    print("--- Starting Bitcoin Grid Strategy Assistant ---")
    print("Phase 1: Calculating Parameter Suggestions...")

    # 1. Fetch Historical Data
    df_history = get_historical_data(SYMBOL, INTERVAL, HISTORY_LIMIT)

    final_min_price, final_max_price, final_num_grids = None, None, None
    suggestion_method_used = "None"

    if df_history is not None:
        # 2. Get Suggestions from preferred and fallback methods
        min_hist, max_hist = suggest_params_historical(df_history, HISTORICAL_LOOKBACK)
        min_atr, max_atr = suggest_params_atr(df_history, ATR_PERIOD, ATR_FACTOR)

        # 3. Select the parameters to use based on preference
        if PREFERRED_METHOD == 'ATR' and min_atr is not None:
            final_min_price, final_max_price = min_atr, max_atr
            suggestion_method_used = "ATR"
        elif min_hist is not None: # Fallback to historical or use if preferred
            final_min_price, final_max_price = min_hist, max_hist
            suggestion_method_used = "Historical"
        else: # If historical also failed
             print("Error: Both ATR and Historical suggestions failed. Cannot proceed.")
             exit() # Exit if no valid range found


        # 4. Suggest Grid Density based on the chosen range
        if final_min_price is not None and final_max_price is not None:
             print(f"\nCalculating Grid Density using '{suggestion_method_used}' suggested range...")
             final_num_grids = suggest_num_grids(final_min_price, final_max_price, TARGET_PROFIT_PER_GRID_PCT, FEE_PCT)
        else:
             # This case should ideally not be reached due to the exit() above, but as safeguard:
             print("Error: No valid price range determined. Cannot calculate grid density.")
             exit()

        if final_num_grids is None:
             print("Error: Failed to suggest number of grids. Cannot proceed.")
             exit()

    else:
        print("Error: Failed to fetch historical data. Cannot proceed.")
        exit() # Exit if historical data failed

    # --- Phase 2: Setup Monitoring ---
    print("\n--- Phase 2: Initializing Price Monitoring ---")
    print(f"Using parameters suggested by: {suggestion_method_used}")
    print(f"Monitoring Range: {final_min_price:.2f} - {final_max_price:.2f}")
    print(f"Number of Grids: {final_num_grids}")

    # Check email config before starting loop
    if not EMAIL_RECEIVER or '@' not in EMAIL_RECEIVER:
         print("\n*** WARNING: EMAIL_RECEIVER is not set correctly! Notifications will not be sent. ***\n")
    if not EMAIL_SENDER or '@' not in EMAIL_SENDER or not EMAIL_PASSWORD or EMAIL_PASSWORD == 'YOUR_APP_PASSWORD':
        print("\n*** WARNING: EMAIL_SENDER or EMAIL_PASSWORD not configured correctly (check .env file/environment variables)! Email sending likely to fail. ***\n")


    # Calculate the specific levels to monitor
    monitoring_grid_levels = calculate_monitoring_grid_levels(final_min_price, final_max_price, final_num_grids)

    if not monitoring_grid_levels:
        print("Error: Calculated monitoring grid levels are empty. Check parameters.")
        exit()

    print(f"Calculated Monitoring Levels: {[f'{lvl:.2f}' for lvl in monitoring_grid_levels]}")
    print(f"Monitoring Interval: {CHECK_INTERVAL_SECONDS} seconds")
    print("-----------------------------------------")
    time.sleep(2) # Brief pause before starting loop

    # Format the explanation text with the final parameters
    grid_explanation_dynamic = GRID_EXPLANATION_TEMPLATE.format(
        method=suggestion_method_used,
        min_p=final_min_price,
        max_p=final_max_price,
        num_g=final_num_grids
    )

    # --- Phase 3: Monitoring Loop ---
    while True:
        current_price = get_current_btc_price()

        if current_price is not None:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{now_str}] Current BTC Price: ${current_price:.2f}", end='\r') # Use end='\r' to overwrite line

            if last_price is not None:
                for level in monitoring_grid_levels:
                    level_str = f"{level:.2f}" # Use consistent formatting

                    # Check for crossing DOWNWARDS (Potential Buy Signal)
                    if last_price > level >= current_price and level_str not in triggered_levels:
                        print(f"\n[{now_str}] --- Potential BUY Signal --- Price crossed BELOW {level_str}") # Print on new line
                        subject = f"BTC Grid Alert: Potential BUY near ${level_str}"
                        body = (
                            f"Bitcoin price crossed below grid level ${level_str}.\n\n"
                            f"Current Price: ${current_price:.2f}\n"
                            f"Timestamp: {now_str}\n\n"
                            f"{grid_explanation_dynamic}" # Use the formatted explanation
                        )
                        send_email(subject, body)
                        triggered_levels.add(level_str) # Mark level as triggered

                    # Check for crossing UPWARDS (Potential Sell Signal)
                    elif last_price < level <= current_price and level_str not in triggered_levels:
                        print(f"\n[{now_str}] --- Potential SELL Signal --- Price crossed ABOVE {level_str}") # Print on new line
                        subject = f"BTC Grid Alert: Potential SELL near ${level_str}"
                        body = (
                            f"Bitcoin price crossed above grid level ${level_str}.\n\n"
                            f"Current Price: ${current_price:.2f}\n"
                            f"Timestamp: {now_str}\n\n"
                            f"{grid_explanation_dynamic}" # Use the formatted explanation
                        )
                        send_email(subject, body)
                        triggered_levels.add(level_str) # Mark level as triggered

            last_price = current_price # Update last price for the next check
        else:
            # Avoid spamming 'failed' message if it keeps failing
            if last_price is not None: # Only print failure once after a success
                 print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to fetch current price. Retrying...")
                 last_price = None # Reset last_price to avoid false triggers after connection resumes


        # Wait before the next check
        time.sleep(CHECK_INTERVAL_SECONDS)
import requests
import pandas as pd
import pandas_ta as ta
import math
import argparse
from datetime import datetime, timedelta
import sys # To exit gracefully

# --- Configuration ---

# API Endpoints (Using Binance public data)
SYMBOL = "ETHUSDT" # MODIFIED FOR ETH
CURRENT_PRICE_API_URL = f"https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}"
HISTORICAL_KLINE_API_URL = "https://api.binance.com/api/v3/klines"

# Default User Holdings (Can be overridden by command-line args)
DEFAULT_ETH_BALANCE = 0.02 # MODIFIED FOR ETH (Example value)
DEFAULT_USDT_BALANCE = 57.88751710 # Kept USDT balance same as example

# Historical Data Parameters
HISTORY_DAYS = 365 # Fetch 1 year of daily data

# Algorithm Parameters
## ATR Based Algorithm
ATR_PERIOD = 14          # Period for ATR calculation (common default)
ATR_FACTOR = 2.0         # Multiplier for ATR (adjust based on risk: lower=tighter range)
## Historical Range Algorithm
HISTORICAL_LOOKBACK_DAYS = 180 # Use last 180 days within the 1-year data for range

# Grid Density Calculation Parameters
TARGET_PROFIT_PER_GRID_PCT = 5  # Target gross profit % per grid step (before fees)
FEE_PCT = 0                     # Estimated trading fee PER trade (e.g., 0.1%)

# --- Helper Functions ---

def get_current_price(symbol):
    """Fetches the current market price."""
    try:
        # Construct URL within the function to use the passed symbol
        price_api_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        response = requests.get(price_api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = float(data['price'])
        return price
    except Exception as e:
        print(f"Error fetching current price for {symbol}: {e}", file=sys.stderr)
        return None

def get_historical_data(symbol, interval, limit):
    """Fetches historical candlestick data."""
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        response = requests.get(HISTORICAL_KLINE_API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'Open time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close time', 'Quote asset volume', 'Number of trades',
            'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'
        ])
        # Use Close time for more accurate date representation of the bar's end
        df['Date'] = pd.to_datetime(df['Close time'], unit='ms')
        num_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)
        # Drop rows with NaNs potentially introduced by coercion
        df.dropna(subset=num_cols, inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching historical data for {symbol}: {e}", file=sys.stderr)
        return None

def calculate_atr(df, atr_period):
    """Calculates ATR and returns latest value."""
    if df is None or len(df) < atr_period + 1: return None
    try:
        atr_col_name = f'ATRr_{atr_period}'
        # Ensure the index is a DatetimeIndex for pandas_ta
        df.index = pd.to_datetime(df.index)
        df.ta.atr(length=atr_period, append=True)

        if atr_col_name not in df.columns or df[atr_col_name].isnull().all():
            print(f"Could not calculate ATR column '{atr_col_name}'.", file=sys.stderr)
            return None
        latest_atr = df[atr_col_name].iloc[-1]
        return latest_atr if pd.notna(latest_atr) else None
    except Exception as e:
        print(f"Error calculating ATR: {e}", file=sys.stderr)
        return None

def suggest_range_atr(df_history, current_price, atr_period, atr_factor):
    """Calculates range based on ATR around current price."""
    latest_atr = calculate_atr(df_history, atr_period)
    if latest_atr is None or current_price is None:
        return None, None, None # Indicate failure

    min_price = current_price - atr_factor * latest_atr
    max_price = current_price + atr_factor * latest_atr
    return min_price, max_price, latest_atr

def suggest_range_historical(df_history, lookback_days):
    """Calculates range based on High/Low over the lookback period."""
    if df_history is None or len(df_history) < lookback_days:
        print(f"Warning: Not enough historical data ({len(df_history)} days) for lookback {lookback_days} days.", file=sys.stderr)
        lookback_days = len(df_history) # Adjust if needed
        if lookback_days == 0: return None, None

    recent_data = df_history.iloc[-lookback_days:]
    min_price = recent_data['Low'].min()
    max_price = recent_data['High'].max()
    return min_price, max_price

def suggest_total_grids(min_price, max_price, target_profit_pct, fee_pct):
    """Suggests TOTAL number of grids for the range."""
    if not all([min_price, max_price]) or min_price <= 0 or min_price >= max_price or target_profit_pct <= 0:
        print("Invalid inputs for suggesting grid count.", file=sys.stderr)
        return None

    min_profitable_step_pct = 2 * fee_pct
    if target_profit_pct <= min_profitable_step_pct:
        print(f"Warning: Target profit/grid ({target_profit_pct}%) might not cover estimated fees ({min_profitable_step_pct}%).")

    # Base step calculation on min_price for conservatism
    approx_grid_step_value = min_price * (target_profit_pct / 100.0)
    if approx_grid_step_value <= 0:
        print("Calculated approximate grid step is zero or negative.", file=sys.stderr)
        return None

    # num_grids = (Range / Step) - 1
    num_grids = math.floor((max_price - min_price) / approx_grid_step_value) - 1
    return max(1, num_grids) # Ensure at least 1 grid

def calculate_grid_levels(min_p, max_p, num_grids):
    """Calculates the actual grid price levels."""
    if not all([min_p, max_p]) or min_p >= max_p or num_grids <= 0:
        return []
    step = (max_p - min_p) / (num_grids + 1)
    # Ensure levels don't slightly exceed bounds due to float precision
    levels = [min(max_p, max(min_p, min_p + (i + 1) * step)) for i in range(num_grids)]
    return sorted(levels)

def generate_grid_plan(min_price, max_price, total_num_grids, current_price, user_eth, user_usdt): # MODIFIED user_eth
    """Generates the specific buy/sell actions based on balances and levels."""
    if not all([min_price, max_price, total_num_grids, current_price]):
        print("Invalid inputs for generating grid plan.", file=sys.stderr)
        return [], 0, 0

    all_levels = calculate_grid_levels(min_price, max_price, total_num_grids)
    if not all_levels:
        print("Failed to calculate grid levels.", file=sys.stderr)
        return [], 0, 0

    buy_levels = sorted([level for level in all_levels if level < current_price])
    sell_levels = sorted([level for level in all_levels if level >= current_price])

    num_buy_grids = len(buy_levels)
    num_sell_grids = len(sell_levels)

    plan_details = []
    usdt_per_buy_grid = (user_usdt / num_buy_grids) if num_buy_grids > 0 and user_usdt > 0 else 0
    eth_per_sell_grid = (user_eth / num_sell_grids) if num_sell_grids > 0 and user_eth > 0 else 0 # MODIFIED eth_per_sell_grid, user_eth

    for level in buy_levels:
        if usdt_per_buy_grid > 0:
            eth_to_buy_est = usdt_per_buy_grid / level # MODIFIED eth_to_buy_est
            plan_details.append({
                'type': 'BUY', 'price': level,
                'usdt_amount': usdt_per_buy_grid, 'eth_amount_est': eth_to_buy_est # MODIFIED eth_amount_est
            })

    for level in sell_levels:
        if eth_per_sell_grid > 0: # MODIFIED eth_per_sell_grid
            usdt_to_receive_est = eth_per_sell_grid * level # MODIFIED eth_per_sell_grid
            plan_details.append({
                'type': 'SELL', 'price': level,
                'eth_amount': eth_per_sell_grid, 'usdt_amount_est': usdt_to_receive_est # MODIFIED eth_amount, eth_per_sell_grid
            })

    return plan_details, num_buy_grids, num_sell_grids


def display_plan(plan, method_name, config):
    """Formats and prints the generated plan."""
    print("\n" + "="*60)
    print(f"--- Grid Trading Plan Suggestion ({method_name} Algorithm) ---")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current {config['symbol']} Price: ${config['current_price']:.2f}")
    print(f"Input Balances: {config['user_eth']:.8f} ETH, {config['user_usdt']:.4f} USDT") # MODIFIED user_eth, ETH
    print("-"*60)
    print("Parameters Used:")
    print(f"  Algorithm: {method_name}")
    if method_name == 'ATR':
        latest_atr_display = f"{config['latest_atr']:.2f}" if isinstance(config['latest_atr'], (int, float)) else config['latest_atr']
        print(f"  ATR Period: {config['atr_period']}, ATR Factor: {config['atr_factor']}, Latest ATR: {latest_atr_display}")
    elif method_name == 'Historical':
        print(f"  Historical Lookback: {config['hist_lookback']} days")
    print(f"  Target Profit/Grid: {config['target_profit_pct']}% (Gross)")
    print(f"  Estimated Fee/Trade: {config['fee_pct']}%")
    print("-"*60)
    print("Generated Plan:")
    print(f"  Price Range: ${config['min_price']:.2f} - ${config['max_price']:.2f}")
    print(f"  Total Grids: {config['total_grids']} (Buy: {config['num_buy']}, Sell: {config['num_sell']})")

    if not plan:
        print("\n  No actionable grid levels generated with these parameters/balances.")
        print("  Consider adjusting parameters (e.g., wider range, different target profit) or balances.")
    else:
        print("\n  Actions:")
        for item in plan:
            if item['type'] == 'BUY':
                print(f"    BUY at ~${item['price']:<9.2f} | Spend ${item['usdt_amount']:.4f} USDT (Est. Buy {item['eth_amount_est']:.8f} ETH)") # MODIFIED eth_amount_est, ETH
            elif item['type'] == 'SELL':
                print(f"    SELL at ~${item['price']:<9.2f} | Sell {item['eth_amount']:.8f} ETH (Est. Recv ${item['usdt_amount_est']:.4f} USDT)") # MODIFIED eth_amount, ETH

    print("\n" + "="*60)
    print("Disclaimer:")
    print("This is an algorithmically generated plan based on historical data and parameters.")
    print("It is NOT financial advice. Cryptocurrency trading is highly risky.")
    print("Market conditions can change rapidly, making this plan obsolete.")
    print("You are solely responsible for any trading decisions. Fees & slippage apply.")
    print("="*60)

# --- Main Execution ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"Generate a personalized grid trading plan for {SYMBOL}.") # MODIFIED SYMBOL
    parser.add_argument("--eth", type=float, default=DEFAULT_ETH_BALANCE, # MODIFIED --eth, DEFAULT_ETH_BALANCE
                        help=f"Your current ETH balance (default: {DEFAULT_ETH_BALANCE})") # MODIFIED ETH, DEFAULT_ETH_BALANCE
    parser.add_argument("--usdt", type=float, default=DEFAULT_USDT_BALANCE,
                        help=f"Your current USDT balance (default: {DEFAULT_USDT_BALANCE})")
    parser.add_argument("--algorithm", type=str, required=True, choices=['ATR', 'Historical'],
                        help="The algorithm to use for range calculation ('ATR' or 'Historical')")

    args = parser.parse_args()

    print(f"Starting plan generation for {SYMBOL} using '{args.algorithm}' algorithm...") # MODIFIED SYMBOL
    print(f"Input Balances - ETH: {args.eth:.8f}, USDT: {args.usdt:.4f}") # MODIFIED ETH, args.eth

    # 1. Fetch Data
    current_price = get_current_price(SYMBOL)
    df_history = get_historical_data(SYMBOL, '1d', HISTORY_DAYS) # Fetch 1 year daily data

    if current_price is None or df_history is None:
        print("\nFailed to fetch necessary market data. Exiting.", file=sys.stderr)
        sys.exit(1) # Exit with error code

    if len(df_history) < 30: # Basic check for sufficient data
        print(f"\nWarning: Fetched only {len(df_history)} days of historical data. Results may be unreliable.", file=sys.stderr)
        if len(df_history) == 0:
            print("No historical data fetched. Exiting.", file=sys.stderr)
            sys.exit(1)


    # 2. Determine Range based on chosen algorithm
    min_price, max_price = None, None
    algo_specific_config = {} # To store params used by the chosen algo

    if args.algorithm == 'ATR':
        min_price, max_price, latest_atr = suggest_range_atr(df_history, current_price, ATR_PERIOD, ATR_FACTOR)
        algo_specific_config = {'atr_period': ATR_PERIOD, 'atr_factor': ATR_FACTOR, 'latest_atr': latest_atr if latest_atr else 'N/A'}
        if min_price is None:
            print("\nFailed to calculate range using ATR algorithm. Exiting.", file=sys.stderr)
            sys.exit(1)
    elif args.algorithm == 'Historical':
        min_price, max_price = suggest_range_historical(df_history, HISTORICAL_LOOKBACK_DAYS)
        algo_specific_config = {'hist_lookback': HISTORICAL_LOOKBACK_DAYS}
        if min_price is None:
            print("\nFailed to calculate range using Historical algorithm. Exiting.", file=sys.stderr)
            sys.exit(1)

    # 3. Suggest Total Grids
    total_num_grids = suggest_total_grids(min_price, max_price, TARGET_PROFIT_PER_GRID_PCT, FEE_PCT)
    if total_num_grids is None:
        print("\nFailed to suggest number of grids. Exiting.", file=sys.stderr)
        sys.exit(1)

    # 4. Generate the detailed plan
    grid_plan, num_buy, num_sell = generate_grid_plan(
        min_price, max_price, total_num_grids, current_price, args.eth, args.usdt # MODIFIED args.eth
    )

    # 5. Display the plan
    display_config = {
        'symbol': SYMBOL,
        'current_price': current_price,
        'user_eth': args.eth, # MODIFIED user_eth, args.eth
        'user_usdt': args.usdt,
        'min_price': min_price,
        'max_price': max_price,
        'total_grids': total_num_grids,
        'num_buy': num_buy,
        'num_sell': num_sell,
        'target_profit_pct': TARGET_PROFIT_PER_GRID_PCT,
        'fee_pct': FEE_PCT,
        **algo_specific_config # Merge algo-specific params
    }
    display_plan(grid_plan, args.algorithm, display_config)
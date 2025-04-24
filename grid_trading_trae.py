import requests
import time
import smtplib
import pandas as pd
import pandas_ta as ta
from email.mime.text import MIMEText

# Configuration
EMAIL_CONFIG = {
    'sender': 'your_email@example.com',
    'password': 'your_email_password',
    'smtp_server': 'smtp.example.com',
    'smtp_port': 587
}

GRID_CONFIG = {
    'symbol': 'BTCUSDT',
    'interval': '1h',
    'num_grids': 10,
    'price_range_percent': 5,
    'check_interval': 10,
    'historical_days': 14,
    'atr_period': 14,
    'atr_factor': 3,
    'target_profit_pct': 1.5,
    'trading_fee': 0.1,
    'max_grids': 20
}

BINANCE_API = "https://api.binance.com/api/v3/klines"

def get_historical_data():
    """Fetch historical candlestick data from Binance"""
    try:
        params = {
            'symbol': GRID_CONFIG['symbol'],
            'interval': GRID_CONFIG['interval'],
            'limit': GRID_CONFIG['historical_days']*24
        }
        response = requests.get(BINANCE_API, params=params, timeout=10)
        response.raise_for_status()
        
        df = pd.DataFrame(response.json(), columns=[
            'Open time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close time', 'Quote asset volume', 'Number of trades',
            'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'
        ])
        num_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
        df['Open time'] = pd.to_datetime(df['Open time'], unit='ms')
        return df.set_index('Open time').sort_index()
    except Exception as e:
        print(f"Historical data error: {e}")
        return None

def calculate_atr(df):
    """Calculate Average True Range with error handling"""
    try:
        df.ta.atr(length=GRID_CONFIG['atr_period'], append=True)
        return df[f'ATR_{GRID_CONFIG["atr_period"]}'].iloc[-1]
    except Exception as e:
        print(f"ATR calculation error: {e}")
        return None

def suggest_parameters(current_price):
    """Generate dynamic grid parameters"""
    df = get_historical_data()
    params = {
        'price_range': current_price * GRID_CONFIG['price_range_percent'] / 100,
        'num_grids': GRID_CONFIG['num_grids']
    }
    
    if df is not None and not df.empty:
        # ATR-based calculation
        atr_value = calculate_atr(df)
        if atr_value:
            params.update({
                'min_price': current_price - GRID_CONFIG['atr_factor'] * atr_value,
                'max_price': current_price + GRID_CONFIG['atr_factor'] * atr_value
            })
        
        # Grid density calculation
        if 'min_price' in params and 'max_price' in params:
            price_range = params['max_price'] - params['min_price']
            params['num_grids'] = min(
                int(price_range / (current_price * GRID_CONFIG['target_profit_pct'] / 100)),
                GRID_CONFIG['max_grids']
            )
    
    return params

def generate_grid(params, current_price):
    """Generate grid levels with dynamic parameters"""
    min_price = params.get('min_price', current_price * (1 - GRID_CONFIG['price_range_percent']/100))
    max_price = params.get('max_price', current_price * (1 + GRID_CONFIG['price_range_percent']/100))
    
    levels = []
    if max_price > min_price:
        step = (max_price - min_price) / (params['num_grids'] + 1)
        levels = [min_price + (i + 1) * step for i in range(params['num_grids'])]
    
    return {
        'buy_levels': sorted(levels),
        'sell_levels': sorted(levels, reverse=True),
        'triggered': [False] * params['num_grids']
    }

def send_email(subject, message):
    # ... existing email sending code ...
    pass

def get_bitcoin_price():
    # ... existing price fetching code ...
    pass

def main():
    current_price = get_bitcoin_price()
    if current_price is None:
        print("Failed to get initial Bitcoin price")
        return
    
    params = suggest_parameters(current_price)
    grid = generate_grid(params, current_price)
    
    print(f"Grid initialized with {params['num_grids']} levels")
    print(f"Price range: {params.get('min_price', 'Auto')} - {params.get('max_price', 'Auto')}")
    
    while True:
        time.sleep(GRID_CONFIG['check_interval'])
        price = get_bitcoin_price()
        if price is None:
            continue
        
        # Check buy levels
        for i, level in enumerate(grid['buy_levels']):
            if price <= level and not grid['triggered'][i]:
                send_email("Buy Signal", f"Price reached buy level: {level:.2f}")
                grid['triggered'][i] = True
        
        # Check sell levels
        for i, level in enumerate(grid['sell_levels']):
            if price >= level and not grid['triggered'][i]:
                send_email("Sell Signal", f"Price reached sell level: {level:.2f}")
                grid['triggered'][i] = True

if __name__ == "__main__":
    main()
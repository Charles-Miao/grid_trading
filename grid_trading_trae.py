import requests
import time
import smtplib
import pandas as pd
import pandas_ta as ta
from email.mime.text import MIMEText

# Configuration
EMAIL_CONFIG = {
    'sender': 'fengkuang33@163.com',
    'password': '241668Miao',
    'smtp_server': 'applesmtp.163.com',
    'smtp_port': 465
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
    """
    获取Binance平台的历史蜡烛图数据

    Args:
        无

    Returns:
        pandas.DataFrame: 包含历史蜡烛图数据的DataFrame对象，索引为时间，列为开盘价、最高价、最低价、收盘价、成交量、成交量（基础资产）、成交量（报价资产）、成交笔数、买单基础资产成交量、买单报价资产成交量、忽略。

    Raises:
        无

    """
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
    """
    波动率量化，通过计算指定周期（当前配置为14小时）的ATR指标，衡量市场波动强度。ATR值越大表示市场波动越剧烈。
    动态风控参数生成，返回最新的ATR值给调用方（如suggest_parameters函数），用于计算动态交易区间。

    Args:
        df (pandas.DataFrame): 包含价格数据的DataFrame。

    Returns:
        float: 计算的ATR值，如果发生错误则返回None。

    Raises:
        Exception: 在计算ATR时发生任何异常。

    """
    """Calculate Average True Range with error handling"""
    try:
        df.ta.atr(length=GRID_CONFIG['atr_period'], append=True)
        return df[f'ATR_{GRID_CONFIG["atr_period"]}'].iloc[-1]
    except Exception as e:
        print(f"ATR calculation error: {e}")
        return None

def suggest_parameters(current_price):
    """
    根据当前价格生成动态网格参数。

    Args:
        current_price (float): 当前价格。

    Returns:
        dict: 包含网格参数的字典，包括价格范围、网格数量和最小价格、最大价格等。

    """
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
    """
    核心功能包括：

    价格区间计算
    根据传入参数或默认配置（price_range_percent），动态确定交易的最低价格（min_price）和最高价格（max_price）

    网格步长生成
    通过 (max_price - min_price) / (网格数量 + 1) 的算法，创建等间距的价格台阶。例如当价格区间为 100-200，网格数量为4时，会产生 [120, 140, 160, 180] 的网格点位

    买卖方向优化
    买入网格按升序排列（价格下跌触发买入），卖出网格按降序排列（价格上涨触发卖出），这种排列方式与常规交易逻辑完全匹配

    状态跟踪初始化
    创建与网格数量相同的布尔值列表，用于记录每个网格是否已被触发，避免重复报警

    Args:
        params (dict): 包含网格参数的字典，包括：
            - 'min_price' (float, optional): 网格的最小价格，默认为当前价格的 (1 - GRID_CONFIG['price_range_percent']/100) 倍。
            - 'max_price' (float, optional): 网格的最大价格，默认为当前价格的 (1 + GRID_CONFIG['price_range_percent']/100) 倍。
            - 'num_grids' (int): 网格的数量。
        current_price (float): 当前价格。

    Returns:
        dict: 包含生成的网格等级的字典，包含以下键：
            - 'buy_levels' (list of float): 按升序排列的买入网格等级。
            - 'sell_levels' (list of float): 按降序排列的卖出网格等级。
            - 'triggered' (list of bool): 一个布尔值列表，表示每个网格是否已触发，默认为 False。

    """
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

def get_bitcoin_price():
    """
    获取比特币当前价格。

    Args:
        无。

    Returns:
        float: 比特币当前价格，若获取失败则返回 None。

    Raises:
        无。

    """
    """Fetch current Bitcoin price from Binance"""
    try:
        response = requests.get(
            f'https://api.binance.com/api/v3/ticker/price?symbol={GRID_CONFIG["symbol"]}'
        )
        response.raise_for_status()
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Price fetch error: {e}")
        return None

def send_email(subject, message):
    """
    发送电子邮件警告。

    Args:
        subject (str): 邮件主题。
        message (str): 邮件内容。

    Returns:
        None

    Raises:
        Exception: 如果邮件发送失败，则抛出异常。
    """
    """Send email alert using SMTP"""
    msg = MIMEText(message, 'plain', 'utf-8')
    msg['From'] = EMAIL_CONFIG['sender']
    msg['To'] = EMAIL_CONFIG['sender']  # Using same email for sender/receiver
    msg['Subject'] = subject
    
    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender'], EMAIL_CONFIG['password'])
            server.sendmail(EMAIL_CONFIG['sender'], [EMAIL_CONFIG['sender']], msg.as_string())
        print("Email alert sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    """
    主函数，用于执行比特币网格交易策略。

    Args:
        无

    Returns:
        无

    """
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
import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# Binance API 配置
exchange = ccxt.binance({
    'apiKey': '你的API_KEY',
    'secret': '你的API_SECRET',
})

# 邮件配置
sender_email = 'fengkuang33@gmail.com'
receiver_email = 'fengkuang33@gmail.com'
smtp_server = 'smtp.gmail.com'
smtp_port = 587
smtp_password = '362580Lv'  # 或使用应用专用密码

# 网格交易参数
symbol = 'BTC/USDT'
grid_factor = 0.5  # 网格密度系数
grid_count = 10    # 网格数量
order_amount = 0.001  # 每个订单的数量

# 获取历史数据并计算 ATR
def get_atr():
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df['ATR'].mean()

# 获取当前价格
def get_current_price():
    ticker = exchange.fetch_ticker(symbol)
    return ticker['last']

# 计算网格密度和价格范围
def calculate_grid_parameters():
    average_atr = get_atr()
    grid_spacing = average_atr * grid_factor
    current_price = get_current_price()
    price_range = 10 * average_atr
    return current_price, grid_spacing, price_range

# 下买单
def place_buy_order(price):
    order = exchange.create_limit_buy_order(symbol, order_amount, price)
    send_email(f'买单已触发', f'已在价格 {price} 下单买入 {order_amount} BTC')
    return order

# 下卖单
def place_sell_order(price):
    order = exchange.create_limit_sell_order(symbol, order_amount, price)
    send_email(f'卖单已触发', f'已在价格 {price} 下单卖出 {order_amount} BTC')
    return order

# 发送邮件提醒
def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, smtp_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())

# 网格交易主逻辑
def grid_trading():
    current_price, grid_spacing, price_range = calculate_grid_parameters()
    buy_price = current_price - price_range / 2
    sell_price = current_price + price_range / 2

    for i in range(grid_count):
        place_buy_order(buy_price)
        place_sell_order(sell_price)
        buy_price += grid_spacing
        sell_price -= grid_spacing
        time.sleep(1)  # 避免频繁请求

if __name__ == '__main__':
    grid_trading()

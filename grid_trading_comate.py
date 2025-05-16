import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import time

# 配置SMTP邮件发送
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587  # Try port 587 for STARTTLS
SMTP_USER = 'XXX@gmail.com'
SMTP_PASS = 'vxju gkgl htsa abcd'  # Replace with your app-specific password
RECEIVER_EMAIL = 'XXX@gmail.com'

# 假设我们已知过去30天的最低价和最高价（实际应用中应通过API获取）
HISTORICAL_LOW = 76000  # 假设的30天最低价
HISTORICAL_HIGH = 95000  # 假设的30天最高价

# 网格交易配置
GRID_PERCENTAGE = 0.02  # 网格密度百分比，例如2%

# 计算价格范围和网格密度
PRICE_RANGE = (HISTORICAL_LOW, HISTORICAL_HIGH)
GRID_DENSITY = (PRICE_RANGE[1] - PRICE_RANGE[0]) * GRID_PERCENTAGE

def get_bitcoin_price():
    """获取比特币价格"""
    try:
        response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=10) #add timeout
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        return data['bitcoin']['usd']
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Bitcoin price: {e}")
        return None

def send_email(subject, message):
    """发送邮件提醒"""
    msg = MIMEText(message, 'plain', 'utf-8')
    msg['From'] = SMTP_USER
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) #add timeout
        server.set_debuglevel(1) #add debug level
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [RECEIVER_EMAIL], msg.as_string())
        server.quit()
        print("邮件发送成功")
    except smtplib.SMTPException as e:
        print(f"邮件发送失败: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during email sending: {e}")

def grid_trading_alert():
    """网格交易提醒"""
    buy_prices = []
    sell_prices = []

    # 根据价格范围和网格密度计算买单和卖单价格点
    price = PRICE_RANGE[0]
    while price <= PRICE_RANGE[1]:
        buy_prices.append(price)
        sell_prices.append(price + GRID_DENSITY)  # 假设卖单价格比买单价格高一个网格密度
        price += GRID_DENSITY

    # 移除超出范围的卖单价格点
    sell_prices = [p for p in sell_prices if p <= PRICE_RANGE[1]]

    while True:
        current_price = get_bitcoin_price()
        if current_price is None:
            time.sleep(60)
            continue
        print(f"当前比特币价格: {current_price}")

        # 检查是否触发买单
        for buy_price in buy_prices:
            if current_price <= buy_price:
                send_email("网格交易提醒", f"触发买单，当前价格: {current_price}，买单价格: {buy_price}")
                # 这里可以添加实际下单的代码，但本示例仅发送提醒
                break  # 假设每次只触发一个买单，触发后跳出循环

        # 检查是否触发卖单
        for sell_price in sell_prices:
            if current_price >= sell_price:
                send_email("网格交易提醒", f"触发卖单，当前价格: {current_price}，卖单价格: {sell_price}")
                # 这里可以添加实际下单的代码，但本示例仅发送提醒
                break  # 假设每次只触发一个卖单，触发后跳出循环

        time.sleep(60)  # 每分钟检查一次价格

if __name__ == "__main__":
    grid_trading_alert()

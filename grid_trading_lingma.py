import time
import smtplib
import requests
import numpy as np
from scipy.stats import norm
from email.mime.text import MIMEText

class BitcoinGridTrader:
    def __init__(self, algorithm_type='volatility'):
        # API配置
        self.api_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        self.history_url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        
        # 运行参数
        self.check_interval = 30  # 秒
        self.algorithm_type = algorithm_type  # 算法类型
        self.base_range = 0.1    # 初始范围（10%）
        self.base_density = 10   # 初始密度
        
        # 邮件配置
        self.email_config = {
            'sender': 'fengkuang33@gmail.com',
            'password': 'vxju gkgl htsa bhoq',
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'receiver': 'fengkuang33@gmail.com'
        }
        
        # 状态变量
        self.current_price = None
        self.buy_levels = []
        self.sell_levels = []
        self.triggered_levels = set()
        self.history_window = 30  # 历史数据天数

    # 核心方法 -------------------------------------------------
    def run(self):
        """启动网格交易监控"""
        print("比特币网格交易系统启动...")
        print(f"当前使用算法: {self.algorithm_type}")
        while True:
            self.check_price()
            time.sleep(self.check_interval)

    def check_price(self):
        """价格检查主逻辑"""
        new_price = self.get_bitcoin_price()
        if new_price is None:
            return

        # 当需要重新生成网格时
        if self.should_regenerate_grid(new_price):
            self.generate_grid(new_price)
            self.triggered_levels.clear()
            self.current_price = new_price

        # 检查交易信号
        self.check_trading_signals(new_price)

    # 网格生成相关 ---------------------------------------------
    def generate_grid(self, base_price):
        """生成交易网格"""
        # 自动更新参数
        self.auto_update_parameters()
        
        # 计算网格参数
        price_range = base_price * self.base_range
        step = price_range / self.base_density
        
        # 生成买卖点位
        self.buy_levels = self.calculate_levels(base_price, -step)
        self.sell_levels = self.calculate_levels(base_price, step)
        
        print(f"\n【网格更新】价格: ${base_price:.2f} | 范围: ±{self.base_range*100}%")
        print(f"网格密度: {self.base_density}层 | 买入区间: [${self.buy_levels[-1]:.2f} ~ ${base_price:.2f}]")
        print(f"卖出区间: [${base_price:.2f} ~ ${self.sell_levels[-1]:.2f}]")

    def calculate_levels(self, base, step):
        """计算价格层级"""
        return [base + i*step for i in range(1, self.base_density+1)]

    def should_regenerate_grid(self, new_price):
        """判断是否需要重新生成网格"""
        if not self.current_price:
            return True
        current_min = min(self.buy_levels) if self.buy_levels else 0
        current_max = max(self.sell_levels) if self.sell_levels else 0
        return new_price < current_min or new_price > current_max

    # 智能算法部分 ---------------------------------------------
    def auto_update_parameters(self):
        """根据算法类型自动更新参数"""
        historical = self.fetch_historical_data()
        if not historical or len(historical) < 30:
            return

        try:
            if self.algorithm_type == 'volatility':
                self.update_by_volatility(historical)
            elif self.algorithm_type == 'atr':
                self.update_by_atr(historical)
            elif self.algorithm_type == 'regime':
                self.update_by_regime(historical)
        except Exception as e:
            print(f"参数更新失败: {e}")

    def update_by_volatility(self, prices):
        """波动率算法更新"""
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns)
        z_score = norm.ppf(0.975)  # 95%置信区间
        
        self.base_range = z_score * volatility
        self.base_density = int(10 / (volatility * 100))
        self.base_density = np.clip(self.base_density, 5, 20)

    def update_by_atr(self, prices):
        """ATR算法更新（需要最高/低价数据）"""
        # 获取高低价数据
        high_low = self.fetch_high_low_data()
        if not high_low or len(high_low) < 14:
            return
            
        # 计算ATR
        tr = [high_low[0]['high'] - high_low[0]['low']]
        for i in range(1, len(high_low)):
            tr.append(max(
                high_low[i]['high'] - high_low[i]['low'],
                abs(high_low[i]['high'] - high_low[i-1]['high']),
                abs(high_low[i]['low'] - high_low[i-1]['low'])
            ))
        atr = np.mean(tr[-14:])
        
        self.base_range = 3 * atr / prices[-1]  # 转换为百分比
        self.base_density = int((3 * atr) / (0.5 * atr))
        self.base_density = np.clip(self.base_density, 8, 25)

    def update_by_regime(self, prices):
        """市场状态算法更新"""
        ma_short = np.mean(prices[-7:])   # 7日均线
        ma_long = np.mean(prices[-30:])   # 30日均线
        trend_strength = abs(ma_short - ma_long) / ma_long
        
        if trend_strength > 0.05:  # 趋势市场
            self.base_range *= 0.6
            self.base_density = int(self.base_density * 0.7)
        else:  # 震荡市场
            self.base_range *= 1.3
            self.base_density = int(self.base_density * 1.4)
        
        self.base_density = np.clip(self.base_density, 8, 25)
        self.base_range = np.clip(self.base_range, 0.05, 0.3)

    # 数据获取相关 ---------------------------------------------
    def get_bitcoin_price(self):
        """获取实时价格"""
        try:
            response = requests.get(self.api_url, timeout=5)
            return response.json()['bitcoin']['usd']
        except Exception as e:
            print(f"价格获取失败: {e}")
            return None

    def fetch_historical_data(self):
        """获取历史收盘价"""
        try:
            params = {'vs_currency': 'usd', 'days': self.history_window}
            response = requests.get(self.history_url, params=params)
            return [x[1] for x in response.json()['prices']]
        except Exception as e:
            print(f"历史数据获取失败: {e}")
            return None

    def fetch_high_low_data(self):
        """获取高低价数据（用于ATR）"""
        try:
            params = {'vs_currency': 'usd', 'days': self.history_window}
            response = requests.get(self.history_url, params=params)
            return [{'high': x[1], 'low': x[2]} for x in response.json()['prices']]
        except:
            return None

    # 交易信号处理 ---------------------------------------------
    def check_trading_signals(self, price):
        """检查买卖信号"""
        for level in self.buy_levels:
            if price <= level and level not in self.triggered_levels:
                self.trigger_signal(level, price, "买入")

        for level in self.sell_levels:
            if price >= level and level not in self.triggered_levels:
                self.trigger_signal(level, price, "卖出")

    def trigger_signal(self, level, price, signal_type):
        """触发交易信号"""
        self.triggered_levels.add(level)
        subject = f"比特币{signal_type}信号 @ ${level:.2f}"
        message = f"""检测到交易信号：
        类型：{signal_type}
        触发价：${level:.2f}
        当前价：${price:.2f}
        时间：{time.strftime('%Y-%m-%d %H:%M:%S')}
        """
        self.send_email(subject, message)
        print(f"! {signal_type}信号 @ ${level:.2f}")

    # 邮件服务 ------------------------------------------------
    def send_email(self, subject, message):
        """发送通知邮件"""
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = self.email_config['sender']
        msg['To'] = self.email_config['receiver']

        try:
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender'], self.email_config['password'])
                server.send_message(msg)
            print("邮件已发送")
        except Exception as e:
            print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    # 初始化交易系统（选择算法：volatility/atr/regime）
    trader = BitcoinGridTrader(algorithm_type='volatility')
    trader.run()
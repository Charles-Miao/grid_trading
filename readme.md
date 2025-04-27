## 问题和想法

- 平时有购买一些比特币，虽然赚了一点钱，但是都是透过手动低买高卖的方式来实现的，这种方式需要花费很多时间在监视比特币的价格上，忙起来的时候，就错过了很多机会。
- 故想通过量化的方式来实现自动的提醒，了解一些算法之后，其中网格交易最简单，也最容易实现，故有了如下一些具体实现。

## 实践1

```bash
grid_trading_comate.py # 这个是comate的实现，需要手动输入最高和最低价格，不够智能，而且买卖逻辑也有点问题，懒得进一步debug，好再实现了gmail发送功能

grid_trading_chatgpt.py # 这个是chatgpt的实现，需要Binance api key，待进一步研究

grid_trading_trae.py # 这个是trae的实现，ATR calculation error: 'ATR_14'，待进一步debug

grid_trading_lingma.py # 这个是lingma的实现，可以发送邮件，但是api.coingecko.com抓取价格的时候容易出错

grid_trading_gemini.py #可以稳定实现，但是无实际用途，脱离了账户的BTC余额，无法实现交易
```

## 新的问题

- 无法基于实际账户中的BTC余额进行评估
- 无法给出多少价格买入多少，多少价格卖出多少的建议

## 实践2
```bash
grid_planner.py

#Example 1: Generate plan using ATR algorithm with default balances:
python grid_planner.py --algorithm ATR

#Example 2: Generate plan using Historical algorithm with default balances:
python grid_planner.py --algorithm Historical

#Example 3: Generate plan using ATR algorithm with custom balances:
python grid_planner.py --algorithm ATR --btc 0.1 --usdt 5000

#Example 4: Generate plan using Historical algorithm with custom balances:
python grid_planner.py --algorithm Historical --btc 0.005 --usdt 1500

#Interpret the Output:
--- Grid Trading Plan Suggestion (Historical Algorithm) ---
Timestamp: 2025-04-27 20:43:36
Current BTCUSDT Price: $93791.22
Input Balances: 0.00061608 BTC, 57.8875 USDT
------------------------------------------------------------
Parameters Used:
  Algorithm: Historical
  Historical Lookback: 180 days
  Target Profit/Grid: 5% (Gross)
  Estimated Fee/Trade: 0%
------------------------------------------------------------
Generated Plan:
  Price Range: $66835.00 - $109588.00
  Total Grids: 11 (Buy: 7, Sell: 4)

  Actions:
    BUY at ~$70397.75  | Spend $8.2696 USDT (Est. Buy 0.00011747 BTC)
    BUY at ~$73960.50  | Spend $8.2696 USDT (Est. Buy 0.00011181 BTC)
    BUY at ~$77523.25  | Spend $8.2696 USDT (Est. Buy 0.00010667 BTC)
    BUY at ~$81086.00  | Spend $8.2696 USDT (Est. Buy 0.00010199 BTC)
    BUY at ~$84648.75  | Spend $8.2696 USDT (Est. Buy 0.00009769 BTC)
    BUY at ~$88211.50  | Spend $8.2696 USDT (Est. Buy 0.00009375 BTC)
    BUY at ~$91774.25  | Spend $8.2696 USDT (Est. Buy 0.00009011 BTC)
    SELL at ~$95337.00  | Sell 0.00015402 BTC (Est. Recv $14.6838 USDT)
    SELL at ~$98899.75  | Sell 0.00015402 BTC (Est. Recv $15.2325 USDT)
    SELL at ~$102462.50 | Sell 0.00015402 BTC (Est. Recv $15.7813 USDT)
    SELL at ~$106025.25 | Sell 0.00015402 BTC (Est. Recv $16.3300 USDT)
```


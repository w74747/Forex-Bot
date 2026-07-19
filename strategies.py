"""
strategies.py - Advanced Strategies
"""

class AdvancedStrategies:
    @staticmethod
    def strategy_momentum_breakout(symbol, bid, ask, price_history):
        mid = (bid + ask) / 2
        price_history[symbol].add(mid)
        if len(list(price_history[symbol].prices)) < 20:
            return None
        prices = list(price_history[symbol].prices)[-20:]
        highest = max(prices[-10:])
        lowest = min(prices[-10:])
        rsi = price_history[symbol].get_rsi(14)
        if mid > highest and rsi and rsi > 50 and rsi < 70:
            return "BUY"
        if mid < lowest and rsi and rsi < 50 and rsi > 30:
            return "SELL"
        return None
    
    @staticmethod
    def strategy_macd_crossover(symbol, bid, ask, price_history):
        mid = (bid + ask) / 2
        price_history[symbol].add(mid)
        if len(list(price_history[symbol].prices)) < 26:
            return None
        prices = list(price_history[symbol].prices)
        ema12 = sum(prices[-12:]) / 12
        ema26 = sum(prices[-26:]) / 26
        macd_now = ema12 - ema26
        macd_prev = (sum(prices[-13:-1]) / 12) - (sum(prices[-27:-1]) / 26)
        signal = (macd_now + macd_prev) / 2
        if macd_prev < signal and macd_now > signal:
            return "BUY"
        if macd_prev > signal and macd_now < signal:
            return "SELL"
        return None
    
    @staticmethod
    def strategy_mean_reversion(symbol, bid, ask, price_history):
        mid = (bid + ask) / 2
        price_history[symbol].add(mid)
        if len(list(price_history[symbol].prices)) < 50:
            return None
        prices = list(price_history[symbol].prices)
        mean = sum(prices[-50:]) / 50
        variance = sum((p - mean) ** 2 for p in prices[-50:]) / 50
        std_dev = variance ** 0.5
        upper_band = mean + (std_dev * 2)
        lower_band = mean - (std_dev * 2)
        if mid < lower_band:
            return "BUY"
        if mid > upper_band:
            return "SELL"
        return None

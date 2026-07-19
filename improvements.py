"""
improvements.py - Strategy Enhancements
"""

class StrategyImprovements:
    
    @staticmethod
    def prevent_overtrading(symbol, open_trades, max_per_symbol=1):
        """منع فتح صفقات متعددة على نفس الزوج"""
        symbol_trades = [t for t in open_trades if t['symbol'] == symbol]
        return len(symbol_trades) < max_per_symbol
    
    @staticmethod
    def add_confirmation_filter(rsi, macd, stoch):
        """تحتاج 2 مؤشرات على الأقل"""
        confirmation = 0
        if rsi and 30 < rsi < 70:
            confirmation += 1
        if macd and macd > 0:
            confirmation += 1
        if stoch and 30 < stoch < 70:
            confirmation += 1
        return confirmation >= 2
    
    @staticmethod
    def dynamic_tp_sl(atr_value, risk_reward=2.0):
        """TP/SL ديناميكي"""
        if atr_value is None:
            atr_value = 0.0005
        sl = atr_value * 1.0
        tp = sl * risk_reward
        return sl, tp
    
    @staticmethod
    def trend_filter(prices, period=20):
        """تصفية بناءً على الاتجاه"""
        if len(prices) < period:
            return None
        sma = sum(prices[-period:]) / period
        current = prices[-1]
        return "UP" if current > sma else "DOWN"

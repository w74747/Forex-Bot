"""
strategies.py - Trading Strategies
"""

import logging

logger = logging.getLogger("strategies")

class TradingStrategies:
    @staticmethod
    def rsi_strategy(prices, period=14):
        """استراتيجية RSI"""
        if len(prices) < period:
            return None
        
        recent = prices[-period:]
        gains = sum(recent[i] - recent[i-1] for i in range(1, len(recent)) if recent[i] > recent[i-1])
        losses = sum(recent[i-1] - recent[i] for i in range(1, len(recent)) if recent[i] < recent[i-1])
        
        avg_gain = gains / period if gains > 0 else 0
        avg_loss = losses / period if losses > 0 else 0
        
        if avg_loss == 0:
            rsi = 100 if avg_gain > 0 else 0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        if rsi < 30:
            return "BUY"
        elif rsi > 70:
            return "SELL"
        return None
    
    @staticmethod
    def moving_average_strategy(prices, short=5, long=20):
        """استراتيجية المتوسطات المتحركة"""
        if len(prices) < long:
            return None
        
        sma_short = sum(prices[-short:]) / short
        sma_long = sum(prices[-long:]) / long
        
        if sma_short > sma_long:
            return "BUY"
        elif sma_short < sma_long:
            return "SELL"
        return None

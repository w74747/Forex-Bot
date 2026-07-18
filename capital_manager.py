"""
capital_manager.py - Dynamic Capital Management for Small & Large Accounts
"""

import logging
from balance_reader import BalanceReader

logger = logging.getLogger("capital_manager")

class CapitalManager:
    def __init__(self, database_url, starting_balance=200, risk_per_trade=3.0):
        """
        إدارة رأس المال الديناميكية
        
        Args:
            database_url: رابط قاعدة البيانات
            starting_balance: الرصيد الابتدائي ($200-300 للحسابات الصغيرة)
            risk_per_trade: نسبة المخاطرة من الرصيد (2-5% للحسابات الصغيرة)
        """
        self.balance_reader = BalanceReader(database_url)
        self.starting_balance = starting_balance
        self.risk_per_trade = risk_per_trade
        
        logger.info(
            f"[Capital Manager] Initialized with ${starting_balance} | "
            f"Risk: {risk_per_trade}% per trade"
        )
    
    def get_current_balance(self):
        """الرصيد الحالي من قاعدة البيانات"""
        return self.balance_reader.get_current_balance()
    
    def get_optimal_lot_size(self, entry_price, strategy=""):
        """
        حساب حجم الـ Lot الأمثل
        
        الصيغة:
        lot_size = (balance × risk%) ÷ (price × 100000)
        
        مثال:
        Balance: $200, Risk: 3%, Entry: 1.08500
        Risk Amount: 200 × 3% = $6
        lot_size = 6 ÷ (1.08500 × 100000) = 0.0055 لوت
        """
        current_balance = self.get_current_balance()
        
        # المبلغ المعرّض للخطر
        risk_amount = current_balance * (self.risk_per_trade / 100)
        
        # حساب الـ Lot
        if entry_price <= 0:
            return 0.001
        
        lot_size = risk_amount / (entry_price * 100000)
        
        # تقريب لـ 4 عشريات
        lot_size = round(lot_size, 4)
        
        # حد أدنى: 0.001 لوت (Micro Lot)
        lot_size = max(0.001, lot_size)
        
        logger.info(
            f"[Lot Size] Balance: ${current_balance:.2f} | "
            f"Risk: ${risk_amount:.2f} ({self.risk_per_trade}%) | "
            f"Entry: {entry_price:.5f} | "
            f"Strategy: {strategy} | "
            f"Lot Size: {lot_size}"
        )
        
        return lot_size
    
    def get_account_stats(self):
        """الإحصائيات الكاملة"""
        current_balance = self.get_current_balance()
        monthly_pnl = self.balance_reader.get_monthly_pnl()
        unrealized_pnl = self.balance_reader.get_open_trades_pnl()
        
        total_pnl = current_balance - self.starting_balance
        roi = (total_pnl / self.starting_balance) * 100
        
        return {
            "starting_balance": self.starting_balance,
            "current_balance": current_balance,
            "total_pnl": total_pnl,
            "monthly_pnl": monthly_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_with_unrealized": current_balance + unrealized_pnl,
            "roi_percent": roi,
            "risk_per_trade": self.risk_per_trade
        }
    
    def get_strategy_allocations(self):
        """توزيع الرصيد على الاستراتيجيات"""
        current_balance = self.get_current_balance()
        
        return {
            "RSI_EMA_MACD": current_balance * 0.333,
            "BB_STOCH": current_balance * 0.333,
            "EMA_ATR": current_balance * 0.334
        }

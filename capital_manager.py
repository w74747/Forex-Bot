"""
capital_manager.py - Dynamic Capital Management
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
            starting_balance: الرصيد الابتدائي
            risk_per_trade: نسبة المخاطرة (%)
        """
        self.balance_reader = BalanceReader(database_url, starting_balance)
        self.starting_balance = starting_balance
        self.risk_per_trade = risk_per_trade
        
        logger.info(
            f"[Capital Manager] Started | "
            f"Balance: ${starting_balance} | Risk: {risk_per_trade}%"
        )
    
    def get_current_balance(self):
        """الرصيد الحالي"""
        return self.balance_reader.get_current_balance()
    
    def get_optimal_lot_size(self, entry_price, strategy=""):
        """حساب حجم الـ Lot الأمثل"""
        current_balance = self.get_current_balance()
        risk_amount = current_balance * (self.risk_per_trade / 100)
        
        if entry_price <= 0:
            return 0.001
        
        lot_size = risk_amount / (entry_price * 100000)
        lot_size = round(lot_size, 4)
        lot_size = max(0.001, lot_size)
        
        logger.info(
            f"[Lot Size] Balance: ${current_balance:.2f} | "
            f"Risk: ${risk_amount:.2f} | Price: {entry_price:.5f} | Lot: {lot_size}"
        )
        
        return lot_size
    
    def get_account_stats(self):
        """الإحصائيات الكاملة"""
        current_balance = self.get_current_balance()
        monthly_pnl = self.balance_reader.get_monthly_pnl()
        unrealized_pnl = self.balance_reader.get_open_trades_pnl()
        
        total_pnl = current_balance - self.starting_balance
        roi = (total_pnl / self.starting_balance) * 100 if self.starting_balance > 0 else 0
        
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

"""
capital_manager.py - Dynamic Capital Management with Real Balance
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

logger = logging.getLogger("capital_manager")

class CapitalManager:
    def __init__(self, database_url, starting_balance=200, risk_per_trade=3, lot_size_multiplier=1.0, ctrader_connector=None):
        self.database_url = database_url
        self.starting_balance = starting_balance
        self.risk_per_trade = risk_per_trade
        self.lot_size_multiplier = lot_size_multiplier
        self.ctrader_connector = ctrader_connector
        self.current_balance = starting_balance
        self.equity = starting_balance
    
    def get_current_balance(self) -> float:
        """قراءة الرصيد الحالي من cTrader أو قاعدة البيانات"""
        try:
            # إذا كان متصلاً مع cTrader، اقرأ الرصيد الحقيقي
            if self.ctrader_connector and self.ctrader_connector.is_connected():
                account_info = self.ctrader_connector.get_account_info()
                if account_info:
                    self.current_balance = account_info.get('balance', self.current_balance)
                    self.equity = account_info.get('equity', self.current_balance)
                    logger.info(f"[Balance] Real: ${self.current_balance:.2f}")
                    return self.current_balance
            
            # إذا لم يكن متصلاً، احسب من قاعدة البيانات
            conn = psycopg2.connect(self.database_url, connect_timeout=5)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(net_pnl), 0) as total_pnl
                    FROM live_paper_trades
                    WHERE status = 'CLOSED'
                """)
                result = cur.fetchone()
                total_pnl = float(result['total_pnl']) if result else 0
            
            conn.close()
            self.current_balance = self.starting_balance + total_pnl
            return self.current_balance
        
        except Exception as e:
            logger.error(f"[Get Balance] {e}")
            return self.current_balance
    
    def get_optimal_lot_size(self, entry_price: float, strategy: str = "MANUAL") -> float:
        """حساب حجم الـ Lot الأمثل مع تطبيق المضاعف"""
        try:
            current_balance = self.get_current_balance()
            risk_amount = (current_balance * self.risk_per_trade) / 100
            
            # حساب الـ lot بناءً على السعر
            lot_size = risk_amount / (entry_price * 100000)
            
            # تطبيق المضاعف
            lot_size = lot_size * self.lot_size_multiplier
            
            # تحديد الحد الأدنى
            lot_size = max(lot_size, 0.001)
            
            logger.info(f"[Lot Size] Balance: ${current_balance:.2f} | Risk: ${risk_amount:.2f} | Price: {entry_price} | Lot: {lot_size}")
            
            return lot_size
        except Exception as e:
            logger.error(f"[Lot Size Error] {e}")
            return 0.001
    
    def get_account_stats(self) -> dict:
        """الحصول على إحصائيات الحساب"""
        try:
            current_balance = self.get_current_balance()
            
            conn = psycopg2.connect(self.database_url, connect_timeout=5)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(SUM(net_pnl), 0) as total_pnl,
                        COUNT(*) as total_trades
                    FROM live_paper_trades
                    WHERE status = 'CLOSED'
                """)
                result = cur.fetchone()
            
            conn.close()
            
            total_pnl = float(result['total_pnl']) if result else 0
            
            return {
                'starting_balance': self.starting_balance,
                'current_balance': current_balance,
                'monthly_pnl': total_pnl,
                'total_trades': result['total_trades'] if result else 0
            }
        except Exception as e:
            logger.error(f"[Account Stats] {e}")
            return {
                'starting_balance': self.starting_balance,
                'current_balance': self.current_balance,
                'monthly_pnl': 0,
                'total_trades': 0
            }

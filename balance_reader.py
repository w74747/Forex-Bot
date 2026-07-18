"""
balance_reader.py - Read Actual Balance from Database
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("balance_reader")

class BalanceReader:
    def __init__(self, database_url):
        self.database_url = database_url
        self.starting_balance = 200  # البداية بـ $200
    
    def get_db(self):
        try:
            return psycopg2.connect(self.database_url, connect_timeout=5)
        except Exception as e:
            logger.error(f"[DB] Connection error: {e}")
            return None
    
    def get_current_balance(self):
        """
        حساب الرصيد الحقيقي:
        Starting Balance + All Net PnL from Closed Trades
        """
        conn = self.get_db()
        if not conn:
            return self.starting_balance
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # احسب مجموع الأرباح من الصفقات المُغلقة
                cur.execute("""
                    SELECT 
                        COALESCE(SUM(net_pnl), 0) as total_pnl
                    FROM live_paper_trades 
                    WHERE status = 'CLOSED'
                """)
                
                result = cur.fetchone()
                total_pnl = float(result['total_pnl']) if result else 0
                
                # الرصيد الحالي = البداية + الأرباح
                current_balance = self.starting_balance + total_pnl
                
                logger.info(
                    f"[Balance] Starting: ${self.starting_balance:.2f} | "
                    f"PnL: ${total_pnl:+.2f} | "
                    f"Current: ${current_balance:.2f}"
                )
                
                return current_balance
        except Exception as e:
            logger.error(f"[Balance Error] {e}")
            return self.starting_balance
        finally:
            conn.close()
    
    def get_monthly_pnl(self):
        """الأرباح/الخسائر للشهر الحالي"""
        conn = self.get_db()
        if not conn:
            return 0
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(SUM(net_pnl), 0) as total_pnl
                    FROM live_paper_trades 
                    WHERE status = 'CLOSED'
                    AND DATE_TRUNC('month', closed_at) = DATE_TRUNC('month', NOW())
                """)
                
                result = cur.fetchone()
                return float(result['total_pnl']) if result else 0
        except Exception as e:
            logger.error(f"[Monthly PnL Error] {e}")
            return 0
        finally:
            conn.close()
    
    def get_open_trades_pnl(self):
        """ربح/خسارة الصفقات المفتوحة الحالية (unrealized)"""
        conn = self.get_db()
        if not conn:
            return 0
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(SUM(gross_pnl), 0) as total_unrealized
                    FROM live_paper_trades 
                    WHERE status = 'OPEN'
                """)
                
                result = cur.fetchone()
                return float(result['total_unrealized']) if result else 0
        except Exception as e:
            logger.error(f"[Open Trades PnL Error] {e}")
            return 0
        finally:
            conn.close()

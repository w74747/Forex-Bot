"""
monthly_tracker.py - Monthly Profit Tracking with Auto Reset
"""

import json
import logging
from datetime import datetime
import os

logger = logging.getLogger("monthly_tracker")

class MonthlyTracker:
    def __init__(self, storage_path="/data/monthly_counter.json"):
        self.storage_path = storage_path
        self.current_month = datetime.now().strftime("%Y-%m")
        self.data = self._load_data()
    
    def _load_data(self):
        """تحميل البيانات من الملف"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    
                    # تحقق من تغيير الشهر
                    if data.get("month") != self.current_month:
                        logger.info(f"[Monthly] Month changed: {data.get('month')} → {self.current_month}")
                        logger.info("[Monthly] Resetting counter for new month")
                        return self._create_empty_data()
                    
                    return data
            except Exception as e:
                logger.error(f"[Monthly] Load error: {e}")
                return self._create_empty_data()
        else:
            return self._create_empty_data()
    
    def _create_empty_data(self):
        """إنشاء بيانات فارغة للشهر الجديد"""
        return {
            "month": self.current_month,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "total_commission": 0.0,
            "net_pnl": 0.0,
            "max_drawdown": 0.0,
            "cumulative_balance": 1000.0,
            "first_trade_time": None,
            "last_trade_time": None,
            "reset_date": datetime.now().isoformat()
        }
    
    def _save_data(self):
        """حفظ البيانات في الملف"""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(self.data, f, indent=2)
            logger.info(f"[Monthly] Data saved")
        except Exception as e:
            logger.error(f"[Monthly] Save error: {e}")
    
    def record_trade(self, pnl, commission, direction=""):
        """تسجيل صفقة"""
        net_pnl = pnl - commission
        
        self.data["total_trades"] += 1
        
        if pnl > 0:
            self.data["winning_trades"] += 1
        else:
            self.data["losing_trades"] += 1
        
        self.data["total_pnl"] += pnl
        self.data["total_commission"] += commission
        self.data["net_pnl"] += net_pnl
        self.data["last_trade_time"] = datetime.now().isoformat()
        
        if not self.data["first_trade_time"]:
            self.data["first_trade_time"] = datetime.now().isoformat()
        
        self._save_data()
        
        logger.info(
            f"[Monthly] Trade recorded: {direction} | PnL: ${pnl:.2f} | "
            f"Monthly Total: ${self.data['net_pnl']:.2f}"
        )
    
    def update_balance(self, current_balance):
        """تحديث الرصيد"""
        self.data["cumulative_balance"] = current_balance
        self._save_data()
    
    def get_summary(self):
        """الحصول على ملخص الشهر الحالي"""
        total_trades = self.data.get("total_trades", 0)
        win_rate = (self.data.get("winning_trades", 0) / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "month": self.current_month,
            "total_trades": self.data.get("total_trades", 0),
            "winning_trades": self.data.get("winning_trades", 0),
            "losing_trades": self.data.get("losing_trades", 0),
            "total_pnl": self.data.get("total_pnl", 0),
            "net_pnl": self.data.get("net_pnl", 0),
            "win_rate": win_rate,
            "balance": self.data.get("cumulative_balance", 0),
            "commission": self.data.get("total_commission", 0)
        }
    
    def is_new_month(self):
        """التحقق من تغيير الشهر"""
        return self.data.get("month") != self.current_month

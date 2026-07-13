"""
risk_manager.py
================
حارس التراجع اليومي (Daily Drawdown Guard) — يتوافق مع شروط شركات
التمويل (Prop Firms) الشائعة: إيقاف كل التداول وإغلاق كل الصفقات
فورًا إذا وصلت خسارة اليوم إلى نسبة محددة (افتراضيًا 4%) من رصيد
بداية اليوم.

هذا الملف لا يتصل بأي API مباشرة — فقط يراقب الأرقام ويستدعي دالة
"إغلاق كل شيء الآن" التي يُمررها له main.py (والتي بدورها تستخدم
fix_executor.py للتنفيذ الفعلي).
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Dict, Optional

from config import RiskConfig

logger = logging.getLogger("forex_bot.risk_manager")


@dataclass
class OpenPositionInfo:
    position_id: int
    symbol_name: str
    symbol_id: int
    is_buy: bool
    volume_lots: float


class RiskManager:
    def __init__(self, cfg: RiskConfig, on_emergency_close_all: Callable[[str], None]):
        self.cfg = cfg
        self.on_emergency_close_all = on_emergency_close_all

        self.daily_start_equity: Optional[float] = None
        self.current_equity: Optional[float] = None
        self.current_balance: Optional[float] = None
        self._last_reset_day: Optional[date] = None
        self.trading_halted = False

        # سجل الصفقات المفتوحة حاليًا (يُحدَّث من main.py عند كل تنفيذ/إغلاق)
        self.open_positions: Dict[int, OpenPositionInfo] = {}

    # ---------- تتبع رأس المال ----------

    def update_account_info(self, balance: float, equity: float):
        today = datetime.now(timezone.utc).date()
        if self._last_reset_day != today:
            self._reset_daily_tracking(equity, today)

        self.current_balance = balance
        self.current_equity = equity
        self._check_drawdown()

    def _reset_daily_tracking(self, equity: float, today: date):
        logger.info("[Risk] بداية يوم تداول جديد — رصيد بداية اليوم: %.2f", equity)
        self.daily_start_equity = equity
        self._last_reset_day = today
        self.trading_halted = False

    def _check_drawdown(self):
        if self.daily_start_equity is None or self.current_equity is None:
            return
        if self.daily_start_equity <= 0:
            return

        drawdown_pct = (self.daily_start_equity - self.current_equity) / self.daily_start_equity * 100.0

        if drawdown_pct >= self.cfg.max_daily_drawdown_pct and not self.trading_halted:
            self.trading_halted = True
            reason = (
                f"تجاوز التراجع اليومي الحد المسموح: {drawdown_pct:.2f}% "
                f">= {self.cfg.max_daily_drawdown_pct}% — إغلاق طارئ لكل الصفقات"
            )
            logger.critical("[Risk] %s", reason)
            self.on_emergency_close_all(reason)

    # ---------- فحوصات ما قبل فتح صفقة جديدة ----------

    def can_open_new_position(self) -> bool:
        if self.trading_halted:
            return False
        if len(self.open_positions) >= self.cfg.max_concurrent_positions:
            return False
        return True

    def calculate_position_size_lots(self, stop_loss_pips: float, pip_value_per_lot: float = 10.0,
                                      contract_size: int = 100_000) -> float:
        """
        يحدد حجم الصفقة بلوت حسب وضع الإعدادات:
          - use_fixed_volume=True  → حجم ثابت دائمًا (trade_volume_units) — موصى به لحساب صغير جدًا
          - use_fixed_volume=False → % من رأس المال مقسومة على مسافة وقف الخسارة (ديناميكي)
        """
        if self.cfg.use_fixed_volume:
            return round(self.cfg.trade_volume_units / contract_size, 2)

        if self.current_equity is None or stop_loss_pips <= 0:
            return 0.0
        risk_amount = self.current_equity * (self.cfg.risk_per_trade_pct / 100.0)
        risk_per_lot = stop_loss_pips * pip_value_per_lot
        if risk_per_lot <= 0:
            return 0.0
        return max(0.0, round(risk_amount / risk_per_lot, 2))

    # ---------- تتبع الصفقات المفتوحة ----------

    def register_open_position(self, info: OpenPositionInfo):
        self.open_positions[info.position_id] = info

    def unregister_position(self, position_id: int):
        self.open_positions.pop(position_id, None)

    def current_drawdown_pct(self) -> float:
        if not self.daily_start_equity or self.current_equity is None:
            return 0.0
        return (self.daily_start_equity - self.current_equity) / self.daily_start_equity * 100.0

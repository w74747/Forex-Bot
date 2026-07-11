"""
TimeLockManager
================
يدير نافذة حماية التمديد الليلي (Rollover Spread Spike Guard):
  - تجميد فتح صفقات جديدة قبل ساعة من موعد التمديد
  - تصفية إجبارية للصفقات المفتوحة قبل موعد التمديد بـ 15 دقيقة
  - فترة تبريد بعد إعادة فتح السوق
"""

import logging
from datetime import datetime, time as dtime
from enum import Enum, auto

from config import Config

logger = logging.getLogger("forex_bot.time_lock")


class MarketPhase(Enum):
    NORMAL = auto()            # التداول مسموح بشكل طبيعي
    FROZEN_NEW_TRADES = auto() # ممنوع فتح صفقات جديدة، الصفقات القائمة مسموحة
    FORCE_LIQUIDATE = auto()   # يجب تصفية كل الصفقات الآن
    ROLLOVER_BLACKOUT = auto() # ممنوع أي تداول إطلاقًا (نافذة الخطر)
    COOLOFF = auto()           # لا يزال ممنوعًا، بانتظار استقرار السبريد


class TimeLockManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _now_est(self) -> datetime:
        return datetime.now(self.cfg.tz_est)

    def now_makkah_str(self) -> str:
        return datetime.now(self.cfg.tz_makkah).strftime("%Y-%m-%d %H:%M:%S")

    def get_phase(self, now: datetime | None = None) -> MarketPhase:
        """يحدد الطور الحالي للسوق بناءً على الوقت الحالي بتوقيت EST."""
        now = now or self._now_est()
        t = now.time()

        freeze_start = dtime(self.cfg.freeze_start_hour_est, self.cfg.freeze_start_minute_est)
        force_liq = dtime(self.cfg.force_liquidation_hour_est, self.cfg.force_liquidation_minute_est)
        rollover_end = dtime(self.cfg.rollover_window_end_hour_est, self.cfg.rollover_window_end_minute_est)
        cooloff_end = dtime(self.cfg.cooloff_end_hour_est, self.cfg.cooloff_end_minute_est)

        if freeze_start <= t < force_liq:
            return MarketPhase.FROZEN_NEW_TRADES
        if force_liq <= t < rollover_end:
            # طوال هذا النطاق: يجب أن تكون كل الصفقات مُصفّاة وممنوع فتح أي صفقة جديدة.
            # المحرك يستدعي التصفية على كل تكة هنا؛ لو لم تعد هناك صفقات مفتوحة
            # فالعملية idempotent ولا تفعل شيئًا - وهذا هو السلوك الآمن المطلوب.
            return MarketPhase.FORCE_LIQUIDATE
        if rollover_end <= t < cooloff_end:
            return MarketPhase.COOLOFF
        return MarketPhase.NORMAL

    def can_open_new_trade(self, now: datetime | None = None) -> bool:
        return self.get_phase(now) == MarketPhase.NORMAL

    def must_force_liquidate(self, now: datetime | None = None) -> bool:
        return self.get_phase(now) == MarketPhase.FORCE_LIQUIDATE

    def log_phase_transition(self, previous: MarketPhase, current: MarketPhase):
        if previous != current:
            logger.info(
                f"[TimeLock] تغيّر طور السوق: {previous.name} -> {current.name} "
                f"| مكة: {self.now_makkah_str()}"
            )

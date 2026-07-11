"""
MarketScanner
=============
منطق الدخول القائم على الإحصاء البحت (Mean Reversion):
  - يحسب ATR والانحراف المعياري المتحرك (Rolling STD)
  - يصدر إشارة عندما ينحرف السعر عن المتوسط الصغير بأكثر من X انحراف معياري
لا يستخدم أي مؤشر تأخّري تقليدي ولا أي نموذج تعلم آلي.
"""

import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from statistics import mean, pstdev
from typing import Deque, Optional

from config import Config

logger = logging.getLogger("forex_bot.market_scanner")


class SignalType(Enum):
    NONE = auto()
    BUY_REVERSION = auto()   # السعر منخفض بشكل متطرف -> نتوقع ارتدادًا صعوديًا
    SELL_REVERSION = auto()  # السعر مرتفع بشكل متطرف -> نتوقع ارتدادًا هبوطيًا


@dataclass
class Tick:
    symbol: str
    bid: float
    ask: float
    timestamp: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pips(self) -> float:
        # نفترض 5 خانات عشرية لأزواج XXX/USD -> النقطة (pip) = 0.0001
        return (self.ask - self.bid) * 10000.0


class SymbolWindow:
    """يحتفظ بنافذة متحركة من الأسعار لرمز واحد لحساب ATR/STD."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        max_len = max(cfg.atr_period, cfg.std_period) + 1
        self.prices: Deque[float] = deque(maxlen=max_len)
        self.highs: Deque[float] = deque(maxlen=cfg.atr_period + 1)
        self.lows: Deque[float] = deque(maxlen=cfg.atr_period + 1)

    def update(self, tick: Tick):
        self.prices.append(tick.mid)
        self.highs.append(tick.ask)
        self.lows.append(tick.bid)

    def rolling_std(self) -> Optional[float]:
        if len(self.prices) < self.cfg.std_period:
            return None
        window = list(self.prices)[-self.cfg.std_period:]
        return pstdev(window)

    def rolling_mean(self) -> Optional[float]:
        if len(self.prices) < self.cfg.std_period:
            return None
        window = list(self.prices)[-self.cfg.std_period:]
        return mean(window)

    def atr(self) -> Optional[float]:
        if len(self.highs) < self.cfg.atr_period + 1:
            return None
        highs = list(self.highs)
        lows = list(self.lows)
        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - highs[i - 1]),
                abs(lows[i] - lows[i - 1]),
            )
            true_ranges.append(tr)
        if not true_ranges:
            return None
        return mean(true_ranges[-self.cfg.atr_period:])


class MarketScanner:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.windows = {symbol: SymbolWindow(cfg) for symbol in cfg.target_pairs}

    def on_tick(self, tick: Tick) -> SignalType:
        window = self.windows.get(tick.symbol)
        if window is None:
            return SignalType.NONE

        window.update(tick)

        std = window.rolling_std()
        m = window.rolling_mean()
        atr_val = window.atr()

        if std is None or m is None or atr_val is None or std == 0:
            return SignalType.NONE

        # فلترة السبريد: لا إشارة إذا كان السبريد أعلى من الحد المسموح
        if tick.spread_pips > self.cfg.max_allowed_spread_pips:
            return SignalType.NONE

        deviation = tick.mid - m
        z_like = deviation / std  # مقياس مشابه لـ z-score باستخدام الانحراف المعياري المتحرك

        threshold = self.cfg.entry_std_multiplier

        if z_like <= -threshold:
            logger.debug(
                f"[Scanner] {tick.symbol} انحراف سفلي متطرف z={z_like:.2f} -> إشارة شراء ارتدادي"
            )
            return SignalType.BUY_REVERSION
        elif z_like >= threshold:
            logger.debug(
                f"[Scanner] {tick.symbol} انحراف علوي متطرف z={z_like:.2f} -> إشارة بيع ارتدادي"
            )
            return SignalType.SELL_REVERSION

        return SignalType.NONE

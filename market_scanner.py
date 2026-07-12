"""
market_scanner.py
===================
منطق الدخول الإحصائي البحت (Mean Reversion) — بلا أي اعتماد على Twisted
أو asyncio، فقط دوال حسابية عادية. يُغذّى ببيانات الأسعار الواردة من
openapi_streamer.py عبر callback بسيط.

القيم الافتراضية هنا (عتبة 2.5 انحراف معياري / SL=4 / TP=6 نقاط) هي
نفس نتيجة البحث المنهجي (param_sweep) الذي أجريناه على النسخة السابقة
من المشروع على بيانات اصطناعية — راجع تنبيهات README لعدم اعتبارها
حافة مضمونة على بيانات حقيقية.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from statistics import mean, pstdev
from typing import Deque, Optional


class SignalType(Enum):
    NONE = auto()
    BUY_REVERSION = auto()
    SELL_REVERSION = auto()


@dataclass
class ScannerConfig:
    std_period: int = 20
    entry_std_multiplier: float = 2.5
    max_allowed_spread_pips: float = 0.3
    pip_size: float = 0.0001


class SymbolWindow:
    def __init__(self, cfg: ScannerConfig):
        self.cfg = cfg
        self.prices: Deque[float] = deque(maxlen=cfg.std_period)

    def update(self, mid_price: float):
        self.prices.append(mid_price)

    def rolling_std(self) -> Optional[float]:
        if len(self.prices) < self.cfg.std_period:
            return None
        return pstdev(self.prices)

    def rolling_mean(self) -> Optional[float]:
        if len(self.prices) < self.cfg.std_period:
            return None
        return mean(self.prices)


class MarketScanner:
    def __init__(self, cfg: ScannerConfig, symbols: list[str]):
        self.cfg = cfg
        self.windows = {s: SymbolWindow(cfg) for s in symbols}

    def on_price(self, symbol: str, bid: float, ask: float) -> SignalType:
        window = self.windows.get(symbol)
        if window is None:
            return SignalType.NONE

        mid = (bid + ask) / 2.0
        window.update(mid)

        std = window.rolling_std()
        m = window.rolling_mean()
        if std is None or m is None or std == 0:
            return SignalType.NONE

        spread_pips = (ask - bid) / self.cfg.pip_size
        if spread_pips > self.cfg.max_allowed_spread_pips:
            return SignalType.NONE

        z_like = (mid - m) / std
        if z_like <= -self.cfg.entry_std_multiplier:
            return SignalType.BUY_REVERSION
        if z_like >= self.cfg.entry_std_multiplier:
            return SignalType.SELL_REVERSION
        return SignalType.NONE

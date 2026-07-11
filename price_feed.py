"""
SimulatedPriceFeed
===================
مولد تكات (ticks) وهمي باستخدام Random Walk + عودة للمتوسط طفيفة،
يُستخدم فقط لاختبار منطق البوت محليًا دون اتصال حقيقي بالسوق.

⚠️ هذه بيانات اصطناعية وليست بيانات سوق حقيقية - الغرض منها اختبار
   الكود فقط (Paper Trading الداخلي)، وليست مؤشرًا على أداء حقيقي متوقع.

عند الربط بـ MT5 الحقيقي، يُستبدل هذا الملف بجلب التكات الفعلية عبر
`MetaTrader5.symbol_info_tick(symbol)`.
"""

import random
import time
from typing import AsyncIterator, Dict

from market_scanner import Tick


class SimulatedPriceFeed:
    def __init__(self, symbols, base_prices: Dict[str, float] | None = None, seed: int | None = None):
        self.symbols = symbols
        self.rng = random.Random(seed)
        self.base_prices = base_prices or {"EURUSD": 1.08500, "GBPUSD": 1.27000}
        self.current = dict(self.base_prices)
        # نطاق سبريد واقعي تقريبي لحسابات ECN (بالنقاط)
        self.spread_pips = {"EURUSD": 0.15, "GBPUSD": 0.2}

    def _step_price(self, symbol: str) -> float:
        price = self.current[symbol]
        pip = 0.0001
        # حركة عشوائية صغيرة + ميل طفيف للعودة نحو السعر الأساسي (mean reversion صناعي)
        drift_to_base = (self.base_prices[symbol] - price) * 0.02
        noise = self.rng.gauss(0, 1) * pip * 1.2
        # أحيانًا نضخّم الحركة لمحاكاة "انحرافات" يمكن للاستراتيجية اكتشافها
        if self.rng.random() < 0.03:
            noise += self.rng.choice([-1, 1]) * pip * self.rng.uniform(3, 8)
        new_price = price + drift_to_base + noise
        self.current[symbol] = new_price
        return new_price

    def next_tick(self, symbol: str, sim_time: float) -> Tick:
        mid = self._step_price(symbol)
        half_spread = (self.spread_pips[symbol] / 2) * 0.0001
        return Tick(
            symbol=symbol,
            bid=mid - half_spread,
            ask=mid + half_spread,
            timestamp=sim_time,
        )

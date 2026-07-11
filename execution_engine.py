"""
ExecutionEngine
===============
الحلقة الرئيسية (asyncio) التي تراقب الأسعار لكل زوج بالتوازي،
تطبق حماية التمديد الليلي، وتُنفّذ منطق الدخول/الخروج عبر PaperBroker.

هذا الملف يعمل حاليًا في وضع "محاكاة" (Simulation Mode) باستخدام
SimulatedPriceFeed. عند الربط بحساب MT5 حقيقي، يُستبدل مصدر التكات
فقط - بقية المنطق (الحماية الزمنية، الفلترة، التنفيذ) يبقى كما هو.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from config import Config
from market_scanner import MarketScanner, SignalType
from paper_broker import PaperBroker
from price_feed import SimulatedPriceFeed
from time_lock import MarketPhase, TimeLockManager

logger = logging.getLogger("forex_bot.engine")


class ExecutionEngine:
    def __init__(self, cfg: Config, sim_start_est: datetime | None = None, seed: int | None = None,
                 real_time_sleep: bool = True):
        self.cfg = cfg
        self.scanner = MarketScanner(cfg)
        self.broker = PaperBroker(cfg)
        self.time_lock = TimeLockManager(cfg)
        self.feed = SimulatedPriceFeed(cfg.target_pairs, seed=seed)
        self.latest_ticks = {}
        self._last_phase = MarketPhase.NORMAL
        self._last_day = None
        self.real_time_sleep = real_time_sleep

        # في وضع المحاكاة، نتحكم بالوقت يدويًا لنستطيع "تسريع" الأيام بدل انتظارها فعليًا
        self.sim_time = sim_start_est or datetime.now(cfg.tz_est)
        # كل خطوة محاكاة تقدّم الوقت بضع ثوانٍ لتسريع اختبار سيناريوهات التمديد الليلي
        self.sim_step_seconds = 20

    async def run_symbol_loop(self, symbol: str, stop_event: asyncio.Event, sim_end_time: datetime):
        while not stop_event.is_set():
            if self.sim_time >= sim_end_time:
                stop_event.set()
                break

            tick = self.feed.next_tick(symbol, self.sim_time.timestamp())
            self.latest_ticks[symbol] = tick

            phase = self.time_lock.get_phase(self.sim_time)
            self.time_lock.log_phase_transition(self._last_phase, phase)
            self._last_phase = phase

            # --- إدارة يومية: إعادة ضبط تتبع الخسارة اليومية عند بداية يوم جديد ---
            current_day = self.sim_time.date()
            if self._last_day != current_day:
                self.broker.reset_daily_tracking()
                self._last_day = current_day

            # --- Pillar A: حماية التمديد الليلي ---
            if phase == MarketPhase.FORCE_LIQUIDATE:
                if self.broker.has_open_position(symbol):
                    self.broker.close_position(symbol, tick, reason="ROLLOVER_FORCE_CLOSE")
                await asyncio.sleep(0)  # لا تنفيذ صفقات جديدة أثناء هذا الطور
            elif phase in (MarketPhase.ROLLOVER_BLACKOUT, MarketPhase.COOLOFF):
                pass  # ممنوع أي تداول
            elif phase == MarketPhase.FROZEN_NEW_TRADES:
                # صفقات جديدة ممنوعة، لكن إدارة الصفقات القائمة مستمرة
                if self.broker.has_open_position(symbol):
                    self._manage_open_position(symbol, tick)
            else:  # NORMAL
                if self.broker.has_open_position(symbol):
                    self._manage_open_position(symbol, tick)
                else:
                    signal = self.scanner.on_tick(tick)
                    if signal != SignalType.NONE:
                        self.broker.open_position(tick, signal)

            self.sim_time += timedelta(seconds=self.sim_step_seconds)
            if self.real_time_sleep:
                await asyncio.sleep(1.0 / self.cfg.ticks_per_second)
            else:
                await asyncio.sleep(0)  # يترك الفرصة لبقية المهام بدون إبطاء فعلي

    def _manage_open_position(self, symbol: str, tick):
        pos = self.broker.account.open_positions.get(symbol)
        if pos is None:
            return
        self.broker.update_trailing_stop(pos, tick)
        exit_reason = self.broker.check_exit_conditions(pos, tick)
        if exit_reason:
            self.broker.close_position(symbol, tick, reason=exit_reason)

    async def run(self, total_sim_seconds: float):
        stop_event = asyncio.Event()
        sim_end_time = self.sim_time + timedelta(seconds=total_sim_seconds)

        tasks = [
            asyncio.create_task(self.run_symbol_loop(s, stop_event, sim_end_time))
            for s in self.cfg.target_pairs
        ]

        await asyncio.gather(*tasks)

        # تصفية أي صفقات متبقية في نهاية المحاكاة
        self.broker.force_close_all(self.latest_ticks, reason="SIMULATION_END")

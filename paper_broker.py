"""
PaperBroker
===========
سمسار وهمي (Paper Trading) يحاكي فتح/إغلاق الصفقات، حساب العمولة،
وتتبع رأس المال والأرباح والخسائر - دون أي اتصال بمال حقيقي.

هذا الملف هو ما يسمح لنا باختبار منطق البوت بأكمله محليًا وبأمان
قبل أي ربط لاحق مع MetaTrader5 حقيقي.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import Config
from market_scanner import SignalType, Tick

logger = logging.getLogger("forex_bot.paper_broker")


@dataclass
class Position:
    symbol: str
    direction: str          # "BUY" or "SELL"
    entry_price: float
    lot_size: float
    open_time: float
    stop_price: float
    take_profit_price: float
    id: str


@dataclass
class ClosedTrade:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    lot_size: float
    pnl: float
    commission: float
    net_pnl: float
    reason: str
    open_time: float
    close_time: float


@dataclass
class AccountState:
    equity: float
    starting_equity: float
    open_positions: Dict[str, Position] = field(default_factory=dict)
    closed_trades: List[ClosedTrade] = field(default_factory=list)
    daily_start_equity: float = 0.0


class PaperBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.account = AccountState(
            equity=cfg.starting_equity,
            starting_equity=cfg.starting_equity,
            daily_start_equity=cfg.starting_equity,
        )
        self._position_counter = 0

    # ---------- حساب حجم الصفقة ----------
    def calculate_lot_size(self) -> float:
        """يحسب حجم اللوت بناءً على % المخاطرة من رأس المال والرافعة المحددة في الإعدادات."""
        risk_amount = self.account.equity * (self.cfg.risk_per_trade_pct / 100.0)
        # نفترض أن وقف الخسارة بالنقاط يحدد الخسارة القصوى المسموحة لكل لوت
        risk_per_lot = self.cfg.trailing_stop_pips * self.cfg.pip_value_per_lot
        if risk_per_lot <= 0:
            return 0.0
        raw_lot = risk_amount / risk_per_lot

        # تطبيق سقف الرافعة: القيمة الاسمية للصفقة يجب ألا تتجاوز equity * leverage
        notional_cap = (self.account.equity * self.cfg.leverage) / 100000.0  # بالوحدات القياسية للوت
        lot_size = min(raw_lot, notional_cap)

        # تقريب لأقرب micro-lot (0.01)
        lot_size = max(0.0, round(lot_size, 2))
        return lot_size

    def has_open_position(self, symbol: str) -> bool:
        return symbol in self.account.open_positions

    def can_open_more_positions(self) -> bool:
        return len(self.account.open_positions) < self.cfg.max_concurrent_positions

    def daily_drawdown_pct(self) -> float:
        if self.account.daily_start_equity == 0:
            return 0.0
        diff = self.account.daily_start_equity - self.account.equity
        return (diff / self.account.daily_start_equity) * 100.0

    def daily_limit_hit(self) -> bool:
        return self.daily_drawdown_pct() >= self.cfg.max_daily_drawdown_pct

    def reset_daily_tracking(self):
        self.account.daily_start_equity = self.account.equity

    # ---------- فتح الصفقات ----------
    def open_position(self, tick: Tick, signal: SignalType) -> Optional[Position]:
        if self.has_open_position(tick.symbol):
            return None
        if not self.can_open_more_positions():
            return None
        if self.daily_limit_hit():
            logger.warning("[Broker] تم بلوغ حد الخسارة اليومية - رفض فتح صفقة جديدة")
            return None

        lot_size = self.calculate_lot_size()
        if lot_size <= 0:
            return None

        direction = "BUY" if signal == SignalType.BUY_REVERSION else "SELL"
        entry_price = tick.ask if direction == "BUY" else tick.bid

        pip = 0.0001
        if direction == "BUY":
            stop_price = entry_price - self.cfg.trailing_stop_pips * pip
            tp_price = entry_price + self.cfg.fixed_take_profit_pips * pip
        else:
            stop_price = entry_price + self.cfg.trailing_stop_pips * pip
            tp_price = entry_price - self.cfg.fixed_take_profit_pips * pip

        self._position_counter += 1
        pos = Position(
            symbol=tick.symbol,
            direction=direction,
            entry_price=entry_price,
            lot_size=lot_size,
            open_time=tick.timestamp,
            stop_price=stop_price,
            take_profit_price=tp_price,
            id=f"P{self._position_counter}",
        )
        self.account.open_positions[tick.symbol] = pos
        logger.info(
            f"[Broker] فتح {direction} {tick.symbol} @ {entry_price:.5f} "
            f"لوت={lot_size} SL={stop_price:.5f} TP={tp_price:.5f}"
        )
        return pos

    # ---------- إدارة الوقف المتحرك + التحقق من الإغلاق ----------
    def update_trailing_stop(self, pos: Position, tick: Tick):
        pip = 0.0001
        if pos.direction == "BUY":
            new_stop = tick.bid - self.cfg.trailing_stop_pips * pip
            if new_stop > pos.stop_price:
                pos.stop_price = new_stop
        else:
            new_stop = tick.ask + self.cfg.trailing_stop_pips * pip
            if new_stop < pos.stop_price:
                pos.stop_price = new_stop

    def check_exit_conditions(self, pos: Position, tick: Tick) -> Optional[str]:
        if pos.direction == "BUY":
            if tick.bid <= pos.stop_price:
                return "STOP_LOSS"
            if tick.bid >= pos.take_profit_price:
                return "TAKE_PROFIT"
        else:
            if tick.ask >= pos.stop_price:
                return "STOP_LOSS"
            if tick.ask <= pos.take_profit_price:
                return "TAKE_PROFIT"
        return None

    def close_position(self, symbol: str, tick: Tick, reason: str) -> Optional[ClosedTrade]:
        pos = self.account.open_positions.pop(symbol, None)
        if pos is None:
            return None

        exit_price = tick.bid if pos.direction == "BUY" else tick.ask
        pip = 0.0001
        pip_diff = (exit_price - pos.entry_price) / pip
        if pos.direction == "SELL":
            pip_diff = -pip_diff

        gross_pnl = pip_diff * self.cfg.pip_value_per_lot * pos.lot_size
        commission = self.cfg.commission_per_lot_round_turn * pos.lot_size
        net_pnl = gross_pnl - commission

        self.account.equity += net_pnl

        trade = ClosedTrade(
            symbol=symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            lot_size=pos.lot_size,
            pnl=gross_pnl,
            commission=commission,
            net_pnl=net_pnl,
            reason=reason,
            open_time=pos.open_time,
            close_time=tick.timestamp,
        )
        self.account.closed_trades.append(trade)

        logger.info(
            f"[Broker] إغلاق {pos.direction} {symbol} @ {exit_price:.5f} | السبب={reason} "
            f"| PnL إجمالي={gross_pnl:.3f} عمولة={commission:.3f} صافي={net_pnl:.3f} "
            f"| الرصيد الآن={self.account.equity:.2f}"
        )
        return trade

    def force_close_all(self, latest_ticks: Dict[str, Tick], reason: str = "ROLLOVER_FORCE_CLOSE"):
        symbols = list(self.account.open_positions.keys())
        for symbol in symbols:
            tick = latest_ticks.get(symbol)
            if tick:
                self.close_position(symbol, tick, reason)

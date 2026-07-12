"""
main.py
========
نقطة التشغيل المركزية. يربط:
  - openapi_streamer.py  (بيانات + مصادقة + SL/TP على الخادم)
  - fix_executor.py      (تنفيذ سريع للدخول/الخروج)
  - market_scanner.py    (منطق الإشارة الرياضي)
  - risk_manager.py      (حارس التراجع اليومي 4%)
  - telegram_notifier.py (إشعارات + عداد شهري)

⚠️ ترتيب الاستيراد أدناه إلزامي ولا يجوز تغييره:
   يجب تثبيت asyncioreactor **قبل** أي استيراد لأي وحدة تستورد Twisted
   reactor (بشكل مباشر أو غير مباشر عبر ctrader_open_api / ctrader_fix)،
   لأن Twisted يُثبّت الـ reactor الافتراضي تلقائيًا عند أول
   "from twisted.internet import reactor" في أي مكان بالكود.
   هذا هو الأساس التقني لتشغيل الحزمتين معًا بدون تعارض أو Threading.
"""

import asyncio
import logging
import sys

from twisted.internet import asyncioreactor

_event_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_event_loop)
asyncioreactor.install(_event_loop)

# ⬇️ كل الاستيرادات التالية تأتي بعد تثبيت الـ reactor عن قصد — لا تُعِد ترتيبها
from twisted.internet import reactor  # noqa: E402
from twisted.internet.task import LoopingCall  # noqa: E402

from config import Config  # noqa: E402
from fix_executor import FixExecutor  # noqa: E402
from market_scanner import MarketScanner, ScannerConfig, SignalType  # noqa: E402
from openapi_streamer import OpenApiStreamer  # noqa: E402
from risk_manager import OpenPositionInfo, RiskManager  # noqa: E402
from startup_reconciliation import StartupReconciler  # noqa: E402
from telegram_notifier import MonthlyProfitCounter, TelegramNotifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("forex_bot.log", encoding="utf-8")],
)
logger = logging.getLogger("forex_bot.main")


class TradingSystem:
    """يحمل الحالة المشتركة بين كل المكونات، ويمرر الـ callbacks بينها."""

    CONTRACT_SIZE = 100_000
    SL_PIPS = 4.0
    TP_PIPS = 6.0
    PIP_SIZE = 0.0001

    def __init__(self, cfg: Config):
        self.cfg = cfg

        self.scanner = MarketScanner(
            ScannerConfig(entry_std_multiplier=2.5, max_allowed_spread_pips=0.3),
            symbols=cfg.risk.target_symbols,
        )
        self.risk_manager = RiskManager(cfg.risk, on_emergency_close_all=self._emergency_close_all)
        self.telegram = TelegramNotifier(cfg.telegram, MonthlyProfitCounter())

        # ذاكرة محلية للصفقات المفتوحة: position_id -> تفاصيل الدخول
        self._local_positions: dict[int, dict] = {}
        self._latest_prices: dict[str, tuple[float, float]] = {}

        self.openapi = OpenApiStreamer(
            cfg,
            on_price_update=self._on_price_update,
            on_account_info=self._on_account_info,
            on_reconcile=self._on_reconcile,
        )
        self.fix = FixExecutor(
            cfg,
            on_execution=self._on_fix_execution,
            on_reject=self._on_fix_reject,
        )
        self.reconciler = StartupReconciler(
            sl_pips=self.SL_PIPS, tp_pips=self.TP_PIPS, pip_size=self.PIP_SIZE,
            amend_sl_tp_fn=self.openapi.amend_position_sl_tp,
        )

    # ---------- التشغيل ----------

    def start(self):
        logger.info("=== بدء نظام التداول الهجين (OpenAPI + FIX) ===")
        logger.info("وضع التشغيل: %s", "DRY_RUN (محاكاة تنفيذ فعلي بدون إرسال أوامر حقيقية)"
                     if self.cfg.dry_run else "🔴 LIVE — تنفيذ أوامر حقيقية")
        self.telegram.notify_system_event("تم بدء تشغيل البوت" +
                                           (" في وضع DRY_RUN" if self.cfg.dry_run else " في وضع LIVE"))

        self.openapi.start()
        self.fix.start()

        # استطلاع دوري لمعلومات الحساب (الرصيد) كل 30 ثانية — Open API لا يبث
        # الرصيد تلقائيًا، لذا نطلبه صراحة بشكل متكرر
        self._account_poll = LoopingCall(self.openapi.fetch_trader_info)
        self._account_poll.start(30, now=False)

    def stop(self):
        logger.info("=== إيقاف النظام ===")
        if hasattr(self, "_account_poll") and self._account_poll.running:
            self._account_poll.stop()
        self.fix.stop()

    # ---------- استقبال الأسعار وتوليد الإشارات ----------

    def _on_price_update(self, symbol: str, bid: float, ask: float):
        self._latest_prices[symbol] = (bid, ask)

        # 1) فحص خروج للصفقات المفتوحة على هذا الرمز أولاً (أولوية للحماية)
        self._check_local_exits(symbol, bid, ask)

        # 2) بحث عن إشارة دخول جديدة إن لم تكن هناك صفقة مفتوحة عليه
        if not self.risk_manager.can_open_new_position():
            return
        if any(p["symbol_name"] == symbol for p in self._local_positions.values()):
            return  # صفقة واحدة كحد أقصى لكل رمز في هذا البويلربليت

        signal = self.scanner.on_price(symbol, bid, ask)
        if signal == SignalType.NONE:
            return

        self._open_new_position(symbol, is_buy=(signal == SignalType.BUY_REVERSION), bid=bid, ask=ask)

    def _open_new_position(self, symbol: str, is_buy: bool, bid: float, ask: float):
        symbol_id = self.openapi.symbol_name_to_id.get(symbol)
        if symbol_id is None:
            logger.warning("[Main] symbolId غير معروف بعد لـ %s — تخطي الإشارة", symbol)
            return

        volume_lots = self.risk_manager.calculate_position_size_lots(self.SL_PIPS)
        if volume_lots <= 0:
            logger.warning("[Main] حجم صفقة محسوب = 0 — تخطي (تأكد من وصول معلومات الحساب)")
            return

        if self.cfg.dry_run:
            logger.info("[DRY_RUN] كان سيُفتح %s %s حجم=%s لوت (لا إرسال فعلي)",
                         "شراء" if is_buy else "بيع", symbol, volume_lots)
            return

        entry_price = ask if is_buy else bid
        sl_price = entry_price - self.SL_PIPS * self.PIP_SIZE if is_buy else entry_price + self.SL_PIPS * self.PIP_SIZE
        tp_price = entry_price + self.TP_PIPS * self.PIP_SIZE if is_buy else entry_price - self.TP_PIPS * self.PIP_SIZE

        intent = {
            "symbol_name": symbol,
            "symbol_id": symbol_id,
            "is_buy": is_buy,
            "volume_lots": volume_lots,
            "planned_sl_price": sl_price,
            "planned_tp_price": tp_price,
        }
        self.fix.send_market_order(symbol_id, is_buy, volume_lots, self.CONTRACT_SIZE, intent_tag=intent)

    def _check_local_exits(self, symbol: str, bid: float, ask: float):
        for position_id, pos in list(self._local_positions.items()):
            if pos["symbol_name"] != symbol or pos.get("closing"):
                continue
            price_now = bid if pos["is_buy"] else ask
            hit_sl = price_now <= pos["planned_sl_price"] if pos["is_buy"] else price_now >= pos["planned_sl_price"]
            hit_tp = price_now >= pos["planned_tp_price"] if pos["is_buy"] else price_now <= pos["planned_tp_price"]
            if hit_sl or hit_tp:
                pos["closing"] = True
                reason = "TAKE_PROFIT" if hit_tp else "STOP_LOSS"
                logger.info("[Main] إغلاق برمجي (%s) لصفقة %s على %s", reason, position_id, symbol)
                self.fix.close_position(pos["symbol_id"], pos["is_buy"], pos["volume_lots"], position_id,
                                         self.CONTRACT_SIZE)

    # ---------- ردود الفعل من FIX ----------

    def _on_fix_execution(self, report: dict):
        position_id = report.get("position_id")
        if position_id is None:
            logger.warning("[Main] تقرير تنفيذ بلا position_id — تعذّر ربطه: %s", report)
            return

        is_closing = "closing_position_id" in report

        if not is_closing:
            # فتح صفقة جديدة بنجاح
            entry_price = report.get("avg_price")
            self._local_positions[position_id] = {
                "symbol_name": report["symbol_name"],
                "symbol_id": report["symbol_id"],
                "is_buy": report["is_buy"],
                "volume_lots": report["volume_lots"],
                "entry_price": entry_price,
                "planned_sl_price": report["planned_sl_price"],
                "planned_tp_price": report["planned_tp_price"],
                "closing": False,
            }
            self.risk_manager.register_open_position(OpenPositionInfo(
                position_id=position_id, symbol_name=report["symbol_name"],
                symbol_id=report["symbol_id"], is_buy=report["is_buy"],
                volume_lots=report["volume_lots"],
            ))
            # تثبيت SL/TP على مستوى الخادم كشبكة أمان (عبر Open API — الطريقة
            # الوحيدة الممكنة تقنيًا) بالإضافة إلى المراقبة البرمجية الأسرع أعلاه
            self.openapi.amend_position_sl_tp(
                position_id,
                stop_loss=report["planned_sl_price"],
                take_profit=report["planned_tp_price"],
            )
            logger.info("[Main] صفقة جديدة مسجّلة محليًا: %s", position_id)

        else:
            # إغلاق صفقة قائمة — نحسب الربح/الخسارة التقريبي
            original = self._local_positions.pop(position_id, None)
            self.risk_manager.unregister_position(position_id)
            if original is None:
                logger.warning("[Main] إغلاق صفقة غير معروفة محليًا: %s", position_id)
                return

            exit_price = report.get("avg_price") or 0.0
            entry_price = original["entry_price"] or exit_price
            pip_diff = (exit_price - entry_price) / self.PIP_SIZE
            if not original["is_buy"]:
                pip_diff = -pip_diff
            # ⚠️ تقريبي: لا يشمل العمولة الفعلية (تتطلب ProtoOADealListReq من
            # Open API لجلب العمولة الدقيقة لكل صفقة — TODO لنسخة لاحقة)
            pip_value_per_lot = 10.0
            gross_pnl = pip_diff * pip_value_per_lot * original["volume_lots"]

            reason = "TAKE_PROFIT" if pip_diff > 0 else "STOP_LOSS"
            self.telegram.notify_trade_closed(original["symbol_name"],
                                               "شراء" if original["is_buy"] else "بيع",
                                               gross_pnl, reason)
            logger.info("[Main] صفقة %s أُغلقت — ربح/خسارة تقريبي: %.2f$", position_id, gross_pnl)

    def _on_fix_reject(self, cl_ord_id: str, reason: str):
        logger.error("[Main] رُفض أمر %s: %s", cl_ord_id, reason)
        self.telegram.notify_system_event(f"رُفض أمر تداول: {reason}")

    # ---------- معلومات الحساب وإدارة المخاطر ----------

    def _on_account_info(self, balance: float, equity: float):
        self.risk_manager.update_account_info(balance, equity)

    def _on_reconcile(self, positions: list[dict]):
        """يُستدعى مرة واحدة عند الإقلاع بقائمة الصفقات الحقيقية من الخادم."""
        logger.info("[Main] بدء فحص ما بعد الإقلاع لـ %d صفقة", len(positions))

        # إعادة بناء الحالة المحلية من الخادم (مصدر الحقيقة) بدل الاعتماد على
        # أي ذاكرة محلية قد تكون فُقدت عند إعادة التشغيل
        for pos in positions:
            volume_lots = pos["volume_units"] / self.CONTRACT_SIZE
            sl_price, tp_price = self.reconciler.expected_sl_tp(pos["is_buy"], pos["entry_price"])
            self._local_positions[pos["position_id"]] = {
                "symbol_name": pos["symbol_name"],
                "symbol_id": pos["symbol_id"],
                "is_buy": pos["is_buy"],
                "volume_lots": volume_lots,
                "entry_price": pos["entry_price"],
                "planned_sl_price": pos["stop_loss"] or sl_price,
                "planned_tp_price": pos["take_profit"] or tp_price,
                "closing": False,
            }
            self.risk_manager.register_open_position(OpenPositionInfo(
                position_id=pos["position_id"], symbol_name=pos["symbol_name"],
                symbol_id=pos["symbol_id"], is_buy=pos["is_buy"], volume_lots=volume_lots,
            ))

        findings = self.reconciler.run(positions)
        report = self.reconciler.build_telegram_report(findings)
        self.telegram.send_async(report)
        logger.info("[Main] اكتمل فحص ما بعد الإقلاع — تم إرسال التقرير لتيليجرام")

    def _emergency_close_all(self, reason: str):
        logger.critical("[Main] تنفيذ إغلاق طارئ لكل الصفقات: %s", reason)
        self.telegram.notify_emergency_halt(reason)
        for position_id, pos in list(self._local_positions.items()):
            if pos.get("closing"):
                continue
            pos["closing"] = True
            self.fix.close_position(pos["symbol_id"], pos["is_buy"], pos["volume_lots"],
                                     position_id, self.CONTRACT_SIZE)


def main():
    cfg = Config()
    system = TradingSystem(cfg)
    system.start()

    reactor.addSystemEventTrigger("before", "shutdown", system.stop)
    reactor.run()


if __name__ == "__main__":
    main()

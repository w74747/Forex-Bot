"""
fix_executor.py
================
مسؤول حصريًا عن تنفيذ أوامر السوق بأقصى سرعة ممكنة عبر جلسة FIX (TRADE).

⚠️ تذكير مهم (تأكدنا منه من الكود المصدري لحزمة cTraderFixPy نفسها):
   NewOrderSingle عبر FIX **لا يدعم** إرفاق StopLoss/TakeProfit إطلاقًا.
   لذلك هذا الملف يُنفّذ الدخول/الخروج فقط، ثم يُبلّغ main.py بمعرّف
   الصفقة (Position ID) ليُرسله فورًا إلى openapi_streamer.py لتثبيت
   SL/TP على مستوى الخادم.

   إغلاق صفقة قائمة يتم بإرسال أمر معاكس (Side معكوس) مع تمرير نفس
   الـ Position ID في الحقل 721 (PosMaintRptID) — هذا مؤكد من توثيق
   ومنتدى cTrader الرسمي وليس تخمينًا.
"""

import logging
import uuid
from typing import Callable, Optional

from ctrader_fix import Client, LogonRequest, LogoutRequest, NewOrderSingle, ResponseMessage
from twisted.internet.defer import Deferred

from config import Config, FixConfig

logger = logging.getLogger("forex_bot.fix_executor")

SIDE_BUY = "1"
SIDE_SELL = "2"
ORD_TYPE_MARKET = "1"
TIME_IN_FORCE_IOC = "3"  # Immediate Or Cancel — مناسب لأوامر السوق الفورية

# رموز حالة الأوامر (Tag 39 - OrdStatus) وأنواع التنفيذ (Tag 150 - ExecType) المهمة لنا
ORD_STATUS_FILLED = "2"
ORD_STATUS_REJECTED = "8"
EXEC_TYPE_TRADE = "F"
EXEC_TYPE_REJECTED = "8"


class FixExecutor:
    def __init__(self, cfg: Config,
                 on_execution: Callable[[dict], None],
                 on_reject: Callable[[str, str], None]):
        """
        on_execution(report: dict): يُستدعى عند تنفيذ صفقة بنجاح، يحتوي
            symbol, side, position_id, avg_price, qty
        on_reject(clOrdId, reason): يُستدعى عند رفض أمر
        """
        self.cfg = cfg
        self.fix_cfg: FixConfig = cfg.fix
        self.on_execution = on_execution
        self.on_reject = on_reject

        self._config_dict = self.fix_cfg.as_dict()
        self.client = Client(self.fix_cfg.host, self.fix_cfg.port, ssl=self.fix_cfg.ssl)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)

        self.is_logged_on = False
        # نتتبع طلبات محلية بانتظار تنفيذها لربط ClOrdID بالنية الأصلية
        self._pending_orders: dict[str, dict] = {}

    # ---------- دورة الاتصال ----------

    def start(self):
        logger.info("[FIX] بدء الاتصال بجلسة TRADE ...")
        self.client.startService()

    def stop(self):
        if self.is_logged_on:
            logout = LogoutRequest(self._config_dict)
            self.client.send(logout).addErrback(self._on_error)
        self.client.stopService()

    def _on_connected(self, client: Client):
        logger.info("[FIX] تم الاتصال — إرسال Logon")
        logon = LogonRequest(self._config_dict)
        client.send(logon).addErrback(self._on_error)

    def _on_disconnected(self, client: Client, reason):
        logger.warning("[FIX] انقطع الاتصال: %s — إعادة المحاولة تلقائيًا", reason)
        self.is_logged_on = False

    def _on_error(self, failure):
        logger.error("[FIX] خطأ في الإرسال: %s", failure)

    # ---------- معالجة الرسائل ----------

    def _on_message(self, client: Client, message: ResponseMessage):
        msg_type = message.getFieldValue(35)

        if msg_type == "A":  # Logon response
            logger.info("[FIX] تم تسجيل الدخول بنجاح لجلسة TRADE")
            self.is_logged_on = True
            return

        if msg_type == "5":  # Logout
            logger.warning("[FIX] تسجيل خروج من السيرفر: %s", message.getFieldValue(58))
            self.is_logged_on = False
            return

        if msg_type == "8":  # Execution Report
            self._handle_execution_report(message)
            return

        if msg_type == "9":  # Order Cancel Reject
            logger.warning("[FIX] رفض إلغاء/تعديل أمر: %s", message.getFieldValue(58))
            return

    def _handle_execution_report(self, message: ResponseMessage):
        ord_status = message.getFieldValue(39)
        exec_type = message.getFieldValue(150)
        cl_ord_id = message.getFieldValue(11)
        symbol_id = message.getFieldValue(55)
        side = message.getFieldValue(54)
        position_id = message.getFieldValue(721)
        avg_price = message.getFieldValue(6)
        qty = message.getFieldValue(38)
        text = message.getFieldValue(58)

        if exec_type == EXEC_TYPE_REJECTED or ord_status == ORD_STATUS_REJECTED:
            logger.error("[FIX] رُفض الأمر %s: %s", cl_ord_id, text)
            self.on_reject(cl_ord_id, text or "سبب غير معروف")
            self._pending_orders.pop(cl_ord_id, None)
            return

        if exec_type == EXEC_TYPE_TRADE and ord_status == ORD_STATUS_FILLED:
            logger.info("[FIX] تم تنفيذ الأمر %s | رمز=%s جانب=%s سعر=%s كمية=%s صفقة=%s",
                         cl_ord_id, symbol_id, side, avg_price, qty, position_id)
            original_intent = self._pending_orders.pop(cl_ord_id, {})
            self.on_execution({
                "cl_ord_id": cl_ord_id,
                "symbol_id": int(symbol_id) if symbol_id else None,
                "side": side,
                "position_id": int(position_id) if position_id else None,
                "avg_price": float(avg_price) if avg_price else None,
                "qty": float(qty) if qty else None,
                **original_intent,
            })

    # ---------- إرسال الأوامر ----------

    def send_market_order(self, symbol_id: int, is_buy: bool, volume_lots: float,
                           contract_size: int = 100_000, intent_tag: Optional[dict] = None) -> str:
        """
        يرسل أمر سوق فوري (Market Order). يعيد ClOrdID لتتبع التنفيذ لاحقًا
        عبر on_execution callback.
        """
        if not self.is_logged_on:
            logger.error("[FIX] تعذّر إرسال الأمر — الجلسة غير مسجّلة دخول بعد")
            return ""

        cl_ord_id = str(uuid.uuid4())[:12]
        units = int(round(volume_lots * contract_size))

        order = NewOrderSingle(self._config_dict)
        order.ClOrdID = cl_ord_id
        order.Symbol = symbol_id
        order.Side = SIDE_BUY if is_buy else SIDE_SELL
        order.OrderQty = units
        order.OrdType = ORD_TYPE_MARKET
        # ملاحظة: تحققنا من الكود المصدري لـ NewOrderSingle في cTraderFixPy —
        # لا يُضمّن حقل TimeInForce(59) إطلاقًا لأوامر السوق، فهي تُنفَّذ
        # حسب سلوك السيرفر الافتراضي لأوامر Market (فورية).

        self._pending_orders[cl_ord_id] = intent_tag or {}
        self.client.send(order).addErrback(self._on_error)
        logger.info("[FIX] أُرسل أمر %s: رمز=%s %s حجم=%s لوت (%s وحدة)",
                     cl_ord_id, symbol_id, "شراء" if is_buy else "بيع", volume_lots, units)
        return cl_ord_id

    def close_position(self, symbol_id: int, was_buy: bool, volume_lots: float,
                        position_id: int, contract_size: int = 100_000) -> str:
        """
        يُغلق صفقة قائمة بإرسال أمر معاكس مع تمرير نفس Position ID
        (الحقل 721 / PosMaintRptID) — هذا يضمن إغلاق نفس الصفقة تحديدًا
        بدل فتح صفقة جديدة معاكسة.
        """
        if not self.is_logged_on:
            logger.error("[FIX] تعذّر إغلاق الصفقة — الجلسة غير مسجّلة دخول بعد")
            return ""

        cl_ord_id = str(uuid.uuid4())[:12]
        units = int(round(volume_lots * contract_size))

        order = NewOrderSingle(self._config_dict)
        order.ClOrdID = cl_ord_id
        order.Symbol = symbol_id
        order.Side = SIDE_SELL if was_buy else SIDE_BUY  # عكس الاتجاه الأصلي
        order.OrderQty = units
        order.OrdType = ORD_TYPE_MARKET
        order.PosMaintRptID = position_id

        self._pending_orders[cl_ord_id] = {"closing_position_id": position_id}
        self.client.send(order).addErrback(self._on_error)
        logger.info("[FIX] أُرسل أمر إغلاق %s لصفقة %s", cl_ord_id, position_id)
        return cl_ord_id

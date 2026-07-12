"""
openapi_streamer.py
====================
مسؤول عن كل ما تفعله Open API في هذا النظام الهجين:
  1. المصادقة (Application + Account)
  2. جلب قائمة الرموز وتحويل الاسم (EURUSD) إلى symbolId الرقمي الخاص بالوسيط
  3. الاشتراك في بث الأسعار اللحظية (Bid/Ask) لكل رمز مستهدف
  4. تعديل/تعيين وقف الخسارة وجني الربح على صفقة مفتوحة (ProtoOAAmendPositionSLTPReq)
     — هذا غير ممكن إطلاقًا عبر FIX، لذلك يجب أن يمر دائمًا من هنا
  5. جلب معلومات الحساب (الرصيد/الهامش) لتغذية RiskManager

⚠️ هذا الملف لا يُشغّل reactor بنفسه — التشغيل الفعلي (reactor.run()) يتم
   مركزيًا من main.py فقط، حتى تعمل كل الاتصالات (Open API + FIX) على نفس
   حلقة الأحداث بدون تضارب.
"""

import logging
from typing import Callable, Dict, Optional

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAApplicationAuthReq,
    ProtoOAErrorRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOASubscribeSpotsReq,
    ProtoOASymbolsListReq,
    ProtoOATraderReq,
)
from twisted.internet.defer import Deferred

from config import Config, OpenApiConfig, RiskConfig

logger = logging.getLogger("forex_bot.openapi_streamer")


class OpenApiStreamer:
    def __init__(self, cfg: Config, on_price_update: Callable[[str, float, float], None],
                 on_account_info: Callable[[float, float], None]):
        """
        on_price_update(symbol_name, bid, ask): يُستدعى عند كل تحديث سعر
        on_account_info(balance, equity): يُستدعى عند وصول معلومات الحساب
        """
        self.cfg = cfg
        self.oa_cfg: OpenApiConfig = cfg.open_api
        self.risk_cfg: RiskConfig = cfg.risk
        self.on_price_update = on_price_update
        self.on_account_info = on_account_info

        host = EndPoints.PROTOBUF_LIVE_HOST if self.oa_cfg.use_live else EndPoints.PROTOBUF_DEMO_HOST
        self.client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)

        self.symbol_name_to_id: Dict[str, int] = {}
        self.symbol_id_to_name: Dict[int, str] = {}
        self.is_account_authorized = False

    # ---------- دورة الاتصال ----------

    def start(self):
        """يبدأ محاولة الاتصال. يجب استدعاؤه بعد تثبيت الـ reactor في main.py."""
        logger.info("[OpenAPI] بدء الاتصال بـ %s ...",
                     "LIVE" if self.oa_cfg.use_live else "DEMO")
        self.client.startService()

    def _on_connected(self, client: Client):
        logger.info("[OpenAPI] تم الاتصال — إرسال مصادقة التطبيق")
        request = ProtoOAApplicationAuthReq()
        request.clientId = self.oa_cfg.client_id
        request.clientSecret = self.oa_cfg.client_secret
        deferred: Deferred = client.send(request)
        deferred.addErrback(self._on_error)

    def _on_disconnected(self, client: Client, reason):
        logger.warning("[OpenAPI] انقطع الاتصال: %s — Twisted ClientService سيعيد المحاولة تلقائيًا", reason)
        self.is_account_authorized = False

    def _on_error(self, failure):
        logger.error("[OpenAPI] خطأ في الإرسال: %s", failure)

    # ---------- معالجة الرسائل الواردة ----------

    def _on_message(self, client: Client, message):
        if message.payloadType == ProtoOAErrorRes().payloadType:
            error = Protobuf.extract(message)
            logger.error("[OpenAPI] ProtoOAErrorRes: %s", error)
            return

        payload = Protobuf.extract(message)
        payload_type_name = type(payload).__name__

        if payload_type_name == "ProtoOAApplicationAuthRes":
            logger.info("[OpenAPI] تمت مصادقة التطبيق — إرسال مصادقة الحساب")
            self._auth_account()

        elif payload_type_name == "ProtoOAAccountAuthRes":
            logger.info("[OpenAPI] تمت مصادقة الحساب رقم %s", self.oa_cfg.account_id)
            self.is_account_authorized = True
            self._fetch_symbols()
            self._fetch_trader_info()

        elif payload_type_name == "ProtoOASymbolsListRes":
            for symbol in payload.symbol:
                if symbol.symbolName in self.risk_cfg.target_symbols:
                    self.symbol_name_to_id[symbol.symbolName] = symbol.symbolId
                    self.symbol_id_to_name[symbol.symbolId] = symbol.symbolName
            logger.info("[OpenAPI] تم تحميل الرموز: %s", self.symbol_name_to_id)
            self._subscribe_spots()

        elif payload_type_name == "ProtoOASpotEvent":
            symbol_name = self.symbol_id_to_name.get(payload.symbolId)
            if symbol_name and payload.bid and payload.ask:
                # الأسعار تصل مضروبة بـ 100000 حسب توثيق Open API (عدد صحيح بدل عشري)
                bid = payload.bid / 100000.0
                ask = payload.ask / 100000.0
                self.on_price_update(symbol_name, bid, ask)

        elif payload_type_name == "ProtoOATraderRes":
            trader = payload.trader
            scale = 10 ** trader.moneyDigits if trader.moneyDigits else 100
            balance = trader.balance / scale
            equity = balance  # equity الحقيقي يتطلب جمع unrealized PnL من الصفقات المفتوحة
            self.on_account_info(balance, equity)

        elif payload_type_name == "ProtoOAAmendPositionSLTPRes":
            logger.info("[OpenAPI] تم تعديل SL/TP بنجاح")

    # ---------- طلبات مساعدة ----------

    def _auth_account(self):
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = self.oa_cfg.account_id
        request.accessToken = self.oa_cfg.access_token
        self.client.send(request).addErrback(self._on_error)

    def _fetch_symbols(self):
        request = ProtoOASymbolsListReq()
        request.ctidTraderAccountId = self.oa_cfg.account_id
        self.client.send(request).addErrback(self._on_error)

    def _subscribe_spots(self):
        if not self.symbol_name_to_id:
            logger.warning("[OpenAPI] لا توجد رموز محمّلة بعد — تعذّر الاشتراك في الأسعار")
            return
        request = ProtoOASubscribeSpotsReq()
        request.ctidTraderAccountId = self.oa_cfg.account_id
        for symbol_id in self.symbol_name_to_id.values():
            request.symbolId.append(symbol_id)
        self.client.send(request).addErrback(self._on_error)
        logger.info("[OpenAPI] تم الاشتراك في بث الأسعار")

    def fetch_trader_info(self):
        self._fetch_trader_info()

    def _fetch_trader_info(self):
        request = ProtoOATraderReq()
        request.ctidTraderAccountId = self.oa_cfg.account_id
        self.client.send(request).addErrback(self._on_error)

    def amend_position_sl_tp(self, position_id: int, stop_loss: Optional[float] = None,
                              take_profit: Optional[float] = None):
        """
        الطريقة الوحيدة الممكنة تقنيًا لتعيين/تعديل SL أو TP على صفقة مفتوحة.
        يُستدعى مباشرة بعد فتح صفقة عبر fix_executor.py لتأمينها على مستوى الخادم.
        """
        if not self.is_account_authorized:
            logger.error("[OpenAPI] لا يمكن تعديل SL/TP — الحساب غير مصادَق عليه بعد")
            return
        request = ProtoOAAmendPositionSLTPReq()
        request.ctidTraderAccountId = self.oa_cfg.account_id
        request.positionId = position_id
        if stop_loss is not None:
            request.stopLoss = stop_loss
        if take_profit is not None:
            request.takeProfit = take_profit
        self.client.send(request).addErrback(self._on_error)
        logger.info("[OpenAPI] أُرسل طلب تعديل SL=%s TP=%s لصفقة %s", stop_loss, take_profit, position_id)

"""
telegram_notifier.py
======================
إرسال إشعار تيليجرام لكل صفقة مُغلقة (ربح/خسارة/المبلغ)، مع عداد
تراكمي للأرباح الصافية يُصفَّر تلقائيًا مع بداية كل شهر ميلادي جديد.

⚠️ يستخدم مكتبة urllib القياسية فقط (بدون أي اعتمادية خارجية إضافية)
   ويعمل بشكل غير متزامن فوق Twisted عبر deferToThread حتى لا يُعطّل
   حلقة الأحداث الرئيسية أثناء انتظار رد تيليجرام.

📌 التخزين الدائم للعداد الشهري: يُحفظ في ملف JSON على المسار المحدد
   في MONTHLY_COUNTER_PATH (على Railway: اجعله داخل Volume دائم، مثل
   /data/monthly_counter.json — وإلا سيُصفَّر عند كل إعادة نشر).
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from twisted.internet.threads import deferToThread

from config import TelegramConfig

logger = logging.getLogger("forex_bot.telegram_notifier")

DEFAULT_COUNTER_PATH = os.environ.get("MONTHLY_COUNTER_PATH", "monthly_counter.json")


class MonthlyProfitCounter:
    """عداد أرباح تراكمي يُصفَّر تلقائيًا أول كل شهر، مع حفظ دائم في ملف JSON."""

    def __init__(self, storage_path: str = DEFAULT_COUNTER_PATH):
        self.storage_path = Path(storage_path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("[MonthlyCounter] تعذّرت قراءة الملف، سيُعاد إنشاؤه: %s", e)
        return {"month_key": self._current_month_key(), "total_profit": 0.0, "trade_count": 0}

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _current_month_key() -> str:
        now = datetime.now(timezone.utc)
        return f"{now.year:04d}-{now.month:02d}"

    def _reset_if_new_month(self):
        current_key = self._current_month_key()
        if self._data.get("month_key") != current_key:
            logger.info("[MonthlyCounter] شهر جديد — تصفير العداد التراكمي")
            self._data = {"month_key": current_key, "total_profit": 0.0, "trade_count": 0}
            self._save()

    def add_trade_result(self, net_pnl: float) -> dict:
        self._reset_if_new_month()
        self._data["total_profit"] = round(self._data["total_profit"] + net_pnl, 2)
        self._data["trade_count"] += 1
        self._save()
        return dict(self._data)

    @property
    def total_profit(self) -> float:
        self._reset_if_new_month()
        return self._data["total_profit"]

    @property
    def trade_count(self) -> int:
        self._reset_if_new_month()
        return self._data["trade_count"]


class TelegramNotifier:
    def __init__(self, cfg: TelegramConfig, counter: Optional[MonthlyProfitCounter] = None):
        self.cfg = cfg
        self.counter = counter or MonthlyProfitCounter()

    def _send_raw(self, text: str):
        if not self.cfg.enabled:
            logger.debug("[Telegram] معطّل (لا يوجد Token/Chat ID) — تخطي الإرسال: %s", text)
            return
        url = f"https://api.telegram.org/bot{self.cfg.bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": self.cfg.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning("[Telegram] رد غير متوقع: %s", resp.status)
        except Exception as e:
            logger.error("[Telegram] فشل إرسال الرسالة: %s", e)

    def send_async(self, text: str):
        """يرسل الرسالة في Thread منفصل حتى لا يُعطّل حلقة أحداث Twisted."""
        deferToThread(self._send_raw, text)

    def notify_trade_closed(self, symbol: str, direction: str, net_pnl: float, reason: str):
        result = self.counter.add_trade_result(net_pnl)
        emoji = "✅" if net_pnl > 0 else "🔴"
        status_text = "ربح" if net_pnl > 0 else "خسارة"

        text = (
            f"{emoji} <b>صفقة مُغلقة</b>\n"
            f"الرمز: {symbol} | الاتجاه: {direction}\n"
            f"الحالة: {status_text} | المبلغ: {net_pnl:+.2f}$\n"
            f"السبب: {reason}\n"
            f"—\n"
            f"📊 إجمالي أرباح الشهر ({result['month_key']}): {result['total_profit']:+.2f}$ "
            f"({result['trade_count']} صفقة)"
        )
        self.send_async(text)

    def notify_emergency_halt(self, reason: str):
        text = f"🚨 <b>إيقاف طارئ للتداول</b>\n{reason}"
        self.send_async(text)

    def notify_system_event(self, text: str):
        self.send_async(f"ℹ️ {text}")

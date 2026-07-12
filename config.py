"""
config.py
=========
كل الإعدادات والأسرار تُقرأ من متغيرات البيئة (Environment Variables) —
لا تضع أي مفتاح أو كلمة سر مباشرة في الكود، خصوصًا أن المستودع Public.

على Railway: أضف هذه كلها في تبويب Variables للخدمة.
محليًا للاختبار: انسخ .env.example إلى .env واملأه (لا ترفع .env لـ GitHub).
"""

import os
from dataclasses import dataclass, field
from typing import List


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"متغير البيئة المطلوب '{name}' غير موجود. "
            f"أضفه في Railway Variables أو في ملف .env المحلي."
        )
    return value


@dataclass(frozen=True)
class OpenApiConfig:
    """إعدادات اتصال Open API (Protobuf) — لبث الأسعار وتعديل SL/TP ومراقبة الحساب."""
    client_id: str = field(default_factory=lambda: _env("CTRADER_CLIENT_ID", required=True))
    client_secret: str = field(default_factory=lambda: _env("CTRADER_CLIENT_SECRET", required=True))
    access_token: str = field(default_factory=lambda: _env("CTRADER_ACCESS_TOKEN", required=True))
    refresh_token: str = field(default_factory=lambda: _env("CTRADER_REFRESH_TOKEN", required=True))
    account_id: int = field(default_factory=lambda: int(_env("CTRADER_ACCOUNT_ID", required=True)))
    use_live: bool = field(default_factory=lambda: _env("CTRADER_USE_LIVE", "false").lower() == "true")


@dataclass(frozen=True)
class FixConfig:
    """
    إعدادات اتصال FIX (جلسة TRADE) — لتنفيذ الأوامر بأقصى سرعة فقط.
    ⚠️ هذه القيم (Host/Port/SenderCompID...) تجدها في: cTrader ID -> FIX Settings
    لدى وسيطك، وليست نفس بيانات Open API إطلاقًا.
    """
    host: str = field(default_factory=lambda: _env("CTRADER_FIX_HOST", required=True))
    port: int = field(default_factory=lambda: int(_env("CTRADER_FIX_PORT", "5201")))
    ssl: bool = field(default_factory=lambda: _env("CTRADER_FIX_SSL", "false").lower() == "true")
    username: str = field(default_factory=lambda: _env("CTRADER_FIX_USERNAME", required=True))
    password: str = field(default_factory=lambda: _env("CTRADER_FIX_PASSWORD", required=True))
    sender_comp_id: str = field(default_factory=lambda: _env("CTRADER_FIX_SENDER_COMP_ID", required=True))
    sender_sub_id: str = field(default_factory=lambda: _env("CTRADER_FIX_SENDER_SUB_ID", "TRADE"))
    target_comp_id: str = field(default_factory=lambda: _env("CTRADER_FIX_TARGET_COMP_ID", "cServer"))
    target_sub_id: str = field(default_factory=lambda: _env("CTRADER_FIX_TARGET_SUB_ID", "TRADE"))
    begin_string: str = field(default_factory=lambda: _env("CTRADER_FIX_BEGIN_STRING", "FIX.4.4"))
    heartbeat: str = field(default_factory=lambda: _env("CTRADER_FIX_HEARTBEAT", "30"))

    def as_dict(self) -> dict:
        """cTraderFixPy يطلب config كقاموس بمفاتيح بأسماء محددة بالضبط."""
        return {
            "Host": self.host,
            "Port": self.port,
            "SSL": self.ssl,
            "Username": self.username,
            "Password": self.password,
            "BeginString": self.begin_string,
            "SenderCompID": self.sender_comp_id,
            "SenderSubID": self.sender_sub_id,
            "TargetCompID": self.target_comp_id,
            "TargetSubID": self.target_sub_id,
            "HeartBeat": self.heartbeat,
        }


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID", ""))

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass(frozen=True)
class RiskConfig:
    """حماية إلزامية للتوافق مع شروط شركات التمويل (Prop Firms)."""
    max_daily_drawdown_pct: float = field(
        default_factory=lambda: float(_env("MAX_DAILY_DRAWDOWN_PCT", "4.0"))
    )
    max_concurrent_positions: int = field(
        default_factory=lambda: int(_env("MAX_CONCURRENT_POSITIONS", "2"))
    )
    risk_per_trade_pct: float = field(
        default_factory=lambda: float(_env("RISK_PER_TRADE_PCT", "1.0"))
    )
    target_symbols: List[str] = field(default_factory=lambda: ["EURUSD", "GBPUSD"])

    # ---------- حجم الصفقة الثابت (لحماية الحسابات الصغيرة جدًا) ----------
    # cTrader يُعبّر عن الحجم بالوحدات (Units) وليس اللوت مباشرة:
    # 1000 وحدة = 0.01 لوت (Micro Lot) — هذا أصغر حجم متاح غالبًا لدى أغلب الوسطاء.
    # عند TRUE: يُستخدم هذا الحجم الثابت دائمًا (بدل الحساب الديناميكي القائم
    # على % المخاطرة)، وهو المناسب لحساب صغير جدًا (~100$) حيث الحساب الديناميكي
    # قد يُقرَّب أحيانًا إلى صفر ويمنع فتح أي صفقة.
    use_fixed_volume: bool = field(
        default_factory=lambda: _env("USE_FIXED_VOLUME", "true").lower() == "true"
    )
    trade_volume_units: int = field(
        default_factory=lambda: int(_env("TRADE_VOLUME_UNITS", "1000"))
    )


@dataclass(frozen=True)
class Config:
    open_api: OpenApiConfig = field(default_factory=OpenApiConfig)
    fix: FixConfig = field(default_factory=FixConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    dry_run: bool = field(default_factory=lambda: _env("DRY_RUN", "true").lower() == "true")

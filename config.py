import os
import logging

logger = logging.getLogger("config")

def _env(key: str, required: bool = False, default=None):
    value = os.environ.get(key, "").strip()
    if not value:
        if required:
            raise RuntimeError(f"متغير البيئة المطلوب '{key}' غير موجود")
        return default
    return value

class TelegramConfig:
    def __init__(self):
        self.bot_token = _env("TELEGRAM_BOT_TOKEN")
        self.chat_id = _env("TELEGRAM_CHAT_ID")

class OpenApiConfig:
    def __init__(self):
        self.client_id = _env("CTRADER_CLIENT_ID")
        self.client_secret = _env("CTRADER_CLIENT_SECRET")
        self.access_token = _env("CTRADER_ACCESS_TOKEN")
        self.refresh_token = _env("CTRADER_REFRESH_TOKEN")
        acc_id = _env("CTRADER_ACCOUNT_ID")
        self.account_id = int(acc_id) if acc_id else None
        self.use_live = _env("CTRADER_USE_LIVE", default="false").lower() == "true"

class FixConfig:
    def __init__(self):
        self.host = _env("CTRADER_FIX_HOST", default="demo-uk-eqx-01.p.c-trader.com")
        self.port = int(_env("CTRADER_FIX_PORT", default="5212"))
        self.ssl = _env("CTRADER_FIX_SSL", default="true").lower() == "true"
        self.username = _env("CTRADER_FIX_USERNAME", default="")
        self.password = _env("CTRADER_FIX_PASSWORD", default="")
        self.sender_comp_id = _env("CTRADER_FIX_SENDER_COMP_ID", default="")
        self.sender_sub_id = "TRADE"
        self.target_comp_id = "cServer"
        self.target_sub_id = "TRADE"

class RiskConfig:
    def __init__(self):
        self.max_daily_drawdown_pct = float(_env("MAX_DAILY_DRAWDOWN_PCT", default="4.0"))
        self.max_concurrent_positions = int(_env("MAX_CONCURRENT_POSITIONS", default="2"))
        self.risk_per_trade_pct = float(_env("RISK_PER_TRADE_PCT", default="1.0"))
        self.target_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]

class Config:
    def __init__(self):
        self.dry_run = _env("DRY_RUN", default="true").lower() == "true"
        self.telegram = TelegramConfig()
        self.open_api = OpenApiConfig()
        self.fix = FixConfig()
        self.risk = RiskConfig()
        self.monthly_counter_path = _env("MONTHLY_COUNTER_PATH", default="/data/monthly_counter.json")
        self.database_url = _env("DATABASE_URL", required=True)
        self.fallback_database_url = _env("FALLBACK_DATABASE_URL")

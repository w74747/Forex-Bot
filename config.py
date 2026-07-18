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
        self.enabled = bool(self.bot_token and self.chat_id)

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
        self.risk_per_trade_pct = float(_env("RISK_PER_TRADE_PCT", default="3.0"))
        self.target_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        self.use_fixed_volume = _env("USE_FIXED_VOLUME", default="false").lower() == "true"
        self.trade_volume_units = int(_env("TRADE_VOLUME_UNITS", default="1000"))

class StrategyConfig:
    def __init__(self):
        self.rsi_period = int(_env("RSI_PERIOD", default="14"))
        self.rsi_oversold = float(_env("RSI_OVERSOLD", default="30"))
        self.rsi_overbought = float(_env("RSI_OVERBOUGHT", default="70"))
        self.ema_fast = int(_env("EMA_FAST", default="5"))
        self.ema_slow = int(_env("EMA_SLOW", default="10"))
        self.stoch_period = int(_env("STOCH_PERIOD", default="5"))
        self.stoch_lower = float(_env("STOCH_LOWER", default="20"))
        self.stoch_upper = float(_env("STOCH_UPPER", default="80"))
        self.ema_trend_period = int(_env("EMA_TREND_PERIOD", default="20"))
        self.atr_period = int(_env("ATR_PERIOD", default="14"))
        self.atr_sl_multiplier = float(_env("ATR_SL_MULTIPLIER", default="1.5"))
        self.atr_tp_multiplier = float(_env("ATR_TP_MULTIPLIER", default="2.5"))

class CapitalManagementConfig:
    def __init__(self):
        self.starting_balance = float(_env("STARTING_BALANCE", default="200"))
        self.risk_per_trade_pct = float(_env("RISK_PER_TRADE_PCT", default="3"))
        self.use_dynamic_sizing = _env("USE_DYNAMIC_SIZING", default="true").lower() == "true"

class Config:
    def __init__(self):
        self.dry_run = _env("DRY_RUN", default="true").lower() == "true"
        self.telegram = TelegramConfig()
        self.open_api = OpenApiConfig()
        self.fix = FixConfig()
        self.risk = RiskConfig()
        self.strategy = StrategyConfig()
        self.capital = CapitalManagementConfig()
        self.database_url = _env("DATABASE_URL", required=True)
        self.monthly_counter_path = _env("MONTHLY_COUNTER_PATH", default="/data/monthly_counter.json")
        
        self._log_config()
    
    def _log_config(self):
        logger.info("="*60)
        logger.info("🔧 Configuration Loaded:")
        logger.info(f"  DRY_RUN: {self.dry_run}")
        logger.info(f"  Starting Balance: ${self.capital.starting_balance}")
        logger.info(f"  Risk Per Trade: {self.capital.risk_per_trade_pct}%")
        logger.info(f"  Dynamic Sizing: {self.capital.use_dynamic_sizing}")
        logger.info(f"  Target Symbols: {', '.join(self.risk.target_symbols)}")
        logger.info("="*60)

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
    
    def as_dict(self):
        return {
            "bot_token": self.bot_token,
            "chat_id": self.chat_id,
            "enabled": self.enabled
        }

class OpenApiConfig:
    def __init__(self):
        self.client_id = _env("CTRADER_CLIENT_ID")
        self.client_secret = _env("CTRADER_CLIENT_SECRET")
        self.access_token = _env("CTRADER_ACCESS_TOKEN")
        self.refresh_token = _env("CTRADER_REFRESH_TOKEN")
        acc_id = _env("CTRADER_ACCOUNT_ID")
        self.account_id = int(acc_id) if acc_id else None
        self.use_live = _env("CTRADER_USE_LIVE", default="false").lower() == "true"
    
    def as_dict(self):
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "account_id": self.account_id,
            "use_live": self.use_live
        }

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
    
    def as_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "ssl": self.ssl,
            "username": self.username,
            "password": self.password,
            "sender_comp_id": self.sender_comp_id,
            "sender_sub_id": self.sender_sub_id,
            "target_comp_id": self.target_comp_id,
            "target_sub_id": self.target_sub_id
        }

class RiskConfig:
    def __init__(self):
        self.max_daily_drawdown_pct = float(_env("MAX_DAILY_DRAWDOWN_PCT", default="4.0"))
        self.max_concurrent_positions = int(_env("MAX_CONCURRENT_POSITIONS", default="2"))
        self.risk_per_trade_pct = float(_env("RISK_PER_TRADE_PCT", default="1.0"))
        self.target_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        self.use_fixed_volume = _env("USE_FIXED_VOLUME", default="true").lower() == "true"
        self.trade_volume_units = int(_env("TRADE_VOLUME_UNITS", default="1000"))
    
    def as_dict(self):
        return {
            "max_daily_drawdown_pct": self.max_daily_drawdown_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "target_symbols": self.target_symbols,
            "use_fixed_volume": self.use_fixed_volume,
            "trade_volume_units": self.trade_volume_units
        }

class CapitalManagementConfig:
    def __init__(self):
        self.initial_balance = float(_env("INITIAL_BALANCE", default="1000"))
        self.max_drawdown_pct = float(_env("MAX_DRAWDOWN_PCT", default="20"))
        self.risk_per_trade_pct = float(_env("RISK_PER_TRADE_PCT", default="1.0"))
        self.strategy_allocation = {
            "RSI_EMA_MACD": 0.333,
            "BB_STOCH": 0.333,
            "EMA_ATR": 0.334
        }
        self.use_dynamic_sizing = _env("USE_DYNAMIC_SIZING", default="true").lower() == "true"
        self.rebalance_interval = int(_env("REBALANCE_INTERVAL", default="3600"))
    
    def as_dict(self):
        return {
            "initial_balance": self.initial_balance,
            "max_drawdown_pct": self.max_drawdown_pct,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "strategy_allocation": self.strategy_allocation,
            "use_dynamic_sizing": self.use_dynamic_sizing,
            "rebalance_interval": self.rebalance_interval
        }

class StrategyConfig:
    def __init__(self):
        # RSI + EMA + MACD
        self.rsi_period = int(_env("RSI_PERIOD", default="14"))
        self.rsi_oversold = float(_env("RSI_OVERSOLD", default="30"))
        self.rsi_overbought = float(_env("RSI_OVERBOUGHT", default="70"))
        self.ema_fast = int(_env("EMA_FAST", default="5"))
        self.ema_slow = int(_env("EMA_SLOW", default="10"))
        
        # Bollinger + Stochastic
        self.stoch_period = int(_env("STOCH_PERIOD", default="5"))
        self.stoch_lower = float(_env("STOCH_LOWER", default="20"))
        self.stoch_upper = float(_env("STOCH_UPPER", default="80"))
        
        # EMA + ATR
        self.ema_trend_period = int(_env("EMA_TREND_PERIOD", default="20"))
        self.atr_period = int(_env("ATR_PERIOD", default="14"))
        self.atr_sl_multiplier = float(_env("ATR_SL_MULTIPLIER", default="1.5"))
        self.atr_tp_multiplier = float(_env("ATR_TP_MULTIPLIER", default="2.5"))
    
    def as_dict(self):
        return {
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "stoch_period": self.stoch_period,
            "stoch_lower": self.stoch_lower,
            "stoch_upper": self.stoch_upper,
            "ema_trend_period": self.ema_trend_period,
            "atr_period": self.atr_period,
            "atr_sl_multiplier": self.atr_sl_multiplier,
            "atr_tp_multiplier": self.atr_tp_multiplier
        }

class Config:
    def __init__(self):
        self.dry_run = _env("DRY_RUN", default="true").lower() == "true"
        self.telegram = TelegramConfig()
        self.open_api = OpenApiConfig()
        self.fix = FixConfig()
        self.risk = RiskConfig()
        self.capital = CapitalManagementConfig()
        self.strategy = StrategyConfig()
        self.monthly_counter_path = _env("MONTHLY_COUNTER_PATH", default="/data/monthly_counter.json")
        self.database_url = _env("DATABASE_URL", required=True)
        self.fallback_database_url = _env("FALLBACK_DATABASE_URL")
        
        self._log_config()
    
    def _log_config(self):
        """تسجيل الإعدادات عند البدء"""
        logger.info("="*60)
        logger.info("🔧 Configuration Loaded:")
        logger.info(f"  DRY_RUN: {self.dry_run}")
        logger.info(f"  Initial Balance: ${self.capital.initial_balance}")
        logger.info(f"  Max Drawdown: {self.capital.max_drawdown_pct}%")
        logger.info(f"  Dynamic Sizing: {self.capital.use_dynamic_sizing}")
        logger.info(f"  Rebalance Interval: {self.capital.rebalance_interval}s")
        logger.info(f"  Target Symbols: {', '.join(self.risk.target_symbols)}")
        logger.info(f"  Max Concurrent Positions: {self.risk.max_concurrent_positions}")
        logger.info("="*60)
    
    def as_dict(self):
        """تحويل كل الإعدادات إلى قاموس"""
        return {
            "dry_run": self.dry_run,
            "telegram": self.telegram.as_dict(),
            "open_api": self.open_api.as_dict(),
            "fix": self.fix.as_dict(),
            "risk": self.risk.as_dict(),
            "capital": self.capital.as_dict(),
            "strategy": self.strategy.as_dict(),
            "database_url": self.database_url[:50] + "..." if self.database_url else None
        }

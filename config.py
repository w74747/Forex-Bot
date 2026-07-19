"""
config.py - Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

class TelegramConfig:
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    enabled = bool(bot_token and chat_id)

class CapitalConfig:
    starting_balance = float(os.getenv('STARTING_BALANCE', 200))
    risk_per_trade_pct = float(os.getenv('RISK_PER_TRADE_PCT', 3))
    lot_size_multiplier = float(os.getenv('LOT_SIZE_MULTIPLIER', 1.0))
    use_real_balance = os.getenv('USE_REAL_BALANCE', 'true').lower() == 'true'

class CTraderConfig:
    client_id = os.getenv('CTRADER_CLIENT_ID', '')
    account_id = os.getenv('CTRADER_ACCOUNT_ID', '')
    username = os.getenv('CTRADER_FIX_USERNAME', '')
    password = os.getenv('CTRADER_FIX_PASSWORD', '')
    access_token = os.getenv('CTRADER_ACCESS_TOKEN', '')
    enabled = bool(client_id and account_id and username and password)

class RiskConfig:
    target_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']
    max_concurrent_positions = int(os.getenv('MAX_CONCURRENT_POSITIONS', 2))
    max_daily_drawdown_pct = float(os.getenv('MAX_DAILY_DRAWDOWN_PCT', 4.0))

class Config:
    def __init__(self):
        self.telegram = TelegramConfig()
        self.capital = CapitalConfig()
        self.ctrader = CTraderConfig()
        self.risk = RiskConfig()
        self.database_url = os.getenv('DATABASE_URL', '')
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'

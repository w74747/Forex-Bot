"""
config.py - Configuration Management
"""

import os
from dotenv import load_dotenv

load_dotenv()

class TelegramConfig:
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    enabled = bool(bot_token and chat_id)

class ExnessConfig:
    server = os.getenv('EXNESS_SERVER', 'Exness-MT5')
    login = os.getenv('EXNESS_LOGIN', '')
    password = os.getenv('EXNESS_PASSWORD', '')
    enabled = bool(login and password)

class CapitalConfig:
    starting_balance = float(os.getenv('STARTING_BALANCE', 100))
    risk_per_trade_pct = float(os.getenv('RISK_PER_TRADE_PCT', 2))
    lot_size_multiplier = float(os.getenv('LOT_SIZE_MULTIPLIER', 1.0))

class Config:
    def __init__(self):
        self.telegram = TelegramConfig()
        self.exness = ExnessConfig()
        self.capital = CapitalConfig()
        self.database_url = os.getenv('DATABASE_URL', '')
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'

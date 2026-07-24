"""
config.py - Exness Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

class ExnessConfig:
    MT5_LOGIN = int(os.getenv('EXNESS_LOGIN', '0'))
    MT5_PASSWORD = os.getenv('EXNESS_PASSWORD', '')
    MT5_SERVER = os.getenv('EXNESS_SERVER', 'Exness-MT5')

class DatabaseConfig:
    DATABASE_URL = os.getenv('DATABASE_URL', '')

class TradingConfig:
    RISK_PER_TRADE = float(os.getenv('RISK_PER_TRADE_PCT', 2.0))
    LOT_SIZE = float(os.getenv('LOT_SIZE', 0.01))
    MAX_POSITIONS = int(os.getenv('MAX_CONCURRENT_POSITIONS', 2))
    SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']

class TelegramConfig:
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    ENABLED = bool(BOT_TOKEN and CHAT_ID)

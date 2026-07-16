"""
main.py - Hybrid System (OpenAPI + FIX)
"""

import logging
import os
import sys
from twisted.internet import asyncioreactor
asyncioreactor.install()

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from config import Config
from openapi_streamer import OpenApiStreamer
from fix_executor import FixExecutor
from market_scanner import MarketScanner, ScannerConfig
from risk_manager import RiskManager, OpenPositionInfo
from startup_reconciliation import StartupReconciler
from telegram_notifier import TelegramNotifier

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()
trading_halted = False

def on_price_update(symbol_name, bid, ask):
    """OpenAPI يرسل أسعار حقيقية"""
    global trading_halted
    if trading_halted:
        return
    
    signal = market_scanner.on_price(symbol_name, bid, ask)
    if signal.value == 0:
        return
    
    if not risk_manager.can_open_new_position():
        logger.warning(f"[Risk] لا يمكن فتح صفقة جديدة - حد أقصى من الصفقات")
        return
    
    symbol_id = openapi_streamer.symbol_name_to_id.get(symbol_name)
    if not symbol_id:
        logger.error(f"[Error] لا يوجد symbol_id لـ {symbol_name}")
        return
    
    is_buy = signal.name == "BUY_REVERSION"
    lot_size = risk_manager.calculate_position_size_lots(4.0)
    
    if lot_size <= 0:
        logger.warning(f"[Risk] حجم الصفقة = صفر")
        return
    
    if cfg.dry_run:
        logger.info(f"[DRY_RUN] صفقة وهمية: {symbol_name} {'BUY' if is_buy else 'SELL'} {lot_size} لوت @ {(bid+ask)/2:.5f}")
    else:
        cl_ord_id = fix_executor.send_market_order(symbol_id, is_buy, lot_size, intent_tag={"symbol_name": symbol_name})
        if cl_ord_id:
            logger.info(f"[Order Sent] {symbol_name} {'BUY' if is_buy else 'SELL'} - ClOrdID: {cl_ord_id}")

def on_fix_execution(report):
    """FIX منفذ أمر"""
    symbol_name = report.get("symbol_name", "UNKNOWN")
    position_id = report.get("position_id")
    
    if position_id and not cfg.dry_run:
        info = OpenPositionInfo(
            position_id=position_id,
            symbol_name=symbol_name,
            symbol_id=report.get("symbol_id", 0),
            is_buy=report.get("side") == "1",
            volume_lots=report.get("qty", 0) / 100_000
        )
        risk_manager.register_open_position(info)
        logger.info(f"[Position Opened] #{position_id} {symbol_name} - تم التسجيل")
        
        openapi_streamer.amend_position_sl_tp(position_id, sl=None, tp=None)

def on_fix_reject(cl_ord_id, reason):
    """FIX رفض أمر"""
    logger.error(f"[FIX Reject] {cl_ord_id}: {reason}")
    telegram_notifier.notify_system_event(f"❌ رفض أمر: {reason}")

def on_account_info(balance, equity):
    """OpenAPI تحديث معلومات الحساب"""
    risk_manager.update_account_info(balance, equity)

def on_reconcile(positions):
    """OpenAPI استرجاع الصفقات المفتوحة"""
    logger.info(f"[Reconcile] {len(positions)} صفقة مفتوحة على الخادم")
    
    findings = startup_reconciler.run(positions)
    report = startup_reconciler.build_telegram_report(findings)
    telegram_notifier.notify_system_event(report)
    
    for pos in positions:
        info = OpenPositionInfo(
            position_id=pos["position_id"],
            symbol_name=pos["symbol_name"],
            symbol_id=pos["symbol_id"],
            is_buy=pos["is_buy"],
            volume_lots=pos["volume_units"] / 100_000
        )
        risk_manager.register_open_position(info)

def on_emergency_close_all(reason):
    """إغلاق طارئ لكل الصفقات"""
    global trading_halted
    trading_halted = True
    logger.critical(f"[Emergency] {reason}")
    telegram_notifier.notify_emergency_halt(reason)
    
    for position_id in list(risk_manager.open_positions.keys()):
        pos = risk_manager.open_positions[position_id]
        if not cfg.dry_run:
            fix_executor.close_position(
                pos.symbol_id, pos.is_buy, pos.volume_lots, position_id
            )
        risk_manager.unregister_position(position_id)

@inlineCallbacks
def start_system():
    """بدء النظام الهجين"""
    global trading_halted
    trading_halted = False
    
    logger.info("="*60)
    logger.info("🚀 بدء نظام التداول الهجين (OpenAPI + FIX)")
    logger.info(f"📊 الأزواج المستهدفة: {', '.join(cfg.risk.target_symbols)}")
    logger.info(f"🔒 DRY_RUN = {cfg.dry_run}")
    logger.info("="*60)
    
    try:
        openapi_streamer.start()
        yield reactor.callLater(2)
        
        if not cfg.dry_run:
            fix_executor.start()
            yield reactor.callLater(2)
        
        telegram_notifier.notify_system_event(
            f"🚀 نظام التداول بدأ\n"
            f"📊 الأزواج: {', '.join(cfg.risk.target_symbols)}\n"
            f"🔒 Mode: {'DRY_RUN' if cfg.dry_run else 'LIVE'}"
        )
        
    except Exception as e:
        logger.error(f"[Startup Error] {e}")
        telegram_notifier.notify_system_event(f"❌ خطأ في البدء: {e}")
        reactor.stop()

if __name__ == '__main__':
    try:
        market_scanner = MarketScanner(
            ScannerConfig(
                std_period=20,
                entry_std_multiplier=2.5,
                max_allowed_spread_pips=0.3
            ),
            symbols=cfg.risk.target_symbols
        )
        
        risk_manager = RiskManager(
            cfg.risk,
            on_emergency_close_all=on_emergency_close_all
        )
        
        startup_reconciler = StartupReconciler(
            sl_pips=4.0,
            tp_pips=6.0,
            pip_size=0.0001,
            amend_sl_tp_fn=lambda pid, sl, tp: None
        )
        
        telegram_notifier = TelegramNotifier(cfg.telegram)
        
        openapi_streamer = OpenApiStreamer(
            cfg,
            on_price_update=on_price_update,
            on_account_info=on_account_info,
            on_reconcile=on_reconcile
        )
        
        fix_executor = FixExecutor(
            cfg,
            on_execution=on_fix_execution,
            on_reject=on_fix_reject
        )
        
        reactor.callWhenRunning(start_system)
        reactor.run()
        
    except KeyboardInterrupt:
        logger.info("⏹️ إيقاف البوت...")
        if not cfg.dry_run:
            fix_executor.stop()
        reactor.stop()
    except Exception as e:
        logger.critical(f"[Fatal Error] {e}")
        telegram_notifier.notify_system_event(f"💥 خطأ حرج: {e}")

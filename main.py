def notify_on_close(trade, capital_manager, telegram_notifier, monthly_tracker):
    """إرسال إخطار عند إغلاق صفقة"""
    try:
        entry_price = float(trade['entry_price'])
        exit_price = float(trade['exit_price'])
        net_pnl = float(trade['net_pnl'])
        
        # احسب حجم الصفقة (تقريبي)
        lot_size = capital_manager.get_position_size(
            trade['strategy'], entry_price, risk_pct=1.0
        )
        
        # إرسال إخطار Telegram
        telegram_notifier.notify_trade_close(
            trade_id=trade['id'],
            strategy=trade['strategy'],
            symbol=trade['symbol'],
            direction=trade['direction'],
            entry_price=entry_price,
            exit_price=exit_price,
            exit_reason=trade['exit_reason'],
            net_pnl=net_pnl
        )
        
        # تسجيل في العداد الشهري
        monthly_tracker.record_trade(
            pnl=float(trade['gross_pnl']),
            commission=float(trade['commission']),
            direction=trade['direction']
        )
        
    except Exception as e:
        logger.error(f"[Notify Close] {e}")

def notify_on_open(trade_id, strategy, symbol, direction, entry_price, lot_size, sl_price, tp_price, telegram_notifier):
    """إرسال إخطار عند فتح صفقة"""
    try:
        telegram_notifier.notify_trade_open(
            trade_id=trade_id,
            strategy=strategy,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            lot_size=lot_size,
            sl_price=sl_price,
            tp_price=tp_price
        )
    except Exception as e:
        logger.error(f"[Notify Open] {e}")

def send_periodic_summary(capital_manager, telegram_notifier, monthly_tracker, last_summary_time):
    """إرسال ملخص دوري"""
    try:
        now = datetime.now()
        
        # إرسال ملخص يومي كل ساعة
        if (now - last_summary_time[0]).total_seconds() >= 3600:
            summary = monthly_tracker.get_summary()
            
            telegram_notifier.notify_daily_summary(
                total_trades=summary['total_trades'],
                winning_trades=summary['winning_trades'],
                losing_trades=summary['losing_trades'],
                total_pnl=summary['net_pnl'],
                win_rate=summary['win_rate'],
                balance=summary['balance']
            )
            
            # إرسال تحديث رأس المال
            telegram_notifier.notify_capital_update(
                current_balance=capital_manager.current_balance,
                strategy_balances=capital_manager.strategy_balances
            )
            
            last_summary_time[0] = now
            
            # التحقق من تغيير الشهر
            if monthly_tracker.is_new_month():
                logger.info("[System] New month detected, resetting tracker")
                monthly_tracker = MonthlyTracker()
    
    except Exception as e:
        logger.error(f"[Periodic Summary] {e}")
    
    return monthly_tracker

def main():
    # ... الكود السابق ...
    
    monthly_tracker = MonthlyTracker()
    last_summary_time = [datetime.now()]
    
    try:
        iteration = 0
        while True:
            iteration += 1
            prices = generate_prices()
            
            # تحديث الرصيد والملخصات الدورية
            if iteration % 10 == 0:
                current_balance = capital_manager.current_balance + random.uniform(-10, 50)
                capital_manager.update_balance(current_balance)
                monthly_tracker.update_balance(current_balance)
            
            # إرسال ملخص دوري
            if iteration % 120 == 0:
                monthly_tracker = send_periodic_summary(
                    capital_manager, telegram_notifier, monthly_tracker, last_summary_time
                )
            
            # إعادة توازن
            if capital_manager.should_rebalance():
                capital_manager.rebalance()
            
            conn = get_db()
            if conn:
                check_open_positions(prices, conn)
                
                # إرسال إخطارات الصفقات المُغلقة
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM live_paper_trades 
                        WHERE status = 'CLOSED' 
                        AND closed_at >= NOW() - INTERVAL '1 minute'
                        AND id > ?
                    """)  # تعديل للحصول على الصفقات الجديدة فقط
            
            # ... باقي الكود ...

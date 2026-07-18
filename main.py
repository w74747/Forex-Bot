# أضف هذا في main()

from ai_analyzer import DeepSeekAnalyzer

def get_trades_last_30min(conn):
    """جلب الصفقات آخر 30 دقيقة"""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(net_pnl), 0) as pnl
                FROM live_paper_trades 
                WHERE status = 'CLOSED'
                AND closed_at >= NOW() - INTERVAL '30 minutes'
            """)
            result = cur.fetchone()
            return dict(result) if result else {
                'total': 0, 'wins': 0, 'losses': 0, 'pnl': 0
            }
    except:
        return {'total': 0, 'wins': 0, 'losses': 0, 'pnl': 0}

def main():
    # ... كود البداية ...
    
    # إضافة DeepSeek
    deepseek_key = _env("DEEPSEEK_API_KEY")
    ai_analyzer = DeepSeekAnalyzer(deepseek_key, cfg.database_url) if deepseek_key else None
    
    last_report_time = [datetime.now()]
    last_ai_analysis_time = [datetime.now()]
    
    try:
        iteration = 0
        while True:
            iteration += 1
            prices = generate_prices()
            
            now = datetime.now()
            
            # تقرير مختصر كل 30 دقيقة
            if (now - last_report_time[0]).total_seconds() >= 1800:
                try:
                    conn = get_db()
                    if conn:
                        trades_30min = get_trades_last_30min(conn)
                        account_stats = capital_manager.get_account_stats()
                        monthly_summary = monthly_tracker.get_summary()
                        
                        telegram_notifier.notify_compact_report(
                            account_stats=account_stats,
                            trades_data={
                                'total_trades': trades_30min['total'],
                                'wins': trades_30min['wins'],
                                'losses': trades_30min['losses'],
                                'pnl_30min': trades_30min['pnl']
                            },
                            monthly_summary=monthly_summary
                        )
                        
                        conn.close()
                    
                    last_report_time[0] = now
                except Exception as e:
                    logger.error(f"[Report] {e}")
            
            # تحليل AI كل 30 دقيقة أيضاً (يمكن أن يكون في وقت مختلف)
            if (now - last_ai_analysis_time[0]).total_seconds() >= 1800 and ai_analyzer:
                try:
                    # تحليل الأداء
                    performance = ai_analyzer.analyze_performance()
                    
                    # مراجعة الكود
                    code_review = ai_analyzer.analyze_code()
                    
                    if performance and code_review:
                        telegram_notifier.notify_ai_analysis(
                            performance_analysis=performance['analysis'],
                            code_review=code_review['analysis']
                        )
                        
                        logger.info("[AI Analysis] Completed successfully")
                    
                    last_ai_analysis_time[0] = now
                except Exception as e:
                    logger.error(f"[AI Analysis] {e}")
            
            # ... باقي الكود ...

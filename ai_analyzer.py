"""
ai_analyzer.py - DeepSeek AI Code & Performance Analyzer
"""

import logging
import requests
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

logger = logging.getLogger("ai_analyzer")

class DeepSeekAnalyzer:
    def __init__(self, api_key, database_url):
        self.api_key = api_key
        self.database_url = database_url
        self.base_url = "https://api.deepseek.com/chat/completions"
    
    def get_db(self):
        try:
            return psycopg2.connect(self.database_url, connect_timeout=5)
        except Exception as e:
            logger.error(f"[DB] {e}")
            return None
    
    def call_deepseek(self, prompt):
        """استدعاء DeepSeek API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 1500
            }
            
            response = requests.post(
                self.base_url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                logger.error(f"[DeepSeek] Error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"[DeepSeek API] {e}")
            return None
    
    def get_last_30min_trades(self):
        """جلب الصفقات آخر 30 دقيقة"""
        conn = self.get_db()
        if not conn:
            return []
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        id, symbol, direction, entry_price, exit_price,
                        status, net_pnl, strategy, opened_at, closed_at
                    FROM live_paper_trades 
                    WHERE closed_at >= NOW() - INTERVAL '30 minutes'
                    ORDER BY closed_at DESC
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"[Trades Query] {e}")
            return []
        finally:
            conn.close()
    
    def get_performance_stats(self):
        """إحصائيات الأداء"""
        conn = self.get_db()
        if not conn:
            return {}
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # آخر 30 دقيقة
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                        COALESCE(SUM(net_pnl), 0) as total_pnl,
                        AVG(net_pnl) as avg_pnl
                    FROM live_paper_trades 
                    WHERE status = 'CLOSED'
                    AND closed_at >= NOW() - INTERVAL '30 minutes'
                """)
                
                result = cur.fetchone()
                return dict(result) if result else {}
        except Exception as e:
            logger.error(f"[Stats] {e}")
            return {}
        finally:
            conn.close()
    
    def analyze_performance(self):
        """تحليل الأداء باستخدام DeepSeek"""
        trades = self.get_last_30min_trades()
        stats = self.get_performance_stats()
        
        if not trades and stats.get('total_trades', 0) == 0:
            logger.info("[Analysis] No trades in last 30 minutes")
            return None
        
        # تنسيق البيانات للتحليل
        trades_summary = json.dumps(trades, default=str, indent=2)
        
        prompt = f"""
أنت مُحلل تداول احترافي. حلل الصفقات التالية وقيّم الأداء:

📊 إحصائيات آخر 30 دقيقة:
- إجمالي الصفقات: {stats.get('total_trades', 0)}
- صفقات رابحة: {stats.get('wins', 0)}
- صفقات خاسرة: {stats.get('losses', 0)}
- الربح الكلي: ${stats.get('total_pnl', 0):.2f}
- متوسط الربح: ${stats.get('avg_pnl', 0):.2f}

📈 تفاصيل الصفقات:
{trades_summary}

قيّم:
1. هل الاستراتيجيات تعمل بشكل صحيح؟
2. ما هي أفضل وأسوأ الاستراتيجيات؟
3. هل هناك أنماط مقلقة؟
4. التوصيات للتحسن؟

أجب بشكل مختصر وواضح (3-5 نقاط رئيسية فقط).
"""
        
        analysis = self.call_deepseek(prompt)
        
        if analysis:
            logger.info(f"[Analysis] DeepSeek analysis completed")
            return {
                "timestamp": datetime.now().isoformat(),
                "trades_count": stats.get('total_trades', 0),
                "total_pnl": stats.get('total_pnl', 0),
                "analysis": analysis
            }
        
        return None
    
    def analyze_code(self):
        """مراجعة الكود للبحث عن مشاكل"""
        
        code_files = {
            "main.py": self._read_file("main.py"),
            "config.py": self._read_file("config.py"),
            "capital_manager.py": self._read_file("capital_manager.py")
        }
        
        # فلتر الكود - خذ أول 1000 حرف من كل ملف
        code_summary = "\n\n".join([
            f"--- {name} ---\n{content[:1000]}..."
            for name, content in code_files.items()
            if content
        ])
        
        prompt = f"""
أنت مهندس برمجيات متخصص. مراجعة هذا الكود للبحث عن مشاكل تقنية:

{code_summary}

ركز على:
1. أخطاء منطقية (bugs)
2. تسرب الموارد (resource leaks)
3. مشاكل الأداء
4. مشاكل الأمان

أذكر:
- المشكلة
- موقع المشكلة (اسم الملف والدالة)
- السبب المحتمل
- الحل المقترح

إجابة مختصرة (3-5 مشاكل رئيسية فقط).
"""
        
        analysis = self.call_deepseek(prompt)
        
        if analysis:
            logger.info(f"[Code Review] DeepSeek code review completed")
            return {
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis
            }
        
        return None
    
    def _read_file(self, filename):
        """قراءة ملف الكود"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return None

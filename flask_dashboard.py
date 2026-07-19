"""
flask_dashboard.py - Trading Dashboard
"""

import os
import logging
from datetime import datetime
from io import BytesIO

import psycopg2
from flask import Flask, render_template, jsonify, request
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

app = Flask(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/trades')
def api_trades():
    conn = get_db()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    id, symbol, direction, entry_price, exit_price,
                    status, net_pnl, strategy, opened_at, closed_at
                FROM live_paper_trades
                ORDER BY id DESC
                LIMIT 100
            """)
            trades = [dict(row) for row in cur.fetchall()]
        
        conn.close()
        return jsonify(trades)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) as closed_trades,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_trades,
                    SUM(CASE WHEN net_pnl > 0 AND status = 'CLOSED' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN net_pnl < 0 AND status = 'CLOSED' THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN net_pnl ELSE 0 END), 0) as total_pnl,
                    COALESCE(AVG(CASE WHEN status = 'CLOSED' THEN net_pnl END), 0) as avg_pnl
                FROM live_paper_trades
            """)
            result = cur.fetchone()
            stats = dict(result) if result else {}
            
            total_trades = stats.get('total_trades', 0) or 0
            wins = stats.get('wins', 0) or 0
            losses = stats.get('losses', 0) or 0
            
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            
            stats['win_rate'] = round(win_rate, 2)
            stats['total_pnl'] = round(float(stats.get('total_pnl', 0) or 0), 2)
            stats['avg_pnl'] = round(float(stats.get('avg_pnl', 0) or 0), 2)
            stats['starting_balance'] = 200
            stats['current_balance'] = 200 + stats['total_pnl']
        
        conn.close()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/equity-curve')
def api_equity_curve():
    conn = get_db()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    closed_at,
                    SUM(net_pnl) OVER (ORDER BY closed_at) as cumulative_pnl
                FROM live_paper_trades
                WHERE status = 'CLOSED' AND closed_at IS NOT NULL
                ORDER BY closed_at
            """)
            
            data = []
            for row in cur.fetchall():
                if row['closed_at']:
                    data.append({
                        'time': row['closed_at'].isoformat(),
                        'balance': 200 + (row['cumulative_pnl'] or 0)
                    })
        
        conn.close()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

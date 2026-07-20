import os
import logging
from flask import Flask, render_template, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

app = Flask(__name__, template_folder='templates')
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
        return jsonify([])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, symbol, direction, entry_price, exit_price,
                       status, net_pnl, strategy FROM live_paper_trades
                ORDER BY id DESC LIMIT 100
            """)
            trades = []
            for row in cur.fetchall():
                trades.append({
                    'id': row['id'],
                    'symbol': row['symbol'],
                    'direction': row['direction'],
                    'entry_price': float(row['entry_price']) if row['entry_price'] else 0,
                    'exit_price': float(row['exit_price']) if row['exit_price'] else None,
                    'status': row['status'],
                    'net_pnl': float(row['net_pnl']) if row['net_pnl'] else 0,
                    'strategy': row['strategy']
                })
        conn.close()
        return jsonify(trades)
    except Exception as e:
        logger.error(f"Trades Error: {e}")
        return jsonify([])

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    if not conn:
        return jsonify({})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) as closed_trades,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_trades,
                    SUM(CASE WHEN net_pnl > 0 AND status = 'CLOSED' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN net_pnl < 0 AND status = 'CLOSED' THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN net_pnl ELSE 0 END), 0) as total_pnl
                FROM live_paper_trades
            """)
            result = cur.fetchone()
        conn.close()
        
        stats = {
            'total_trades': result['total_trades'] or 0,
            'closed_trades': result['closed_trades'] or 0,
            'open_trades': result['open_trades'] or 0,
            'wins': result['wins'] or 0,
            'losses': result['losses'] or 0,
            'total_pnl': float(result['total_pnl'] or 0),
            'starting_balance': 200,
            'current_balance': 200 + float(result['total_pnl'] or 0)
        }
        
        wins = stats['wins']
        losses = stats['losses']
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        stats['win_rate'] = round(win_rate, 2)
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        return jsonify({})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

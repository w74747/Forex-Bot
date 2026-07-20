import os
from flask import Flask, render_template, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__, template_folder='templates')
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=5)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/trades')
def api_trades():
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, symbol, direction, entry_price, exit_price, status, net_pnl, strategy FROM live_paper_trades ORDER BY id DESC LIMIT 100")
            trades = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(trades)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def api_stats():
    try:
        conn = get_db()
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
        
        stats = dict(result)
        wins = stats.get('wins') or 0
        losses = stats.get('losses') or 0
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        return jsonify({
            'total_trades': stats.get('total_trades') or 0,
            'closed_trades': stats.get('closed_trades') or 0,
            'open_trades': stats.get('open_trades') or 0,
            'wins': wins,
            'losses': losses,
            'total_pnl': float(stats.get('total_pnl') or 0),
            'win_rate': round(win_rate, 2),
            'starting_balance': 200,
            'current_balance': 200 + float(stats.get('total_pnl') or 0)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

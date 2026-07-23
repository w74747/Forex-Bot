import os
import psycopg2
from flask import Flask, render_template, jsonify, request

app = Flask(__name__, template_folder='templates')

def get_conn():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/stats')
def stats():
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # إحصائيات فقط
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END), COALESCE(SUM(net_pnl), 0) FROM live_paper_trades WHERE status='CLOSED'")
        total, wins, losses, pnl = cur.fetchone()
        
        cur.close()
        conn.close()
        
        total = total or 0
        wins = wins or 0
        losses = losses or 0
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        return jsonify({'total_trades': total, 'wins': wins, 'losses': losses, 'pnl': float(pnl or 0), 'wr': round(wr, 2), 'balance': 200 + float(pnl or 0)})
    except:
        return jsonify({})

@app.route('/api/trades')
def trades():
    try:
        page = int(request.args.get('page', 1))
        conn = get_conn()
        cur = conn.cursor()
        
        # فقط الصفقات المغلقة
        cur.execute("SELECT COUNT(*) FROM live_paper_trades WHERE status='CLOSED'")
        total = cur.fetchone()[0]
        
        offset = (page - 1) * 10
        cur.execute("SELECT id, symbol, direction, entry_price, exit_price, net_pnl, strategy, closed_at FROM live_paper_trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 10 OFFSET %s", (offset,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        trades_list = []
        for row in rows:
            trades_list.append({'id': row[0], 'symbol': row[1], 'direction': row[2], 'entry': float(row[3] or 0), 'exit': float(row[4] or 0), 'pnl': float(row[5] or 0), 'strategy': row[6], 'date': str(row[7] or '')})
        
        return jsonify({'trades': trades_list, 'page': page, 'total': total, 'pages': (total + 9) // 10})
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

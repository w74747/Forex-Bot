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
        
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status='CLOSED' AND net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status='CLOSED' AND net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(CASE WHEN status='CLOSED' THEN net_pnl ELSE 0 END), 0) as closed_pnl,
                SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_count
            FROM live_paper_trades
        """)
        total, wins, losses, pnl, open_cnt = cur.fetchone()
        cur.close()
        conn.close()
        
        total = total or 0
        wins = wins or 0
        losses = losses or 0
        wr = round((wins / (wins + losses) * 100) if (wins + losses) > 0 else 0, 2)
        
        return jsonify({
            'total_trades': total,
            'closed_trades': (total - (open_cnt or 0)),
            'open_trades': open_cnt or 0,
            'wins': wins,
            'losses': losses,
            'total_pnl': float(pnl or 0),
            'win_rate': wr,
            'starting_balance': 200,
            'current_balance': 200 + float(pnl or 0)
        })
    except Exception as e:
        print(f"Stats Error: {e}")
        return jsonify({})

@app.route('/api/trades')
def trades():
    try:
        page = int(request.args.get('page', 1))
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM live_paper_trades WHERE status='CLOSED'")
        total = cur.fetchone()[0] or 0
        
        limit = 10
        offset = (page - 1) * limit
        
        cur.execute("""
            SELECT id, symbol, direction, entry_price, exit_price, status, net_pnl, strategy, closed_at 
            FROM live_paper_trades 
            WHERE status='CLOSED'
            ORDER BY id DESC 
            LIMIT %s OFFSET %s
        """, (limit, offset))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        trades_list = []
        for row in rows:
            trades_list.append({
                'id': row[0],
                'symbol': row[1],
                'direction': row[2],
                'entry_price': float(row[3]) if row[3] else 0,
                'exit_price': float(row[4]) if row[4] else 0,
                'status': row[5],
                'net_pnl': float(row[6]) if row[6] else 0,
                'strategy': row[7] or 'N/A',
                'closed_at': str(row[8])[:16] if row[8] else '-'
            })
        
        total_pages = (total + limit - 1) // limit
        
        return jsonify({
            'trades': trades_list,
            'page': page,
            'total_pages': total_pages,
            'total': total
        })
    except Exception as e:
        print(f"Trades Error: {e}")
        return jsonify({'trades': [], 'error': str(e)})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

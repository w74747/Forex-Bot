import os
import psycopg2
from flask import Flask, render_template, jsonify, request
from datetime import datetime

app = Flask(__name__, template_folder='templates')

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/stats')
def stats():
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(net_pnl), 0) as pnl
            FROM live_paper_trades WHERE status = 'CLOSED'
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        total = row[0] or 0
        wins = row[1] or 0
        losses = row[2] or 0
        pnl = row[3] or 0
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        return jsonify({
            'total_trades': total,
            'starting_balance': 200,
            'current_balance': 200 + pnl,
            'total_pnl': pnl,
            'win_rate': round(wr, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trades')
def trades():
    try:
        page = int(request.args.get('page', 1))
        from_date = request.args.get('from_date', '')
        to_date = request.args.get('to_date', '')
        
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cur = conn.cursor()
        
        where = "WHERE status = 'CLOSED'"
        if from_date:
            where += f" AND closed_at >= '{from_date}'"
        if to_date:
            where += f" AND closed_at <= '{to_date}'"
        
        # عد الإجمالي
        cur.execute(f"SELECT COUNT(*) FROM live_paper_trades {where}")
        total = cur.fetchone()[0]
        
        # احسب offset
        limit = 10
        offset = (page - 1) * limit
        
        cur.execute(f"""
            SELECT id, symbol, direction, entry_price, exit_price, status, net_pnl, strategy, closed_at
            FROM live_paper_trades {where} ORDER BY id DESC LIMIT {limit} OFFSET {offset}
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        data = []
        for row in rows:
            data.append({
                'id': row[0],
                'symbol': row[1],
                'direction': row[2],
                'entry_price': float(row[3]) if row[3] else 0,
                'exit_price': float(row[4]) if row[4] else None,
                'status': row[5],
                'net_pnl': float(row[6]) if row[6] else 0,
                'strategy': row[7],
                'closed_at': str(row[8]) if row[8] else '-'
            })
        
        pages = (total + limit - 1) // limit
        
        return jsonify({
            'trades': data,
            'page': page,
            'total_pages': pages,
            'total_trades': total
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

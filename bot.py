import ccxt
import pandas as pd
import pandas_ta as ta
import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Default Weights
current_weights = {
    'bb_weight': 50.0,
    'rsi_weight': 50.0,
    'signal_threshold_long': 85.0,
    'signal_threshold_short': 15.0
}

def load_json(filename, default_val):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return default_val
    return default_val

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def send_telegram_msg(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def calculate_score(df, weights):
    if len(df) < 20: return 50, 50, 50
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_low'] = df['bb_mid'] - (2.0 * df['bb_std'])
    df['bb_high'] = df['bb_mid'] + (2.0 * df['bb_std'])
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    last_row = df.iloc[-1]
    price = last_row['close']
    bb_low = last_row['bb_low']
    bb_high = last_row['bb_high']
    
    if bb_high == bb_low: 
        bb_score = 50
    else:
        raw_val = ((price - bb_low) / (bb_high - bb_low)) * 100
        bb_score = 100 - max(0, min(100, raw_val))
    
    rsi_score = 100 - last_row['rsi']
    total_score = (bb_score * (weights['bb_weight']/100)) + (rsi_score * (weights['rsi_weight']/100))
    return round(total_score, 1), round(bb_score, 1), round(rsi_score, 1)

def run_evaluation(journal, exchange, weights):
    now = datetime.utcnow()
    updated = False
    closed_this_round = []
    
    for trade in journal:
        if trade['status'] == 'open':
            entry_time = datetime.fromisoformat(trade['entry_time'])
            if now - entry_time >= timedelta(hours=1):
                try:
                    ticker = exchange.fetch_ticker(trade['symbol'])
                    curr_price = ticker['last']
                    
                    if trade['direction'] == 'LONG':
                        pnl_pct = (curr_price - trade['entry_price']) / trade['entry_price'] * 100
                        is_win = curr_price > trade['entry_price']
                    else:
                        pnl_pct = (trade['entry_price'] - curr_price) / trade['entry_price'] * 100
                        is_win = curr_price < trade['entry_price']
                        
                    trade['status'] = 'closed'
                    trade['exit_price'] = curr_price
                    trade['pnl'] = round(pnl_pct, 2)
                    trade['win'] = is_win
                    updated = True
                    closed_this_round.append(trade)
                    
                    msg = f"📊 **1-Hour Verif**: {trade['symbol']}\nResult: {'✅ WIN' if is_win else '❌ LOSS'} ({trade['pnl']}%)"
                    send_telegram_msg(msg)
                except Exception as e:
                    print(f"Error evaluating {trade['symbol']}: {e}")

    # Self-Correction
    if closed_this_round:
        closed_signals = [t for t in journal if t['status'] == 'closed']
        if len(closed_signals) >= 10:
            recent_10 = closed_signals[-10:]
            wins = len([t for t in recent_10 if t.get('win') is True])
            win_rate = wins / 10.0
            
            if win_rate < 0.40:
                bb_blame, rsi_blame = 0, 0
                for t in recent_10:
                    if not t.get('win'):
                        if t['direction'] == 'LONG':
                            if t['bb_score'] > t['rsi_score']: bb_blame += 1
                            else: rsi_blame += 1
                        else:
                            if t['bb_score'] < t['rsi_score']: bb_blame += 1
                            else: rsi_blame += 1
                
                if bb_blame > rsi_blame:
                    weights['bb_weight'] = max(10, weights['bb_weight'] - 10)
                    weights['rsi_weight'] = min(90, weights['rsi_weight'] + 10)
                else:
                    weights['rsi_weight'] = max(10, weights['rsi_weight'] - 10)
                    weights['bb_weight'] = min(90, weights['bb_weight'] + 10)
                    
                msg = f"📉 **AI Auto-Adjustment**\nWin rate: {win_rate*100}%\nNew BB: {weights['bb_weight']}%, New RSI: {weights['rsi_weight']}%"
                send_telegram_msg(msg)
                
                for t in closed_signals:
                    t['status'] = 'archived'
                updated = True

    return updated

def main():
    print("Initializing Serverless Bot...")
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    
    weights = load_json('weights.json', current_weights)
    journal = load_json('trading_journal.json', [])
    
    # Run evaluation on existing open trades
    run_evaluation(journal, exchange, weights)
    
    # Run new market scan
    exclusions = ['BTCDOM/USDT', 'DEFI/USDT', 'FOOTBALL/USDT', 'BLUEBIRD/USDT', 'DXY/USDT']
    markets = exchange.load_markets()
    symbols = [s for s in markets.keys() if s.endswith(':USDT') and s.split(':')[0] not in [e.split('/')[0] for e in exclusions]]
    
    new_active_signals = []
    
    # Process synchronously but grouped to respect rate limits (simplified for cron script)
    chunk_size = 5
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i+chunk_size]
        for sym in chunk:
            try:
                bars = exchange.fetch_ohlcv(sym, timeframe='1h', limit=30)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                tot, bb, rsi = calculate_score(df, weights)
                
                if tot >= weights['signal_threshold_long'] or tot <= weights['signal_threshold_short']:
                    dir = "LONG" if tot >= 50 else "SHORT"
                    price = df.iloc[-1]['close']
                    now_utc = datetime.utcnow()
                    
                    sig = {
                        "symbol": sym, "direction": dir, "price": price, 
                        "score": tot, "time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                    }
                    new_active_signals.append(sig)
                    
                    already_open = any(j['symbol'] == sym and j['status'] == 'open' for j in journal)
                    if not already_open:
                        max_id = max([t.get('id', 0) for t in journal]) if journal else 0
                        journal.append({
                            'id': max_id + 1, 'symbol': sym, 'direction': dir,
                            'entry_price': price, 'total_score': tot, 'bb_score': bb, 'rsi_score': rsi,
                            'entry_time': now_utc.isoformat(), 'status': 'open',
                            'exit_price': None, 'pnl': None, 'win': None
                        })
                        msg = f"🔥 **NEW {dir} (Score: {tot})**: {sym} at {price}"
                        send_telegram_msg(msg)
                        
            except Exception as e:
                pass # skip errors on individual symbols
                
    new_active_signals = sorted(new_active_signals, key=lambda x: abs(x['score'] - 50), reverse=True)
    
    status_data = {
        "status": "running (cron)",
        "last_scan": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "market_count": len(symbols),
        "signals_count": len(new_active_signals)
    }

    # Save exactly into data/ directory
    save_json('weights.json', weights)
    save_json('status.json', status_data)
    save_json('signals.json', new_active_signals)
    save_json('trading_journal.json', journal)
    
    print("Run complete. Artifacts saved to /data.")

if __name__ == "__main__":
    main()

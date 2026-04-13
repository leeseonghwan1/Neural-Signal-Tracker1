import { useState, useEffect } from 'react'
import './index.css'

function App() {
  const [signals, setSignals] = useState([])
  const [journal, setJournal] = useState([])
  const [status, setStatus] = useState({ 
    state: 'checking...', 
    last_scan: '-', 
    markets: 0,
    weights: { bb_weight: 50, rsi_weight: 50, signal_threshold_long: 85, signal_threshold_short: 15 }
  })

  const fetchData = async () => {
    try {
      // Auto-detect GitHub Pages repository name
      const host = window.location.hostname;
      let basePath = '';
      
      if (host.includes('github.io')) {
        const user = host.split('.')[0];
        const repo = window.location.pathname.split('/')[1] || '';
        basePath = `https://raw.githubusercontent.com/${user}/${repo}/main/data`;
      } else {
        basePath = '/data'; // Local dev fallback
      }

      const [resSig, resStat, resJour] = await Promise.all([
        fetch(`${basePath}/signals.json`),
        fetch(`${basePath}/status.json`),
        fetch(`${basePath}/trading_journal.json`)
      ])

      if (resSig.ok) setSignals(await resSig.json())
      if (resStat.ok) {
        const data = await resStat.json()
        setStatus({
          state: data.status,
          last_scan: data.last_scan || 'Never',
          markets: data.market_count,
          weights: data.weights || { bb_weight: 50, rsi_weight: 50, signal_threshold_long: 85, signal_threshold_short: 15 }
        })
      } else {
        setStatus(s => ({ ...s, state: 'failed offline' }))
      }
      if (resJour.ok) setJournal((await resJour.json()).reverse())
    } catch (e) {
      console.error("Failed to fetch data", e)
      setStatus(s => ({ ...s, state: 'failed offline' }))
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  const closedTrades = journal.filter(j => j.status === 'closed')
  const wins = closedTrades.filter(j => j.win)
  const winRate = closedTrades.length > 0 ? ((wins.length / closedTrades.length) * 100).toFixed(1) : '-'

  return (
    <div className="dashboard-container">
      <header>
        <div>
          <h1>Neural Signal Tracker</h1>
          <p className="subtitle">AI Multi-Factor Scoring & Weight Optimization</p>
        </div>
        <div className="header-stats">
          <div className="stat-block">
            <span className="stat-label">System State</span>
            <span className="stat-value" style={{ color: status.state === 'running' ? 'var(--accent-green)' : 'var(--accent-red)' }}>
              {status.state.toUpperCase()}
            </span>
          </div>
          <div className="stat-block">
            <span className="stat-label">Markets Scanned</span>
            <span className="stat-value">{status.markets}</span>
          </div>
        </div>
      </header>

      <div className="main-grid">
        {/* SIDEBAR: AI Param view */}
        <aside className="params-sidebar">
          <div className="glass-card">
            <div className="live-badge">
              <div className="dot"></div>
              Live Engine Weights
            </div>
            
            <div className="param-item">
              <span className="param-name">BB Score Weight</span>
              <span className="param-val">{Number(status.weights.bb_weight).toFixed(1)}%</span>
            </div>
            <div className="param-item">
              <span className="param-name">RSI Score Weight</span>
              <span className="param-val">{Number(status.weights.rsi_weight).toFixed(1)}%</span>
            </div>
            <div style={{ marginTop: '1rem', marginBottom: '1rem', borderTop: '1px solid var(--border-glass)' }}></div>
            <div className="param-item">
              <span className="param-name">Strong Buy Threshold</span>
              <span className="param-val">&ge; {Number(status.weights.signal_threshold_long).toFixed(1)}</span>
            </div>
            <div className="param-item">
              <span className="param-name">Strong Sell Threshold</span>
              <span className="param-val">&le; {Number(status.weights.signal_threshold_short).toFixed(1)}</span>
            </div>
            
            <div style={{ marginTop: '2rem', borderTop: '1px solid var(--border-glass)', paddingTop: '1rem' }}>
              <span className="stat-label">1-Hour Realized Win Rate</span>
              <span className="stat-value" style={{ color: winRate > 50 ? 'var(--accent-green)' : (winRate === '-' ? 'var(--text-main)' : 'var(--accent-red)') }}>
                {winRate}{winRate !== '-' && '%'}
              </span>
            </div>
          </div>
        </aside>

        {/* MAIN CONTENT */}
        <main className="content-area">
          
          {/* Active Signals Row */}
          <div>
            <h2 className="section-title">📡 Active Live Signals</h2>
            <div className="signals-flex">
              {signals.length === 0 ? (
                 <div className="glass-card empty-state" style={{flex: 1}}>No active extremely-scored signals right now.</div>
              ) : (
                signals.map((sig, idx) => {
                  const isLong = sig.score >= 50
                  return (
                    <div key={idx} className={`glass-card signal-card ${isLong ? 'LONG' : 'SHORT'}`}>
                      <div className="signal-header">
                        <span className="symbol">{sig.symbol}</span>
                        <span className={`direction-tag ${isLong ? 'LONG' : 'SHORT'}`}>{sig.direction}</span>
                      </div>
                      <div className="price-row">
                        <span style={{color: 'var(--text-muted)'}}>Current Price</span>
                        <span>${sig.price.toFixed(4)}</span>
                      </div>
                      <div className="price-row" style={{ marginTop: '0.25rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.25rem' }}>
                        <span style={{color: 'var(--text-muted)'}}>AI Score</span>
                        <span style={{fontWeight: 800, color: isLong ? 'var(--accent-green)' : 'var(--accent-red)'}}>{sig.score.toFixed(1)} / 100</span>
                      </div>
                      <div className="time-row">
                        Log: {sig.time.split(' ')[1]}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Trading Journal / History */}
          <div>
            <h2 className="section-title">📜 1-Hour Verification Journal</h2>
            <div className="glass-card" style={{ padding: 0, overflow: 'hidden', overflowX: 'auto' }}>
              {journal.length === 0 ? (
                <div className="empty-state">No signals evaluated yet.</div>
              ) : (
                <table className="journal-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Symbol</th>
                      <th>Dir</th>
                      <th>Score</th>
                      <th>Entry Price</th>
                      <th>1Hr Exit Price</th>
                      <th>PnL %</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {journal.map((j, i) => (
                      <tr key={i}>
                        <td>{new Date(j.entry_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</td>
                        <td style={{fontWeight: 'bold'}}>{j.symbol}</td>
                        <td>
                          <span className={`direction-tag ${j.direction}`}>{j.direction}</span>
                        </td>
                        <td><span style={{fontWeight: 'bold'}}>{j.total_score.toFixed(1)}</span></td>
                        <td>${j.entry_price.toFixed(4)}</td>
                        <td>{j.exit_price ? `$${j.exit_price.toFixed(4)}` : '-'}</td>
                        <td style={{ color: j.pnl > 0 ? 'var(--accent-green)' : (j.pnl < 0 ? 'var(--accent-red)' : 'var(--text-main)') }}>
                          {j.pnl ? `${j.pnl > 0 ? '+' : ''}${j.pnl}%` : '-'}
                        </td>
                        <td>
                          {j.status === 'open' && <span className="status-open">Waiting (1h)</span>}
                          {j.status === 'closed' && (j.win ? <span className="status-win">WIN</span> : <span className="status-loss">LOSS</span>)}
                          {j.status === 'archived' && <span className="status-loss" style={{color: 'var(--text-muted)'}}>ARCHIVED</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

        </main>
      </div>
    </div>
  )
}

export default App

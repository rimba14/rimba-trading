import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchWeather = async () => {
    try {
      const resp = await fetch('http://localhost:8001/api/weather');
      const json = await resp.json();
      setData(json);
      setLoading(false);
    } catch (err) {
      console.error("Fetch error:", err);
    }
  };

  useEffect(() => {
    fetchWeather();
    const interval = setInterval(fetchWeather, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading">Initializing Weather Oracle...</div>;

  return (
    <div className="container">
      <header>
        <h1>POLYMARKET <span className="highlight">WEATHER NODE</span></h1>
        <div className="status-badge">LIVE SRE FEED</div>
      </header>

      <main>
        <section className="trade-panel">
          <div className="card hero">
            <div className="card-label">CURRENT EXPOSURE</div>
            <div className={`bet-status ${data.trading_state.current_bet}`}>
              {data.trading_state.current_bet}
            </div>
            <div className="last-action">
              Last Action: <span>{data.trading_state.last_trade}</span>
            </div>
          </div>

          <div className="card agreement">
            <div className="card-label">API AGREEMENT METER</div>
            <div className="meter-container">
              <div 
                className="meter-fill" 
                style={{ width: data.agreement ? '100%' : '33%' }}
              ></div>
            </div>
            <div className="agreement-text">
              {data.agreement ? "CONSENSUS: PRECIPITATION EXPECTED" : "NO CONSENSUS"}
            </div>
          </div>
        </section>

        <section className="sources-grid">
          {data.sources.map((src, i) => (
            <div key={i} className="card source-card">
              <div className="source-name">{src.source}</div>
              <div className="source-prob">{src.prob}%</div>
              <div className="source-condition">{src.condition}</div>
            </div>
          ))}
        </section>
      </main>

      <footer>
        <div className="location">NEW YORK CITY (40.71°N, 74.00°W)</div>
        <div className="node-info">SENTINEL v19.5 | ADAPTIVE ARCHITECTURE</div>
      </footer>
    </div>
  );
}

export default App;

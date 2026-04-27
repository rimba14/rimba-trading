import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_hmm as hmm
import gitagent_sigproc as sigproc
import gitagent_eco as eco
import gitagent_adaptive as adi
import traceback

# ─── Live VIX from yfinance ───
def live_vix():
    try:
        import yfinance as yf
        hist = yf.Ticker('^VIX').history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception:
        pass
    return 20.0  # Default fallback

mt5.initialize()

# ─── TOP 50 PRIORITY WATCHLIST ───
symbols = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY+", "GBPJPY+",
    "EURGBP+", "EURAUD+", "GBPAUD+", "AUDJPY+", "CADJPY+", "NZDJPY+", "CHFJPY+",
    "NAS100.r", "SP500.r", "DJ30.r", "UK100.r", "GER40.r", "EU50.r", "SPI200.r",
    "XAUUSD+", "XAGUSD", "CL-OIL", "COPPER-Cr", "NG-Cr",
    "NVIDIA", "AAPL", "MSFT", "META", "GOOG", "TSLA", "AMAZON", "AVGO",
    "JPM", "GS", "BAC", "VISA",
    "SHELL", "ASML", "AZN", "LVMH", "SAP", "HSBA",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD",
]

def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def stoch(high, low, close, k=14, d=3):
    lowest_low = low.rolling(window=k).min()
    highest_high = high.rolling(window=k).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    stoch_d = stoch_k.rolling(window=d).mean()
    return stoch_k, stoch_d

def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line

asset_data = []

# Phase 1: Gather Cross-Sectional Data
for i, sym in enumerate(symbols):
    try:
        print(f"[{i+1}/{len(symbols)}] Scanning {sym}...")
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 400)
        if rates is None or len(rates) < 150: continue
            
        df = pd.DataFrame(rates)
        rets = df['close'].pct_change().dropna().values
        
        # Econophysics Tiers
        alpha = eco.levy_alpha(rets[-60:])
        gamma = eco.levy_scale(rets[-60:], alpha)
        kl_div = eco.kl_divergence(rets[-60:], rets[:-60])
        persistence = eco.volatility_clustering(rets[-60:])
        
        # Standard Indicators
        price = df['close'].iloc[-1]
        chg = ((price - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]
        r_val = rsi(df['close'], 14).iloc[-1]
        macdH = macd(df['close']).iloc[-1]
        stK, stD = stoch(df['high'], df['low'], df['close'])
        sk, sd = stK.iloc[-1], stD.iloc[-1]
        std = df['close'].rolling(20).std().iloc[-1]
        bbM = df['close'].rolling(20).mean().iloc[-1]
        bbU, bbL = bbM + 2*std, bbM - 2*std
        vol_ratio = df['tick_volume'].iloc[-1] / df['tick_volume'].rolling(20).mean().iloc[-1]
        
        # Performance Metrics
        maxDD = -((df['close'].cummax() - df['close']) / df['close'].cummax()).max()
        ret_mean, ret_std = df['close'].pct_change().mean(), df['close'].pct_change().std()
        sharpe = (ret_mean / ret_std) * np.sqrt(252) if ret_std > 0 else 0
        
        # v7.2 Adaptive Metrics
        sentiment_score = np.clip((chg * 0.5) + (1.0 if r_val > 60 else -1.0 if r_val < 40 else 0), -1.0, 1.0)
        h_data = adi.hurst_exponent(rets[-100:])
        i_data = adi.ising_herding(rets[-60:], r_val, sentiment_score)
        f_data = adi.fractal_dimension(df['close'].values[-60:])
        
        # HMM
        hmm_state, hmm_prob, _ = hmm.get_current_state(df['close'].values)

        # RPBERT Score
        rpb_score = (r_val / 100) * 0.4 + (0.2 if macdH > 0 else 0) + (chg / 100) * 0.4
        
        asset_data.append({
            'sym': sym, 'price': price, 'chg': chg, 'sma50': sma50, 'sma200': sma200, 
            'r': r_val, 'macdH': macdH, 'sk': sk, 'sd': sd, 'bbL': bbL, 'bbU': bbU, 'bbM': bbM,
            'maxDD': maxDD, 'sharpe': sharpe, 'rpb_score': rpb_score, 'sentiment_score': sentiment_score,
            'vol_ratio': vol_ratio, 'hmm_state': hmm_state, 'hmm_prob': hmm_prob,
            'alpha': alpha, 'kl': kl_div, 'persistence': persistence, 'rets': rets,
            'hurst': h_data, 'ising': i_data, 'fractal': f_data, 'ret_mean': ret_mean, 'ret_std': ret_std
        })
    except Exception as e:
        print(f"Error scanning {sym}: {e}")
        traceback.print_exc()
        continue

# Phase 2: Ranking
asset_data.sort(key=lambda x: x['rpb_score'], reverse=True)
for i, ad in enumerate(asset_data):
    ad['rpb_decile'] = i / max(1, len(asset_data) - 1)

# Volatility Regime — live VIX
vix_price = live_vix()
print(f"[VIX] Live: {vix_price:.2f}")
if vix_price < 15:
    VOL_REGIME, REGIME_CONF_THRESHOLD, REGIME_SIZE_MULT = "LOW", 70.0, 1.0
elif vix_price < 25:
    VOL_REGIME, REGIME_CONF_THRESHOLD, REGIME_SIZE_MULT = "MEDIUM", 55.0, 1.0
elif vix_price < 35:
    VOL_REGIME, REGIME_CONF_THRESHOLD, REGIME_SIZE_MULT = "HIGH", 65.0, 0.65
else:
    VOL_REGIME, REGIME_CONF_THRESHOLD, REGIME_SIZE_MULT = "EXTREME", 80.0, 0.35

results = []
# Phase 3: Swarm Processing
for ad in asset_data:
    # Agents
    w_b, w_s = 0.3, 0.1
    if ad['r'] < 30: w_b+=0.25
    elif ad['r'] > 70: w_s+=0.2
    if ad['macdH'] > 0: w_b+=0.15
    else: w_s+=0.1
    if ad['price'] < ad['bbL']: w_b+=0.1
    if ad['price'] > ad['bbU']: w_s+=0.1
    
    wy_b, wy_s = 0.25, 0.15
    if ad['price'] > ad['sma50'] and ad['price'] > ad['sma200']: wy_b+=0.2
    if ad['price'] < ad['sma50']: wy_s+=0.2
    
    b_b, b_s = 0.25, 0.15
    if ad['price'] > ad['bbM']: b_b+=0.1
    if ad['sk'] > ad['sd'] and ad['macdH'] > 0: b_b+=0.15
    if ad['sk'] < ad['sd'] and ad['macdH'] < 0: b_s+=0.15

    mb_b, mb_s = 0.1, 0.2
    if ad['r'] < 35: mb_b+=0.2
    if ad['sharpe'] > 1.2: mb_b+=0.2
    
    smc_b, smc_s, smc_h = 0.2, 0.1, 0.7
    if ad['price'] > ad['sma50']: smc_b+=0.12
    if ad['r'] < 40: smc_b+=0.12

    rpb_b, rpb_s, rpb_h = 0.1, 0.1, 0.8
    if ad['rpb_decile'] <= 0.2: rpb_b += 0.4; rpb_h -= 0.3
    elif ad['rpb_decile'] >= 0.8: rpb_s += 0.4; rpb_h -= 0.3

    llm_b, llm_s, llm_h = 0.3, 0.3, 0.4
    if ad['rpb_decile'] <= 0.3 and ad['sentiment_score'] > 0.5: llm_b += 0.3
    if ad['rpb_decile'] >= 0.7 and ad['sentiment_score'] < -0.5: llm_s += 0.3

    whl_b, whl_s, whl_h = 0.1, 0.1, 0.8
    if ad['vol_ratio'] > 2.0:
        if ad['chg'] > 0 and ad['price'] > ad['sma50']: whl_b += 0.5
        if ad['chg'] < 0 and ad['price'] < ad['sma50']: whl_s += 0.5

    sen_b, sen_s, sen_h = 0.2, 0.2, 0.6
    if ad['sentiment_score'] > 0.6: sen_b += 0.4
    elif ad['sentiment_score'] < -0.6: sen_s += 0.4

    # Swarm Consensus Calculation (v7.2 Weighted)
    totalW = 1.2 + 1.0 + 0.9 + 1.25 + 1.15 + 1.4 + 1.5 + 1.3 + 1.0
    cB = (ad['hurst']['trend_boost'] * (w_b*1.2 + wy_b*1.0 + b_b*0.9 + smc_b*1.15 + rpb_b*1.4 + whl_b*1.3) + 
          ad['hurst']['mr_boost'] * (mb_b*1.25 + llm_b*1.5 + sen_b*1.0)) / totalW
    cS = (ad['hurst']['trend_boost'] * (w_s*1.2 + wy_s*1.0 + b_s*0.9 + smc_s*1.15 + rpb_s*1.4 + whl_s*1.3) + 
          ad['hurst']['mr_boost'] * (mb_s*1.25 + llm_s*1.5 + sen_s*1.0)) / totalW
    cH = 1.0 - (cB + cS) # Simplification
    
    # Signal Quality
    votes = [[w_b, w_s, 0.6], [wy_b, wy_s, 0.6], [b_b, b_s, 0.6], [mb_b, mb_s, 0.7], 
             [smc_b, smc_s, 0.7], [rpb_b, rpb_s, rpb_h], [llm_b, llm_s, llm_h], 
             [whl_b, whl_s, whl_h], [sen_b, sen_s, sen_h]]
    ib = sigproc.information_bottleneck(votes)
    fft = sigproc.fft_cycle_detector(ad['rets'][-60:])
    kal = sigproc.adaptive_kalman(ad['rets'][-60:])
    dwt = sigproc.haar_dwt(ad['rets'][-60:])
    snr_mult = 1.05 if abs(kal['innovation']) < 0.02 else 0.95 
    sig_q = sigproc.calculate_sig_quality(fft, kal, dwt, snr_mult, ib['multiplier'], (1 if cB > cS else -1 if cS > cB else 0))
    
    # Eco Adjust
    temp = eco.thermodynamic_temperature(ad['alpha'], ad['kl'], ad['persistence'], vix_price)
    eco_mult = 1.0 / max(1.0, temp)
    
    # Meta Gate
    tp_p = ad['price'] * (1 + 2 * ad['ret_std'])
    sl_p = ad['price'] * (1 - ad['ret_std'])
    p_tp = adi.first_passage_probability(ad['price'], tp_p, sl_p, ad['ret_mean'], ad['ret_std'], ad['ret_std'])
    m_score, m_dec = adi.meta_label_gate(p_tp, ("A" if snr_mult > 1.0 else "C"), ad['hurst']['tradable'], ad['ising']['phase'], sig_q, ad['fractal']['modifier'])
    
    sig = "BUY" if cB > cS and cB > cH else "SELL" if cS > cB and cS > cH else "HOLD"
    conf = max(cB, cS, cH) * 100 * sig_q * eco_mult
    if m_dec == "SKIP": conf = min(conf, 30.0)
    
    # Final Size
    riskLimit = 0.20
    riskMult = 1.0
    if ad['maxDD'] <= -0.4: riskMult *= 0.5
    if ad['sharpe'] > 1.0: riskMult *= 1.15
    hmm_conf_adj, hmm_size_adj = hmm.hmm_regime_adjustment(ad['hmm_state'], sig)
    asset_conf_threshold = REGIME_CONF_THRESHOLD + hmm_conf_adj
    asset_size_mult      = REGIME_SIZE_MULT * hmm_size_adj
    finalLimit = min(max(riskLimit * riskMult * asset_size_mult, 0.025), 0.25)
    
    if sig in ("BUY", "SELL") and conf < asset_conf_threshold: sig = "HOLD"
    
    results.append({
        "sym": ad['sym'], "price": ad['price'], "sig": sig, "conf": conf, "alloc": finalLimit,
        "hmm": ad['hmm_state'], "sig_q": sig_q, "cycle": fft['phase_label'], "diversity": ib['diversity'],
        "hurst": ad['hurst']['H'], "fractal": ad['fractal']['D'], "ising": ad['ising']['phase'], "meta": m_score
    })

# Output
results.sort(key=lambda x: (1 if x['sig']=="BUY" else 0, x['conf']), reverse=True)
print(f"\n=== VANTAGE INSTRUMENTS ANALYSIS (GITAGENT V7.2 ADAPTIVE) ===")
print(f"VOL REGIME: {VOL_REGIME} | VIX: {vix_price:.2f} | Min Conf: {REGIME_CONF_THRESHOLD:.0f}%")
print(f"{'SYM':<10} | {'SIG':<5} | {'CONF':<5} | {'META':<5} | {'HURST':<5} | {'FRAC':<5} | {'ISING':<7} | {'DIV':<5}")
print("-" * 90)
for r in results:
    print(f"{r['sym']:<10} | {r['sig']:<5} | {r['conf']:<4.1f}% | {r['meta']:<5.1f} | {r['hurst']:<5.2f} | {r['fractal']:<5.2f} | {r['ising']:<7} | {r['diversity']:.2f}")

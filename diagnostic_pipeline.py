"""
DIAGNOSTIC: Trace the full execution pipeline for top assets.
Shows exactly which gate blocks each asset and why.
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_sigproc as sigproc
import gitagent_eco as eco
import gitagent_adaptive as adi

mt5.initialize()

# Test a few key assets
test_syms = ["NAS100.r", "GER40.r", "XAUUSD+", "EURUSD", "BTCUSD", "GBPUSD"]

print("=" * 80)
print("PIPELINE DIAGNOSTIC — Tracing each gate for selected assets")
print("=" * 80)

for sym in test_syms:
    print(f"\n{'─' * 60}")
    print(f"  ASSET: {sym}")
    print(f"{'─' * 60}")
    
    sym_info = mt5.symbol_info(sym)
    if sym_info is None:
        print(f"  [SKIP] Symbol not found")
        continue
    if not sym_info.visible:
        mt5.symbol_select(sym, True)
    
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 1000)
    if rates is None or len(rates) < 500:
        print(f"  [SKIP] Not enough M15 data: {len(rates) if rates is not None else 0} bars")
        continue
    
    df = pd.DataFrame(rates)
    price = df['close'].iloc[-1]
    vol = df['tick_volume'].iloc[-1]
    vol_sma = df['tick_volume'].rolling(20).mean().iloc[-1]
    vol_ratio = vol / vol_sma if vol_sma > 0 else 1.0
    chg = ((price - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
    sma50 = df['close'].rolling(50).mean().iloc[-1]
    sma200 = df['close'].rolling(200).mean().iloc[-1]
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    r = (100 - (100 / (1 + rs))).iloc[-1]
    
    # MACD
    exp12 = df['close'].ewm(span=12).mean()
    exp26 = df['close'].ewm(span=26).mean()
    macdLine = exp12 - exp26
    signal_line = macdLine.ewm(span=9).mean()
    macdH = (macdLine - signal_line).iloc[-1]
    
    # Stoch
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    sk = (100 * (df['close'] - low14) / (high14 - low14)).iloc[-1]
    sd = (100 * (df['close'] - low14) / (high14 - low14)).rolling(3).mean().iloc[-1]
    
    current_atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    rets = df['close'].pct_change().dropna().values
    
    print(f"  Price: {price:.5f} | RSI: {r:.1f} | MACD_H: {macdH:.5f} | ATR: {current_atr:.5f}")
    print(f"  SMA50: {sma50:.5f} | SMA200: {sma200:.5f} | Vol Ratio: {vol_ratio:.2f}")
    
    # ─── GATE 1: Agent Swarm Consensus ───
    # Simplified — just check Williams + Wyckoff + basic consensus
    w_b, w_s = 0.3, 0.1
    if r < 30: w_b += 0.25
    elif r > 70: w_s += 0.2
    if macdH > 0: w_b += 0.15
    else: w_s += 0.1
    tot = w_b + w_s + 0.6
    w_buy, w_sell = w_b/tot, w_s/tot
    
    wy_b, wy_s = 0.25, 0.15
    if price > sma50 and price > sma200: wy_b += 0.2
    if price < sma50: wy_s += 0.2
    tot2 = wy_b + wy_s + 0.6
    wy_buy, wy_sell = wy_b/tot2, wy_s/tot2
    
    avg_buy = (w_buy + wy_buy) / 2
    avg_sell = (w_sell + wy_sell) / 2
    avg_hold = 1 - avg_buy - avg_sell
    
    sig = "BUY" if avg_buy > avg_sell and avg_buy > avg_hold else "SELL" if avg_sell > avg_buy and avg_sell > avg_hold else "HOLD"
    raw_conf = max(avg_buy, avg_sell, avg_hold) * 100
    
    print(f"\n  GATE 1 — Agent Consensus:")
    print(f"  Signal: {sig} | Raw Conf: {raw_conf:.1f}%")
    print(f"  Buy={avg_buy:.3f} Sell={avg_sell:.3f} Hold={avg_hold:.3f}")
    
    if sig == "HOLD":
        print(f"  >>> BLOCKED at GATE 1: Signal is HOLD (no directional consensus)")
        print(f"  >>> This means Buy ({avg_buy:.3f}) and Sell ({avg_sell:.3f}) are both < Hold ({avg_hold:.3f})")
        continue
    
    # ─── GATE 2: Signal Processing ───
    fft = sigproc.fft_cycle_detector(rets[-60:])
    kal = sigproc.adaptive_kalman(rets[-60:])
    dwt = sigproc.haar_dwt(rets[-60:])
    
    # SNR
    snr_val = sigproc.signal_noise_ratio(kal, dwt, fft)
    snr_mult = snr_val.get('mult', 1.0) if isinstance(snr_val, dict) else 1.0
    sig_q = snr_mult
    
    print(f"\n  GATE 2 — Signal Processing:")
    print(f"  FFT: {fft}")
    print(f"  Kalman: {kal}")
    print(f"  SNR mult: {snr_mult:.3f} | SigQ: {sig_q:.3f}")
    
    # ─── GATE 3: v7.2 ADI ───
    h_data = adi.hurst_exponent(rets[-100:])
    i_data = adi.ising_herding(rets[-60:], r, 0)
    f_data = adi.fractal_dimension(df['close'].values[-60:])
    
    print(f"\n  GATE 3 — Adaptive Intelligence:")
    print(f"  Hurst: H={h_data['H']:.3f} regime={h_data['regime']} tradable={h_data['tradable']}")
    print(f"  Ising: phase={i_data['phase']} M={i_data.get('magnetization', 0):.3f}")
    print(f"  Fractal: D={f_data['D']:.3f} roughness={f_data['roughness']} modifier={f_data['modifier']}")
    
    # ─── GATE 4: Meta-Labeling ───
    dailyDrift = np.mean(rets)
    dailyVol = np.std(rets)
    tp_dist = 2 * current_atr
    sl_dist = 1 * current_atr
    tp_price = price + tp_dist if sig == "BUY" else price - tp_dist
    sl_price = price - sl_dist if sig == "BUY" else price + sl_dist
    
    # EWMA vol forecast
    sq_rets = rets[-20:]**2
    ewma_var = sq_rets[-1]
    for sr in sq_rets[-2::-1]:
        ewma_var = 0.94 * ewma_var + 0.06 * sr
    vol_forecast = float(np.sqrt(max(1e-10, ewma_var)))
    
    p_tp = adi.first_passage_probability(price, tp_price, sl_price, dailyDrift, dailyVol, vol_forecast)
    snr_grade = "A" if snr_mult > 1.0 else "C"
    
    print(f"\n  GATE 4 — Meta-Label Gate:")
    print(f"  Daily Drift: {dailyDrift:.8f} | Daily Vol: {dailyVol:.6f} | Vol Forecast: {vol_forecast:.6f}")
    print(f"  TP: {tp_price:.5f} | SL: {sl_price:.5f}")
    print(f"  P(TP): {p_tp:.4f} | SNR Grade: {snr_grade}")
    
    # Score breakdown
    score = 0.0
    scores_detail = []
    
    if p_tp > 0.60: score += 1.5; scores_detail.append(f"  FP: +1.5 (p_tp={p_tp:.3f} > 0.60)")
    elif p_tp > 0.52: score += 1.0; scores_detail.append(f"  FP: +1.0 (p_tp={p_tp:.3f} > 0.52)")
    elif p_tp > 0.48: score += 0.5; scores_detail.append(f"  FP: +0.5 (p_tp={p_tp:.3f} > 0.48)")
    elif p_tp > 0.45: score += 0.3; scores_detail.append(f"  FP: +0.3 (p_tp={p_tp:.3f} > 0.45)")
    else: scores_detail.append(f"  FP: +0.0 (p_tp={p_tp:.3f} <= 0.45) <<<< PROBLEM")
    
    if snr_grade in ["A", "B"]: score += 1.0; scores_detail.append(f"  SNR: +1.0 (grade={snr_grade})")
    elif snr_grade == "C": score += 0.5; scores_detail.append(f"  SNR: +0.5 (grade={snr_grade})")
    else: scores_detail.append(f"  SNR: +0.0 (grade={snr_grade})")
    
    if h_data['tradable']: score += 1.0; scores_detail.append(f"  Hurst: +1.0 (tradable=True, H={h_data['H']:.3f})")
    else: score += 0.2; scores_detail.append(f"  Hurst: +0.2 (tradable=False, H={h_data['H']:.3f}) <<<< PROBLEM")
    
    if i_data['phase'] == "BALANCED": score += 0.8; scores_detail.append(f"  Ising: +0.8 (BALANCED)")
    elif i_data['phase'] == "MODERATE_HERD": score += 0.5; scores_detail.append(f"  Ising: +0.5")
    elif i_data['phase'] == "EXTREME_HERD": score += 0.7; scores_detail.append(f"  Ising: +0.7")
    else: scores_detail.append(f"  Ising: +0.0 ({i_data['phase']})")
    
    if sig_q > 1.05: score += 1.0; scores_detail.append(f"  SigQ: +1.0 (sigQ={sig_q:.3f} > 1.05)")
    elif sig_q > 0.95: score += 0.5; scores_detail.append(f"  SigQ: +0.5 (sigQ={sig_q:.3f} > 0.95)")
    elif sig_q > 0.85: score += 0.3; scores_detail.append(f"  SigQ: +0.3 (sigQ={sig_q:.3f} > 0.85)")
    else: scores_detail.append(f"  SigQ: +0.0 (sigQ={sig_q:.3f} <= 0.85) <<<< PROBLEM")
    
    frac_score = max(0, (f_data['modifier'] - 0.7) * 2)
    score += frac_score
    scores_detail.append(f"  Fractal: +{frac_score:.2f} (modifier={f_data['modifier']})")
    
    print(f"\n  META-SCORE BREAKDOWN (threshold = 3.0):")
    for d in scores_detail:
        print(f"  {d}")
    print(f"  {'='*40}")
    print(f"  TOTAL: {score:.2f} | {'EXECUTE' if score >= 3.0 else 'SKIP'}")
    
    m_score, m_dec = adi.meta_label_gate(p_tp, snr_grade, h_data['tradable'], i_data['phase'], sig_q, f_data['modifier'])
    print(f"  Actual meta_label_gate() returned: score={m_score:.2f}, decision={m_dec}")

    if m_dec == "SKIP":
        print(f"\n  >>> BLOCKED at GATE 4: Meta-Score {m_score:.1f} < 3.0")
        continue
    
    # ─── GATE 5: CPCV ───
    cpcv_score, cpcv_grade = adi.cpcv_reliability(rets, sig, h_data['H'], 1.8)
    print(f"\n  GATE 5 — CPCV: score={cpcv_score:.2f} grade={cpcv_grade}")
    if cpcv_grade == "F":
        print(f"  >>> BLOCKED at GATE 5: CPCV Grade F")
        continue
    
    # ─── GATE 6: Regime Conf ───
    conf = raw_conf * sig_q
    print(f"\n  GATE 6 — Regime Confidence: conf={conf:.1f}% vs threshold=55%")
    if conf < 55:
        print(f"  >>> BLOCKED at GATE 6: Confidence {conf:.1f}% < 55%")
        continue
    
    print(f"\n  ✅ WOULD PASS ALL GATES — Would proceed to M15 Tactical!")

print(f"\n{'=' * 80}")
print("DIAGNOSTIC COMPLETE")
print(f"{'=' * 80}")

mt5.shutdown()

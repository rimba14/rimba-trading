import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_utils as utils
import gitagent_sigproc as sigproc
import gitagent_hmm as hmm

def run_forensic_audit(symbol, signal_type, score):
    print(f"\n[FORENSIC] Auditing {symbol} | Signal: {signal_type} | Score: {score}")
    
    if not mt5.initialize():
        print(" -> [FAIL] MT5 Sync: Terminal not initialized.")
        return
        
    # Layer 1: Normalization Audit
    info = mt5.symbol_info(symbol)
    if not info:
        print(f" -> [FAIL] MT5 Sync: Symbol {symbol} not found in MarketWatch.")
        return
        
    # Mock a $10 risk calculation
    risk_usd = 10.0
    tick = mt5.symbol_info_tick(symbol)
    atr = 0.001 # placeholder
    risk_per_lot = (atr * 4.2 / info.trade_tick_size) * info.trade_tick_value
    lot_raw = risk_usd / (risk_per_lot + 1e-9)
    
    norm_vol = utils.normalize_volume(symbol, lot_raw)
    print(f" -> [LAYER 1] Lot Normalization: Raw={lot_raw:.4f} | Normalized={norm_vol} | Min={info.volume_min}")
    if norm_vol < info.volume_min:
        print(f"    [KILLER] Silent Drop: Lot size {norm_vol} falls below broker minimum {info.volume_min}.")
        
    # Layer 2: Regime Blockage Audit
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 200)
    if rates is not None:
        df = pd.DataFrame(rates)
        # Efficiency Ratio calculation (ER)
        price_diff = df['close'].diff()
        direction = abs(df['close'].iloc[-1] - df['close'].iloc[-10])
        volatility = price_diff.tail(10).abs().sum()
        er = direction / (volatility + 1e-9)
        
        # HMM Adjustment
        state_label, prob, _ = hmm.get_current_state(df['close'].values)
        hmm_adj, size_adj = hmm.hmm_regime_adjustment(state_label, signal_type)
        
        print(f" -> [LAYER 2] Regime Filter: ER={er:.2f} (Block if < 0.3) | HMM State={state_label} | HMM Adj={hmm_adj} | Size Adj={size_adj}")
        if er < 0.3:
            print(f"    [KILLER] Regime Blockage: Efficiency Ratio {er:.2f} < 0.3 threshold. Market too choppy for SMC.")
        if hmm_adj > 5.0:
            print(f"    [KILLER] HMM Blockage: Regime is raising signal threshold by +{hmm_adj}.")

    # Layer 3: Sync & Pre-Flight
    acc = mt5.account_info()
    term = mt5.terminal_info()
    print(f" -> [LAYER 3] MT5 Sync: Connected={term.connected} | TradeAllowed={acc.trade_allowed} | MarginFree=${acc.margin_free:.2f}")
    if not term.connected:
        print("    [KILLER] Connection: Terminal disconnected from broker server.")
    if not acc.trade_allowed:
        print("    [KILLER] Account: Trading is disabled (check 'AutoTrading' button or broker status).")
    if acc.margin_free < 50:
        print(f"    [KILLER] Margin: Insufficient free margin (${acc.margin_free:.2f}) for new entries.")

    print("[FORENSIC] Audit complete.")

if __name__ == "__main__":
    # Test with a known candidate
    run_forensic_audit("EURUSD", "BUY", 32.5)

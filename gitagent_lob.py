import MetaTrader5 as mt5
import numpy as np
from datetime import datetime

def get_lob_analytics(symbol, my_size=0.1):
    """
    Upgrade 3 & 5: Enhanced LOB + Opponent Modeling Proxies.
    Returns: { 'spread_norm': float, 'mid_ret': float, 'queue_imb': float, 
               'vol_imb': float, 'depth_norm': float, 'signed_vol': float,
               'comp_pressure': float, 'adv_rate': float, 'vpin': float,
               'spread_comp': float }
    """
    # Fetch 500 ticks for flow analysis
    ticks = mt5.copy_ticks_from(symbol, datetime.now(), 500, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) < 100:
        return {k: 0.0 for k in ['spread_norm', 'mid_ret', 'queue_imb', 'vol_imb', 'depth_norm', 
                                 'signed_vol', 'comp_pressure', 'adv_rate', 'vpin', 'spread_comp']}

    bids = ticks['bid']; asks = ticks['ask']; vols = ticks['volume']; flags = ticks['flags']
    
    # 1. Spreads & Returns
    current_mid = (bids[-1] + asks[-1]) / 2.0
    prev_mid = (bids[-50] + asks[-50]) / 2.0
    mid_ret = np.log(current_mid / prev_mid)
    spread_norm = (asks[-1] - bids[-1]) / (np.mean(asks - bids) + 1e-9)
    
    # 2. Imbalances (Proxies using aggressive volumes if available, else tick direction)
    # BUY flag = 32, SELL flag = 64 (Metatrader flags for tick direction)
    buy_vol = np.sum(vols[flags & 32 > 0])
    sell_vol = np.sum(vols[flags & 64 > 0])
    vol_imb = (buy_vol - sell_vol) / (buy_vol + sell_vol + 1e-9)
    signed_vol = (buy_vol - sell_vol) / (np.mean(vols) * 100 + 1e-9)
    
    # 3. Queue Imbalance (L1 proxy: tick-volume ratio of last 10 ticks)
    queue_imb = (np.sum(vols[-10:][flags[-10:] & 32 > 0]) - np.sum(vols[-10:][flags[-10:] & 64 > 0])) / \
                (np.sum(vols[-10:]) + 1e-9)

    # 4. Opponent Modeling (Upgrade 5)
    # VPIN (Volume-Synchronized Probability of Informed Trading)
    # Using 10 bins of 50 ticks
    bin_size = 50
    vpin_val = 0.0
    for i in range(10):
        b_buy = np.sum(vols[i*bin_size:(i+1)*bin_size][flags[i*bin_size:(i+1)*bin_size] & 32 > 0])
        b_sell = np.sum(vols[i*bin_size:(i+1)*bin_size][flags[i*bin_size:(i+1)*bin_size] & 64 > 0])
        vpin_val += abs(b_buy - b_sell)
    vpin = vpin_val / (np.sum(vols) + 1e-9)
    
    # Adverse selection: frequency of price moving against trade direction immediately after aggressive fill
    adv_rate = (np.mean(mid_ret) * (vol_imb)) # simple proxy: high vol imbalance + negative drift = high toxicity
    
    # Spread compression
    spread_comp = (asks[-1] - bids[-1]) / (asks[-50] - bids[-50] + 1e-9) - 1.0

    return {
        "spread_norm": float(np.clip(spread_norm, -2, 2)),
        "mid_ret": float(np.clip(mid_ret * 1000, -2, 2)),
        "queue_imb": float(np.clip(queue_imb, -1, 1)),
        "vol_imb": float(np.clip(vol_imb, -1, 1)),
        "depth_norm": float(np.clip(np.sum(vols[-20:]) / (np.mean(vols) * 20 + 1e-9), 0, 3)),
        "signed_vol": float(np.clip(signed_vol, -1, 1)),
        "comp_pressure": float(np.clip(my_size / (np.mean(vols[-5:]) + 1e-9), 0, 5)), # My size vs avail liquidity
        "adv_rate": float(np.clip(adv_rate, -1, 1)),
        "vpin": float(np.clip(vpin, 0, 1)),
        "spread_comp": float(np.clip(spread_comp, -1, 1))
    }

if __name__ == "__main__":
    if mt5.initialize():
        print("--- TICK-LOB PROBE ---")
        for sym in ["EURUSD", "NAS100", "XAUUSD"]:
            res = get_lob_analytics(sym)
            print(f"{sym}: L1 Imbalance={res['l1_imbalance']:+.2f} | Spread={res['spread_bps']:.2f} bps")
        mt5.shutdown()

import os
import asyncio
import logging
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from pydantic import BaseModel
from typing import Optional
import ccxt.async_support as ccxt_async
import math
from dotenv import load_dotenv

load_dotenv()

# Use the existing ATR logic from the main framework
from fastapi_sniper import calculate_structural_atr_d1, get_structural_multiplier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [BINANCE] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Sentinel Binance Execution Bridge")

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    expected_key = os.getenv("SENTINEL_API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")

class TradeSignal(BaseModel):
    symbol: str
    direction: str
    conviction: Optional[float] = 0.80
    xgb_p: float = 0.5
    ddqn_p: float = 0.5
    wasserstein_state: str = "HIGH-VOL MEAN REVERSION"
    timestamp: Optional[int] = None
    reasoning: str = ""
    vpin: float = 0.0
    signal_type: str = "UNKNOWN"
    rsi: Optional[float] = None
    data_quality_flag: str = "PRISTINE"
    alpha_features: Optional[dict] = None
    vrs: Optional[float] = 1.0
    applied_dynamic_gate: Optional[float] = None
    strategy_type: Optional[str] = "MOMENTUM"
    sl: Optional[float] = 0.0
    tp: Optional[float] = 0.0
    size_multiplier: Optional[float] = 1.0
    override_lot: Optional[float] = 0.0
    tag: Optional[str] = ""

def map_symbol(oracle_sym: str) -> str:
    """Translates BTCUSD to BTC/USDT:USDT (CCXT linear futures unified symbol)"""
    base = oracle_sym.replace("USD", "")
    return f"{base}/USDT:USDT"

async def get_exchange():
    api_key = os.getenv('BINANCE_API_KEY')
    secret = os.getenv('BINANCE_SECRET')
    if not api_key or not secret:
        raise HTTPException(status_code=400, detail="BINANCE_API_KEY and BINANCE_SECRET must be set in .env")
        
    exchange = ccxt_async.binanceusdm({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'
        }
    })
    # Bypass CCXT sandbox deprecation block by overriding all endpoints
    for k, v in exchange.urls['api'].items():
        if isinstance(v, str):
            exchange.urls['api'][k] = v.replace('fapi.binance.com', 'testnet.binancefuture.com').replace('api.binance.com', 'testnet.binancefuture.com').replace('sapi.binance.com', 'testnet.binancefuture.com')
    
    return exchange

@app.post("/execute_trade", dependencies=[Depends(verify_api_key)])
async def execute_trade(signal: TradeSignal):
    logger.info(f"Received Binance execution signal for {signal.symbol} | Dir: {signal.direction}")
    
    binance_sym = map_symbol(signal.symbol)
    exchange = await get_exchange()
    
    try:
        await exchange.load_markets()
        if binance_sym not in exchange.markets:
            raise HTTPException(status_code=400, detail=f"Symbol {binance_sym} not tradeable on Binance Futures")
            
        market = exchange.market(binance_sym)
        ticker = await exchange.fetch_ticker(binance_sym)
        current_price = ticker.get('ask') if signal.direction == 'BUY' else ticker.get('bid')
        if current_price is None:
            current_price = ticker.get('last')
        # 1. Structural ATR & SL/TP
        structural_atr = await asyncio.to_thread(calculate_structural_atr_d1, signal.symbol, period=14)
        if structural_atr is None:
            logger.warning(f"MT5 could not resolve {signal.symbol} ATR. Fetching natively via Binance CCXT.")
            ohlcv = await exchange.fetch_ohlcv(binance_sym, timeframe='1d', limit=15)
            if ohlcv and len(ohlcv) >= 14:
                tr_list = []
                for i in range(1, len(ohlcv)):
                    h, l, prev_c = ohlcv[i][2], ohlcv[i][3], ohlcv[i-1][4]
                    tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                    tr_list.append(tr)
                structural_atr = sum(tr_list[-14:]) / 14.0
            else:
                structural_atr = current_price * 0.05  # 5% fallback
                
        multiplier = get_structural_multiplier(signal.symbol) or 1.0
        
        dynamic_sl_dist = structural_atr * multiplier
        daily_atr_floor = structural_atr * 1.0
        percentage_floor = current_price * 0.002
        
        final_sl_dist = max(dynamic_sl_dist, daily_atr_floor, percentage_floor)
        
        sl_price = current_price - final_sl_dist if signal.direction == 'BUY' else current_price + final_sl_dist
        tp_dist = final_sl_dist * 1.5 # Fixed symmetric T/P for simplicity unless Conviction allows more
        
        # Dynamic TP
        p_entry = signal.conviction if signal.direction == 'BUY' else (1.0 - signal.conviction)
        p_entry = max(abs(p_entry - 0.5) + 0.5, 0.60)
        normalized_p = (p_entry - 0.60) / 0.40
        tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
        conviction_tp_dist = structural_atr * tp_multiplier
        tp_dist = max(conviction_tp_dist, tp_dist)
        
        tp_price = current_price + tp_dist if signal.direction == 'BUY' else current_price - tp_dist
        
        sl_price = float(exchange.price_to_precision(binance_sym, sl_price))
        tp_price = float(exchange.price_to_precision(binance_sym, tp_price))
        
        # 2. Risk Sizing
        balance = await exchange.fetch_balance()
        usdt_free = balance.get('USDT', {}).get('free', 0.0)
        if usdt_free <= 0:
            usdt_free = balance.get('total', {}).get('USDT', 0.0)
            
        if signal.override_lot > 0:
            final_lot = signal.override_lot
        else:
            dollar_risk = usdt_free * 0.02
            # Size = Risk / Distance
            raw_lot = dollar_risk / final_sl_dist
            final_lot = exchange.amount_to_precision(binance_sym, raw_lot)
            
        final_lot = float(final_lot)
        min_amount = market['limits']['amount']['min']
        if final_lot < min_amount:
            logger.warning(f"Calculated lot {final_lot} < minimum {min_amount}. Clamping.")
            final_lot = min_amount

        # 3. Execution
        side = 'buy' if signal.direction == 'BUY' else 'sell'
        inv_side = 'sell' if side == 'buy' else 'buy'
        
        logger.info(f"[{binance_sym}] Executing {side.upper()} {final_lot} at {current_price} | SL: {sl_price} | TP: {tp_price}")
        
        # Market Order
        main_order = await exchange.create_order(binance_sym, 'market', side, final_lot)
        
        # SL and TP using closePosition
        sl_params = {'closePosition': True, 'stopPrice': float(sl_price)}
        tp_params = {'closePosition': True, 'stopPrice': float(tp_price)}
        
        try:
            sl_order = await exchange.create_order(binance_sym, 'stop_market', inv_side, final_lot, None, sl_params)
            tp_order = await exchange.create_order(binance_sym, 'take_profit_market', inv_side, final_lot, None, tp_params)
            logger.info(f"[{binance_sym}] Attached SL and TP brackets successfully.")
        except Exception as e:
            logger.error(f"[{binance_sym}] Bracket attachment failed: {e}")
            
        return {"status": "success", "main_order": main_order['id']}
        
    except Exception as e:
        logger.error(f"Execution Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await exchange.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("binance_sniper:app", host="127.0.0.1", port=8002, reload=False)

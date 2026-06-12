import MetaTrader5 as mt5

def hard_close():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    tickets = [1149039783, 1149437588]
    
    for tkt in tickets:
        p = mt5.positions_get(ticket=tkt)
        if not p:
            print(f"Ticket {tkt} not found.")
            continue
        
        pos = p[0]
        symbol = pos.symbol
        volume = pos.volume
        pos_type = pos.type # 0=BUY, 1=SELL
        
        # Determine opposite order type
        order_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print(f"Failed to get tick for {symbol}")
            continue
            
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        
        # Attempt close using risk-gated ActionLayer
        from gitagent_action_layer import get_action_layer
        from gitagent_types import SmartTradeRequest
        req = SmartTradeRequest(
            symbol=symbol,
            side=order_type,
            volume=volume,
            comment="HARD_CLOSE_OUTLIER",
            position_ticket=pos.ticket
        )
        result = get_action_layer().execute_smart_trade(req)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"SUCCESS: Closed Ticket {tkt}")
        else:
            err_msg = result.comment if result else "No Result"
            err_code = result.retcode if result else -1
            print(f"FAILED: Ticket {tkt} | {err_code}: {err_msg}")

    
    mt5.shutdown()

if __name__ == "__main__":
    hard_close()

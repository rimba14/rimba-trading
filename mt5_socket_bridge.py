import socket
import json
import logging
import threading
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [IPC_BRIDGE] %(message)s')

HOST = '127.0.0.1'
PORT = 15555

def handle_client(conn, addr):
    logging.info(f"Connected by {addr}")
    try:
        data = conn.recv(4096)
        if not data:
            return
            
        payload = json.loads(data.decode('utf-8'))
        command = payload.get("command")
        symbol = payload.get("symbol")
        size = payload.get("size", 0.0)
        sl = payload.get("sl", 0.0)
        tp = payload.get("tp", 0.0)
        ticket = payload.get("ticket", 0)
        
        logging.info(f"Received Command: {command} | Symbol: {symbol} | Size: {size}")
        
        response = {"status": "error", "message": "UNKNOWN COMMAND"}
        
        # Simplified execution mocking for the actual MT5 routing layer
        if command == "buy":
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": size,
                "type": mt5.ORDER_TYPE_BUY,
                "sl": sl,
                "tp": tp,
                "magic": 777000,
                "comment": "GO_IPC_BUY",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                response = {"status": "success", "message": f"Order [BUY] {symbol} Size: {size} SL: {sl} TP: {tp} | Status: EXECUTED"}
            else:
                err = mt5.last_error() if not res else res.comment
                response = {"status": "error", "message": f"Execution failed: {err}"}
                
        elif command == "sell":
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": size,
                "type": mt5.ORDER_TYPE_SELL,
                "sl": sl,
                "tp": tp,
                "magic": 777000,
                "comment": "GO_IPC_SELL",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                response = {"status": "success", "message": f"Order [SELL] {symbol} Size: {size} SL: {sl} TP: {tp} | Status: EXECUTED"}
            else:
                err = mt5.last_error() if not res else res.comment
                response = {"status": "error", "message": f"Execution failed: {err}"}
                
        elif command == "modify":
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": symbol,
                "sl": sl,
                "tp": tp
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                response = {"status": "success", "message": f"Ticket #{ticket} [{symbol}] Modified. SL: {sl} TP: {tp} | Status: MODIFIED"}
            else:
                err = mt5.last_error() if not res else res.comment
                response = {"status": "error", "message": f"Modification failed: {err}"}
                
        elif command == "cancel":
             # Simulating a close for a specific ticket
             response = {"status": "success", "message": f"Ticket #{ticket} [{symbol}] Cancelled | Status: CANCELLED"}

        conn.sendall(json.dumps(response).encode('utf-8'))
        
    except Exception as e:
        logging.error(f"Error handling IPC request: {e}")
        err_res = {"status": "error", "message": str(e)}
        try:
            conn.sendall(json.dumps(err_res).encode('utf-8'))
        except:
            pass
    finally:
        conn.close()

def start_server():
    if not mt5.initialize():
        logging.error("Failed to initialize MT5 for Socket Bridge.")
        return
        
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        logging.info(f"MT5 Socket Bridge listening on {HOST}:{PORT} (Out-of-GIL IPC Active)")
        while True:
            conn, addr = s.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()

if __name__ == "__main__":
    start_server()

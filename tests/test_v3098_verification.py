import os
import sys
import pytest
from unittest import mock

sys.path.insert(0, r"C:\Sentinel_Project")
os.chdir(r"C:\Sentinel_Project")

import pre_execution_gate as peg
import MetaTrader5 as mt5

class MockPosition:
    def __init__(self, ticket, symbol, type_, price_open, sl=0.0, tp=0.0, volume=0.01, profit=10.0, time=123456, magic=142):
        self.ticket = ticket
        self.symbol = symbol
        self.type = type_
        self.price_open = price_open
        self.sl = sl
        self.tp = tp
        self.volume = volume
        self.profit = profit
        self.time = time
        self.magic = magic

class MockOrder:
    def __init__(self, ticket, symbol, type_, magic=142):
        self.ticket = ticket
        self.symbol = symbol
        self.type = type_
        self.magic = magic

def get_mock_symbol_info(symbol):
    m = mock.Mock()
    m.digits = 5
    m.trade_contract_size = 100000.0
    m.volume_step = 0.01
    m.volume_min = 0.01
    m.trade_stops_level = 10
    m.point = 0.00001
    m.spread = 2
    m.trade_tick_size = 0.00001
    return m

def test_gate0_allow():
    mock_positions = [
        MockPosition(1, "BTCUSD", 0, 50000.0), # BUY (type 0)
        MockPosition(2, "USDCAD", 1, 1.3500)   # RISK_OFF
    ]
    mock_orders = []
    
    with mock.patch("pre_execution_gate.mt5.positions_get", return_value=mock_positions), \
         mock.patch("pre_execution_gate.mt5.orders_get", return_value=mock_orders), \
         mock.patch("pre_execution_gate.mt5.initialize", return_value=True):
        
        res = peg.gate0_correlation_cluster_limit("ETHUSD", "SELL")
        assert res.status == peg.ALLOW

def test_gate0_global_cap_reached():
    mock_positions = [
        MockPosition(1, "BTCUSD", 0, 50000.0),
        MockPosition(2, "SP500", 0, 4000.0),
        MockPosition(3, "GBPJPY", 1, 180.0)
    ]
    mock_orders = []
    
    with mock.patch("pre_execution_gate.mt5.positions_get", return_value=mock_positions), \
         mock.patch("pre_execution_gate.mt5.orders_get", return_value=mock_orders), \
         mock.patch("pre_execution_gate.mt5.initialize", return_value=True):
        
        res = peg.gate0_correlation_cluster_limit("ETHUSD", "BUY")
        assert res.status == peg.BLOCK
        assert res.gate == "GATE-0-GLOBAL-CONTAGION"

def test_gate0_cluster_limit():
    mock_positions = [
        MockPosition(1, "BTCUSD", 0, 50000.0),
        MockPosition(2, "ETHUSD", 1, 3000.0)
    ]
    mock_orders = []
    
    with mock.patch("pre_execution_gate.mt5.positions_get", return_value=mock_positions), \
         mock.patch("pre_execution_gate.mt5.orders_get", return_value=mock_orders), \
         mock.patch("pre_execution_gate.mt5.initialize", return_value=True):
         
        res = peg.gate0_correlation_cluster_limit("SOLUSD", "BUY")
        assert res.status == peg.BLOCK
        assert "limit reached" in res.message

def test_gate0_same_direction():
    mock_positions = [
        MockPosition(1, "BTCUSD", 0, 50000.0)
    ]
    mock_orders = []
    
    with mock.patch("pre_execution_gate.mt5.positions_get", return_value=mock_positions), \
         mock.patch("pre_execution_gate.mt5.orders_get", return_value=mock_orders), \
         mock.patch("pre_execution_gate.mt5.initialize", return_value=True):
         
        res = peg.gate0_correlation_cluster_limit("SP500", "BUY")
        assert res.status == peg.BLOCK
        assert res.gate == "GATE-0-SAME-DIRECTION"


import json
import os

class SentinelFactChecker:
    def __init__(self, palace_db="C:\\Sentinel_Project\\sentinel_palace_graph.json"):
        self.palace_db = palace_db
        self.palace = self._load_palace()

    def _load_palace(self):
        if os.path.exists(self.palace_db):
            with open(self.palace_db, 'r', encoding='utf-8') as f: return json.load(f)
        return {}

    def verify_signal(self, symbol: str, regime: int, score: float) -> float:
        """Verify signal against the Palace knowledge halls. Returns TPS adjustment."""
        if not self.palace: return 0.0
        
        adjustment = 0.0
        
        # 1. Check Hall of Drawdowns
        fail_room = f"room_{symbol}_failures"
        failures = self.palace.get('halls', {}).get('hall_drawdowns', {}).get('rooms', {}).get(fail_room, [])
        
        if len(failures) > 3:
            print(f"[FACT_CHECK] 🔴 TOXIC CLUSTER FOUND: {symbol} has high failure density in Palace.")
            adjustment -= 0.15
            
        # 2. Check Asset Confidence Wing
        asset_info = self.palace.get('wings', {}).get('wing_assets', {}).get(symbol, {})
        if asset_info.get('net_pnl', 0) < -50:
            print(f"[FACT_CHECK] 🟡 {symbol} is currently in the 'Purgatory' floor of the Palace.")
            adjustment -= 0.10
        
        return adjustment

if __name__ == "__main__":
    checker = SentinelFactChecker()
    adj = checker.verify_signal("XAUUSD", 1, 0.85)
    print(f"[FACT_CHECK] Test Adjustment: {adj:.2f}")

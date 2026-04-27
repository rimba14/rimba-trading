import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

PALACE_DB = "C:\\Sentinel_Project\\sentinel_palace_graph.json"
PALACE_MD = "C:\\Sentinel_Project\\SENTINEL_PALACE.md"

class SentinelPalace:
    def __init__(self):
        self.palace = self._load_palace()

    def _load_palace(self):
        if os.path.exists(PALACE_DB):
            with open(PALACE_DB, 'r', encoding='utf-8') as f: return json.load(f)
        return {
            "wings": {
                "wing_assets": {},
                "wing_risk": {},
                "wing_strategy": {}
            },
            "halls": {
                "hall_regimes": {"rooms": {}},
                "hall_drawdowns": {"rooms": {}},
                "hall_forensics": {"rooms": {}}
            },
            "meta": {"last_reconstruction": 0}
        }

    def save_palace(self):
        with open(PALACE_DB, 'w', encoding='utf-8') as f:
            json.dump(self.palace, f, indent=2)

    def crystallize_trade(self, trade: Dict[str, Any]):
        """Place a trade memory into the exact room/hall for 34% better retrieval"""
        sym = trade['symbol']
        regime = trade.get('regime', 0)
        outcome = trade.get('outcome', 'UNKNOWN')
        pnl = trade.get('pnl_dollars', 0)
        
        # v142 Foundation Model Telemetry Autopsy
        telemetry = {
            "kronos_prob": trade.get('kronos_prob', 0.5),
            "tfm_held": trade.get('tfm_held', True),
            "hmm_state": trade.get('hmm_state', 'RANGE'),
            "oracle_accuracy": (trade.get('kronos_prob', 0.5) > 0.5 and outcome == "WIN") or 
                               (trade.get('kronos_prob', 0.5) < 0.5 and outcome == "LOSS")
        }
        
        # 1. Update WING: Assets
        if sym not in self.palace['wings']['wing_assets']:
            self.palace['wings']['wing_assets'][sym] = {"confidence": 0.5, "net_pnl": 0, "salience": 0.5, "telemetry_log": []}
        
        asset_wing = self.palace['wings']['wing_assets'][sym]
        asset_wing['net_pnl'] += pnl
        if 'telemetry_log' not in asset_wing: asset_wing['telemetry_log'] = []
        asset_wing['telemetry_log'].append(telemetry)
        
        # AgentRecall Salience: recency(0.3) + importance(0.1) + connections(0.2)
        asset_wing['salience'] = min(1.0, 0.3*(time.time()/1e9) + 0.1*(abs(pnl)/100) + 0.5) 
        asset_wing['confidence'] = min(1.0, asset_wing['confidence'] + 0.01)

        # 2. Update HALL: Regimes (Specific Room for this Regime)
        regime_room = f"regime_{regime}"
        if regime_room not in self.palace['halls']['hall_regimes']['rooms']:
            self.palace['halls']['hall_regimes']['rooms'][regime_room] = {"total_trades": 0, "win_rate": 0, "oracle_score": 0.0}
        
        room = self.palace['halls']['hall_regimes']['rooms'][regime_room]
        room['total_trades'] += 1
        # Track oracle accuracy per regime
        if telemetry['oracle_accuracy']:
            room['oracle_score'] = (room.get('oracle_score', 0.0) * (room['total_trades']-1) + 1.0) / room['total_trades']
        
        # 3. Update HALL: Drawdowns (If Toxic)
        if outcome == "LOSS" and pnl < -15:
            fail_room = f"room_{sym}_failures"
            if fail_room not in self.palace['halls']['hall_drawdowns']['rooms']:
                self.palace['halls']['hall_drawdowns']['rooms'][fail_room] = []
            
            self.palace['halls']['hall_drawdowns']['rooms'][fail_room].append({
                "pnl": pnl, "time": time.time(), "type": "SL_Wick", "telemetry": telemetry
            })

        self.palace['meta']['last_reconstruction'] = time.time()

    def generate_palace_view(self):
        """Visual representation of the Memory Palace"""
        with open(PALACE_MD, "w", encoding='utf-8') as f:
            f.write("# 🏛️ THE SENTINEL PALACE (Spatial Memory v1.0)\n")
            f.write(f"*Last Reconstruction: {datetime.now(timezone.utc).isoformat()}*\n\n")
            
            f.write("## 🏗️ WING: Assets ⛓️\n")
            # Sort by Salience (AgentRecall logic)
            sorted_assets = sorted(self.palace['wings']['wing_assets'].items(), key=lambda x: x[1].get('salience', 0), reverse=True)
            for sym, data in sorted_assets:
                f.write(f"- **{sym}**: Salience: {data.get('salience', 0):.2f} | Conf: {data['confidence']:.2f} | Net: ${data['net_pnl']:.2f}\n")
            
            f.write("\n## 🛣️ HALL: Regimes 📉\n")
            for room, data in self.palace['halls']['hall_regimes']['rooms'].items():
                f.write(f"- **{room}**: Total Conduction events: {data['total_trades']}\n")

            f.write("\n## 💀 HALL: Drawdowns (Toxic Memory) ☢️\n")
            for room, data in self.palace['halls']['hall_drawdowns']['rooms'].items():
                f.write(f"- **{room}**: {len(data)} documented failures. 🟡\n")

if __name__ == "__main__":
    palace = SentinelPalace()
    # Mocking one crystallization pass
    palace.crystallize_trade({"symbol": "XAUUSD", "outcome": "LOSS", "pnl_dollars": -25.2, "regime": 1})
    palace.generate_palace_view()
    palace.save_palace()
    print("[PALACE] Spatial reconstruction successful.")

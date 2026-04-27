from execution_logic import PolyExecutionAgent
from noaa_mexico_adapter import NOAAMexicoAdapter
from accuweather_adapter import AccuWeatherAdapter
from open_meteo_adapter import OpenMeteoAdapter
import time
import os

class MexicoWeatherStrategy:
    """
    Implements: Buy NO at $5.5 -> Flip to YES when NOAA, AccuWeather & Open-Meteo agree.
    Target Market: Mexico City Highest Temp (21C+)
    """
    def __init__(self):
        # Market: Will the highest temperature in Mexico City be 21°C or higher on April 24?
        self.yes_token = "34126062999425736948029384257632445347548239157449010449157184364086557615775"
        self.no_token = "17944529757142138818442022713093530061624279168288060812506304230559869068518"
        self.temp_threshold = 21.0
        
        self.noaa = NOAAMexicoAdapter()
        self.accu = AccuWeatherAdapter()
        self.meteo = OpenMeteoAdapter()
        self.executor = PolyExecutionAgent()
        
        self.current_state = "IDLE"
        
    def check_consensus(self):
        print(f"\n🔄 [CONSENSUS] Auditing Mexico City Weather Consensus...")
        
        t1 = self.noaa.get_latest_temp()
        t2 = self.accu.get_daily_high()
        t3 = self.meteo.get_daily_high()
        
        results = [t1, t2, t3]
        valid_results = [r for r in results if r is not None]
        
        if len(valid_results) < 3:
            print("⚠️ [CONSENSUS] Data incomplete. 3/3 required for flip.")
            return False
            
        consensus = all(t >= self.temp_threshold for t in valid_results)
        
        if consensus:
            print(f"🚀 [CONSENSUS] YES DETECTED: {t1}C, {t2}C, {t3}C all >= {self.temp_threshold}C.")
        else:
            print("⚖️ [CONSENSUS] Mixed or Below Threshold. Remaining in NO bias.")
            
        return consensus

    def run_cycle(self):
        # 1. Initial State: Establish NO position
        if self.current_state == "IDLE":
            print(f"📉 [STARTUP] Buying NO for $5.50 USD as base position...")
            # Using $5.50 to clear the 5-token minimum size requirement
            self.executor.place_order(
                token_id=self.no_token,
                side="BUY",
                amount_usd=5.5,
                limit_price=0.99 
            )
            self.current_state = "HOLDING_NO"
            
        # 2. Monitor for Flip
        if self.current_state == "HOLDING_NO":
            if self.check_consensus():
                print("💥 [FLIP] Consensus Reached! Liquidating NO and going LONG YES!")
                
                # 1. SDK-based Cancellation
                self.executor.cancel_all_orders()
                
                # 2. Market Buy YES (Spend $5.50)
                self.executor.place_order(
                    token_id=self.yes_token,
                    side="BUY",
                    amount_usd=5.5,
                    limit_price=0.99
                )
                self.current_state = "HOLDING_YES"
        
        elif self.current_state == "HOLDING_YES":
            print("✅ [STATUS] YES position established. Monitoring for next cycle or resolution.")

if __name__ == "__main__":
    strat = MexicoWeatherStrategy()
    while True:
        strat.run_cycle()
        print("\n💤 Sleeping for 900s...")
        time.sleep(900)

from execution_logic import PolyExecutionAgent
from weather_perception import WeatherConsensusOracle
from noaa_adapter import NOAAStationAdapter
from probabilistic_arb_engine import ProbabilisticArbEngine
import time

class WeatherStrategyAgent:
    """
    Implements the "Buy NO @ 20.9c -> Flip to YES on 3/3 consensus" strategy.
    """
    def __init__(self, yes_token, no_token, lat, lon, station_id="KJFK"):
        self.yes_token = yes_token
        self.no_token = no_token
        self.oracle = WeatherConsensusOracle(lat, lon)
        self.noaa_station = NOAAStationAdapter(station_id)
        self.arb_engine = ProbabilisticArbEngine()
        self.executor = PolyExecutionAgent()
        self.current_state = "IDLE"
        self.no_price_threshold = 0.209 # 20.9 cents
        
    def run_strategy_cycle(self):
        print(f"\n🌀 [STRATEGY] Auditing Weather Market Consensus...")
        
        # 1. Physical Layer: Triple Agreement + Station Check
        is_consensus_yes = self.oracle.check_triple_agreement("rain")
        station_data = self.noaa_station.get_latest_observations()
        
        # 2. Cognition Layer: Calculate Bias
        physical_prob = 0.95 if is_consensus_yes else 0.05
        precip = station_data.get('precipitation_last_hour') if station_data else 0
        if precip and precip > 0:
            physical_prob = max(physical_prob, 0.80)


        # Mock market price for bias calculation (in production, fetch from CLOB)
        market_price = 0.25 
        recommendation, score = self.arb_engine.calculate_bias(physical_prob, market_price)
        print(f"🧠 [BIAS] Recommendation: {recommendation} (Confidence: {score:.2f})")

        if recommendation != "BULLISH_ARBITRAGE":
            # Strategy: Maintain NO bias
            if self.current_state != "HOLDING_NO":
                print(f"📉 [BIAS] Risk-off. Establishing NO position at {self.no_price_threshold*100:.1f}c...")
                # v142: Using the 5-token exchange floor
                min_amount = 5.0 * self.no_price_threshold
                self.executor.place_order(
                    token_id=self.no_token,
                    side="BUY",
                    amount_usd=max(0.01, min_amount),
                    limit_price=self.no_price_threshold
                )
                self.current_state = "HOLDING_NO"
        else:
            # BULLISH ARBITRAGE: Physical Reality > Market Price
            if self.current_state == "HOLDING_NO":
                print("💥 [FLIP] Arbitrage Detected! Liquidating NO and going LONG YES!")
                # 1. SDK-based Cancellation
                self.executor.cancel_all_orders()
                
                # 2. Market Buy YES
                # v142: Using the 5-token exchange floor
                min_amount = 5.0 * 0.99
                self.executor.place_order(
                    token_id=self.yes_token,
                    side="BUY",
                    amount_usd=max(0.02, min_amount),
                    limit_price=0.99
                )
                self.current_state = "HOLDING_YES"


if __name__ == "__main__":
    # Test for NY Rain contract
    strat = WeatherStrategyAgent("NY_RAIN_APR17", 40.7128, -74.0060)
    # Manual cycle trigger
    strat.run_strategy_cycle()

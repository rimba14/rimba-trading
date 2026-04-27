
import os

# --- Directive 2: Define Mock Scenario ---
ACCOUNT_BALANCE = 1000.00
SYMBOL = "XAUUSD"
KRONOS_PROB = 0.85
KELLY_FRACTION = 0.25
MAX_RISK_CAP = 0.02
STOP_LOSS_PIPS = 50.0

# In MT5, 1.0 lot of Gold with a 50-pip stop has a specific dollar risk.
# For XAUUSD, 1.0 lot = 100 ounces. 
# 1 pip (0.01 price move) = $1.00 per lot.
# 50 pips = $50.00 per lot.
PIP_VALUE_PER_LOT = 1.0  # For 1.0 lot, 1 pip change = $1.00 USD

def run_simulation():
    print("="*60)
    print(f" ADAPTIVE SENTINEL v15.0 - RISK SIMULATION (Offline)")
    print("="*60)
    print(f"[*] Account Balance: ${ACCOUNT_BALANCE:,.2f}")
    print(f"[*] Asset:           {SYMBOL}")
    print(f"[*] AI Conviction:   {KRONOS_PROB:.2%}")
    print(f"[*] Stop Loss:       {STOP_LOSS_PIPS} pips")
    print("-" * 60)

    # --- Directive 3: Recreate Phase 4 Math ---
    
    # 1. Calculate q (Probability of loss)
    p = KRONOS_PROB
    q = 1.0 - p
    
    # 2. Assume b = 1.0 (1:1 Risk/Reward Baseline)
    b = 1.0
    
    # 3. Calculate Full Kelly (F_Star_Raw)
    # f* = p - (q/b)
    f_star_raw = p - (q / b)
    
    # 4. Calculate Adjusted Kelly (F_Star_Adj)
    f_star_adj = f_star_raw * KELLY_FRACTION
    
    # 5. Apply Hard Risk Cap (MAX_RISK_CAP)
    is_capped = f_star_adj > MAX_RISK_CAP
    final_risk_percent = min(max(0, f_star_adj), MAX_RISK_CAP)
    
    # 6. Calculate Exact Dollar Risk
    dollar_risk = ACCOUNT_BALANCE * final_risk_percent
    
    # 7. Calculate Simulated Lot Size
    # Risk = Lots * Stop_Pips * Pip_Value
    # Lots = Risk / (Stop_Pips * Pip_Value)
    simulated_lots = dollar_risk / (STOP_LOSS_PIPS * PIP_VALUE_PER_LOT + 1e-12)
    
    # Round to standard broker step (0.01)
    rounded_lots = round(simulated_lots, 2)

    # --- Directive 4: Print the Receipt ---
    print(f"[1] Raw Kelly Output:     {f_star_raw:.2%} (Theoretical Max Risk)")
    print(f"[2] Fractional Scaling:   {f_star_adj:.2%} (Quarter-Kelly Protection)")
    
    if is_capped:
        print(f"[3] Safety Intervention:  YES - CLAMPED TO {MAX_RISK_CAP:.2%} HARD CAP")
    else:
        print(f"[3] Safety Intervention:  NO - WITHIN SAFETY BOUNDS")
        
    print("-" * 60)
    print(f"[4] FINAL RISK BUDGET:    {final_risk_percent:.2%} of Account")
    print(f"[5] TOTAL DOLLAR RISK:    ${dollar_risk:.2f}")
    print(f"[6] CALCULATED VOLUME:    {rounded_lots:.2f} Lots")
    print("-" * 60)
    
    print(f"SUMMARY: The system converted an aggressive {f_star_raw:.1%} raw bet into")
    print(f"a surgical {final_risk_percent:.1%} execution. Your account survived.")
    print("="*60)

if __name__ == "__main__":
    run_simulation()

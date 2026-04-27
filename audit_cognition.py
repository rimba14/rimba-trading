import json
import pandas as pd
from tabulate import tabulate
import os

def audit_cognition():
    log_path = r"C:\Sentinel_Project\cognition_bridge.json"
    
    if not os.path.exists(log_path):
        print(f"[ERROR] {log_path} not found. Run create_dummy_audit.py first.")
        return

    try:
        with open(log_path, 'r') as f:
            data = json.load(f)
        
        # Handle new format with profiles and ledger
        if isinstance(data, dict) and 'ledger' in data:
            ledger_data = data['ledger']
        else:
            ledger_data = data

        if not ledger_data:
            print("[INFO] Cognition ledger is empty.")
            return

        df = pd.DataFrame(ledger_data)
        
        # Format for display
        display_df = df.copy()
        
        # Convert final_p and f_star to percentages
        display_df['final_p'] = (display_df['final_p'] * 100).map('{:,.1f}%'.format)
        display_df['f_star'] = (display_df['f_star'] * 100).map('{:,.2f}%'.format)
        
        # Add a visual indicator for Legend Overrides
        display_df['legend_active'] = display_df['legend_active'].apply(lambda x: "YES" if x else "NO")
        
        print("\n" + "="*80)
        print("SENTINEL COGNITION AUDIT LEDGER")
        print("="*80)
        
        print(tabulate(display_df, headers='keys', tablefmt='psql', showindex=False))
        
        print("\n[SUMMARY]")
        print(f"Total Events: {len(df)}")
        print(f"Legend Overrides: {len(df[df['legend_active'] == True])}")
        print(f"Average Conviction: {(df['final_p'].mean()*100):.1f}%")
        print("="*80 + "\n")

    except Exception as e:
        print(f"[ERROR] Failed to audit cognition: {e}")

if __name__ == "__main__":
    audit_cognition()

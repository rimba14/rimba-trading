import pandas as pd
from deepchecks.tabular.suites import train_test_validation
from deepchecks.tabular import Dataset
import os

class SentinelDashboard:
    def __init__(self):
        self.dashboard_path = "C:\\Sentinel_Project\\SENTINEL_DASHBOARD.html"

    def generate_live_drift_report(self, reference_df: pd.DataFrame, current_df: pd.DataFrame):
        """Phase 172: Deepchecks-based Dashboard (Python 3.14 Compatible)"""
        if reference_df.empty or current_df.empty: return
        
        # Prepare Deepchecks Datasets
        ref_ds = Dataset(reference_df, label=None, cat_features=[])
        cur_ds = Dataset(current_df, label=None, cat_features=[])
        
        # Run Train-Test Validation Suite (Includes Drift & Distribution checks)
        suite = train_test_validation()
        result = suite.run(ref_ds, cur_ds)
        
        # Export Visual Report
        result.save_as_html(self.dashboard_path)
        
        # Heuristic Drift Score extraction
        # We check for 'Feature Drift' pass status
        drift_passed = True
        for check_result in result.get_not_passed_checks():
            if "Drift" in check_result.check.name():
                drift_passed = False
                break
                
        return 0.0 if drift_passed else 0.5

if __name__ == "__main__":
    # Test pass
    ref = pd.DataFrame({"val": [1, 2, 3, 4, 5], "vol": [10, 11, 10, 12, 11]})
    cur = pd.DataFrame({"val": [1.1, 2.1, 3.2, 4.0, 5.1], "vol": [10, 11, 10, 12, 11]})
    dash = SentinelDashboard()
    score = dash.generate_live_drift_report(ref, cur)
    print(f"[DASHBOARD] Deepchecks report generated: {dash.dashboard_path} (Score: {score})")

import pandas as pd
from deepchecks.tabular import Dataset
from deepchecks.tabular.suites import data_integrity, train_test_validation
import os

class SentinelValidator:
    def __init__(self):
        self.report_path = "C:\\Sentinel_Project\\SENTINEL_INTEGRITY_REPORT.html"

    def validate_price_data(self, df: pd.DataFrame):
        """Phase 171: Deepchecks Data Integrity Suite"""
        if df.empty: return False
        
        # Convert to Deepchecks Dataset
        ds = Dataset(df, label=None, cat_features=[])
        
        # Run Integrity Suite
        suite = data_integrity()
        result = suite.run(ds)
        
        # Export for institutional audit
        result.save_as_html(self.report_path)
        
        # Return boolean based on critical failures
        # Simple heuristic: if we have more than 2 failed checks, signal a caution
        return len(result.get_not_passed_checks()) < 2

if __name__ == "__main__":
    # Test with dummy data
    test_data = pd.DataFrame({"close": [1.1, 1.2, 1.15], "volume": [100, 200, 150]})
    validator = SentinelValidator()
    passed = validator.validate_price_data(test_data)
    print(f"[VALIDATOR] Data Integrity Pass: {passed}")

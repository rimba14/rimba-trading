import sys
sys.path.append('C:/Sentinel_Project')
from sentinel_slow_loop import fetch_and_calculate_raw_features
import MetaTrader5 as mt5
mt5.initialize()
prep_data = fetch_and_calculate_raw_features('EURUSD')
df_ml = prep_data['df_ml']
print('df_ml columns:', df_ml.columns.tolist())
import xgboost as xgb
xgb_model = xgb.Booster()
xgb_model.load_model('C:/Sentinel_Project/data/sentinel_xgb_model.json')
missing = [c for c in xgb_model.feature_names if c not in df_ml.columns]
print('Missing features:', missing)

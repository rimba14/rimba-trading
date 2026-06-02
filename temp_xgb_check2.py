import sys
sys.path.append('C:/Sentinel_Project')
from sentinel_slow_loop import fetch_and_calculate_raw_features
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import xgboost as xgb

mt5.initialize()
prep_data = fetch_and_calculate_raw_features('EURUSD')
df_ml = prep_data['df_ml']

xgb_model = xgb.Booster()
xgb_model.load_model('C:/Sentinel_Project/data/sentinel_xgb_model.json')

latest_features = df_ml.tail(1).copy()
cols = []
for col in xgb_model.feature_names:
    if col in latest_features.columns:
        cols.append(latest_features[col])
    else:
        cols.append(pd.Series([0.0], index=latest_features.index, name=col))
latest_features = pd.concat(cols, axis=1)
latest_features.columns = xgb_model.feature_names

dmat = xgb.DMatrix(latest_features)
pred = xgb_model.predict(dmat)[0]

print('XGB Prediction:', pred)
print('XGB Feature Values:')
print(latest_features.iloc[0])

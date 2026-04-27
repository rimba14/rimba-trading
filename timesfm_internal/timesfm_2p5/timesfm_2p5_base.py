# TimesFM 2p5 base implementation
import dataclasses
import collections
import numpy as np
from .. import configs

def strip_leading_nans(arr):
  isnan = np.isnan(arr)
  if not np.any(~isnan): return np.array([])
  first_valid_index = np.argmax(~isnan)
  return arr[first_valid_index:]

def linear_interpolation(arr):
  nans = np.isnan(arr)
  if not np.any(nans): return arr
  def x(z): return z.nonzero()[0]
  nans_indices = x(nans); non_nans_indices = x(~nans); non_nans_values = arr[~nans]
  try: arr[nans] = np.interp(nans_indices, non_nans_indices, non_nans_values)
  except: mu = np.nanmean(arr) if non_nans_values.size > 0 else 0.0; arr = np.where(np.isfinite(arr), arr, mu)
  return arr

@dataclasses.dataclass(frozen=True)
class TimesFM_2p5_200M_Definition:
  context_limit = 16384
  input_patch_len: int = 32
  output_patch_len: int = 128
  output_quantile_len: int = 1024
  quantiles: list[float] = dataclasses.field(default_factory=lambda: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
  decode_index: int = 5
  tokenizer: configs.ResidualBlockConfig = configs.ResidualBlockConfig(64, 1280, 1280, True, "swish")
  stacked_transformers: configs.StackedTransformersConfig = configs.StackedTransformersConfig(20, configs.TransformerConfig(1280, 1280, 16, "rms", "rms", "rms", False, True, "swish", True))
  output_projection_point: configs.ResidualBlockConfig = configs.ResidualBlockConfig(1280, 1280, 1280, False, "swish")
  output_projection_quantiles: configs.ResidualBlockConfig = configs.ResidualBlockConfig(1280, 1280, 10240, False, "swish")

class TimesFM_2p5:
  forecast_config: configs.ForecastConfig | None = None
  compiled_decode = None; global_batch_size: int = 0
  def forecast(self, horizon, inputs):
    if self.compiled_decode is None: raise RuntimeError("Not compiled")
    context = self.forecast_config.max_context; num_inputs = len(inputs)
    if (w := num_inputs % self.global_batch_size) != 0: inputs += [np.array([0.0]*3)] * (self.global_batch_size - w)
    output_points = []; output_quantiles = []; values = []; masks = []; idx = 0
    for each_input in inputs:
      value = linear_interpolation(strip_leading_nans(np.array(each_input)))
      if (w := len(value)) >= context: value = value[-context:]; mask = np.zeros_like(value, dtype=bool)
      else: mask = np.array([True]*(context-w) + [False]*w); value = np.pad(value, (context-w, 0), "constant")
      values.append(value); masks.append(mask); idx += 1
      if idx == self.global_batch_size:
        idx = 0; point_forecast, quantile_forecast = self.compiled_decode(horizon, values, masks)
        output_points.append(point_forecast); output_quantiles.append(quantile_forecast)
        values = []; masks = []
    output_points = np.concatenate(output_points, axis=0); output_quantiles = np.concatenate(output_quantiles, axis=0)
    return output_points[:num_inputs], output_quantiles[:num_inputs]

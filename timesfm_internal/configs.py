# Reconstructed configs.py for TimesFM 2.5
import dataclasses
from typing import Literal

@dataclasses.dataclass(frozen=True)
class ForecastConfig:
  max_context: int = 0
  max_horizon: int = 0
  normalize_inputs: bool = False
  window_size: int = 0
  per_core_batch_size: int = 1
  use_continuous_quantile_head: bool = False
  force_flip_invariance: bool = True
  infer_is_positive: bool = True
  fix_quantile_crossing: bool = False
  return_backcast: bool = False

@dataclasses.dataclass(frozen=True)
class ResidualBlockConfig:
  input_dims: int
  hidden_dims: int
  output_dims: int
  use_bias: bool
  activation: Literal["relu", "swish", "none"]

@dataclasses.dataclass(frozen=True)
class RandomFourierFeaturesConfig:
  input_dims: int
  output_dims: int
  projection_stddev: float
  use_bias: bool

@dataclasses.dataclass(frozen=True)
class TransformerConfig:
  model_dims: int
  hidden_dims: int
  num_heads: int
  attention_norm: Literal["rms"]
  feedforward_norm: Literal["rms"]
  qk_norm: Literal["rms", "none"]
  use_bias: bool
  use_rotary_position_embeddings: bool
  ff_activation: Literal["relu", "swish", "none"]
  fuse_qkv: bool

@dataclasses.dataclass(frozen=True)
class StackedTransformersConfig:
  num_layers: int
  transformer: TransformerConfig

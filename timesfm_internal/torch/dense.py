# Dense layers for TimesFM
import torch
from torch import nn
from .. import configs

class ResidualBlock(nn.Module):
  def __init__(self, config: configs.ResidualBlockConfig):
    super().__init__()
    self.config = config
    self.hidden_layer = nn.Linear(in_features=config.input_dims, out_features=config.hidden_dims, bias=config.use_bias)
    self.output_layer = nn.Linear(in_features=config.hidden_dims, out_features=config.output_dims, bias=config.use_bias)
    self.residual_layer = nn.Linear(in_features=config.input_dims, out_features=config.output_dims, bias=config.use_bias)
    if config.activation == "relu": self.activation = nn.ReLU()
    elif config.activation == "swish": self.activation = nn.SiLU()
    elif config.activation == "none": self.activation = nn.Identity()
    else: raise ValueError(f"Activation: {config.activation} not supported.")
  def forward(self, x: torch.Tensor) -> torch.Tensor:
    return self.output_layer(self.activation(self.hidden_layer(x))) + self.residual_layer(x)

class RandomFourierFeatures(nn.Module):
  def __init__(self, config: configs.RandomFourierFeaturesConfig):
    super().__init__()
    self.config = config
    if config.output_dims % 4 != 0: raise ValueError(f"Output dims must be a multiple of 4: {config.output_dims} % 4 != 0.")
    num_projected_features = config.output_dims // 4
    self.phase_shifts = nn.Parameter(torch.zeros(2, num_projected_features))
    self.projection_layer = nn.Linear(in_features=config.input_dims, out_features=num_projected_features, bias=config.use_bias)
    self.residual_layer = nn.Linear(in_features=config.input_dims, out_features=config.output_dims, bias=config.use_bias)
  def forward(self, x: torch.Tensor) -> torch.Tensor:
    projected = self.projection_layer(x)
    cos_features = torch.cos(projected)
    sin_features = torch.sin(projected)
    sq_wave_1 = torch.sign(torch.sin(projected + self.phase_shifts[0, :]))
    sq_wave_2 = torch.sign(torch.sin(projected + self.phase_shifts[1, :]))
    fourier_features = torch.cat([cos_features, sin_features, sq_wave_1, sq_wave_2], dim=-1)
    residual = self.residual_layer(x)
    return fourier_features + residual

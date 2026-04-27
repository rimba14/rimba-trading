# Normalization layers for TimesFM
import torch
from torch import nn

class RMSNorm(nn.Module):
  def __init__(self, num_features: int, *, epsilon: float = 1e-6):
    super().__init__()
    self.scale = nn.Parameter(torch.zeros(num_features))
    self.num_features = num_features
    self.epsilon = epsilon
  def forward(self, inputs: torch.Tensor) -> torch.Tensor:
    var = torch.mean(torch.square(inputs), dim=-1, keepdim=True)
    normed_inputs = inputs * torch.rsqrt(var + self.epsilon)
    normed_inputs = normed_inputs * self.scale
    return normed_inputs

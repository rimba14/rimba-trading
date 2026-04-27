# Utility functions for TimesFM
import dataclasses
import torch
_TOLERANCE = 1e-6

@dataclasses.dataclass(frozen=False)
class DecodeCache:
  next_index: torch.Tensor
  num_masked: torch.Tensor
  key: torch.Tensor
  value: torch.Tensor

def update_running_stats(n, mu, sigma, x, mask):
  is_legit = torch.logical_not(mask)
  inc_n = torch.sum(is_legit.to(x.dtype), dim=-1)
  inc_mu_numerator = torch.sum(x * is_legit, dim=-1)
  inc_n_safe = torch.where(inc_n == 0, 1.0, inc_n)
  inc_mu = inc_mu_numerator / inc_n_safe
  inc_mu = torch.where(inc_n == 0, 0.0, inc_mu)
  inc_var_numerator = torch.sum(((x - inc_mu.unsqueeze(-1)) ** 2) * is_legit, dim=-1)
  inc_var = inc_var_numerator / inc_n_safe
  inc_var = torch.where(inc_n == 0, 0.0, inc_var)
  inc_sigma = torch.sqrt(inc_var)
  new_n = n + inc_n
  new_n_safe = torch.where(new_n == 0, 1.0, new_n)
  new_mu = (n * mu + inc_mu * inc_n) / new_n_safe
  new_mu = torch.where(new_n == 0, 0.0, new_mu)
  term1 = n * sigma.pow(2); term2 = inc_n * inc_sigma.pow(2)
  term3 = n * (mu - new_mu).pow(2); term4 = inc_n * (inc_mu - new_mu).pow(2)
  new_var = (term1 + term2 + term3 + term4) / new_n_safe
  new_var = torch.where(new_n == 0, 0.0, new_var)
  new_sigma = torch.sqrt(torch.clamp(new_var, min=0.0))
  return (w := (new_n, new_mu, new_sigma)), w

def revin(x, mu, sigma, reverse=False):
  if len(mu.shape) == len(x.shape) - 1:
    mu = mu[..., None]; sigma = sigma[..., None]
  elif len(mu.shape) == len(x.shape) - 2:
    mu = mu[..., None, None]; sigma = sigma[..., None, None]
  if reverse: return x * sigma + mu
  else: return (x - mu) / torch.where(sigma < _TOLERANCE, 1.0, sigma)

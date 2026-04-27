# Transformer layers for TimesFM
import math
from typing import Callable
import torch
import torch.nn.functional as F
from torch import nn
from .. import configs
from . import normalization, util

LayerNorm = nn.LayerNorm
RMSNorm = normalization.RMSNorm
DecodeCache = util.DecodeCache

def make_attn_mask(query_length, num_all_masked_kv, query_index_offset=None, kv_length=0):
  if kv_length == 0: kv_length = query_length
  q_index = torch.arange(query_length, device=num_all_masked_kv.device)[None, None, :, None]
  if query_index_offset is not None: q_index = q_index + query_index_offset[:, None, None, None]
  kv_index = torch.arange(kv_length, device=num_all_masked_kv.device)[None, None, None, :]
  return torch.logical_and(q_index >= kv_index, kv_index >= num_all_masked_kv[:, None, None, None])

class RotaryPositionalEmbedding(nn.Module):
  def __init__(self, embedding_dims, min_timescale=1.0, max_timescale=10000.0):
    super().__init__()
    self.embedding_dims = embedding_dims
    self.min_timescale = min_timescale
    self.max_timescale = max_timescale
  def forward(self, inputs, position=None):
    if self.embedding_dims != inputs.shape[-1]: raise ValueError("Embedding dims mismatch")
    half_embedding_dim = self.embedding_dims // 2
    fraction = 2 * torch.arange(0, half_embedding_dim, device=inputs.device) / self.embedding_dims
    timescale = (self.min_timescale * (self.max_timescale / self.min_timescale) ** fraction).to(inputs.device)
    if position is None:
      seq_length = inputs.shape[1]
      position = torch.arange(seq_length, dtype=torch.float32, device=inputs.device)[None, :]
    if len(inputs.shape) == 4:
      position = position[..., None, None]; timescale = timescale[None, None, None, :]
    elif len(inputs.shape) == 3:
      position = position[..., None]; timescale = timescale[None, None, :]
    else: raise ValueError("Rank 3 or 4 required")
    sinusoid_inp = position / timescale
    sin = torch.sin(sinusoid_inp); cos = torch.cos(sinusoid_inp)
    first_half, second_half = torch.chunk(inputs, 2, dim=-1)
    return torch.cat([first_half * cos - second_half * sin, second_half * cos + first_half * sin], dim=-1)

def _torch_dot_product_attention(query, key, value, mask=None):
  query = query.permute(0, 2, 1, 3); key = key.permute(0, 2, 1, 3); value = value.permute(0, 2, 1, 3)
  output = F.scaled_dot_product_attention(query, key, value, attn_mask=mask, scale=1.0)
  return output.permute(0, 2, 1, 3)

class PerDimScale(nn.Module):
  def __init__(self, num_dims):
    super().__init__()
    self.num_dims = num_dims
    self.per_dim_scale = nn.Parameter(torch.zeros(num_dims))
  def forward(self, x: torch.Tensor) -> torch.Tensor:
    scale_factor = 1.442695041 / math.sqrt(self.num_dims) * F.softplus(self.per_dim_scale)
    return x * scale_factor

class MultiHeadAttention(nn.Module):
  def __init__(self, num_heads, in_features, use_per_dim_scale=True, use_rotary_position_embeddings=True, use_bias=False, attention_fn=_torch_dot_product_attention, qk_norm="rms", fuse_qkv=False):
    super().__init__()
    self.num_heads = num_heads; self.in_features = in_features; self.head_dim = in_features // num_heads
    self.use_bias = use_bias; self.attention_fn = attention_fn; self.qk_norm = qk_norm; self.fuse_qkv = fuse_qkv
    if self.fuse_qkv: self.qkv_proj = nn.Linear(in_features, 3 * in_features, bias=use_bias)
    else:
      self.query = nn.Linear(in_features, in_features, bias=use_bias)
      self.key = nn.Linear(in_features, in_features, bias=use_bias)
      self.value = nn.Linear(in_features, in_features, bias=use_bias)
    self.out = nn.Linear(in_features, in_features, bias=use_bias)
    self.query_ln = RMSNorm(self.head_dim) if qk_norm == "rms" else nn.Identity()
    self.key_ln = RMSNorm(self.head_dim) if qk_norm == "rms" else nn.Identity()
    self.use_rotary_position_embeddings = use_rotary_position_embeddings
    if use_rotary_position_embeddings: self.rotary_position_embedding = RotaryPositionalEmbedding(self.head_dim)
    self.use_per_dim_scale = use_per_dim_scale
    if use_per_dim_scale: self.per_dim_scale = PerDimScale(self.head_dim)

  def forward(self, inputs_q, *, decode_cache=None, patch_mask=None):
    b, n_patches, _ = inputs_q.shape
    if patch_mask is None: patch_mask = torch.zeros(b, n_patches, dtype=torch.bool, device=inputs_q.device)
    if self.fuse_qkv:
      qkv = self.qkv_proj(inputs_q)
      query, key, value = torch.chunk(qkv, 3, dim=-1)
      query = query.view(b, n_patches, self.num_heads, self.head_dim)
      key = key.view(b, n_patches, self.num_heads, self.head_dim)
      value = value.view(b, n_patches, self.num_heads, self.head_dim)
    else:
      query = self.query(inputs_q).view(b, n_patches, self.num_heads, self.head_dim)
      key = self.key(inputs_q).view(b, n_patches, self.num_heads, self.head_dim)
      value = self.value(inputs_q).view(b, n_patches, self.num_heads, self.head_dim)
    if decode_cache is None:
      num_masked = torch.sum(patch_mask.to(torch.int32), dim=-1)
      next_index = torch.zeros_like(num_masked, dtype=torch.int32)
    else:
      num_masked = torch.sum(patch_mask.to(torch.int32), dim=-1) + decode_cache.num_masked
      next_index = decode_cache.next_index.clone()
    if self.use_rotary_position_embeddings:
      position = torch.arange(n_patches, device=inputs_q.device)[None, :] + next_index[:, None] - num_masked[:, None]
      query = self.rotary_position_embedding(query, position); key = self.rotary_position_embedding(key, position)
    query = self.query_ln(query); key = self.key_ln(key)
    if self.use_per_dim_scale: query = self.per_dim_scale(query)
    if decode_cache is not None:
      start = decode_cache.next_index[0]; end = start + n_patches
      decode_cache.key[:, start:end] = key; decode_cache.value[:, start:end] = value
      key = decode_cache.key; value = decode_cache.value
      decode_cache.next_index += n_patches; decode_cache.num_masked = num_masked
      attn_mask = make_attn_mask(n_patches, num_masked, next_index, decode_cache.value.shape[1])
    else: attn_mask = make_attn_mask(n_patches, num_masked)
    x = self.attention_fn(query, key, value, mask=attn_mask)
    x = x.reshape(b, n_patches, self.in_features)
    return self.out(x), decode_cache

class Transformer(nn.Module):
  def __init__(self, config: configs.TransformerConfig):
    super().__init__()
    self.config = config
    self.pre_attn_ln = RMSNorm(config.model_dims) if config.attention_norm == "rms" else None
    self.post_attn_ln = RMSNorm(config.model_dims) if config.attention_norm == "rms" else None
    self.attn = MultiHeadAttention(config.num_heads, config.model_dims, use_rotary_position_embeddings=config.use_rotary_position_embeddings, qk_norm=config.qk_norm, fuse_qkv=config.fuse_qkv)
    self.pre_ff_ln = RMSNorm(config.model_dims) if config.feedforward_norm == "rms" else None
    self.post_ff_ln = RMSNorm(config.model_dims) if config.feedforward_norm == "rms" else None
    self.ff0 = nn.Linear(config.model_dims, config.hidden_dims, bias=config.use_bias)
    self.ff1 = nn.Linear(config.hidden_dims, config.model_dims, bias=config.use_bias)
    if config.ff_activation == "relu": self.activation = nn.ReLU()
    elif config.ff_activation == "swish": self.activation = nn.SiLU()
    else: self.activation = nn.Identity()

  def forward(self, input_embeddings, patch_mask, decode_cache=None):
    attn_output, decode_cache = self.attn(inputs_q=self.pre_attn_ln(input_embeddings), decode_cache=decode_cache, patch_mask=patch_mask)
    attn_output = self.post_attn_ln(attn_output) + input_embeddings
    output_embeddings = self.post_ff_ln(self.ff1(self.activation(self.ff0(self.pre_ff_ln(attn_output))))) + attn_output
    return output_embeddings, decode_cache

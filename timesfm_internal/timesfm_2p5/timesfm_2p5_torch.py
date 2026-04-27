# TimesFM 2.5 Torch Implementation
import dataclasses
import logging
import math
import os
from pathlib import Path
from typing import Optional, Sequence, Union
import numpy as np
import torch
from huggingface_hub import PyTorchModelHubMixin, hf_hub_download
from safetensors.torch import load_file, save_file
from torch import nn
from .. import configs
from ..torch import dense, transformer, util
from . import timesfm_2p5_base

revin = util.revin

class TimesFM_2p5_200M_torch_module(nn.Module):
  config = timesfm_2p5_base.TimesFM_2p5_200M_Definition()
  def __init__(self):
    super().__init__()
    self.p = self.config.input_patch_len; self.o = self.config.output_patch_len
    self.os = self.config.output_quantile_len; self.m = self.o // self.p
    self.x = self.config.stacked_transformers.num_layers; self.h = self.config.stacked_transformers.transformer.num_heads
    self.md = self.config.stacked_transformers.transformer.model_dims; self.hd = self.md // self.h
    self.q = len(self.config.quantiles) + 1; self.aridx = self.config.decode_index
    self.tokenizer = dense.ResidualBlock(self.config.tokenizer)
    self.stacked_xf = nn.ModuleList([transformer.Transformer(self.config.stacked_transformers.transformer) for _ in range(self.x)])
    self.output_projection_point = dense.ResidualBlock(self.config.output_projection_point)
    self.output_projection_quantiles = dense.ResidualBlock(self.config.output_projection_quantiles)
    self.device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    self.device_count = torch.cuda.device_count() if torch.cuda.is_available() else 1

  def load_checkpoint(self, path: str, **kwargs):
    tensors = load_file(path)
    self.load_state_dict(tensors, strict=True); self.to(self.device)
    if kwargs.get("torch_compile", False): self = torch.compile(self)
    self.eval()

  def forward(self, inputs, masks, decode_caches=None):
    tokenizer_inputs = torch.cat([inputs, masks.to(inputs.dtype)], dim=-1)
    output_embeddings = self.tokenizer(tokenizer_inputs)
    if decode_caches is None: decode_caches = [None] * self.x
    new_decode_caches = []
    for i, layer in enumerate(self.stacked_xf):
      output_embeddings, new_cache = layer(output_embeddings, masks[..., -1], decode_caches[i])
      new_decode_caches.append(new_cache)
    return (None, output_embeddings, self.output_projection_point(output_embeddings), self.output_projection_quantiles(output_embeddings)), new_decode_caches

  def decode(self, horizon, inputs, masks):
    with torch.no_grad():
      batch_size, context = inputs.shape[0], inputs.shape[1]
      num_decode_steps = (horizon - 1) // self.o; num_input_patches = context // self.p
      decode_cache_size = num_input_patches + num_decode_steps * self.m
      patched_inputs = torch.reshape(inputs, (batch_size, -1, self.p)); patched_masks = torch.reshape(masks, (batch_size, -1, self.p))
      n = mu = sigma = torch.zeros(batch_size, device=inputs.device); patch_mu = []; patch_sigma = []
      for i in range(num_input_patches):
        (n, mu, sigma), _ = util.update_running_stats(n, mu, sigma, patched_inputs[:, i], patched_masks[:, i])
        patch_mu.append(mu); patch_sigma.append(sigma)
      last_n, last_mu, last_sigma = n, mu, sigma
      context_mu = torch.stack(patch_mu, dim=1); context_sigma = torch.stack(patch_sigma, dim=1)
      decode_caches = [util.DecodeCache(torch.zeros(batch_size, dtype=torch.int32, device=inputs.device), torch.zeros(batch_size, dtype=torch.int32, device=inputs.device), torch.zeros(batch_size, decode_cache_size, self.h, self.hd, device=inputs.device), torch.zeros(batch_size, decode_cache_size, self.h, self.hd, device=inputs.device)) for _ in range(self.x)]
      normed_inputs = revin(patched_inputs, context_mu, context_sigma, reverse=False)
      (_, _, normed_outputs, normed_quantile_spread), decode_caches = self(torch.where(patched_masks, 0.0, normed_inputs), patched_masks, decode_caches)
      renormed_outputs = torch.reshape(revin(normed_outputs, context_mu, context_sigma, reverse=True), (batch_size, -1, self.o, self.q))
      renormed_quantile_spread = torch.reshape(revin(normed_quantile_spread, context_mu, context_sigma, reverse=True), (batch_size, -1, self.os, self.q))[:, -1, ...]
      ar_outputs = []; last_renormed_output = renormed_outputs[:, -1, :, self.aridx]
      for _ in range(num_decode_steps):
        new_patched_input = torch.reshape(last_renormed_output, (batch_size, self.m, self.p)); new_mask = torch.zeros_like(new_patched_input, dtype=torch.bool)
        n, mu, sigma = last_n, last_mu, last_sigma; new_mus = []; new_sigmas = []
        for i in range(self.m):
          (n, mu, sigma), _ = util.update_running_stats(n, mu, sigma, new_patched_input[:, i], new_mask[:, i])
          new_mus.append(mu); new_sigmas.append(sigma)
        last_n, last_mu, last_sigma = n, mu, sigma; new_mu = torch.stack(new_mus, dim=1); new_sigma = torch.stack(new_sigmas, dim=1)
        new_normed_input = revin(new_patched_input, new_mu, new_sigma, reverse=False)
        (_, _, new_normed_output, _), decode_caches = self(new_normed_input, new_mask, decode_caches)
        new_renormed_output = torch.reshape(revin(new_normed_output, new_mu, new_sigma, reverse=True), (batch_size, self.m, self.o, self.q))
        ar_outputs.append(new_renormed_output[:, -1, ...]); last_renormed_output = new_renormed_output[:, -1, :, self.aridx]
      return renormed_outputs, renormed_quantile_spread, (torch.stack(ar_outputs, dim=1) if ar_outputs else None)

class TimesFM_2p5_200M_torch(timesfm_2p5_base.TimesFM_2p5, PyTorchModelHubMixin):
  DEFAULT_REPO_ID = "google/timesfm-2.5-200m-pytorch"; WEIGHTS_FILENAME = "model.safetensors"
  def __init__(self, torch_compile=True, config=None, **kwargs):
    self.model = TimesFM_2p5_200M_torch_module(); self.torch_compile = torch_compile
    if config: self._hub_mixin_config = config
  @classmethod
  def _from_pretrained(cls, *, model_id=DEFAULT_REPO_ID, revision=None, cache_dir=None, force_download=False, local_files_only=False, token=None, config=None, **model_kwargs):
    model_file_path = os.path.join(model_id, cls.WEIGHTS_FILENAME) if os.path.isdir(model_id) else hf_hub_download(repo_id=model_id, filename=cls.WEIGHTS_FILENAME, revision=revision, cache_dir=cache_dir, force_download=force_download, token=token, local_files_only=local_files_only)
    instance = cls(config=config, **model_kwargs); instance.model.load_checkpoint(model_file_path, torch_compile=instance.torch_compile)
    return instance
  def compile(self, forecast_config: configs.ForecastConfig, **kwargs):
    self.global_batch_size = forecast_config.per_core_batch_size * self.model.device_count; fc = forecast_config
    if fc.max_context % self.model.p != 0: fc = dataclasses.replace(fc, max_context=math.ceil(fc.max_context/self.model.p)*self.model.p)
    if fc.max_horizon % self.model.o != 0: fc = dataclasses.replace(fc, max_horizon=math.ceil(fc.max_horizon/self.model.o)*self.model.o)
    self.forecast_config = fc
    def _compiled_decode(horizon, inputs, masks):
      inputs = torch.from_numpy(np.array(inputs)).to(self.model.device).to(torch.float32)
      masks = torch.from_numpy(np.array(masks)).to(self.model.device).to(torch.bool); batch_size = inputs.shape[0]
      is_positive = torch.all(inputs >= 0, dim=-1, keepdim=True) if fc.infer_is_positive else None
      if fc.normalize_inputs: mu = torch.mean(inputs, dim=-1, keepdim=True); sigma = torch.std(inputs, dim=-1, keepdim=True); inputs = revin(inputs, mu, sigma, reverse=False)
      else: mu = sigma = None
      pf, qs, ar = self.model.decode(fc.max_horizon, inputs, masks)
      to_cat = [pf[:, -1, ...]]; 
      if ar is not None: to_cat.append(ar.reshape(batch_size, -1, self.model.q))
      ff = torch.cat(to_cat, dim=1)
      if fc.use_continuous_quantile_head:
        for idx in [1, 2, 3, 4, 6, 7, 8, 9]: ff[:, :, idx] = qs[:, :fc.max_horizon, idx] - qs[:, :fc.max_horizon, 5] + ff[:, :fc.max_horizon, 5]
      ff = ff[:, :horizon, :]
      if fc.normalize_inputs: ff = revin(ff, mu, sigma, reverse=True)
      if is_positive is not None: ff = torch.where(is_positive[..., None], torch.maximum(ff, torch.zeros_like(ff)), ff)
      res = ff.detach().cpu().numpy()
      return res[..., 5], res
    self.compiled_decode = _compiled_decode

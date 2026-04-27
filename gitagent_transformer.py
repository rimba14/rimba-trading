import torch
import torch.nn as nn
import math
import os
import time
import numpy as np
from gitagent_base import BaseModule
from typing import Dict, Any, List
import gitagent_mixts as mixts

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0) # (1, max_len, d_model) for batch_first=True
        self.register_buffer('pe', pe)

    def forward(self, x):
        # x is (batch, seq, dim)
        return x + self.pe[:, :x.size(1), :]

class TransformerEncoderModel(nn.Module):
    def __init__(self, input_dim=5, d_model=64, nhead=4, num_layers=3, dropout=0.1):
        super(TransformerEncoderModel, self).__init__()
        self.d_model = d_model
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        encoder_layers = nn.TransformerEncoderLayer(d_model, nhead, d_model * 4, dropout, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers)
        self.output_layer = nn.Linear(d_model, 1) 

    def forward(self, src):
        # src is (batch, seq, dim)
        src = self.input_proj(src) * math.sqrt(self.d_model)
        src = self.pos_encoder(src)
        output = self.transformer_encoder(src)
        # Slicing for batch_first: (batch, seq, dim) -> take last seq element
        output = output[:, -1, :] 
        return self.output_layer(output)

class CognitionLayer(BaseModule):
    """
    Sentinel Cognition Layer (Layer 3)
    Responsibility: TFT Variable Selection -> Regime Identification via MixTS.
    Input: Representation Tensor (Layer 2 output)
    Output: Dict (Tactical Verdict + Probabilities)
    """
    def __init__(self, model_path="C:\\Sentinel_Project\\transformer_weights.pth"):
        super().__init__("Cognition")
        self.model = TransformerEncoderModel()
        if os.path.exists(model_path):
            try:
                self.model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
                self.model.eval()
            except:
                pass
        self.mix_ts = mixts.MixTSAgent()

    def process(self, representation_data: Dict[str, Any]) -> Dict[str, Any]:
        tensor = representation_data.get('feature_tensor')
        if tensor is None:
            return {"verdict": "NEUTRAL", "regime_id": 0}

        # 1. TFT Inference
        # Fix shape to (seq_len, batch, input_dim) -> (1, 1, 5)
        src = torch.tensor(tensor[:5], dtype=torch.float).view(1, 1, 5)
        with torch.no_grad():
            tft_score = float(torch.clamp(self.model(src), -1.0, 1.0).item())

        # 2. MixTS Regime ID
        regime_id, weights, priors = self.mix_ts.sample_regime_and_weights()
        
        # 3. Verdict
        verdict = "HOLD"
        if tft_score > 0.4 and priors[regime_id] > 0.7: verdict = "BUY"
        elif tft_score < -0.4 and priors[regime_id] > 0.7: verdict = "SELL"

        return {
            "action": verdict,
            "tft_score": tft_score,
            "regime_id": int(regime_id),
            "regime_belief": float(priors[regime_id]),
            "timestamp": time.time()
        }

def get_transformer_score(sequence_df, model_path="C:\\Sentinel_Project\\transformer_weights.pth"):
    # Legacy wrapper
    return 0.0

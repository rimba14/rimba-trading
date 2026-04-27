import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

import gitagent_wavelet as wave

def Wavelet_for_Period(x, k=3):
    """
    COMPONENT 4: Wavelet-based period detection.
    Replaces global FFT with multi-scale wavelet power peaks.
    """
    # [B, T, C]
    # We use the first channel (e.g. Close price) for period detection
    x_np = x[0, :, 0].detach().cpu().numpy()
    
    periods, amplitudes = wave.wavelet_peak_periods(x_np, top_k=k)
    
    # Convert back to torch for the aggregation logic
    # Shape: [k], [B, k]
    return np.array(periods), torch.FloatTensor([amplitudes]).to(x.device)

class Inception_Block_V1(nn.Module):
    def __init__(self, in_channels, out_channels, num_kernels=4, init_weight=True):
        super(Inception_Block_V1, self).__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.num_kernels = num_kernels
        kernels = [1, 3, 5, 7]
        self.convs = nn.ModuleList([
            nn.Conv2d(in_channels, out_channels, kernel_size=2*i+1, padding=i)
            for i in range(num_kernels)
        ])

    def forward(self, x):
        res = []
        for conv in self.convs:
            res.append(conv(x))
        res = torch.stack(res, dim=-1).mean(-1)
        return res

class TimesBlock(nn.Module):
    def __init__(self, d_model, top_k, seq_len):
        super(TimesBlock, self).__init__()
        self.d_model = d_model
        self.k = top_k
        self.seq_len = seq_len
        # Parameter-efficient Inception
        self.conv = nn.Sequential(
            Inception_Block_V1(d_model, d_model),
            nn.GELU(),
            Inception_Block_V1(d_model, d_model)
        )

    def forward(self, x):
        B, T, N = x.size()
        period_list, period_weight = Wavelet_for_Period(x, self.k)

        res = []
        for i in range(self.k):
            period = period_list[i]
            # padding
            if self.seq_len % period != 0:
                length = (((self.seq_len // period) + 1) * period)
                padding = torch.zeros([B, (length - self.seq_len), N]).to(x.device)
                out = torch.cat([x, padding], dim=1)
            else:
                length = self.seq_len
                out = x
            
            # reshape to 2D
            out = out.reshape(B, length // period, period, N).permute(0, 3, 1, 2).contiguous()
            # 2D conv
            out = self.conv(out)
            # reshape back to 1D
            out = out.permute(0, 2, 3, 1).reshape(B, -1, N)
            res.append(out[:, :self.seq_len, :])

        res = torch.stack(res, dim=-1)
        # Adaptive aggregation
        period_weight = F.softmax(period_weight, dim=1)
        period_weight = period_weight.unsqueeze(1).unsqueeze(1).repeat(1, T, N, 1)
        res = torch.sum(res * period_weight, -1)
        
        # residual connection
        res = res + x
        return res

class TimesNetPerception(nn.Module):
    """
    COMPONENT 1, 2, 3: TimesNet Multi-Scale Temporal Perception Layer.
    """
    def __init__(self, enc_in=5, d_model=32, top_k=3, seq_len=128):
        super(TimesNetPerception, self).__init__()
        self.seq_len = seq_len
        self.enc_embedding = nn.Linear(enc_in, d_model)
        self.model = TimesBlock(d_model, top_k, seq_len)
        self.projection = nn.Linear(d_model, d_model) # Feature vector output
        
        # COMPONENT 4: Anomaly Reconstruction Head
        self.reconstruction = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, enc_in)
        )

    def forward(self, x):
        # x: [B, T, enc_in] (e.g. OHLCV)
        B, T, C = x.size()
        
        # Embedding to d_model space
        enc_out = self.enc_embedding(x) # [B, T, d_model]
        
        # Multi-scale temporal features
        enc_out = self.model(enc_out) # [B, T, d_model]
        
        # Final feature vector for the decision step (last bar)
        features = self.projection(enc_out[:, -1, :]) # [B, d_model]
        
        # Self-supervised reconstruction for Anomaly Score
        reconstructed = self.reconstruction(enc_out) # [B, T, C]
        anomaly_score = torch.mean((x - reconstructed) ** 2, dim=(1, 2))
        
        return features, anomaly_score, reconstructed

# Utility for live inference (STFT logic)
def get_timesnet_features(df, model, device='cpu'):
    # df: pandas dataframe with at least last 128 bars
    if len(df) < 128:
        return None
    
    # Extract OHLCV
    data = df[['open', 'high', 'low', 'close', 'tick_volume']].tail(128).values
    # Scale briefly for stability
    data_norm = (data - np.mean(data, axis=0)) / (np.std(data, axis=0) + 1e-9)
    x = torch.FloatTensor(data_norm).unsqueeze(0).to(device)
    
    model.eval()
    with torch.no_grad():
        features, anomaly, _ = model(x)
        
    return features.squeeze().cpu().numpy(), float(anomaly.cpu().item())

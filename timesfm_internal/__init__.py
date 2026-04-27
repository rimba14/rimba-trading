# TimesFM Internal Package Initialization
from . import configs
from .timesfm_2p5 import timesfm_2p5_torch
TimesFM_2p5_200M_torch = timesfm_2p5_torch.TimesFM_2p5_200M_torch
ForecastConfig = configs.ForecastConfig

import os
import sys
import torch
import gc
import time

# Inject Paths
PROJECT_ROOT = "C:/Sentinel_Project"
sys.path.append(PROJECT_ROOT)
KRONOS_REPO_PATH = os.path.join(PROJECT_ROOT, "kronos_repo")
sys.path.append(KRONOS_REPO_PATH)

# Output Paths
TIMESFM_QUANT_PATH = os.path.join(PROJECT_ROOT, "data", "timesfm_quantized.pt")
KRONOS_QUANT_PATH = os.path.join(PROJECT_ROOT, "data", "kronos_quantized.pt")

def compile_timesfm():
    print("\n" + "="*50)
    print("STEP 1: Compiling TimesFM (2.5 200M)...")
    print("="*50)
    
    try:
        from timesfm_internal.timesfm_2p5.timesfm_2p5_torch import TimesFM_2p5_200M_torch
        from timesfm_internal.configs import ForecastConfig
        
        MODEL_NAME = "google/timesfm-2.5-200m-pytorch"
        
        print(f"Loading FP32 model from {MODEL_NAME}...")
        fp32_model = TimesFM_2p5_200M_torch.from_pretrained(MODEL_NAME)
        
        config = ForecastConfig(
            max_context=1024,
            max_horizon=48,
            normalize_inputs=True,
            use_continuous_quantile_head=True
        )
        # v19.5 Fix: Skip pre-compilation to allow serialization of the quantized model.
        # torch.compile creates local functions that prevent pickling.
        # fp32_model.compile(config)
        
        print("Applying dynamic quantization (Linear, LayerNorm)...")
        fp32_model.model = torch.ao.quantization.quantize_dynamic(
            fp32_model.model, {torch.nn.Linear, torch.nn.LayerNorm}, dtype=torch.qint8
        )
        
        print(f"Saving quantized model to {TIMESFM_QUANT_PATH}...")
        os.makedirs(os.path.dirname(TIMESFM_QUANT_PATH), exist_ok=True)
        torch.save(fp32_model, TIMESFM_QUANT_PATH)
        
        print("TimesFM Compilation Successful.")
        
        # Aggressive Cleanup
        del fp32_model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("RAM Reset for next model.")
        
    except Exception as e:
        print(f"FAILED to compile TimesFM: {e}")
        import traceback
        traceback.print_exc()

def compile_kronos():
    print("\n" + "="*50)
    print("STEP 2: Compiling Kronos (Small)...")
    print("="*50)
    
    try:
        from model import Kronos
        
        MODEL_NAME = "NeoQuasar/Kronos-small"
        
        print(f"Loading FP32 model from {MODEL_NAME}...")
        model = Kronos.from_pretrained(MODEL_NAME)
        model.eval()
        
        print("Applying dynamic quantization (Linear, LayerNorm)...")
        quantized_model = torch.ao.quantization.quantize_dynamic(
            model, {torch.nn.Linear, torch.nn.LayerNorm}, dtype=torch.qint8
        )
        
        print(f"Saving quantized model to {KRONOS_QUANT_PATH}...")
        torch.save(quantized_model, KRONOS_QUANT_PATH)
        
        print("Kronos Compilation Successful.")
        
        # Cleanup
        del model
        del quantized_model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
    except Exception as e:
        print(f"FAILED to compile Kronos: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    start_time = time.time()
    
    # 1. Compile TimesFM
    compile_timesfm()
    
    # 2. Compile Kronos
    compile_kronos()
    
    duration = time.time() - start_time
    print(f"\nOffline Compilation Finished in {duration:.2f} seconds.")
    print(f"Artifacts generated:")
    if os.path.exists(TIMESFM_QUANT_PATH):
        print(f" - {TIMESFM_QUANT_PATH} ({os.path.getsize(TIMESFM_QUANT_PATH)/1024/1024:.2f} MB)")
    if os.path.exists(KRONOS_QUANT_PATH):
        print(f" - {KRONOS_QUANT_PATH} ({os.path.getsize(KRONOS_QUANT_PATH)/1024/1024:.2f} MB)")

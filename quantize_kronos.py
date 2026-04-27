import torch
import os
import sys
import onnx
from onnxruntime.quantization import quantize_dynamic, QuantType

# Inject local model path
KRONOS_REPO_PATH = "C:\\Sentinel_Project\\kronos_repo"
if KRONOS_REPO_PATH not in sys.path:
    sys.path.append(KRONOS_REPO_PATH)

try:
    from model import Kronos
except ImportError:
    from model.kronos import Kronos

def quantize_kronos():
    model_dir = "C:\\Sentinel_Project"
    fp32_path = os.path.join(model_dir, "kronos_fp32.onnx")
    int8_path = os.path.join(model_dir, "kronos_int8.onnx")
    
    print("[1/5] Loading PyTorch Kronos Model...")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    model.eval()
    
    # 2. Define Dummy Tensors
    # The Kronos forward pass expects s1_ids and s2_ids (integer indices)
    # Plus an optional stamp [batch, seq, 5]
    batch_size = 1
    sequence_length = 512
    
    s1_ids = torch.zeros((batch_size, sequence_length), dtype=torch.long)
    s2_ids = torch.zeros((batch_size, sequence_length), dtype=torch.long)
    stamp = torch.randn(batch_size, sequence_length, 5) # 5 temporal features
    
    print(f"[2/5] Defined Dummy Tensors (s1_ids, s2_ids, stamp)")
    
    # 3. ONNX Export
    print("[3/5] Exporting to FP32 ONNX...")
    # Setting environment variable to avoid unicode error during internal print
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    torch.onnx.export(
        model,
        (s1_ids, s2_ids, stamp),
        fp32_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['s1_ids', 's2_ids', 'stamp'],
        output_names=['s1_logits', 's2_logits'],
        dynamic_axes={
            's1_ids': {0: 'batch_size', 1: 'sequence_length'},
            's2_ids': {0: 'batch_size', 1: 'sequence_length'},
            'stamp': {0: 'batch_size', 1: 'sequence_length'},
            's1_logits': {0: 'batch_size', 1: 'sequence_length'},
            's2_logits': {0: 'batch_size', 1: 'sequence_length'}
        }
    )
    
    # 4. Dynamic INT8 Quantization
    print("[4/5] Applying Dynamic INT8 Quantization...")
    quantize_dynamic(
        model_input=fp32_path,
        model_output=int8_path,
        weight_type=QuantType.QUInt8,
        nodes_to_quantize=['MatMul', 'Attention', 'Linear']
    )
    
    # 5. Save and Verify
    print("[5/5] Quantization Complete. Verifying compression...")
    
    pt_path = os.path.join(model_dir, "kronos_temp.pt")
    torch.save(model.state_dict(), pt_path)
    
    def get_size(path):
        size = os.path.getsize(path)
        return f"{size / (1024 * 1024):.2f} MB"
    
    print("-" * 30)
    print(f"Original PyTorch (Weights): {get_size(pt_path)}")
    print(f"ONNX FP32:                  {get_size(fp32_path)}")
    print(f"ONNX INT8:                  {get_size(int8_path)}")
    print("-" * 30)
    
    if os.path.exists(pt_path):
        os.remove(pt_path)

if __name__ == "__main__":
    quantize_kronos()

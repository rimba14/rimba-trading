import os
import ast

def get_skeleton(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            node = ast.parse(f.read())
        
        skeleton = []
        for item in node.body:
            if isinstance(item, ast.ClassDef):
                skeleton.append(f"CLASS: {item.name}")
                for subitem in item.body:
                    if isinstance(subitem, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = ast.unparse(subitem.args)
                        skeleton.append(f"  DEF: {subitem.name}({args})")
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = ast.unparse(item.args)
                skeleton.append(f"DEF: {item.name}({args})")
        return skeleton
    except Exception as e:
        return [f"ERR: {e}"]

def main():
    root_files = [
        "adaptive_sentinel_dry_run.py", "alpha_combiner.py", "alpha_strategy_lab.py",
        "arctic_polyfill.py", "audit_drawdown.py", "audit_performance.py", "audit_positions.py",
        "chat_deepseek.py", "chat_gemma.py", "chat_glm.py", "chat_qwen.py",
        "deepseek_bridge.py", "diagnostic_pipeline.py", "gitagent_action_layer.py",
        "gitagent_adaptive.py", "gitagent_adaptive_sentinel.py", "gitagent_base.py",
        "gitagent_context_layer.py", "gitagent_eco.py", "gitagent_execute_sor.py",
        "gitagent_gemma_connector.py", "gitagent_happo.py", "gitagent_hmm.py",
        "gitagent_insider.py", "gitagent_knowledge_oracle.py", "gitagent_kronos_adapter.py",
        "gitagent_learn.py", "gitagent_lob.py", "gitagent_macro_oracle.py",
        "gitagent_memory.py", "gitagent_microstructure.py", "gitagent_mixts.py",
        "gitagent_news_perceiver.py", "gitagent_opportunity_scan.py", "gitagent_owl_bridge.py",
        "gitagent_ppo.py", "gitagent_reflection.py", "gitagent_rsi.py",
        "gitagent_sentiment_bridge.py", "gitagent_sigproc.py", "gitagent_social_oracle.py",
        "gitagent_sor.py", "gitagent_spectral_denoiser.py", "gitagent_synthesis.py",
        "gitagent_transformer.py", "gitagent_utils.py", "gitagent_var.py",
        "gitagent_vision_audit.py", "gitagent_wavelet.py", "gitagent_wednesday_audit.py",
        "medallion_sizing.py", "vantage_execute.py"
    ]
    
    subdirs = ["agents", "strategies"]
    
    files_to_scan = [os.path.join("C:\\Sentinel_Project\\\", f) for f in root_files]
    for d in subdirs:
        dir_path = os.path.join("C:\\Sentinel_Project\\\", d)
        if os.path.exists(dir_path):
            files_to_scan.extend([os.path.join(dir_path, f) for f in os.listdir(dir_path) if f.endswith(".py")])

    with open("C:\\Sentinel_Project\\\architecture_skeleton_core.txt", "w", encoding="utf-8") as f:
        for py_file in sorted(files_to_scan):
            if not os.path.exists(py_file): continue
            rel_path = os.path.relpath(py_file, "C:\\Sentinel_Project\\\")
            f.write(f"\nFILE: {rel_path}\n")
            try:
                with open(py_file, "r", encoding="utf-8") as pf:
                    first_line = pf.readline().strip()
                    if first_line.startswith('"""') or first_line.startswith("'''"):
                        f.write(f"PURPOSE: {first_line.strip('\"\'')}\n")
                    else:
                        f.write(f"PURPOSE: Core Python component {os.path.basename(py_file)}\n")
            except:
                f.write("PURPOSE: Unknown\n")
            
            skeleton = get_skeleton(py_file)
            for line in skeleton:
                f.write(f"{line}\n")

if __name__ == "__main__":
    main()

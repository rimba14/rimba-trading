import time
import numpy as np
from gitagent_memory_fast import FastMemory
from gitagent_groq_lpu import GroqReasoningEngine
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

def benchmark_fast_rag():
    print("[BENCHMARK] Starting Phase 23 Latency Audit (FAISS+Groq Hybrid)...")
    
    # 1. Init
    start_init = time.time()
    memory = FastMemory(dim=89)
    engine = GroqReasoningEngine(model_name="llama-3.1-8b-instant")
    print(f"[BENCHMARK] Initialization: {(time.time() - start_init)*1000:.2f}ms")
    
    # 2. Milvus Retrieval Latency
    query_vec = np.random.randn(89).astype('float32')
    # Store a dummy for search
    memory.store(query_vec, "NEUTRAL", 0.0, "Benchmark seed")
    
    start_retrieval = time.time()
    episodes = memory.retrieve(query_vec, k=2)
    retrieval_latency = (time.time() - start_retrieval) * 1000
    print(f"[BENCHMARK] Milvus Retrieval: {retrieval_latency:.2f}ms")
    
    # 3. Groq Inference Latency
    summary = "BTCUSD Breakout +2.1%, Momentum High, RSI 68"
    start_inference = time.time()
    reasoning = engine.analyze_regime(summary, episodes)
    inference_latency = (time.time() - start_inference) * 1000
    print(f"[BENCHMARK] Groq Inference: {inference_latency:.2f}ms")
    
    # 4. Results
    total_latency = retrieval_latency + inference_latency
    print(f"\n[BENCHMARK] Total RAG Loop: {total_latency:.2f}ms")
    print(f"[BENCHMARK] Reasoning: {reasoning}")
    
    if total_latency < 500:
        print("[BENCHMARK] SUCCESS: Sentinel Phase 23 meets sub-500ms target.")
    else:
        print("[BENCHMARK] WARNING: Latency exceeds target. Consider 8B model or optimization.")

if __name__ == "__main__":
    benchmark_fast_rag()

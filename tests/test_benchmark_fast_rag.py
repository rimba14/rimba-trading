import sys
from unittest.mock import MagicMock

# Mock modules that might have heavy dependencies or be absent
sys.modules['gitagent_groq_lpu'] = MagicMock()
sys.modules['gitagent_memory_fast'] = MagicMock()

import pytest
from unittest.mock import patch
from benchmark_fast_rag import benchmark_fast_rag

@patch('benchmark_fast_rag.FastMemory')
@patch('benchmark_fast_rag.GroqReasoningEngine')
@patch('benchmark_fast_rag.time.time')
def test_benchmark_fast_rag_success(mock_time, mock_engine, mock_memory, capsys):
    # Simulate time.time() calls for total latency < 500ms
    # 1. start_init (0.0)
    # 2. after init (0.1) -> diff 0.1s = 100ms
    # 3. start_retrieval (0.2)
    # 4. after retrieval (0.3) -> diff 0.1s = 100ms
    # 5. start_inference (0.4)
    # 6. after inference (0.5) -> diff 0.1s = 100ms
    # Total latency = 200ms
    mock_time.side_effect = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]

    mock_engine_instance = mock_engine.return_value
    mock_engine_instance.analyze_regime.return_value = "Mocked Reasoning"

    benchmark_fast_rag()

    captured = capsys.readouterr()
    assert "SUCCESS: Sentinel Phase 23 meets sub-500ms target." in captured.out
    assert "Total RAG Loop: 200.00ms" in captured.out

@patch('benchmark_fast_rag.FastMemory')
@patch('benchmark_fast_rag.GroqReasoningEngine')
@patch('benchmark_fast_rag.time.time')
def test_benchmark_fast_rag_warning(mock_time, mock_engine, mock_memory, capsys):
    # Simulate time.time() calls for total latency > 500ms
    # 1. start_init (0.0)
    # 2. after init (0.1) -> diff 0.1s = 100ms
    # 3. start_retrieval (0.2)
    # 4. after retrieval (0.6) -> diff 0.4s = 400ms
    # 5. start_inference (0.7)
    # 6. after inference (0.9) -> diff 0.2s = 200ms
    # Total latency = 600ms
    mock_time.side_effect = [0.0, 0.1, 0.2, 0.6, 0.7, 0.9]

    mock_engine_instance = mock_engine.return_value
    mock_engine_instance.analyze_regime.return_value = "Mocked Reasoning"

    benchmark_fast_rag()

    captured = capsys.readouterr()
    assert "WARNING: Latency exceeds target." in captured.out
    assert "Total RAG Loop: 600.00ms" in captured.out

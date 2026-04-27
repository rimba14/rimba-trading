"""
turbo_wrapper.py - SRE Memory Optimization (OOM Protocol)
Centralized local inference parameters for TurboQuant CPU Backend.
"""

import os
import json
import requests
import logging

# Hard-coded OOM Protocol Boundaries
TURBO_CONFIG = {
    "num_thread": 2,
    "num_batch": 128,
    "num_ctx": 4096,
    "kv_cache_type": "q4_0"
}

class TurboQuantWrapper:
    """
    Utility wrapper to ensure all local LLM requests comply with the 
    community-discovered CPU-safe boundaries.
    """
    
    @staticmethod
    def get_options():
        """Returns the hardware-safe options dictionary."""
        return TURBO_CONFIG.copy()

    @staticmethod
    def inject_payload(payload):
        """
        Injects the OOM protocol boundaries into an OpenAI-style payload.
        """
        if "extra_body" not in payload:
            payload["extra_body"] = {}
        
        # Inject standard Ollama/llama.cpp options
        payload["extra_body"].update(TURBO_CONFIG)
        
        # Ensure max_tokens doesn't exceed ctx limit
        if "max_tokens" in payload and payload["max_tokens"] > TURBO_CONFIG["num_ctx"]:
            payload["max_tokens"] = TURBO_CONFIG["num_ctx"]
            
        return payload

def get_turbo_config():
    """Export for external config files (e.g. hermes config.yaml)"""
    return TURBO_CONFIG

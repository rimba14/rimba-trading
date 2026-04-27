from abc import ABC, abstractmethod
from typing import Any, Dict
import time

class BaseModule(ABC):
    """
    Standardized block for Sentinel Architectural Perfection.
    Ensures non-redundant, atomic, and linear data flow.
    """
    def __init__(self, name: str):
        self.name = name
        self.last_run = 0
        self.execution_time = 0
        
    @abstractmethod
    def process(self, input_data: Any) -> Any:
        """
        Principal entry point: transform Layer (N) output to Layer (N+1) input.
        """
        pass

    def validate_input(self, data: Any) -> bool:
        """
        Step 5: Sanity checks and guardrails.
        """
        return True

    def _run_with_metrics(self, input_data: Any) -> Any:
        start = time.time()
        res = self.process(input_data)
        self.execution_time = time.time() - start
        self.last_run = time.time()
        return res

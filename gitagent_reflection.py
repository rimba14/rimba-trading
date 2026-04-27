from gitagent_memory import EpisodicMemory

class Reflector:
    """
    Tier 3: Recursive Reflection Layer.
    Analyzes trade outcomes and matures past memories into 'Experience'.
    """
    def __init__(self, memory_engine: EpisodicMemory):
        self.memory = memory_engine

    def reflect_on_closure(self, memory_id, real_pnl, max_dd):
        """Performs post-mortem on a closed trade."""
        if memory_id not in self.memory.metadata:
            print(f"[REFLECTION] Memory {memory_id} not found.")
            return

        meta = self.memory.metadata[memory_id]
        was_win = real_pnl > 0
        
        # Self-Healing Logic: Compare reasoning vs outcome
        lesson = "N/A"
        if not was_win:
            if max_dd > 2.0: # Arbitrary threshold for 'High Pain'
                lesson = "Stop Loss was too tight for current volatility scale."
            else:
                lesson = "Regime shift occurred during monitoring; indicators lagged."
        else:
            lesson = "Execution followed SISC pattern accurately."
        
        # Update memory with reflection
        meta["lesson"] = lesson
        meta["final_pnl"] = real_pnl
        meta["pnl_error"] = abs(real_pnl - meta.get("pnl", 0))
        
        self.memory.save()
        print(f"[REFLECTION] Updated Memory {memory_id} with Lesson: {lesson}")
        return lesson

if __name__ == "__main__":
    # Test reflection
    mem = EpisodicMemory(dim=89)
    # Assume ID '0' exists from previous test
    reflector = Reflector(mem)
    reflector.reflect_on_closure("0", -50.0, 2.5)

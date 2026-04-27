import enum

class TaskState(enum.Enum):
    IDLE = 0
    DETECT_ENTRY = 1
    CALCULATE_SIZE = 2
    EXECUTING = 3
    MONITORING = 4
    REFLECTING = 5

class TaskGraph:
    """
    Tier 4: Working Memory State Management.
    Implements a hierarchical task chain to track the agent's intent.
    """
    def __init__(self):
        self.current_state = TaskState.IDLE
        self.temp_memory = {}
        self.active_intent = None

    def set_intent(self, intent_desc):
        self.active_intent = intent_desc
        print(f"[WORKING] New Intent: {intent_desc}")

    def transition(self, new_state: TaskState):
        prev = self.current_state
        self.current_state = new_state
        print(f"[WORKING] Task Graph: {prev.name} -> {new_state.name}")

    def update_payload(self, key, value):
        self.temp_memory[key] = value

    def clear(self):
        self.temp_memory = {}
        self.active_intent = None
        self.current_state = TaskState.IDLE

    def get_status(self):
        return {
            "state": self.current_state.name,
            "intent": self.active_intent,
            "payload": self.temp_memory
        }

if __name__ == "__main__":
    tg = TaskGraph()
    tg.set_intent("Scalp SPI200 breakout")
    tg.transition(TaskState.DETECT_ENTRY)
    tg.update_payload("threshold", 3.5)
    print(tg.get_status())

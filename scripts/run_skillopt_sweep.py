import os
import json
import logging
from typing import List, Dict, Any
from cades_sre_env import CadesMultiTaskEnv

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [SweepLoop] %(message)s')

class MockModel:
    def generate(self, prompt: str, **kwargs) -> str:
        # Simplistic patch simulation
        if "TRACK_A" in prompt:
            return "```python\n# Mock optimization patch\ndef optimized_function():\n    return 'COMPILATION_SUCCESSFUL'\n```"
        else:
            return "```json\n{\"kelly_fraction\": 0.12, \"regime_lookback\": 36, \"conviction_threshold\": 0.85}\n```"

class DualSkillOptSweepRunner:
    def __init__(self, data_root: str, epochs: int = 5, batch_size_per_track: int = 8, edit_budget: int = 6):
        self.data_root = data_root
        self.epochs = epochs
        self.batch_size_per_track = batch_size_per_track
        self.edit_budget = edit_budget
        self.env = CadesMultiTaskEnv()
        self.model = MockModel()
        self.current_skill = "1. Ensure all stops use ATR logic.\n2. Do not use blocking calls.\n3. Optimize Kelly sizes for low-variance."
        self.rejected_buffer = []

    def load_dataset(self, split: str) -> List[Dict[str, Any]]:
        path = os.path.join(self.data_root, split, "items.json")
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Ensure we have mixed Track data for testing. If pure SRE, we mock Track B nodes.
        mixed_data = []
        for i, item in enumerate(data):
            # Alternating tracks for the dataset
            task_type = "TRACK_A" if i % 2 == 0 else "TRACK_B"
            item["task_type"] = task_type
            mixed_data.append(item)
            
        return mixed_data

    def optimize_skill(self, error_trajectory: List[Dict[str, Any]]) -> str:
        """
        Simulates generating a new skill patch constrained by edit_budget.
        """
        logging.info(f"Generating dual-objective skill patch using {len(error_trajectory)} failed trajectories...")
        return self.current_skill + f"\n4. Edit bounded. Max {self.edit_budget} lines changed."

    def run_sweep(self, dry_run: bool = False):
        train_data = self.load_dataset("train")
        val_data = self.load_dataset("val")
        
        if not train_data or not val_data:
            logging.error("Insufficient data to run sweep. Exiting.")
            return

        # Separate data by track for batch building
        train_a = [i for i in train_data if i["task_type"] == "TRACK_A"]
        train_b = [i for i in train_data if i["task_type"] == "TRACK_B"]
        
        if dry_run:
            logging.info("DRY-RUN mode enabled. Slicing data to 1 mini-batch (8 per track).")
            train_a = train_a[:self.batch_size_per_track]
            train_b = train_b[:self.batch_size_per_track]
            val_data = val_data[:self.batch_size_per_track*2]

        best_val_score_a, best_val_score_b = self.evaluate_split(val_data, self.current_skill)
        best_joint_loss = (best_val_score_a + best_val_score_b) / 2.0
        logging.info(f"Initial Baseline - Track A: {best_val_score_a:.4f} | Track B: {best_val_score_b:.4f} | Joint Loss: {best_joint_loss:.4f}")

        num_batches = max(len(train_a) // self.batch_size_per_track, len(train_b) // self.batch_size_per_track)
        
        for epoch in range(self.epochs):
            logging.info(f"--- Starting Epoch {epoch+1}/{self.epochs} ---")
            
            for b_idx in range(num_batches):
                start_idx = b_idx * self.batch_size_per_track
                batch_a = train_a[start_idx:start_idx+self.batch_size_per_track]
                batch_b = train_b[start_idx:start_idx+self.batch_size_per_track]
                
                batch = batch_a + batch_b
                batch_errors = []
                
                for item in batch:
                    prediction, trajectory = self.env.execute(item, self.current_skill, self.model)
                    score = self.env.evaluate(prediction, item)
                    
                    if item["task_type"] == "TRACK_A" and score < 1.0:
                        batch_errors.append({"item": item, "prediction": prediction, "score": score, "trajectory": trajectory})
                    elif item["task_type"] == "TRACK_B" and score < 0.5: # Example threshold for Quant
                        batch_errors.append({"item": item, "prediction": prediction, "score": score, "trajectory": trajectory})
                
                if batch_errors:
                    candidate_skill = self.optimize_skill(batch_errors)
                    cand_a, cand_b = self.evaluate_split(val_data, candidate_skill)
                    
                    # Bounded Joint Loss Function
                    if cand_a == 1.0 and cand_b > best_val_score_b:
                        cand_joint = (cand_a + cand_b) / 2.0
                        logging.info(f"Candidate accepted! Joint Delta: {best_joint_loss:.4f} -> {cand_joint:.4f}")
                        self.current_skill = candidate_skill
                        best_val_score_a, best_val_score_b = cand_a, cand_b
                        best_joint_loss = cand_joint
                    else:
                        logging.warning(f"Candidate rejected (Track A: {cand_a:.2f}, Track B: {cand_b:.4f}). Rolled back.")
                        self.rejected_buffer.append(candidate_skill)
                else:
                    logging.info("Batch passed flawlessly. No optimization step required.")

            if dry_run:
                break
                
        logging.info(f"Sweep complete. Final Joint Validation Score: {best_joint_loss:.4f}")
        
        # Deploy to master skills directory
        output_path = os.path.expanduser("~/.hermes/skills/best_skill.md")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.current_skill)
        logging.info(f"Deployed multi-task procedural state to {output_path}")
        
        return best_joint_loss

    def evaluate_split(self, data: List[Dict[str, Any]], skill: str) -> Tuple[float, float]:
        score_a, score_b = 0.0, 0.0
        count_a, count_b = 0, 0
        
        for item in data:
            prediction, _ = self.env.execute(item, skill, self.model)
            score = self.env.evaluate(prediction, item)
            
            if item["task_type"] == "TRACK_A":
                score_a += score
                count_a += 1
            else:
                score_b += score
                count_b += 1
                
        avg_a = score_a / count_a if count_a else 1.0
        avg_b = score_b / count_b if count_b else 0.0
        return avg_a, avg_b

if __name__ == "__main__":
    runner = DualSkillOptSweepRunner(data_root="C:\\Sentinel_Project\\data\\skillopt_sre")
    logging.info("Initiating DRY-RUN Dual-Task Co-Evolution Sweep...")
    final_score = runner.run_sweep(dry_run=True)
    print(f"|DRY_RUN_FINAL_VAL_SCORE:{final_score:.4f}|")

import torch
import gitagent_happo as happo
import gitagent_ppo as ppo

def bootstrap_89dim_weights():
    print("[BOOTSTRAP] Initializing 89-dimensional HAPPO Orchestrator...")
    # HAPPO (89-dim)
    orchestrator = happo.HAPPOOrchestrator()
    orchestrator.save("C:\\Sentinel_Project\\happo_weights.pth")
    print("[BOOTSTRAP] HAPPO weights (89-dim) saved to C:\\Sentinel_Project\\happo_weights.pth")

    print("[BOOTSTRAP] Initializing 89-dimensional PPO Agent...")
    # PPO (89-dim)
    agent = ppo.PPOAgent(state_dim=89)
    torch.save(agent.policy_old.state_dict(), "C:\\Sentinel_Project\\ppo_policy.pth")
    print("[BOOTSTRAP] PPO policy (89-dim) saved to C:\\Sentinel_Project\\ppo_policy.pth")

if __name__ == "__main__":
    bootstrap_89dim_weights()
    print("[BOOTSTRAP] Complete. Engine 'brain' is now 89-dim compatible.")

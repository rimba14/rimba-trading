"""
Sentinel Version Manifest (v28.12 Ironclad CADES: Telemetry Separation)
Canonical source of truth for system identity and trade signature tracking.
"""

SENTINEL_VERSION = "v28.13"
SENTINEL_BUILD = "IRONCLAD"
SENTINEL_CONSTITUTION = "CADES"
AGENT_SIGNATURE = f"SENTINEL_{SENTINEL_VERSION}_{SENTINEL_BUILD}_{SENTINEL_CONSTITUTION}"

# Banned signatures of legacy systems to prevent ghost executions
LEGACY_BANNED = ["v20.4", "v20.5", "v21.0", "v22.4", "v22.8", "v23.11", "v24.1", "v25.0", "v26.4", "v27.0", "v28.9", "v28.10", "v28.11", "v28.12"]

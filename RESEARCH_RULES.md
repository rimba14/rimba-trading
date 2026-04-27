# Sentinel v11.5 Research Rules (AgentShield / Isolation)

## The Research Subagent Pattern
To maintain execution speed and prevent token bloat during live trading, ALL deep research tasks (e.g., reading GitHub repositories, analyzing external tools, pulling massive datasets) MUST be handled in isolation.

1. **Do NOT** read massive external codebases or documentation directly within the main 'EXECUTION' session while the engine is being monitored.
2. Use a dedicated `task_boundary` entering `PLANNING` mode before performing the research.
3. Summarize findings into an artifact or memory file.
4. Immediately use the `/compact` command (or the UI equivalent) to clear the context window after synthesizing the research.

## Security Profile
- **No untested execution**: External scripts must be dry-run.
- **Library limits**: Stick to `numpy`, `pandas`, `pytorch`, `mt5`, `yfinance`. Avoid injecting unknown PyPI packages without Sandbox testing.

# TRADING STATUS

## System Topology: v37.0 Manager/Delegator Sandwich Topology (Active)
- **Central Director Orchestrator (`sentinel_director.py`):** Running asynchronously (50ms loop synchronization cap verified).
- **Perception Core Workers:**
  - `indicator_timesnet.py` (Active)
  - `indicator_mixts.py` (Active)
  - `indicator_hmm.py` (Active)
- **Execution Conductor (`vantage_execute.py`):** Active (1-second fast execution router).
- **Scale-Out Engine (`cades_sentinel.py`):** Active (Geometric trailing stop-loss modification).
- **Autonomous SRE Watchdog (`isolated_sre_daemon.py`):** Active (Exception tripwire watchdog).

## Key Metrics & Conformance
- **Optimization Loss Metric:** Calmar/Sortino Focused
- **Background Train Status:** Active Continual
- **Monte Carlo Gate:** Enforced / Invariant Check Active
- **Portfolio Protection:** Cooldowns + LowProfit Tracking Live
- **Conformal Predictor Couverture:** 94.2% (Matches baseline specifications of 95.0% target within 1% tolerance)

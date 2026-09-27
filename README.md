# Intelligent Fiber Health System

Discrete-event simulation that studies whether a 5G fronthaul fiber can also work as a
Distributed Acoustic Sensor (DAS) for fault detection, without breaking the fronthaul
latency budget.

The simulation generates the results, tables, and figures used in the research paper
"Fiber Health Paper".

## System model

- Simulator: [SimPy](https://simpy.readthedocs.io/) (discrete-event).
- Topology: 1 CU, 2 DUs, 3 RRUs per DU. One DAS sensor is co-located with each RRU.
- Each DU sends its RRUs' eCPRI traffic and its DAS sensors' traffic over one shared uplink
  fiber to the CU.
- DU scheduling: non-preemptive strict priority (eCPRI before DAS). A DAS transmission that
  has already started runs to completion.
- Only serialization occupies the link. Propagation delay is applied to the in-flight message.
- Each traffic class has its own buffer (1000 messages) with independent drop-tail admission.

All parameters are in `config.py`. `METHODOLOGY.md` lists every parameter value, the
analytical validation, the key results, and the limitations.

## Repository structure

```
.
├── main_fiber_health.py        # Entry point: validation + six scenarios + figures
├── config.py                   # All simulation parameters
├── topology.py                 # CU / DU / RRU / DAS topology
├── build_report.py             # Builds the handoff report (.docx) from results_export.json
├── results_export.json         # Frozen results used by build_report.py
├── METHODOLOGY.md              # Methods, validation, results, limitations
├── network/                    # eCPRI frame, DAS message, fiber events, fiber link model
├── nodes/                      # RRU, DU, CU, DAS sensor, DAS fiber monitor
├── simulation/                 # Engine, response controller, analytical M/G/1 validation
├── visualization/              # Figure generation
└── output/                     # Generated figures (PNG)
```

## Requirements

Python 3 with these packages:

```bash
pip install simpy numpy matplotlib networkx python-docx
```

## How to run

Run all commands from inside this folder.

```bash
python main_fiber_health.py
```

This command:

1. Runs the analytical M/G/1 priority-queue check (`simulation/validation.py`).
2. Runs the six scenarios.
3. Prints a results summary.
4. Writes ten figures to `output/`.

Runtime is several minutes. Results are deterministic (seed 42 + scenario index).

To rebuild the handoff report from `results_export.json`:

```bash
python build_report.py
```

Note: the script that writes `results_export.json` (`extract_results.py`) is not in this
repository. Treat `results_export.json` as the frozen source for the report.

## Scenarios

| # | Scenario |
|---|---|
| 1 | Baseline (No Issues) |
| 2 | Light Vibration (Construction Nearby) |
| 3 | Heavy Vibration (Construction) |
| 4 | Fiber Damage (Micro-cut) |
| 5 | Critical Fiber Cut |
| 6 | Multiple Issues (Cascade) |

Single-fault scenarios start at t = 5.0 s. The cascade scenario staggers its second event.

## Results (from `results_export.json`)

| Scenario | eCPRI mean (µs) | p99 (µs) | Deadline violation (%) | F1 (%) |
|---|---|---|---|---|
| Baseline | 73.3 | 69.6 | 0.32 | — |
| Light Vibration | 111.9 | 118.4 | 0.33 | 0.0 |
| Heavy Vibration | 214.9 | 268.4 | 0.35 | 100.0 |
| Fiber Damage | 431.8 | 568.4 | 73.43 | 66.7 |
| Critical Fiber Cut | 36691.8 | 50068.4 | 73.28 | 100.0 |
| Cascade | 264.8 | 368.4 | 0.32 | 80.0 |

See `METHODOLOGY.md` §3 for the interpretation (heavy-tail effect of DAS bursts on eCPRI latency).

## Limitations

- Mitigation (reroute, isolate) is decision-only. It is not applied to the simulated network.
  Reported latencies are unmitigated fault impact.
- `impact_on_latency_us` per fault event is a set parameter, not derived from optical physics.
- Detection probability is a simple abstraction, not a Rayleigh backscatter simulation.
- Single CU, tree topology, no protection path.
- Each scenario has only 1–2 fault events, so detection metrics are coarse.

Full details: `METHODOLOGY.md` §4.

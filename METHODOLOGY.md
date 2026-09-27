# Simulation Methodology and Validation

Reference for the methods and threats-to-validity sections of the paper.

## 1. System model

A 5G fronthaul segment simulated in SimPy (discrete-event), comprising one CU,
two DUs, and three RRUs per DU. Each RRU is co-located with a DAS sensor.

| Parameter | Value | Source |
|---|---|---|
| eCPRI frame period | 125 µs (8 kHz) | 5G NR numerology |
| eCPRI payload | 9600 B | 30 kHz SCS, 273 RB |
| Antenna ports per RRU | 2 | — |
| Fronthaul deadline | 500 µs | eCPRI latency budget |
| DU→CU fiber | 10 km | — |
| RRU→DU fiber | 5 km | — |
| Link capacity | 25 Gbps | — |
| Propagation speed | 2×10⁸ m/s | typical for silica fiber |
| DAS event rate | 100 events/s per sensor | Poisson |
| DAS burst size | 100 kB mean, σ=2 | lognormal |
| DAS sensors (monitor) | 20 over 10 km | 500 m spacing |
| Detection threshold | 35 dB | — |
| Fiber attenuation | 0.5 dB/km | — |
| Detection latency | 100 ms | — |
| False-alarm rate | 0.02 /s | Poisson |
| Warm-up | 1.0 s (discarded) | — |
| Measurement window | 15.0 s | — |

### Queueing and link model

The DU uplink is a single server under **non-preemptive strict priority**:
eCPRI (class 1) preempts queued DAS (class 2) in selection order, but a DAS
transmission already in progress runs to completion.

Two modelling choices are load-bearing and were the subject of corrections:

1. **Only serialization occupies the link.** Propagation is latency carried by
   the in-flight message, applied concurrently, so the transmitter is free once
   the last bit is clocked out. Charging propagation as holding time caps DU
   throughput at 1/(serialization + propagation) ≈ 18.8 k frames/s against
   48 k frames/s offered, producing unbounded queue growth unrelated to
   capacity.

2. **Per-class buffers with independent admission.** A shared buffer allows
   bulk DAS bursts to occupy every slot and drop-tail arriving eCPRI frames,
   inverting the intended priority — scheduling can only reorder frames that
   were admitted. Each class has a 1000-message buffer.

### Scenario design

All single-fault scenarios share onset at **t = 5.0 s** and persist to the end
of the window. This is deliberate: deadline-violation rate is proportional to
the fraction of the window a fault is active, so unequal onsets would confound
severity with exposure duration. The cascade scenario staggers its second event
to exercise overlapping faults.

## 2. Analytical validation

The simulator is checked against the non-preemptive M/G/1 priority queue
(`simulation/validation.py`). For the high-priority class:

    W₁ = R / (1 − ρ₁),    R = ½ Σₖ λₖ E[Sₖ²]

with sojourn time T₁ = W₁ + E[S₁] + d_prop.

**Offered load:** ρ_eCPRI = 0.147, ρ_DAS = 0.010, **ρ_total = 0.157** (stable).

| σ (DAS lognormal) | Simulated mean | Analytical | Rel. error |
|---|---|---|---|
| 2.0 (default) | 83.9 µs | 63.2 µs | +32.8% |
| 1.0 | 61.3 µs | 53.8 µs | +13.9% |
| 0.5 | 61.0 µs | 53.6 µs | +13.8% |

The error shrinks as the tail lightens, confirming the gap is driven by the
heavy lognormal service distribution, whose sample mean converges slowly. The
residual ≈14% is expected and has a known cause: the analytical model assumes
Poisson eCPRI arrivals, whereas the RRUs are strictly periodic: each of the
three RRUs on a DU emits one frame per antenna port, so six frames arrive
simultaneously every 125 µs — a deterministic batch arrival that M/G/1
does not capture. Simulated **median** latency (62.3 µs) matches the analytical
mean (63.2 µs) to within 1.5%.

**Reproducibility.** Fixed seed yields bit-identical results across runs;
distinct seeds yield distinct results. Each scenario uses seed 42 + index.

## 3. Key results

| Scenario | eCPRI mean | p99 | Deadline viol. | F1 |
|---|---|---|---|---|
| Baseline | 73.3 µs | 69.6 µs | 0.32% | — |
| Light Vibration | 111.9 µs | 118.4 µs | 0.33% | 0.0% |
| Heavy Vibration | 214.9 µs | 268.4 µs | 0.35% | 100.0% |
| Fiber Damage | 431.8 µs | 568.4 µs | 73.43% | 66.7% |
| Critical Fiber Cut | 36691.8 µs | 50068.4 µs | 73.28% | 100.0% |
| Cascade | 264.8 µs | 368.4 µs | 0.32% | 80.0% |

Zero eCPRI loss in all scenarios; latency increases monotonically with fault
severity.

### Heavy-tail finding

Under baseline load the mean (73.3 µs) **exceeds the p99 (69.6 µs)**. This is
not an artifact: 99.0% of frames complete near 61 µs, while <1% are blocked
behind a large DAS burst and reach p99.9 = 2927 µs and a maximum of 17.5 ms.
0.88% of lognormal DAS bursts require more than 500 µs to serialize at 25 Gbps
— alone exceeding the entire fronthaul budget.

**Implication:** mean latency is the wrong metric for fronthaul dimensioning
under mixed traffic. Tail percentiles must be reported. This also motivates
preemption or DAS burst fragmentation as design remedies, since strict priority
alone cannot protect eCPRI from an in-progress bulk transmission.

## 4. Limitations

State these in the paper.

- **Mitigation is not modelled.** `ResponseStrategy` maps severity to actions
  and records decision latency, but does not enact rerouting or isolation on
  the running network. Reported latencies are therefore *unmitigated* fault
  impact. Quantifying mitigation benefit requires a protection-switching model
  and a backup path — future work. Do not claim latency reduction from response.
- **Fault-to-latency mapping is parametric.** `impact_on_latency_us` is a
  stipulated per-event constant, not derived from optical physics. Results
  should be read as a sensitivity analysis over assumed fault severities.
- **Detection is a probabilistic abstraction.** Detection probability is
  1 − exp(−SNR_margin/10) after 0.5 dB/km attenuation; no Rayleigh
  backscatter or coherent-detection physics is simulated.
- **Single CU, no protection path.** Topology is a tree with no redundancy.
- **Small event counts.** Each scenario contains 1–2 fault events, so
  precision/recall are coarse (a single false alarm moves precision by 50
  points). Latency statistics, drawn from ~10⁶ frames, are not affected.
  Repeated trials across seeds would tighten the detection metrics.
- **BER analysis removed.** An earlier version mapped latency impact to SNR
  degradation via 10·log₁₀(1 + impact/500). That mapping has no physical basis
  and was removed rather than reported.

## 5. Reproducing

```bash
cd "INTELLIGENT FIBER HEALTH SYSTEM"
python main_fiber_health.py
```

Writes ten figures to `output/`. Runtime is several minutes, dominated by the
~10⁶ eCPRI frame events per scenario.

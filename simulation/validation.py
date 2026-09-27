"""
Analytical validation of the fronthaul queueing model.

Provides an independent check that the discrete-event simulator reproduces
known queueing-theoretic results. This is the credibility anchor for the
latency numbers reported in the paper: a simulator that cannot match theory
in a regime where theory applies should not be trusted in regimes where it
does not.

Model
-----
The DU uplink is a single server (the fiber transmitter) offered two traffic
classes under non-preemptive strict priority:

  class 1 (high) : eCPRI, deterministic size, periodic arrivals
  class 2 (low)  : DAS, lognormal size, Poisson arrivals

For the high-priority class the mean waiting time follows the standard
non-preemptive priority (M/G/1) result:

    W_1 = R / (1 - rho_1)

where R is the mean residual service time of all classes,

    R = 0.5 * sum_k lambda_k * E[S_k^2]

Total sojourn time adds the class's own service time and the propagation
delay:

    T_1 = W_1 + E[S_1] + d_prop

Because eCPRI arrivals are periodic rather than Poisson, this M/G/1 figure is
an upper bound on the true eCPRI waiting time: deterministic arrivals are
less bursty than Poisson at equal rate. Agreement is therefore expected to be
close but with simulation at or slightly below the analytical value.
"""

import numpy as np


def analytical_priority_queue(
    ecpri_payload_bytes: float,
    ecpri_rate_per_s: float,
    das_mean_bytes: float,
    das_sigma: float,
    das_rate_per_s: float,
    capacity_bps: float,
    propagation_delay_s: float,
) -> dict:
    """
    Mean sojourn time for the high-priority class under non-preemptive
    strict priority (M/G/1 priority queue).

    Args:
        ecpri_payload_bytes: deterministic eCPRI frame size
        ecpri_rate_per_s: aggregate eCPRI arrival rate at the server
        das_mean_bytes: mean DAS burst size E[X]
        das_sigma: lognormal shape parameter
        das_rate_per_s: aggregate DAS arrival rate at the server
        capacity_bps: link capacity
        propagation_delay_s: one-way propagation delay

    Returns:
        Dict of utilizations, waiting times and predicted sojourn times (µs)
    """
    # Service times
    s1 = (ecpri_payload_bytes * 8) / capacity_bps          # deterministic
    s1_sq = s1 ** 2                                        # E[S^2] = E[S]^2

    # Lognormal with mean m and shape sigma: E[X^2] = m^2 * exp(sigma^2)
    s2 = (das_mean_bytes * 8) / capacity_bps
    s2_sq = (s2 ** 2) * np.exp(das_sigma ** 2)

    rho1 = ecpri_rate_per_s * s1
    rho2 = das_rate_per_s * s2

    # Mean residual service time across both classes
    R = 0.5 * (ecpri_rate_per_s * s1_sq + das_rate_per_s * s2_sq)

    # Non-preemptive priority: high class waits only on residual + own class
    w1 = R / (1.0 - rho1) if rho1 < 1 else float("inf")
    # Low class additionally waits behind all high-priority work
    denom = (1.0 - rho1) * (1.0 - rho1 - rho2)
    w2 = R / denom if (rho1 + rho2) < 1 else float("inf")

    return {
        "rho_ecpri": rho1,
        "rho_das": rho2,
        "rho_total": rho1 + rho2,
        "stable": (rho1 + rho2) < 1.0,
        "ecpri_service_us": s1 * 1e6,
        "das_service_us": s2 * 1e6,
        "ecpri_wait_us": w1 * 1e6,
        "das_wait_us": w2 * 1e6,
        "ecpri_sojourn_us": (w1 + s1 + propagation_delay_s) * 1e6,
        "das_sojourn_us": (w2 + s2 + propagation_delay_s) * 1e6,
    }


def offered_load_from_config(topology_cfg, ecpri_cfg, das_cfg, fiber_cfg) -> dict:
    """
    Compute the analytical prediction for one DU uplink directly from the
    simulation configuration objects, so theory and simulation can never
    silently diverge in their parameters.
    """
    # Per DU: each RRU emits one frame per antenna port per frame period
    ecpri_rate = (
        topology_cfg.num_rrus_per_du
        * ecpri_cfg.num_antenna_ports
        / (ecpri_cfg.frame_period_us / 1e6)
    )
    # One DAS sensor is co-located with each RRU
    das_rate = topology_cfg.num_rrus_per_du * das_cfg.event_rate_per_second

    prop_s = (topology_cfg.du_to_cu_distance_km * 1000) / fiber_cfg.propagation_speed_m_s

    return analytical_priority_queue(
        ecpri_payload_bytes=ecpri_cfg.payload_bytes,
        ecpri_rate_per_s=ecpri_rate,
        das_mean_bytes=das_cfg.burst_size_mean_bytes,
        das_sigma=das_cfg.burst_size_sigma,
        das_rate_per_s=das_rate,
        capacity_bps=fiber_cfg.link_capacity_gbps * 1e9,
        propagation_delay_s=prop_s,
    )

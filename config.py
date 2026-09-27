"""
Centralized simulation configuration.
All scenario parameters are defined here.
"""

from dataclasses import dataclass


@dataclass
class TopologyConfig:
    """Fronthaul network topology parameters."""
    num_rrus_per_du: int = 3
    num_dus_per_cu: int = 2
    rru_to_du_distance_km: float = 5.0  # fiber length
    du_to_cu_distance_km: float = 10.0


@dataclass
class ECPRIConfig:
    """eCPRI traffic parameters."""
    frame_period_us: float = 125.0  # 8 kHz sampling (5G NR standard)
    payload_bytes: int = 9600  # typical for 30 kHz SCS, 273 RBs
    num_antenna_ports: int = 2
    priority: int = 0  # high priority in queuing
    deadline_us: float = 500.0  # fronthaul latency budget (us)


@dataclass
class DASConfig:
    """Distributed Acoustic Sensing parameters."""
    event_rate_per_second: float = 100.0  # Poisson arrival rate
    burst_size_mean_bytes: float = 100_000  # 100 KB mean (lognormal)
    burst_size_sigma: float = 2.0  # lognormal sigma
    priority: int = 1  # low priority in queuing


@dataclass
class FiberLinkConfig:
    """Optical fiber link parameters."""
    propagation_speed_m_s: float = 2e8  # typical for fiber
    link_capacity_gbps: float = 25.0  # 25 Gbps


@dataclass
class SimulationConfig:
    """Simulation runtime parameters."""
    warmup_seconds: float = 1.0  # transient period (not measured)
    measurement_seconds: float = 15.0  # steady-state measurement window
    random_seed: int = 42


# Global singleton config (can be overridden per scenario)
default_config = {
    "topology": TopologyConfig(),
    "ecpri": ECPRIConfig(),
    "das": DASConfig(),
    "fiber": FiberLinkConfig(),
    "simulation": SimulationConfig(),
}

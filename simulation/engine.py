"""
SimPy simulation engine.
Orchestrates the entire network simulation.
"""

import simpy
import numpy as np
from typing import Dict, List
from config import (
    TopologyConfig,
    ECPRIConfig,
    DASConfig,
    FiberLinkConfig,
    SimulationConfig,
)
from topology import FronthaulTopology


class SimulationEngine:
    """
    Main simulation orchestrator using SimPy.
    Manages topology, execution, and metrics collection.
    """

    def __init__(
        self,
        topology_config: TopologyConfig,
        ecpri_config: ECPRIConfig,
        das_config: DASConfig,
        fiber_config: FiberLinkConfig,
        simulation_config: SimulationConfig,
        random_seed: int = 42,
        fiber_events: list = None,
    ):
        """
        Initialize the simulation engine.

        Args:
            topology_config: network topology configuration
            ecpri_config: eCPRI traffic configuration
            das_config: DAS traffic configuration
            fiber_config: fiber link configuration
            simulation_config: simulation parameters
            random_seed: random seed for reproducibility
        """
        self.topology_config = topology_config
        self.ecpri_config = ecpri_config
        self.das_config = das_config
        self.fiber_config = fiber_config
        self.simulation_config = simulation_config
        self.random_seed = random_seed

        self.fiber_events = fiber_events or []
        self.env = None
        self.topology = None
        self.rng = np.random.default_rng(random_seed)

    def run(self) -> Dict:
        """
        Execute the simulation and return metrics.

        Returns:
            Dictionary of simulation results including:
            - end_time: total simulation time
            - metrics: per-CU statistics
            - fiber_link_stats: per-link utilization and throughput
        """
        # Create SimPy environment
        self.env = simpy.Environment()

        # Build topology
        self.topology = FronthaulTopology(
            env=self.env,
            topology_config=self.topology_config,
            fiber_config=self.fiber_config,
            ecpri_config=self.ecpri_config,
            das_config=self.das_config,
            rng=self.rng,
            fiber_events=self.fiber_events,
        )
        self.topology.build()
        self.topology.start_du_forwarding()

        # Run simulation
        total_time = self.simulation_config.warmup_seconds + self.simulation_config.measurement_seconds
        self.env.run(until=total_time)

        # Collect and return results
        results = {
            "end_time": self.env.now,
            "warmup_duration": self.simulation_config.warmup_seconds,
            "measurement_duration": self.simulation_config.measurement_seconds,
            "random_seed": self.random_seed,
        }

        # Collect CU metrics (only post-warmup)
        cu_metrics = {}
        warmup_end = self.simulation_config.warmup_seconds
        for cu in self.topology.cus:
            # Filter messages that arrived after warm-up
            cu.messages_received = [
                m for m in cu.messages_received if m["arrival_time"] > warmup_end
            ]
            cu_metrics[f"CU-{cu.cu_id}"] = cu.get_stats()

        results["cu_metrics"] = cu_metrics

        # Collect fiber link metrics
        fiber_link_stats = {}
        for link in self.topology.fiber_links:
            fiber_link_stats[link.link_id] = {
                "utilization": link.get_utilization(warmup_end, self.env.now),
                "throughput_mbps": link.get_throughput_window(warmup_end, self.env.now),
                "capacity_gbps": self.fiber_config.link_capacity_gbps,
                "transmission_count": len(link.transmission_events),
            }

        results["fiber_link_stats"] = fiber_link_stats

        # Per-DU admission / loss accounting, aggregated across DUs so that
        # dropped traffic is always reported alongside delivered traffic.
        du_stats = [du.get_stats() for du in self.topology.dus]
        results["du_stats"] = du_stats

        ecpri_arrivals = sum(d["ecpri_arrivals"] for d in du_stats)
        ecpri_drops = sum(d["ecpri_drops"] for d in du_stats)
        das_arrivals = sum(d["das_arrivals"] for d in du_stats)
        das_drops = sum(d["das_drops"] for d in du_stats)
        results["loss"] = {
            "ecpri_arrivals": ecpri_arrivals,
            "ecpri_drops": ecpri_drops,
            "ecpri_drop_rate": ecpri_drops / ecpri_arrivals if ecpri_arrivals else 0.0,
            "das_arrivals": das_arrivals,
            "das_drops": das_drops,
            "das_drop_rate": das_drops / das_arrivals if das_arrivals else 0.0,
        }

        # Aggregate statistics
        all_messages = []
        for cu in self.topology.cus:
            all_messages.extend(cu.messages_received)

        ecpri_lat = [m["latency_us"] for m in all_messages
                     if m["message_type"] == "ECPRIFrame"]

        results["total_messages"] = len(all_messages)
        results["avg_latency_us"] = float(np.mean([m["latency_us"] for m in all_messages])) if all_messages else 0
        # eCPRI is the service-critical class; report it separately from the
        # aggregate, which is otherwise skewed by bulk DAS traffic.
        results["ecpri_avg_latency_us"] = float(np.mean(ecpri_lat)) if ecpri_lat else 0

        # Sub-sampled empirical latency distribution for CDF plotting. Storing
        # every sample would carry millions of points through the results dict;
        # a fixed-size quantile grid preserves the tail exactly where it matters.
        if ecpri_lat:
            grid = np.concatenate([
                np.linspace(0, 99, 100),
                np.linspace(99, 100, 101),  # dense sampling in the tail
            ])
            results["ecpri_latency_quantiles"] = {
                "percentiles": grid.tolist(),
                "values_us": np.percentile(ecpri_lat, grid).tolist(),
            }
        else:
            results["ecpri_latency_quantiles"] = {"percentiles": [], "values_us": []}

        return results

    def get_topology_graph(self):
        """Return the NetworkX graph for visualization."""
        if self.topology:
            return self.topology.get_graph_for_visualization()
        return None

    def get_cu_messages(self, cu_id: int = 0) -> List[Dict]:
        """
        Get all messages received by a specific CU.

        Args:
            cu_id: CU identifier

        Returns:
            List of message records
        """
        if cu_id < len(self.topology.cus):
            return self.topology.cus[cu_id].messages_received
        return []

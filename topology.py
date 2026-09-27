"""
Network topology construction and management using NetworkX.
Builds the RRU-DU-CU topology with fiber links.
"""

import networkx as nx
from typing import List, Tuple
from config import TopologyConfig, FiberLinkConfig, ECPRIConfig, DASConfig
from nodes.rru import RRU
from nodes.das_sensor import DASSensor
from nodes.du import DU
from nodes.cu import CU
from network.fiber_link import FiberLink
import simpy
import numpy as np


class FronthaulTopology:
    """
    Represents a 5G/6G fronthaul network topology.
    Manages node and link instantiation.
    """

    def __init__(
        self,
        env: simpy.Environment,
        topology_config: TopologyConfig,
        fiber_config: FiberLinkConfig,
        ecpri_config: ECPRIConfig,
        das_config: DASConfig,
        rng: np.random.Generator,
        fiber_events: list = None,
    ):
        """
        Initialize the topology.

        Args:
            env: SimPy environment
            topology_config: topology parameters
            fiber_config: fiber link parameters
            ecpri_config: eCPRI traffic parameters
            das_config: DAS parameters
            rng: numpy random generator
        """
        self.env = env
        self.topology_config = topology_config
        self.fiber_config = fiber_config
        self.ecpri_config = ecpri_config
        self.das_config = das_config
        self.rng = rng
        self.fiber_events = fiber_events or []

        self.graph = nx.DiGraph()

        # Node and link storage
        self.rrus: List[RRU] = []
        self.dus: List[DU] = []
        self.cus: List[CU] = []
        self.das_sensors: List[DASSensor] = []
        self.fiber_links: List[FiberLink] = []

    def build(self):
        """Build the complete topology."""
        # Create CU(s)
        for cu_id in range(1):  # Single CU in basic topology
            cu = CU(cu_id)
            self.cus.append(cu)
            self.graph.add_node(f"CU-{cu_id}", node_obj=cu, node_type="CU")

        # Create DUs
        for du_id in range(self.topology_config.num_dus_per_cu):
            du_obj = DU(self.env, du_id, None, self.cus[0])  # fiber link set later
            self.dus.append(du_obj)
            self.graph.add_node(f"DU-{du_id}", node_obj=du_obj, node_type="DU")

        # Create DU-to-CU fiber links
        for du_idx, du in enumerate(self.dus):
            link_id = f"DU{du_idx}-CU0"
            du_to_cu_fiber = FiberLink(
                env=self.env,
                link_id=link_id,
                capacity_gbps=self.fiber_config.link_capacity_gbps,
                length_km=self.topology_config.du_to_cu_distance_km,
                propagation_speed_m_s=self.fiber_config.propagation_speed_m_s,
                fiber_events=self.fiber_events,
            )
            du.uplink_fiber = du_to_cu_fiber
            self.fiber_links.append(du_to_cu_fiber)
            self.graph.add_edge(f"DU-{du_idx}", f"CU-0", fiber_link=du_to_cu_fiber, link_type="DU-CU")

        # Create RRUs and DAS sensors for each DU
        for du_idx, du in enumerate(self.dus):
            for rru_id_local in range(self.topology_config.num_rrus_per_du):
                rru_global_id = du_idx * self.topology_config.num_rrus_per_du + rru_id_local

                # Create RRU-to-DU fiber link
                link_id = f"RRU{rru_global_id}-DU{du_idx}"
                rru_to_du_fiber = FiberLink(
                    env=self.env,
                    link_id=link_id,
                    capacity_gbps=self.fiber_config.link_capacity_gbps,
                    length_km=self.topology_config.rru_to_du_distance_km,
                    propagation_speed_m_s=self.fiber_config.propagation_speed_m_s,
                )
                self.fiber_links.append(rru_to_du_fiber)

                # Create RRU
                rru = RRU(
                    env=self.env,
                    rru_id=rru_global_id,
                    frame_period_us=self.ecpri_config.frame_period_us,
                    payload_bytes=self.ecpri_config.payload_bytes,
                    num_antenna_ports=self.ecpri_config.num_antenna_ports,
                    priority=self.ecpri_config.priority,
                    deadline_us=self.ecpri_config.deadline_us,
                    du=du,  # Pass DU reference
                )
                self.rrus.append(rru)
                self.graph.add_node(f"RRU-{rru_global_id}", node_obj=rru, node_type="RRU")
                self.graph.add_edge(
                    f"RRU-{rru_global_id}",
                    f"DU-{du_idx}",
                    fiber_link=rru_to_du_fiber,
                    link_type="RRU-DU",
                )

                # Create DAS sensor co-located with this RRU
                sensor_id = rru_global_id * 10 + 1  # unique ID per RRU
                das_sensor = DASSensor(
                    env=self.env,
                    sensor_id=sensor_id,
                    event_rate_per_second=self.das_config.event_rate_per_second,
                    burst_size_mean_bytes=self.das_config.burst_size_mean_bytes,
                    burst_size_sigma=self.das_config.burst_size_sigma,
                    priority=self.das_config.priority,
                    du=du,  # Pass DU reference
                    rng=self.rng,
                )
                self.das_sensors.append(das_sensor)
                self.graph.add_node(f"DASSensor-{sensor_id}", node_obj=das_sensor, node_type="DASSensor")

                # Start RRU and DAS sensor processes
                self.env.process(rru.run())
                self.env.process(das_sensor.run())

    def start_du_forwarding(self):
        """Start the DU forwarding processes."""
        for du in self.dus:
            self.env.process(du.run())

    def get_graph_for_visualization(self):
        """Return the NetworkX graph for plotting."""
        return self.graph

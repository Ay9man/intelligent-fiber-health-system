"""
RRU (Radio Remote Unit) node.
Generates eCPRI frames at fixed intervals.
"""

import simpy
from network.ecpri_frame import ECPRIFrame


class RRU:
    """
    Radio Remote Unit that generates eCPRI frames periodically.
    Each antenna port generates frames independently.
    """

    def __init__(
        self,
        env: simpy.Environment,
        rru_id: int,
        frame_period_us: float,
        payload_bytes: int,
        num_antenna_ports: int,
        priority: int,
        deadline_us: float,
        du,  # reference to DU node
    ):
        """
        Initialize an RRU.

        Args:
            env: SimPy environment
            rru_id: unique RRU identifier
            frame_period_us: period between frames in microseconds
            payload_bytes: payload size per frame
            num_antenna_ports: number of antenna ports to service
            priority: priority level for eCPRI frames
            deadline_us: deadline from creation time in microseconds
            du: reference to destination DU node
        """
        self.env = env
        self.rru_id = rru_id
        self.frame_period_s = frame_period_us / 1e6  # convert to seconds
        self.payload_bytes = payload_bytes
        self.num_antenna_ports = num_antenna_ports
        self.priority = priority
        self.deadline_us = deadline_us
        self.du = du
        self.message_counter = 0

    def run(self):
        """Main RRU process: generate frames periodically."""
        while True:
            yield self.env.timeout(self.frame_period_s)

            # Generate one frame per antenna port
            for port in range(self.num_antenna_ports):
                self.message_counter += 1
                frame = ECPRIFrame(
                    message_id=self.rru_id * 10000 + self.message_counter,
                    source_rru_id=self.rru_id,
                    sequence_number=self.message_counter,
                    payload_bytes=self.payload_bytes,
                    created_at=self.env.now,
                    priority=self.priority,
                    deadline_us=self.deadline_us,
                )
                # Send to DU
                self.du.receive_message(frame)

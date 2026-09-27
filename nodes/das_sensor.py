"""
DAS (Distributed Acoustic Sensing) sensor node.
Generates acoustic event bursts with Poisson arrival and lognormal burst sizes.
"""

import simpy
import numpy as np
from network.das_message import DASMessage, EventType


class DASSensor:
    """
    A distributed acoustic sensor along the fiber that detects acoustic events
    and generates variable-size bursts of data.
    """

    def __init__(
        self,
        env: simpy.Environment,
        sensor_id: int,
        event_rate_per_second: float,
        burst_size_mean_bytes: float,
        burst_size_sigma: float,
        priority: int,
        du,  # reference to DU node
        rng: np.random.Generator,
    ):
        """
        Initialize a DAS sensor.

        Args:
            env: SimPy environment
            sensor_id: unique sensor identifier
            event_rate_per_second: Poisson arrival rate (events/sec)
            burst_size_mean_bytes: mean burst size in bytes (lognormal)
            burst_size_sigma: lognormal sigma parameter
            priority: priority level for DAS messages
            du: reference to destination DU node
            rng: numpy random generator for reproducibility
        """
        self.env = env
        self.sensor_id = sensor_id
        self.event_rate = event_rate_per_second
        self.burst_size_mean = burst_size_mean_bytes
        self.burst_size_sigma = burst_size_sigma
        self.priority = priority
        self.du = du
        self.rng = rng
        self.message_counter = 0

    def run(self):
        """Main DAS sensor process: generate events with Poisson arrivals."""
        while True:
            # Exponential inter-arrival time
            inter_arrival_s = self.rng.exponential(1.0 / self.event_rate)
            yield self.env.timeout(inter_arrival_s)

            # Lognormal burst size.
            # numpy's `mean` argument is mu, the mean of the underlying normal,
            # and E[X] = exp(mu + sigma^2/2). Passing log(target) as mu inflates
            # the realised mean by exp(sigma^2/2) -- a factor of 7.4 at sigma=2.
            # Subtract sigma^2/2 so E[X] equals the configured mean.
            mu = np.log(self.burst_size_mean) - (self.burst_size_sigma ** 2) / 2
            burst_bytes = int(
                self.rng.lognormal(mean=mu, sigma=self.burst_size_sigma)
            )
            burst_bytes = max(burst_bytes, 100)  # minimum 100 bytes

            # Randomly pick an event type
            event_type = self.rng.choice([
                EventType.VIBRATION,
                EventType.INTRUSION,
                EventType.TEMPERATURE_ANOMALY,
            ])

            self.message_counter += 1
            message = DASMessage(
                message_id=100000 + self.sensor_id * 10000 + self.message_counter,
                sensor_id=self.sensor_id,
                event_type=event_type,
                payload_bytes=burst_bytes,
                created_at=self.env.now,
                priority=self.priority,
            )
            # Send to DU
            self.du.receive_message(message)

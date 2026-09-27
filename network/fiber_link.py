"""
Optical fiber link model with priority-aware scheduling.
"""

import simpy
from typing import List, Union
from .ecpri_frame import ECPRIFrame
from .das_message import DASMessage
from .fiber_events import FiberEvent


class FiberLink:
    """
    Models an optical fiber link with serialization and propagation delays.
    Uses SimPy PriorityResource to enforce eCPRI priority over DAS.
    """

    def __init__(
        self,
        env: simpy.Environment,
        link_id: str,
        capacity_gbps: float,
        length_km: float,
        propagation_speed_m_s: float = 2e8,
        fiber_events: List[FiberEvent] = None,
    ):
        """
        Initialize a fiber link.

        Args:
            env: SimPy environment
            link_id: unique link identifier
            capacity_gbps: link capacity in Gigabits per second
            length_km: fiber length in kilometers
            propagation_speed_m_s: speed of light in fiber (m/s)
        """
        self.env = env
        self.link_id = link_id
        self.capacity_bps = capacity_gbps * 1e9  # convert to bps
        self.length_km = length_km
        self.propagation_speed_m_s = propagation_speed_m_s

        # Calculate propagation delay
        self.propagation_delay_s = (length_km * 1000) / propagation_speed_m_s

        self.fiber_events: List[FiberEvent] = fiber_events or []

        self.resource = simpy.PriorityResource(env, capacity=1)
        self.bytes_transmitted = 0
        self.transmission_events = []

    def get_flight_delay_s(self, at_time: float) -> float:
        """
        Delay experienced by a message in flight: propagation plus any
        additional delay from a fiber fault active on this link.

        This is latency carried by the in-flight message, not transmitter
        holding time, so it is applied outside the link resource.

        Args:
            at_time: time the message entered the fiber

        Returns:
            Flight delay in seconds
        """
        extra_delay_s = 0.0
        for ev in self.fiber_events:
            if ev.start_time <= at_time <= (ev.start_time + ev.duration_seconds):
                extra_delay_s = max(extra_delay_s, ev.impact_on_latency_us / 1e6)
        return self.propagation_delay_s + extra_delay_s

    def transmit(self, message: Union[ECPRIFrame, DASMessage]):
        """
        Occupy the fiber for the time needed to serialize this message.

        Only serialization is modelled here. Propagation is a pipelined
        latency applied to the in-flight message by the caller via
        get_flight_delay_s(), so the transmitter is free as soon as the last
        bit is clocked out. Holding the link for the propagation delay would
        cap throughput at 1/(serialization + propagation) regardless of
        capacity.

        Args:
            message: ECPRIFrame or DASMessage to transmit

        Yields:
            SimPy events for link scheduling and serialization
        """
        msg_type = type(message).__name__
        priority = message.priority

        # Serialization delay (time to clock all bits onto the fiber)
        serialization_delay_s = (message.payload_bytes * 8) / self.capacity_bps

        # Request the link resource with priority
        with self.resource.request(priority=priority) as req:
            yield req  # wait for link availability

            start_time = self.env.now
            self.transmission_events.append({
                "start_time": start_time,
                "message_id": message.message_id,
                "message_type": msg_type,
                "priority": priority,
                "payload_bytes": message.payload_bytes,
            })

            yield self.env.timeout(serialization_delay_s)

            # Last bit is on the fiber: the transmitter is now free.
            end_time = self.env.now
            self.bytes_transmitted += message.payload_bytes

            self.transmission_events[-1]["end_time"] = end_time
            self.transmission_events[-1]["total_delay_s"] = end_time - start_time

            message.link_departure_time = start_time

    def get_utilization(self, start_time: float, end_time: float) -> float:
        """
        Calculate link utilization over a time window.

        Args:
            start_time: window start time
            end_time: window end time

        Returns:
            Utilization as fraction 0.0-1.0
        """
        total_duration = end_time - start_time
        if total_duration <= 0:
            return 0.0

        total_busy_time = 0
        for event in self.transmission_events:
            if event.get("start_time") is not None and event.get("end_time") is not None:
                event_start = max(event["start_time"], start_time)
                event_end = min(event["end_time"], end_time)
                if event_end > event_start:
                    total_busy_time += event_end - event_start

        return min(total_busy_time / total_duration, 1.0)

    def get_throughput_window(self, start_time: float, end_time: float) -> float:
        """
        Calculate throughput in a time window in Mbps.

        Args:
            start_time: window start time
            end_time: window end time

        Returns:
            Throughput in Megabits per second
        """
        total_duration = end_time - start_time
        if total_duration <= 0:
            return 0.0

        bytes_in_window = sum(
            event["payload_bytes"]
            for event in self.transmission_events
            if event.get("end_time") is not None
            and event["end_time"] > start_time
            and event["end_time"] <= end_time
        )

        bits_in_window = bytes_in_window * 8
        throughput_mbps = (bits_in_window / total_duration) / 1e6
        return throughput_mbps

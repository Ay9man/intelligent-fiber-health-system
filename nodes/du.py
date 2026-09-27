"""
DU (Distributed Unit) node.
Aggregates traffic from multiple RRUs and DAS sensors,
forwards to CU with strict priority scheduling.
"""

import simpy
from typing import Union
from network.ecpri_frame import ECPRIFrame
from network.das_message import DASMessage
from network.fiber_link import FiberLink
from nodes.cu import CU


class DU:
    """
    Distributed Unit that aggregates traffic from multiple RRUs and DAS sensors.
    Forwards aggregated traffic toward the CU over a shared uplink fiber.

    Scheduling model
    ----------------
    The DU implements a non-preemptive strict-priority queue: an eCPRI frame is
    always selected ahead of any queued DAS message, but a DAS transmission
    already in progress runs to completion.

    Buffering model
    ---------------
    Each traffic class has its own buffer with independent admission control.
    A shared buffer would let bulk DAS bursts occupy every slot and drop-tail
    arriving eCPRI frames, which inverts the intended priority: scheduling can
    only reorder frames that were admitted in the first place. Per-class
    buffers keep the priority guarantee meaningful under DAS overload.

    Link occupancy model
    --------------------
    Only serialization occupies the link. Propagation delay is a latency
    contribution carried by the in-flight message, not holding time on the
    transmitter, so the DU may begin the next frame while previous bits are
    still in flight (a pipelined link). Charging propagation as service time
    would cap DU throughput at 1/(serialization + propagation) and cause
    unbounded queue growth at offered loads the link can actually sustain.
    """

    def __init__(
        self,
        env: simpy.Environment,
        du_id: int,
        uplink_fiber: FiberLink,
        cu: CU,
        ecpri_buffer_size: int = 1000,
        das_buffer_size: int = 1000,
    ):
        """
        Initialize a DU.

        Args:
            env: SimPy environment
            du_id: unique DU identifier
            uplink_fiber: FiberLink to transmit toward CU
            cu: destination CU node
            ecpri_buffer_size: max buffered eCPRI frames (drop-tail if exceeded)
            das_buffer_size: max buffered DAS messages (drop-tail if exceeded)
        """
        self.env = env
        self.du_id = du_id
        self.uplink_fiber = uplink_fiber
        self.cu = cu
        self.ecpri_buffer_size = ecpri_buffer_size
        self.das_buffer_size = das_buffer_size

        # Independent per-class queues (see class docstring)
        self.ecpri_queue = []
        self.das_queue = []

        # Arrival / loss accounting, reported per class so drops are never silent
        self.ecpri_arrivals = 0
        self.das_arrivals = 0
        self.ecpri_drops = 0
        self.das_drops = 0

        # Signals the forwarding loop that work is available, so the DU sleeps
        # instead of polling. Polling with a fixed timeout adds an artificial
        # scheduling quantum to every measured latency.
        self._work = env.event()

    # ------------------------------------------------------------------ ingress

    def receive_message(self, message: Union[ECPRIFrame, DASMessage]):
        """
        Accept a message from an RRU or DAS sensor into its class buffer.

        Admission is per-class: eCPRI is never rejected on account of DAS
        backlog.

        Args:
            message: message to buffer and forward
        """
        if isinstance(message, ECPRIFrame):
            self.ecpri_arrivals += 1
            if len(self.ecpri_queue) >= self.ecpri_buffer_size:
                self.ecpri_drops += 1
                return
            self.ecpri_queue.append(message)
        else:
            self.das_arrivals += 1
            if len(self.das_queue) >= self.das_buffer_size:
                self.das_drops += 1
                return
            self.das_queue.append(message)

        self._signal_work()

    def _signal_work(self):
        """Wake the forwarding loop if it is idle."""
        if not self._work.triggered:
            self._work.succeed()

    # ------------------------------------------------------------------ egress

    def run(self):
        """
        Main DU process: strict-priority forwarding, eCPRI before DAS.

        Blocks on an event when both queues are empty rather than polling.
        """
        while True:
            if self.ecpri_queue:
                message = self.ecpri_queue.pop(0)
            elif self.das_queue:
                message = self.das_queue.pop(0)
            else:
                # Idle: sleep until the next arrival signals work.
                self._work = self.env.event()
                yield self._work
                continue

            yield self.env.process(self._forward_message(message))

    def _forward_message(self, message: Union[ECPRIFrame, DASMessage]):
        """
        Forward one message to the CU over the uplink fiber.

        Occupies the transmitter for the serialization time only; the
        propagation delay is applied to the in-flight message by a detached
        process so the next frame can begin immediately.

        Args:
            message: message to forward
        """
        yield self.env.process(self.uplink_fiber.transmit(message))
        # Propagation runs concurrently with subsequent transmissions.
        self.env.process(self._deliver_after_propagation(message))

    def _deliver_after_propagation(self, message: Union[ECPRIFrame, DASMessage]):
        """Apply propagation (and any fiber-fault) delay, then deliver to the CU."""
        delay_s = self.uplink_fiber.get_flight_delay_s(self.env.now)
        if delay_s > 0:
            yield self.env.timeout(delay_s)
        message.link_arrival_time = self.env.now
        self.cu.receive(message, self.env.now)

    # ------------------------------------------------------------------ stats

    def get_stats(self) -> dict:
        """Return per-class arrival, drop and backlog counters for this DU."""
        return {
            "du_id": self.du_id,
            "ecpri_arrivals": self.ecpri_arrivals,
            "ecpri_drops": self.ecpri_drops,
            "ecpri_drop_rate": (
                self.ecpri_drops / self.ecpri_arrivals if self.ecpri_arrivals else 0.0
            ),
            "das_arrivals": self.das_arrivals,
            "das_drops": self.das_drops,
            "das_drop_rate": (
                self.das_drops / self.das_arrivals if self.das_arrivals else 0.0
            ),
            "ecpri_backlog_final": len(self.ecpri_queue),
            "das_backlog_final": len(self.das_queue),
        }

"""
CU (Central Unit) node.
Sink that receives all messages and records metrics.
"""

from typing import Union, List, Dict
from network.ecpri_frame import ECPRIFrame
from network.das_message import DASMessage


class CU:
    """
    Central Unit that acts as a sink for all eCPRI and DAS messages.
    Records arrival times for latency and deadline analysis.
    """

    def __init__(self, cu_id: int):
        """
        Initialize a CU.

        Args:
            cu_id: unique CU identifier
        """
        self.cu_id = cu_id
        self.messages_received: List[Dict] = []

    def receive(self, message: Union[ECPRIFrame, DASMessage], arrival_time: float):
        """
        Record reception of a message.

        Args:
            message: ECPRIFrame or DASMessage received
            arrival_time: SimPy time when message arrived
        """
        latency_us = (arrival_time - message.created_at) * 1e6
        msg_type = type(message).__name__

        record = {
            "message_id": message.message_id,
            "message_type": msg_type,
            "priority": message.priority,
            "payload_bytes": message.payload_bytes,
            "created_at": message.created_at,
            "arrival_time": arrival_time,
            "latency_us": latency_us,
        }

        # For eCPRI frames, check deadline
        if isinstance(message, ECPRIFrame):
            deadline_time = message.created_at + (message.deadline_us / 1e6)
            record["deadline_met"] = arrival_time <= deadline_time
            record["deadline_us"] = message.deadline_us
        else:
            record["deadline_met"] = True

        self.messages_received.append(record)

    def get_stats(self):
        """
        Compute aggregate statistics from received messages.

        Returns:
            Dictionary of statistics
        """
        if not self.messages_received:
            return {}

        records = self.messages_received
        latencies = [r["latency_us"] for r in records]
        ecpri_latencies = [r["latency_us"] for r in records if r["message_type"] == "ECPRIFrame"]
        das_latencies = [r["latency_us"] for r in records if r["message_type"] == "DASMessage"]

        stats = {
            "total_messages": len(records),
            "ecpri_messages": len(ecpri_latencies),
            "das_messages": len(das_latencies),
            "mean_latency_us": sum(latencies) / len(latencies) if latencies else 0,
        }

        if ecpri_latencies:
            stats["ecpri_mean_latency_us"] = sum(ecpri_latencies) / len(ecpri_latencies)
            stats["ecpri_p50_latency_us"] = self._percentile(ecpri_latencies, 50)
            stats["ecpri_p95_latency_us"] = self._percentile(ecpri_latencies, 95)
            stats["ecpri_p99_latency_us"] = self._percentile(ecpri_latencies, 99)
            stats["ecpri_max_latency_us"] = max(ecpri_latencies)
            deadline_violations = sum(
                1 for r in records if r["message_type"] == "ECPRIFrame" and not r["deadline_met"]
            )
            stats["ecpri_deadline_violation_rate"] = deadline_violations / len(ecpri_latencies)

        if das_latencies:
            stats["das_mean_latency_us"] = sum(das_latencies) / len(das_latencies)
            stats["das_p50_latency_us"] = self._percentile(das_latencies, 50)
            stats["das_p95_latency_us"] = self._percentile(das_latencies, 95)
            stats["das_p99_latency_us"] = self._percentile(das_latencies, 99)

        return stats

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        """
        Linear-interpolated percentile.

        Indexing as int(n * pct/100) is off by one and reads past the end of
        the list whenever n * pct/100 lands on n (e.g. p95 with n=20), raising
        IndexError. This uses the standard rank-based definition instead.

        Args:
            values: sample values (not required to be sorted)
            pct: percentile in [0, 100]

        Returns:
            The requested percentile of the sample
        """
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return float(ordered[0])
        rank = (pct / 100.0) * (len(ordered) - 1)
        low = int(rank)
        high = min(low + 1, len(ordered) - 1)
        weight = rank - low
        return float(ordered[low] * (1 - weight) + ordered[high] * weight)

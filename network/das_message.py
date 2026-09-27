"""
DAS (Distributed Acoustic Sensing) message data structure.
"""

from dataclasses import dataclass
from enum import Enum


class EventType(Enum):
    """Types of acoustic events."""
    VIBRATION = "vibration"
    INTRUSION = "intrusion"
    TEMPERATURE_ANOMALY = "temperature_anomaly"


@dataclass
class DASMessage:
    """Represents one DAS acoustic event burst."""
    message_id: int
    sensor_id: int  # which fiber segment sensor fired
    event_type: EventType
    payload_bytes: int
    created_at: float  # SimPy simulation time
    priority: int = 1  # low priority

    def __lt__(self, other):
        """Support priority queue ordering (lower priority value = higher priority)."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.message_id < other.message_id

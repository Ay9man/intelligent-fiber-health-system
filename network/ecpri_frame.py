"""
eCPRI frame data structure.
"""

from dataclasses import dataclass


@dataclass
class ECPRIFrame:
    """Represents one eCPRI message unit."""
    message_id: int
    source_rru_id: int
    sequence_number: int
    payload_bytes: int
    created_at: float  # SimPy simulation time
    priority: int = 0  # high priority
    deadline_us: float = 500.0  # absolute deadline in microseconds from creation

    def __lt__(self, other):
        """Support priority queue ordering (lower priority value = higher priority)."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.message_id < other.message_id

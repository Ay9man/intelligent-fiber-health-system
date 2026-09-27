"""
Fiber event simulation - models real-world fiber problems.
DAS can detect these through acoustic sensing.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class EventType(Enum):
    """Types of fiber problems."""
    VIBRATION = "vibration"           # Construction, traffic, earthquakes
    TEMPERATURE_SPIKE = "temp_spike"  # Heat affecting fiber
    FIBER_MICRO_CUT = "micro_cut"     # Small damage, may self-heal
    FIBER_MAJOR_CUT = "major_cut"     # Complete break
    STRAIN = "strain"                 # Tension/bending stress
    INTRUSION = "intrusion"           # Unauthorized access/dig


class SeverityLevel(Enum):
    """Severity of the event."""
    LOW = 1      # Minor, self-resolving
    MEDIUM = 2   # Needs attention within hours
    HIGH = 3     # Needs immediate action
    CRITICAL = 4 # Service at risk NOW


@dataclass
class FiberEvent:
    """Represents a problem event in the fiber."""
    event_id: int
    event_type: EventType
    severity: SeverityLevel
    location_km: float          # Where along fiber (0 to total_length)
    start_time: float           # When it starts (SimPy time)
    duration_seconds: float     # How long it lasts
    acoustic_magnitude: float   # Detectable by DAS (0-100 dB)
    impact_on_latency_us: float # How much latency increase if undetected
    requires_reroute: bool      # Does it need rerouting?

    def end_time(self):
        """When this event ends."""
        return self.start_time + self.duration_seconds

    def __repr__(self):
        return f"FiberEvent({self.event_type.value}, {self.severity.name}, {self.acoustic_magnitude:.1f}dB)"

"""
Intelligent response controller.
When DAS detects fiber problems, the system responds intelligently.
"""

import simpy
from enum import Enum
from typing import List, Dict
from network.fiber_events import SeverityLevel, EventType


class ResponseAction(Enum):
    """Actions the system can take."""
    ALERT = "alert"                           # Alert technician
    REDUCE_DAS_LOAD = "reduce_das_load"       # Less monitoring to free bandwidth
    REROUTE_TRAFFIC = "reroute_traffic"       # Switch to backup fiber
    INCREASE_ECPRI_REDUNDANCY = "redundancy"  # Send eCPRI on backup path
    ISOLATE_PROBLEM = "isolate_problem"       # Disconnect affected segment


class ResponseStrategy:
    """
    Severity-driven decision policy for detected fiber faults.

    Scope: this class models the *decision* stage only. It maps a detected
    event to the set of actions an operator or orchestrator would invoke, and
    records the decision latency. It does not enact those actions on the
    running network -- no traffic is actually rerouted and no segment is
    isolated in the simulation, so the reported eCPRI latencies are
    unmitigated fault impact. Quantifying the benefit of mitigation would
    require a protection-switching model and a backup path, which is left as
    future work.
    """

    def __init__(self, env: simpy.Environment):
        """Initialize response strategy."""
        self.env = env
        self.actions_taken: List[Dict] = []

    def decide_response(self, detected_event: Dict, current_time: float) -> List[ResponseAction]:
        """
        Decide what actions to take based on detected event.

        Args:
            detected_event: Event detected by DAS
            current_time: Current simulation time

        Returns:
            List of actions to execute
        """
        event_type = detected_event.get("event_type")
        severity = detected_event.get("severity")
        location = detected_event.get("location_km")

        actions = []

        # Always alert for all events
        actions.append(ResponseAction.ALERT)

        # Response based on severity
        if severity == "LOW":
            # Minor issue - just monitor more closely
            actions.append(ResponseAction.REDUCE_DAS_LOAD)  # Free up bandwidth for monitoring

        elif severity == "MEDIUM":
            # Moderate issue - prepare for problems
            actions.append(ResponseAction.REDUCE_DAS_LOAD)
            actions.append(ResponseAction.INCREASE_ECPRI_REDUNDANCY)

        elif severity == "HIGH":
            # Serious issue - take precautions
            actions.append(ResponseAction.REDUCE_DAS_LOAD)
            actions.append(ResponseAction.INCREASE_ECPRI_REDUNDANCY)
            actions.append(ResponseAction.REROUTE_TRAFFIC)  # Start rerouting

        elif severity == "CRITICAL":
            # Service at risk - immediate action
            actions.append(ResponseAction.REROUTE_TRAFFIC)        # Must reroute NOW
            actions.append(ResponseAction.INCREASE_ECPRI_REDUNDANCY)
            actions.append(ResponseAction.ISOLATE_PROBLEM)

        # Record action
        self.actions_taken.append({
            "time": current_time,
            "event_type": event_type,
            "severity": severity,
            "location_km": location,
            "actions": [a.value for a in actions],
            "num_actions": len(actions),
        })

        return actions

    def get_response_stats(self) -> Dict:
        """
        Compute system response effectiveness.

        Returns:
            Statistics about how well the system responded
        """
        if not self.actions_taken:
            return {
                "responses_triggered": 0,
                "avg_actions_per_event": 0,
                "reroute_activations": 0,
                "critical_events_handled": 0,
            }

        num_responses = len(self.actions_taken)
        avg_actions = sum(a["num_actions"] for a in self.actions_taken) / num_responses

        reroute_count = sum(
            1 for a in self.actions_taken
            if ResponseAction.REROUTE_TRAFFIC.value in a["actions"]
        )

        return {
            "responses_triggered": num_responses,
            "avg_actions_per_event": avg_actions,
            "reroute_activations": reroute_count,
            "critical_events_handled": sum(
                1 for a in self.actions_taken if a["severity"] == "CRITICAL"
            ),
        }

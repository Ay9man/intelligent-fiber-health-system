"""
DAS Fiber Health Monitor
Detects problems in optical fiber through acoustic sensing.
"""

import simpy
import numpy as np
from typing import List
from network.fiber_events import FiberEvent, EventType


class DASFiberMonitor:
    """
    Distributed Acoustic Sensing for fiber health monitoring.
    Detects vibrations, cuts, temperature changes, etc.
    """

    def __init__(
        self,
        env: simpy.Environment,
        fiber_length_km: float,
        num_sensors: int = 20,
        sensitivity_db: float = 35,
        detection_latency_ms: float = 100,
        false_alarm_rate: float = 0.02,
        attenuation_db_per_km: float = 0.5,
        rng: np.random.Generator = None,
    ):
        self.env = env
        self.fiber_length_km = fiber_length_km
        self.num_sensors = num_sensors
        self.sensor_spacing_km = fiber_length_km / num_sensors
        self.sensitivity_db = sensitivity_db
        self.detection_latency_s = detection_latency_ms / 1000.0
        self.false_alarm_rate = false_alarm_rate
        self.attenuation_db_per_km = attenuation_db_per_km
        self.rng = rng if rng is not None else np.random.default_rng()

        self.detected_events: List[dict] = []
        self.missed_events: List[dict] = []
        self.false_alarms: List[dict] = []
        self.monitoring_active = True

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def can_detect(self, fiber_event: FiberEvent) -> bool:
        """
        Probabilistic detection: signal attenuates with distance from interrogator.
        Detection probability grows with SNR margin above threshold.
        """
        attenuation = fiber_event.location_km * self.attenuation_db_per_km
        effective_magnitude = fiber_event.acoustic_magnitude - attenuation

        if effective_magnitude < self.sensitivity_db:
            return False

        snr_margin = effective_magnitude - self.sensitivity_db
        detection_prob = 1.0 - np.exp(-snr_margin / 10.0)
        return bool(self.rng.random() < detection_prob)

    def detect_event(self, fiber_event: FiberEvent, current_time: float):
        """
        Simulate detecting a fiber event.
        On success, also estimates event location and computes localization error.
        """
        if not self.monitoring_active:
            return

        attenuation = fiber_event.location_km * self.attenuation_db_per_km
        effective_magnitude = fiber_event.acoustic_magnitude - attenuation
        snr_margin = max(effective_magnitude - self.sensitivity_db, 0.01)

        if self.can_detect(fiber_event):
            detection_time = current_time + self.detection_latency_s

            # Localization: Gaussian error inversely proportional to SNR
            snr_linear = 10 ** (snr_margin / 10.0)
            loc_std_km = self.sensor_spacing_km / (2.0 * np.sqrt(snr_linear))
            estimated_km = float(np.clip(
                fiber_event.location_km + self.rng.normal(0, loc_std_km),
                0, self.fiber_length_km,
            ))
            localization_error_m = abs(estimated_km - fiber_event.location_km) * 1000.0

            self.detected_events.append({
                "detection_time": detection_time,
                "event_type": fiber_event.event_type.value,
                "severity": fiber_event.severity.name,
                "location_km": fiber_event.location_km,
                "acoustic_magnitude": fiber_event.acoustic_magnitude,
                "detection_latency_ms": self.detection_latency_s * 1000,
                "detected": True,
                "estimated_location_km": estimated_km,
                "localization_error_m": localization_error_m,
                "snr_margin_db": float(snr_margin),
            })
        else:
            self.missed_events.append({
                "event_type": fiber_event.event_type.value,
                "severity": fiber_event.severity.name,
                "location_km": fiber_event.location_km,
                "acoustic_magnitude": fiber_event.acoustic_magnitude,
                "detected": False,
                "snr_margin_db": float(snr_margin),
            })

    def generate_false_alarms(self, window_seconds: float):
        """
        Generate spurious detections over a monitoring window.

        False alarms are modelled as a Poisson process: `false_alarm_rate` is
        the expected number of spurious alerts per second of monitoring, so the
        count scales with observation time rather than with the number of real
        events. Reporting detection rate without this figure would overstate
        detector quality, since a detector can trivially reach 100% recall by
        alarming constantly.

        Args:
            window_seconds: duration of the monitoring window

        Returns:
            The list of false alarms generated for this window
        """
        if not self.monitoring_active or window_seconds <= 0:
            return self.false_alarms

        expected = self.false_alarm_rate * window_seconds
        num_alarms = int(self.rng.poisson(expected))

        for _ in range(num_alarms):
            self.false_alarms.append({
                "alarm_time": float(self.rng.uniform(0, window_seconds)),
                "false_location_km": float(self.rng.uniform(0, self.fiber_length_km)),
                "false_type": str(self.rng.choice(["vibration", "temperature_spike"])),
            })

        self.false_alarms.sort(key=lambda a: a["alarm_time"])
        return self.false_alarms

    # ------------------------------------------------------------------
    # DAS trace generation
    # ------------------------------------------------------------------

    def generate_das_trace(self, events: list, num_points: int = 500) -> dict:
        """
        Generate synthetic DAS acoustic amplitude trace along fiber.

        Returns dict with:
          distances_km       – x-axis (array)
          normal_amplitude_db – baseline noise floor trace
          fault_amplitude_db  – trace with event signatures added
          sensitivity_threshold_db – current detection threshold
        """
        trace_rng = np.random.default_rng(int(self.rng.integers(1_000_000)))
        distances = np.linspace(0, self.fiber_length_km, num_points)

        noise_floor_db = 20.0
        normal_trace = noise_floor_db + trace_rng.normal(0, 1.5, num_points)

        fault_trace = normal_trace.copy()
        for ev in events:
            loc_km = ev["location_km"] if isinstance(ev, dict) else ev.location_km
            magnitude = ev["acoustic_magnitude"] if isinstance(ev, dict) else ev.acoustic_magnitude
            # Gaussian bell centred on event location; width = 3 × sensor spacing
            spread_km = max(self.sensor_spacing_km * 3, 0.3)
            spike = magnitude * np.exp(
                -0.5 * ((distances - loc_km) / spread_km) ** 2
            )
            fault_trace = np.maximum(fault_trace, spike)

        return {
            "distances_km": distances.tolist(),
            "normal_amplitude_db": normal_trace.tolist(),
            "fault_amplitude_db": fault_trace.tolist(),
            "sensitivity_threshold_db": self.sensitivity_db,
            "fiber_length_km": self.fiber_length_km,
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_detection_stats(self) -> dict:
        total_events = len(self.detected_events) + len(self.missed_events)

        if total_events == 0:
            return {
                "detection_rate": 0,
                "total_events_occurred": 0,
                "events_detected": 0,
                "events_missed": 0,
                "mean_detection_latency_ms": 0,
                "false_alarms": len(self.false_alarms),
                "false_alarm_rate": 0,
                "mean_localization_error_m": 0,
                "precision": 0,
                "recall": 0,
                "f1_score": 0,
            }

        detection_rate = len(self.detected_events) / total_events
        detection_latencies = [e["detection_latency_ms"] for e in self.detected_events]
        loc_errors = [e["localization_error_m"] for e in self.detected_events
                      if "localization_error_m" in e]

        # Detection quality as a classifier: true positives are correctly
        # detected real events, false negatives are misses, and false positives
        # are spurious alarms. Precision guards against a detector that reaches
        # high recall simply by alarming often.
        tp = len(self.detected_events)
        fn = len(self.missed_events)
        fp = len(self.false_alarms)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)

        return {
            "total_events_occurred": total_events,
            "events_detected": tp,
            "events_missed": fn,
            "detection_rate": detection_rate * 100,
            "mean_detection_latency_ms": float(np.mean(detection_latencies)) if detection_latencies else 0,
            "false_alarms": fp,
            "false_alarm_rate": fp / total_events if total_events > 0 else 0,
            "mean_localization_error_m": float(np.mean(loc_errors)) if loc_errors else 0,
            "precision": precision * 100,
            "recall": recall * 100,
            "f1_score": f1 * 100,
        }

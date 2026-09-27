"""
Main entry point for Intelligent Fiber Health Monitoring.
Runs all scenarios, prints a summary, and displays visualizations.
"""

import os
import numpy as np
import simpy

from config import default_config
from simulation.engine import SimulationEngine
from simulation.validation import offered_load_from_config
from nodes.das_fiber_monitor import DASFiberMonitor
from simulation.response_controller import ResponseStrategy
from network.fiber_events import FiberEvent, EventType, SeverityLevel
from visualization.fiber_health_plotter import FiberHealthPlotter


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def create_test_scenarios():
    """
    Controlled fault scenarios spanning the severity range.

    All single-fault scenarios share a common onset at t = 5.0 s and persist to
    the end of the measurement window. Deadline-violation rates are therefore
    comparable across scenarios: they reflect fault severity rather than the
    fraction of the window each fault happened to cover. The cascade scenario
    deliberately staggers its second event to exercise overlapping faults.
    """
    return [
        {
            "name": "Baseline (No Issues)",
            "description": "Normal operation, fiber healthy",
            "events": [],
        },
        {
            "name": "Light Vibration (Construction Nearby)",
            "description": "Low-level vibrations at 5km — borderline detectable",
            "events": [
                FiberEvent(
                    event_id=1,
                    event_type=EventType.VIBRATION,
                    severity=SeverityLevel.LOW,
                    location_km=5.0,
                    start_time=5.0,
                    duration_seconds=30,
                    acoustic_magnitude=45,
                    impact_on_latency_us=50,
                    requires_reroute=False,
                )
            ],
        },
        {
            "name": "Heavy Vibration (Construction)",
            "description": "Sustained vibrations from heavy equipment at 5km",
            "events": [
                FiberEvent(
                    event_id=2,
                    event_type=EventType.VIBRATION,
                    severity=SeverityLevel.MEDIUM,
                    location_km=5.0,
                    start_time=5.0,
                    duration_seconds=300,
                    acoustic_magnitude=70,
                    impact_on_latency_us=200,
                    requires_reroute=False,
                )
            ],
        },
        {
            "name": "Fiber Damage (Micro-cut)",
            "description": "Small fiber damage at 7.5km — high impact if missed",
            "events": [
                FiberEvent(
                    event_id=3,
                    event_type=EventType.FIBER_MICRO_CUT,
                    severity=SeverityLevel.HIGH,
                    location_km=7.5,
                    start_time=5.0,
                    duration_seconds=600,
                    acoustic_magnitude=80,
                    impact_on_latency_us=500,
                    requires_reroute=True,
                )
            ],
        },
        {
            "name": "Critical Fiber Cut",
            "description": "Major fiber cut at 10km — massive latency if undetected",
            "events": [
                FiberEvent(
                    event_id=4,
                    event_type=EventType.FIBER_MAJOR_CUT,
                    severity=SeverityLevel.CRITICAL,
                    location_km=10.0,
                    start_time=5.0,
                    duration_seconds=180,
                    acoustic_magnitude=95,
                    impact_on_latency_us=50000,
                    requires_reroute=True,
                )
            ],
        },
        {
            "name": "Multiple Issues (Cascade)",
            "description": "Vibration at 5km then temperature spike at 8km",
            "events": [
                FiberEvent(
                    event_id=5,
                    event_type=EventType.VIBRATION,
                    severity=SeverityLevel.MEDIUM,
                    location_km=5.0,
                    start_time=5.0,
                    duration_seconds=120,
                    acoustic_magnitude=60,
                    impact_on_latency_us=150,
                    requires_reroute=False,
                ),
                FiberEvent(
                    event_id=6,
                    event_type=EventType.TEMPERATURE_SPIKE,
                    severity=SeverityLevel.HIGH,
                    location_km=8.0,
                    start_time=7.0,
                    duration_seconds=180,
                    acoustic_magnitude=75,
                    impact_on_latency_us=300,
                    requires_reroute=False,
                ),
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Single-scenario runner
# ---------------------------------------------------------------------------

def run_fiber_health_scenario(scenario, seed):
    """
    Run one scenario with its own RNG seed.
    Only detected events trigger responses.

    Returns a fully populated results dict for FiberHealthPlotter.
    """
    cfg = default_config
    cfg["simulation"].warmup_seconds = 1.0
    cfg["simulation"].measurement_seconds = 15.0

    rng = np.random.default_rng(seed)

    print(f"\n  Scenario: {scenario['name']}")
    print(f"  Description: {scenario['description']}")

    temp_env = simpy.Environment()
    das_monitor = DASFiberMonitor(
        env=temp_env,
        fiber_length_km=cfg["topology"].du_to_cu_distance_km,
        num_sensors=20,
        sensitivity_db=35,
        detection_latency_ms=100,
        false_alarm_rate=0.02,
        attenuation_db_per_km=0.5,
        rng=rng,
    )

    response_controller = ResponseStrategy(env=temp_env)

    for event in scenario["events"]:
        pre_count = len(das_monitor.detected_events)
        das_monitor.detect_event(event, event.start_time)

        if len(das_monitor.detected_events) > pre_count:
            det = das_monitor.detected_events[-1]
            detection_time = det["detection_time"]
            response_actions = response_controller.decide_response(
                {
                    "event_type": event.event_type.value,
                    "severity": event.severity.name,
                    "location_km": event.location_km,
                },
                detection_time,
            )
            print(
                f"    [{event.start_time:.2f}s] DETECTED {event.event_type.value} "
                f"(severity: {event.severity.name}) at {event.location_km}km  "
                f"SNR margin: {det['snr_margin_db']:.1f}dB  "
                f"loc error: {det['localization_error_m']:.1f}m"
            )
            print(f"    [{detection_time:.2f}s] Response: {[a.value for a in response_actions]}")
        else:
            print(
                f"    [{event.start_time:.2f}s] MISSED  {event.event_type.value} "
                f"(severity: {event.severity.name}) at {event.location_km}km"
            )

    # Spurious detections accumulated over the monitoring window. Applied to
    # every scenario including the baseline, so the false-alarm cost of
    # continuous monitoring is reported even when no real fault occurs.
    das_monitor.generate_false_alarms(
        window_seconds=cfg["simulation"].measurement_seconds
    )

    # Network simulation (fiber events apply extra latency to DU-CU links)
    engine = SimulationEngine(
        topology_config=cfg["topology"],
        ecpri_config=cfg["ecpri"],
        das_config=cfg["das"],
        fiber_config=cfg["fiber"],
        simulation_config=cfg["simulation"],
        random_seed=seed,
        fiber_events=scenario["events"],
    )
    sim_results = engine.run()

    # DAS acoustic trace
    das_trace = das_monitor.generate_das_trace(scenario["events"])

    return {
        "description": scenario["description"],
        "events": [
            {
                "event_type": e.event_type.value,
                "severity": e.severity.name,
                "location_km": e.location_km,
                "start_time": e.start_time,
                "duration_seconds": e.duration_seconds,
                "acoustic_magnitude": e.acoustic_magnitude,
                "impact_on_latency_us": e.impact_on_latency_us,
            }
            for e in scenario["events"]
        ],
        "das_performance": das_monitor.get_detection_stats(),
        "detection_details": das_monitor.detected_events,
        "missed_details": das_monitor.missed_events,
        "system_response": response_controller.get_response_stats(),
        "response_details": response_controller.actions_taken,
        "ecpri_performance": sim_results["cu_metrics"].get("CU-0", {}),
        "avg_latency_us": sim_results.get("avg_latency_us", 0),
        "ecpri_avg_latency_us": sim_results.get("ecpri_avg_latency_us", 0),
        "ecpri_latency_quantiles": sim_results.get("ecpri_latency_quantiles", {}),
        "loss": sim_results.get("loss", {}),
        "das_trace": das_trace,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Anchor to this file's directory so figures always land in
    # "INTELLIGENT FIBER HEALTH SYSTEM/output" regardless of the
    # working directory the script is launched from.
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 70)
    print("INTELLIGENT FIBER HEALTH MONITORING SYSTEM")
    print("DAS-based Problem Detection & Automated Response")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Model validation against queueing theory (run before scenarios so an
    # unstable or mis-parameterised configuration is caught immediately)
    # ------------------------------------------------------------------
    cfg = default_config
    theory = offered_load_from_config(
        cfg["topology"], cfg["ecpri"], cfg["das"], cfg["fiber"]
    )
    print("\nMODEL VALIDATION (DU uplink, analytical M/G/1 priority queue)")
    print(f"  Offered load: eCPRI rho={theory['rho_ecpri']:.3f}  "
          f"DAS rho={theory['rho_das']:.3f}  total={theory['rho_total']:.3f}  "
          f"{'STABLE' if theory['stable'] else 'UNSTABLE'}")
    print(f"  Predicted eCPRI sojourn: {theory['ecpri_sojourn_us']:.1f}us  "
          f"(deadline {cfg['ecpri'].deadline_us:.0f}us)")
    if not theory["stable"]:
        print("  [WARNING] Offered load exceeds capacity; latencies will diverge.")

    scenarios = create_test_scenarios()
    results_summary = {}

    for i, scenario in enumerate(scenarios):
        seed = 42 + i
        try:
            results_summary[scenario["name"]] = run_fiber_health_scenario(scenario, seed)
            print(f"    [OK] Completed")
        except Exception as e:
            print(f"    [ERROR] {e}")
            import traceback; traceback.print_exc()
            results_summary[scenario["name"]] = {"error": str(e)}

    # ------------------------------------------------------------------
    # Printed summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, res in results_summary.items():
        if "error" in res:
            print(f"\n{name}: ERROR — {res['error']}")
            continue

        das = res["das_performance"]
        resp = res["system_response"]

        print(f"\n{name}:")
        if das.get("total_events_occurred", 0) > 0:
            print(f"  DAS: {das['events_detected']}/{das['total_events_occurred']} detected "
                  f"({das['detection_rate']:.1f}%)  "
                  f"latency {das['mean_detection_latency_ms']:.0f}ms  "
                  f"loc error {das['mean_localization_error_m']:.1f}m")
            print(f"       precision {das['precision']:.1f}%  "
                  f"recall {das['recall']:.1f}%  F1 {das['f1_score']:.1f}%  "
                  f"false alarms {das['false_alarms']}")
        else:
            print(f"  DAS: no events (baseline)  "
                  f"false alarms {das.get('false_alarms', 0)}")
        print(f"  Response: {resp['responses_triggered']} triggered, "
              f"{resp['reroute_activations']} reroutes, "
              f"{resp['critical_events_handled']} critical")

        ec = res.get("ecpri_performance", {})
        loss = res.get("loss", {})
        print(f"  eCPRI latency: mean {ec.get('ecpri_mean_latency_us', 0):.1f}us  "
              f"p99 {ec.get('ecpri_p99_latency_us', 0):.1f}us  "
              f"deadline viol. {ec.get('ecpri_deadline_violation_rate', 0) * 100:.2f}%")
        print(f"  Loss: eCPRI {loss.get('ecpri_drop_rate', 0) * 100:.2f}%  "
              f"DAS {loss.get('das_drop_rate', 0) * 100:.2f}%")

    # ------------------------------------------------------------------
    # Visualizations
    # ------------------------------------------------------------------
    valid = {k: v for k, v in results_summary.items() if "error" not in v}
    if valid:
        plotter = FiberHealthPlotter(results=valid, output_dir=output_dir)
        plotter.generate_all()
    else:
        print("No valid results to plot.")

    print("=" * 70)


if __name__ == "__main__":
    main()

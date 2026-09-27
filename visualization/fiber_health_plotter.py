"""
Visualization for Intelligent Fiber Health Monitoring Results.
Accepts results dict directly — no JSON file required.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from typing import Dict


# Consistent color palette across all plots
SEVERITY_COLORS = {
    "LOW": "steelblue",
    "MEDIUM": "darkorange",
    "HIGH": "crimson",
    "CRITICAL": "darkred",
}
# Keyed on EventType.value (lowercase), which is what the results dict stores.
EVENT_COLORS = {
    "vibration": "steelblue",
    "temp_spike": "darkorange",
    "micro_cut": "crimson",
    "major_cut": "darkred",
    "strain": "seagreen",
    "intrusion": "purple",
}


class FiberHealthPlotter:
    """Generate plots for fiber health monitoring results."""

    def __init__(self, results: Dict, output_dir: str = None):
        # Default to "<project root>/output" rather than a path relative to the
        # current working directory, so figures are written next to the code
        # no matter where the script is launched from.
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "output",
            )
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.results = results
        # Scenarios with at least one event (exclude baseline for most plots)
        self.scenarios = [s for s in results if "No Issues" not in s]
        self.all_scenarios = list(results.keys())

    # ------------------------------------------------------------------ helpers

    def _save(self, filename: str):
        plt.savefig(os.path.join(self.output_dir, filename), dpi=150, bbox_inches="tight")
        print(f"  [saved] {filename}")

    def _short(self, name: str) -> str:
        return name.split("(")[0].strip()

    def _deadline_us(self) -> float:
        """Fronthaul deadline used for reference lines, from the eCPRI config."""
        from config import default_config
        return default_config["ecpri"].deadline_us

    # ================================================================== Plot 1
    def plot_das_trace(self, filename: str = "das_trace.png"):
        """
        DAS acoustic amplitude along fiber for every scenario.
        Normal trace (blue) vs fault trace (red) vs detection threshold (dashed).
        """
        n = len(self.all_scenarios)
        cols = 2
        rows = (n + 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(14, rows * 3.2))
        axes = np.array(axes).flatten()
        fig.suptitle("DAS Acoustic Trace: Normal vs Fault Condition",
                     fontsize=14, fontweight="bold")

        for i, scenario in enumerate(self.all_scenarios):
            ax = axes[i]
            trace = self.results[scenario].get("das_trace", {})
            if not trace:
                ax.text(0.5, 0.5, "No trace data", ha="center", va="center",
                        transform=ax.transAxes)
                ax.set_title(self._short(scenario), fontsize=9)
                continue

            dist = np.array(trace["distances_km"])
            normal = np.array(trace["normal_amplitude_db"])
            fault = np.array(trace["fault_amplitude_db"])
            thresh = trace["sensitivity_threshold_db"]

            ax.fill_between(dist, normal, alpha=0.25, color="royalblue")
            ax.plot(dist, normal, color="royalblue", lw=1.2, label="Normal")
            ax.fill_between(dist, fault, alpha=0.2, color="tomato")
            ax.plot(dist, fault, color="tomato", lw=1.5, label="Fault")
            ax.axhline(thresh, color="black", ls="--", lw=1.2,
                       label=f"Threshold ({thresh} dB)")

            # Mark event locations
            for ev in self.results[scenario].get("events", []):
                ax.axvline(ev["location_km"], color="purple", ls=":", lw=1,
                           alpha=0.8)
                ax.text(ev["location_km"] + 0.1, thresh + 2,
                        f"{ev['location_km']}km", fontsize=7, color="purple")

            ax.set_title(self._short(scenario), fontsize=9, fontweight="bold")
            ax.set_xlabel("Distance (km)", fontsize=8)
            ax.set_ylabel("Amplitude (dB)", fontsize=8)
            ax.set_ylim(0, None)
            ax.grid(alpha=0.3)
            if i == 0:
                ax.legend(fontsize=7)

        for j in range(i + 1, len(axes)):
            axes[j].set_visible(False)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== Plot 2
    def plot_localization_error(self, filename: str = "localization_error.png"):
        """
        Bar chart of mean DAS localization error per scenario.
        Shows both detected and missed events.
        """
        fig, ax = plt.subplots(figsize=(12, 5))

        errors, labels = [], []
        for s in self.scenarios:
            dets = self.results[s].get("detection_details", [])
            errs = [d["localization_error_m"] for d in dets
                    if "localization_error_m" in d]
            errors.append(float(np.mean(errs)) if errs else 0.0)
            labels.append(self._short(s).replace(" ", "\n"))

        colors = ["green" if e > 0 else "lightgray" for e in errors]
        bars = ax.bar(range(len(labels)), errors, color=colors,
                      alpha=0.75, edgecolor="darkgreen", linewidth=1.5)

        for bar, err in zip(bars, errors):
            if err > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{err:.1f} m", ha="center", va="bottom",
                        fontweight="bold", fontsize=10)

        ax.set_ylabel("Localization Error (meters)", fontsize=12, fontweight="bold")
        ax.set_title("DAS Fault Localization Accuracy", fontsize=14, fontweight="bold")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, max(errors) * 1.4 + 5 if errors else 10)

        # Sensor spacing reference line
        das_trace = next(
            (v["das_trace"] for v in self.results.values() if v.get("das_trace")),
            None,
        )
        if das_trace:
            spacing_m = (das_trace["fiber_length_km"] / 20) * 1000
            ax.axhline(spacing_m, color="red", ls="--", lw=1.5,
                       label=f"Sensor spacing ({spacing_m:.0f} m)")
            ax.legend(fontsize=10)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== Plot 3
    def plot_threshold_analysis(self, filename: str = "threshold_analysis.png"):
        """
        Detection probability vs threshold for every event across all scenarios.
        Highlights the currently configured threshold.
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        thresholds = np.linspace(15, 65, 200)
        ATTEN = 0.5  # dB/km — must match das_fiber_monitor

        plotted = 0
        for s in self.scenarios:
            for ev in self.results[s].get("events", []):
                effective = ev["acoustic_magnitude"] - ev["location_km"] * ATTEN
                probs = []
                for t in thresholds:
                    if effective < t:
                        probs.append(0.0)
                    else:
                        margin = effective - t
                        probs.append((1.0 - np.exp(-margin / 10.0)) * 100)

                severity = ev["severity"]
                color = SEVERITY_COLORS.get(severity, "gray")
                label = (f"{self._short(s)} — {ev['event_type'].replace('_',' ')} "
                         f"@{ev['location_km']}km ({ev['acoustic_magnitude']}dB)")
                ax.plot(thresholds, probs, color=color, lw=2, label=label)
                plotted += 1

        if plotted == 0:
            ax.text(0.5, 0.5, "No events to analyse", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12)
        else:
            ax.axvline(35, color="black", ls="--", lw=2,
                       label="Current threshold (35 dB)")
            ax.fill_betweenx([0, 100], 0, 35, alpha=0.05, color="red",
                             label="High-miss zone")

        ax.set_xlabel("Detection Threshold (dB)", fontsize=12, fontweight="bold")
        ax.set_ylabel("Detection Probability (%)", fontsize=12, fontweight="bold")
        ax.set_title("Threshold-Based Detection Analysis", fontsize=14, fontweight="bold")
        ax.set_xlim(thresholds[0], thresholds[-1])
        ax.set_ylim(0, 108)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(alpha=0.3)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== Plot 4
    def plot_latency_cdf(self, filename: str = "latency_cdf.png"):
        """
        eCPRI latency distribution per scenario against the fronthaul deadline.

        Replaces the former BER-vs-SNR figure, whose latency-to-SNR mapping had
        no physical basis. Latency is what this simulator actually measures.
        """
        fig, ax = plt.subplots(figsize=(12, 6.5))

        cmap = plt.cm.tab10
        plotted = 0
        for i, s in enumerate(self.all_scenarios):
            q = self.results[s].get("ecpri_latency_quantiles", {})
            vals = q.get("values_us", [])
            pcts = q.get("percentiles", [])
            if not vals:
                continue
            ax.plot(vals, pcts, color=cmap(i % 10), lw=2, label=self._short(s))
            plotted += 1

        if plotted == 0:
            ax.text(0.5, 0.5, "No eCPRI latency data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12)
        else:
            deadline = self._deadline_us()
            ax.axvline(deadline, color="red", ls="--", lw=2, zorder=10,
                       label=f"Fronthaul deadline ({deadline:.0f} µs)")

        ax.set_xscale("log")
        ax.set_xlabel("eCPRI Latency (µs, log scale)", fontsize=12, fontweight="bold")
        ax.set_ylabel("Cumulative probability (%)", fontsize=12, fontweight="bold")
        ax.set_title("eCPRI Latency CDF vs Fronthaul Deadline",
                     fontsize=14, fontweight="bold")
        ax.set_ylim(0, 101)
        ax.legend(fontsize=9, loc="lower right")
        ax.grid(which="both", alpha=0.3)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== Plot 5
    def plot_detection_time(self, filename: str = "detection_time.png"):
        """
        Detection time breakdown per scenario:
        stacked bar — event start → detection (latency) vs detection → response.
        """
        fig, ax = plt.subplots(figsize=(12, 6))

        labels, det_latencies, resp_delays = [], [], []
        for s in self.scenarios:
            dets = self.results[s].get("detection_details", [])
            resps = self.results[s].get("response_details", [])
            if not dets:
                continue

            avg_det_lat = float(np.mean([d["detection_latency_ms"] for d in dets]))
            # Response delay = response_time - detection_time (in ms)
            if resps and dets:
                avg_resp_delay = float(np.mean([
                    (r["time"] - d["detection_time"]) * 1000
                    for r, d in zip(resps, dets)
                ]))
                avg_resp_delay = max(avg_resp_delay, 0)
            else:
                avg_resp_delay = 0.0

            labels.append(self._short(s).replace(" ", "\n"))
            det_latencies.append(avg_det_lat)
            resp_delays.append(avg_resp_delay)

        if not labels:
            ax.text(0.5, 0.5, "No detections", ha="center", va="center",
                    transform=ax.transAxes)
        else:
            x = range(len(labels))
            b1 = ax.bar(x, det_latencies, color="royalblue", alpha=0.8,
                        label="Detection latency (event → DAS alert)")
            b2 = ax.bar(x, resp_delays, bottom=det_latencies, color="darkorange",
                        alpha=0.8, label="Response delay (DAS alert → action)")

            for i, (dl, rd) in enumerate(zip(det_latencies, resp_delays)):
                total = dl + rd
                ax.text(i, total + 2, f"{total:.0f} ms",
                        ha="center", va="bottom", fontweight="bold", fontsize=10)

            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, fontsize=9)

        ax.set_ylabel("Time (milliseconds)", fontsize=12, fontweight="bold")
        ax.set_title("Detection & Response Time Breakdown",
                     fontsize=14, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== Plot 6
    def plot_comparison_table(self, filename: str = "comparison_table.png"):
        """
        Full scenario comparison table rendered as a matplotlib figure.
        """
        columns = [
            "Scenario",
            "Events",
            "Det. Rate\n(%)",
            "Det. Latency\n(ms)",
            "Loc. Error\n(m)",
            "F1\n(%)",
            "False\nAlarms",
            "Responses",
            "Reroutes",
            "eCPRI Mean\n(µs)",
            "eCPRI p99\n(µs)",
            "Deadline\nViol. (%)",
            "eCPRI Loss\n(%)",
        ]

        rows = []
        for s in self.all_scenarios:
            res = self.results[s]
            das = res.get("das_performance", {})
            resp = res.get("system_response", {})
            ec = res.get("ecpri_performance", {})
            loss = res.get("loss", {})
            rows.append([
                self._short(s),
                das.get("total_events_occurred", 0),
                f"{das.get('detection_rate', 0):.1f}",
                f"{das.get('mean_detection_latency_ms', 0):.0f}",
                f"{das.get('mean_localization_error_m', 0):.1f}",
                f"{das.get('f1_score', 0):.1f}",
                das.get("false_alarms", 0),
                resp.get("responses_triggered", 0),
                resp.get("reroute_activations", 0),
                f"{ec.get('ecpri_mean_latency_us', 0):.1f}",
                f"{ec.get('ecpri_p99_latency_us', 0):.1f}",
                f"{ec.get('ecpri_deadline_violation_rate', 0) * 100:.2f}",
                f"{loss.get('ecpri_drop_rate', 0) * 100:.2f}",
            ])

        # Fail loudly on a header/row width mismatch; matplotlib would
        # otherwise raise an opaque IndexError from deep inside table layout.
        for r in rows:
            if len(r) != len(columns):
                raise ValueError(
                    f"comparison table: {len(columns)} column headers but "
                    f"{len(r)} values in row {r[0]!r}"
                )

        n_rows = len(rows)
        n_cols = len(columns)
        fig_h = max(3.5, 0.55 * (n_rows + 1) + 1.5)
        fig, ax = plt.subplots(figsize=(18, fig_h))
        ax.axis("off")

        tbl = ax.table(
            cellText=rows,
            colLabels=columns,
            loc="center",
            cellLoc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9.5)
        tbl.scale(1, 1.9)

        # Header styling
        for j in range(n_cols):
            cell = tbl[0, j]
            cell.set_facecolor("#1565C0")
            cell.set_text_props(color="white", fontweight="bold")

        # Row styling: alternating + highlight by severity of worst event
        severity_row_color = {
            "CRITICAL": "#FFEBEE",
            "HIGH":     "#FFF3E0",
            "MEDIUM":   "#E8F5E9",
            "LOW":      "#E3F2FD",
        }
        for i, (s, row_data) in enumerate(zip(self.all_scenarios, rows), start=1):
            events = self.results[s].get("events", [])
            if events:
                worst = max(events, key=lambda e: ["LOW","MEDIUM","HIGH","CRITICAL"].index(e["severity"]))
                bg = severity_row_color.get(worst["severity"], "#F5F5F5")
            else:
                bg = "#F5F5F5"
            for j in range(n_cols):
                tbl[i, j].set_facecolor(bg)

        ax.set_title("Scenario Comparison Table", fontsize=14,
                     fontweight="bold", pad=20)

        # Color legend
        legend_patches = [
            Patch(color="#FFEBEE", label="Critical severity"),
            Patch(color="#FFF3E0", label="High severity"),
            Patch(color="#E8F5E9", label="Medium severity"),
            Patch(color="#E3F2FD", label="Low / no event"),
        ]
        ax.legend(handles=legend_patches, loc="lower right", fontsize=8,
                  framealpha=0.9)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== original plots (kept)

    def plot_detection_rate(self, filename: str = "detection_rate.png"):
        fig, ax = plt.subplots(figsize=(12, 5))
        rates, labels = [], []
        for s in self.scenarios:
            das = self.results[s].get("das_performance", {})
            rates.append(das.get("detection_rate", 0))
            labels.append(self._short(s).replace(" ", "\n"))

        bars = ax.bar(range(len(labels)), rates,
                      color="green", alpha=0.7, edgecolor="darkgreen", linewidth=2)
        for bar, r in zip(bars, rates):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{r:.0f}%", ha="center", va="bottom",
                    fontweight="bold", fontsize=11)

        ax.axhline(100, color="r", ls="--", alpha=0.5, label="Perfect detection")
        ax.set_ylabel("Detection Rate (%)", fontsize=12, fontweight="bold")
        ax.set_title("DAS Fiber Problem Detection Effectiveness",
                     fontsize=14, fontweight="bold")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylim(0, 120)
        ax.grid(axis="y", alpha=0.3)
        ax.legend()
        plt.tight_layout()
        self._save(filename)

    def plot_system_response(self, filename: str = "system_response.png"):
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        responses, reroutes, labels = [], [], []
        for s in self.scenarios:
            resp = self.results[s].get("system_response", {})
            responses.append(resp.get("responses_triggered", 0))
            reroutes.append(resp.get("reroute_activations", 0))
            labels.append(self._short(s).replace(" ", "\n"))

        for ax, data, color, ec, title, ylabel in [
            (axes[0], responses, "orange", "darkorange",
             "System Responses Triggered", "Responses"),
            (axes[1], reroutes, "red", "darkred",
             "Automatic Traffic Rerouting", "Reroute Activations"),
        ]:
            bars = ax.bar(range(len(labels)), data,
                          color=color, alpha=0.7, edgecolor=ec, linewidth=2)
            for bar, v in zip(bars, data):
                if bar.get_height() > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + 0.05,
                            str(int(v)), ha="center", va="bottom", fontweight="bold")
            ax.set_title(title, fontsize=12, fontweight="bold")
            ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=9)
            ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        self._save(filename)

    def plot_contribution_summary(self, filename: str = "contribution_summary.png"):
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("Intelligent Fiber Monitoring — Contribution Summary",
                     fontsize=15, fontweight="bold")
        labels = [self._short(s) for s in self.scenarios]

        # (0,0) Detected vs Missed
        ax = axes[0, 0]
        det = [self.results[s]["das_performance"].get("events_detected", 0) for s in self.scenarios]
        mis = [self.results[s]["das_performance"].get("events_missed", 0) for s in self.scenarios]
        x = np.arange(len(labels))
        ax.bar(x - 0.175, det, 0.35, label="Detected", color="green", alpha=0.8)
        ax.bar(x + 0.175, mis, 0.35, label="Missed", color="red", alpha=0.8)
        ax.set_title("Detection Success", fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
        ax.legend(); ax.grid(axis="y", alpha=0.3)

        # (0,1) Detector quality: precision vs recall
        ax = axes[0, 1]
        prec = [self.results[s]["das_performance"].get("precision", 0) for s in self.scenarios]
        rec = [self.results[s]["das_performance"].get("recall", 0) for s in self.scenarios]
        x = np.arange(len(labels))
        ax.bar(x - 0.175, prec, 0.35, label="Precision", color="teal", alpha=0.85)
        ax.bar(x + 0.175, rec, 0.35, label="Recall", color="goldenrod", alpha=0.85)
        ax.set_ylabel("%", fontweight="bold")
        ax.set_ylim(0, 112)
        ax.set_title("Detector Quality (Precision vs Recall)", fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
        ax.legend(fontsize=9); ax.grid(axis="y", alpha=0.3)

        # (1,0) Critical events handled
        ax = axes[1, 0]
        crit = [self.results[s]["system_response"].get("critical_events_handled", 0) for s in self.scenarios]
        bars = ax.bar(range(len(labels)), crit, color="darkred", alpha=0.8)
        for bar, v in zip(bars, crit):
            if bar.get_height() > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                        str(int(v)), ha="center", va="bottom", fontweight="bold")
        ax.set_title("Emergency Response Capability", fontweight="bold")
        ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
        ax.grid(axis="y", alpha=0.3)

        # (1,1) eCPRI latency against the fronthaul deadline
        ax = axes[1, 1]
        deadline = self._deadline_us()
        latencies = [
            self.results[s].get("ecpri_performance", {}).get("ecpri_mean_latency_us", 0)
            for s in self.scenarios
        ]
        # Log scale: fault latencies span two orders of magnitude, so a linear
        # axis compresses every sub-deadline scenario into the baseline.
        bar_colors = ["crimson" if v > deadline else "purple" for v in latencies]
        bars = ax.bar(range(len(labels)), latencies, color=bar_colors, alpha=0.8)
        ax.set_yscale("log")
        ax.axhline(deadline, color="green", ls="--", lw=2,
                   label=f"{deadline:.0f}µs deadline", alpha=0.7)
        for bar, v in zip(bars, latencies):
            if bar.get_height() > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.08,
                        f"{v:.0f}µs", ha="center", va="bottom", fontweight="bold", fontsize=9)
        ax.set_ylabel("Mean eCPRI Latency (µs, log scale)", fontweight="bold")
        ax.set_title("eCPRI Service Quality (incl. fault impact)", fontweight="bold")
        ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
        ax.legend(); ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()
        self._save(filename)

    def plot_timeline(self, filename: str = "timeline.png"):
        """Real-time timeline using actual simulation timestamps."""
        fig, ax = plt.subplots(
            figsize=(16, max(6, len(self.all_scenarios) * 1.4))
        )

        from config import default_config
        warmup = default_config["simulation"].warmup_seconds
        sim_end = warmup + default_config["simulation"].measurement_seconds

        for i, scenario in enumerate(self.all_scenarios):
            y = len(self.all_scenarios) - i
            res = self.results[scenario]
            ax.axhline(y=y, color="gray", lw=0.6, alpha=0.4)

            for ev in res.get("events", []):
                color = EVENT_COLORS.get(ev["event_type"], "gray")
                # Faults typically outlast the simulation; clip the drawn bar to
                # the window so the axis is not stretched by a 600 s duration.
                drawn_end = min(ev["start_time"] + ev["duration_seconds"], sim_end)
                drawn_dur = max(drawn_end - ev["start_time"], 0)
                ax.barh(y, drawn_dur, left=ev["start_time"],
                        height=0.45, color=color, alpha=0.45, align="center", zorder=2)
                ax.text(ev["start_time"] + drawn_dur / 2, y + 0.28,
                        f"{ev['event_type'].replace('_',' ')}\n@{ev['location_km']}km",
                        ha="center", va="bottom", fontsize=7.5,
                        fontweight="bold", color=color)

            for det in res.get("detection_details", []):
                dt = det["detection_time"]
                ax.plot(dt, y, "v", ms=11, color="limegreen",
                        markeredgecolor="darkgreen", markeredgewidth=1, zorder=4)
                ax.text(dt, y - 0.28, f"t={dt:.1f}s",
                        ha="center", va="top", fontsize=7, color="darkgreen")

            for resp in res.get("response_details", []):
                rt = resp["time"]
                ax.plot(rt, y, "s", ms=9, color="mediumpurple",
                        markeredgecolor="purple", markeredgewidth=1, zorder=4)
                if "reroute_traffic" in resp.get("actions", []):
                    ax.plot(rt + 0.05, y, "^", ms=9, color="red",
                            markeredgecolor="darkred", markeredgewidth=1, zorder=5)

            ax.text(-0.02 * sim_end, y, self._short(scenario),
                    ha="right", va="center", fontsize=9.5, fontweight="bold")

        ax.axvspan(0, warmup, alpha=0.08, color="gray")
        ax.axvline(warmup, color="gray", lw=1, ls=":", alpha=0.6)
        # Leave room on the left for the scenario labels drawn at x < 0.
        ax.set_xlim(-0.32 * sim_end, sim_end)
        ax.set_ylim(0.2, len(self.all_scenarios) + 0.8)
        ax.set_xlabel("Simulation Time (seconds)", fontsize=12, fontweight="bold")
        ax.set_title("Fiber Event Timeline: Event → Detection → Response",
                     fontsize=13, fontweight="bold")
        ax.set_yticks([])
        ax.grid(axis="x", alpha=0.3)

        legend_elements = [
            Patch(color="steelblue", alpha=0.5, label="Vibration"),
            Patch(color="darkorange", alpha=0.5, label="Temp Spike"),
            Patch(color="crimson", alpha=0.5, label="Micro Cut"),
            Patch(color="darkred", alpha=0.5, label="Major Cut"),
            Line2D([0],[0], marker="v", color="limegreen", ms=10,
                   markeredgecolor="darkgreen", ls="none", label="DAS Detection"),
            Line2D([0],[0], marker="s", color="mediumpurple", ms=9,
                   markeredgecolor="purple", ls="none", label="Response"),
            Line2D([0],[0], marker="^", color="red", ms=9,
                   markeredgecolor="darkred", ls="none", label="Reroute"),
            Patch(color="gray", alpha=0.1, label=f"Warmup ({warmup:.0f}s)"),
        ]
        ax.legend(handles=legend_elements, loc="upper right",
                  fontsize=9, framealpha=0.9)

        plt.tight_layout()
        self._save(filename)

    # ================================================================== main entry

    def generate_all(self):
        """Generate all plots, save PNGs, then display all windows together."""
        print("\n" + "=" * 70)
        print("GENERATING VISUALIZATIONS")
        print("=" * 70)

        # Original plots
        self.plot_detection_rate()
        self.plot_system_response()
        self.plot_contribution_summary()
        self.plot_timeline()

        # New enhanced plots
        self.plot_das_trace()
        self.plot_localization_error()
        self.plot_threshold_analysis()
        self.plot_latency_cdf()
        self.plot_detection_time()
        self.plot_comparison_table()

        print(f"\nAll plots saved to: {self.output_dir}/")
        plt.close("all")

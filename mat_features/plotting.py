"""Optional, headless diagnostic plots of the primary extraction setting."""
from pathlib import Path
import numpy as np


def plot_result(result, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse

    trace = result.trace
    feature = next(row for row in result.features if row["is_primary"])
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    raw_time, raw_z = trace["raw_time"], trace["raw_signals"]
    z = raw_z.copy()
    z[~trace["occupied"], 2:] = np.nan  # Unloaded maps have no interpretable CoP.
    axes[0, 0].plot(raw_time, z[:, 0], color="0.6", lw=1, label="Thresholded frames")
    axes[0, 0].axhline(feature["occupancy_gate"], color="#b56b09", ls=":", label="Occupancy gate")
    axes[0, 0].set(xlabel="Time from first analysed frame (s)", ylabel="Total sensor response (counts)")
    axes[1, 0].plot(raw_time, z[:, 1], color="0.6", lw=1)
    axes[1, 0].set(xlabel="Time from first analysed frame (s)", ylabel="Active cells")
    if "signals" in trace:
        time, signals = trace["time"], trace["signals"]
        for ax, column in ((axes[0, 0], 0), (axes[1, 0], 1)):
            ax.axvspan(time[0], time[-1], color="#007a87", alpha=.12)
            ax.plot(time, signals[:, column], color="#007a87", lw=1.5, label="Selected, smoothed interval")
        xy = signals[:, 2:4]
        axes[0, 1].plot(xy[:, 1], xy[:, 0], color="#007a87", lw=1)
        axes[0, 1].scatter(xy[0, 1], xy[0, 0], s=25, color="#b56b09", label="Start")
        if len(xy) > 2:
            covariance = np.cov(xy[:, ::-1], rowvar=False)
            values, vectors = np.linalg.eigh(covariance)
            order = np.argsort(values)[::-1]
            values, vectors = np.maximum(values[order], 0), vectors[:, order]
            angle = np.degrees(np.arctan2(vectors[1, 0], vectors[0, 0]))
            axes[0, 1].add_patch(Ellipse(xy[:, ::-1].mean(axis=0),
                width=2*np.sqrt(5.991464547*values[0]), height=2*np.sqrt(5.991464547*values[1]),
                angle=angle, fill=False, color="#b56b09", ls="--", label="95% covariance ellipse"))
        axes[0, 1].set(xlabel="CoP column (cell units)", ylabel="CoP row (cell units)")
        axes[0, 1].set_aspect("equal", adjustable="datalim")
        axes[0, 1].legend(fontsize=8)
        map_image = axes[1, 1].imshow(trace["representative_map"], origin="lower", aspect="auto", cmap="viridis")
        axes[1, 1].set(xlabel="Native column index", ylabel="Native row index", title="Middle frame of selected raw interval")
        fig.colorbar(map_image, ax=axes[1, 1], label="Sensor response (counts)")
    else:
        for ax in (axes[0, 1], axes[1, 1]):
            ax.text(.5, .5, "No eligible occupied interval", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
    axes[0, 0].legend(fontsize=8)
    details = "No feature estimate"
    if feature["status"] == "ok":
        details = (f"CoP speed {feature['cop_speed']:.3g} cells/s | ellipse {feature['cop_ellipse']:.3g} cells² | "
                   f"response CV {feature['load_cv_pct']:.2f}% | contact CV {feature['contact_cv_pct']:.2f}%")
    qc = "QC pass" if result.audit["qc_pass"] else "QC flags: " + result.audit["qc_flags"]
    fig.suptitle(f"{result.audit['filename']}\n{details}\n{qc}", fontsize=10)
    fig.savefig(Path(destination), dpi=160)
    plt.close(fig)

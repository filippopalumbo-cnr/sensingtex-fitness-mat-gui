"""Portable batch CLI. Raw recordings are read only and never copied to outputs."""
import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import numpy as np
import scipy

from . import __version__
from .config import ExtractionConfig
from .core import extract_file
from .demo import generate_demo
from .recording import RecordingError, looks_like_recording


def write_csv(path, rows, required_columns):
    columns = list(dict.fromkeys(list(required_columns) + [key for row in rows for key in row]))
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run_batch(source, output, config, *, sensitivity=False, plots=False, save_traces=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.exists():
        raise ValueError(f"Input does not exist: {source}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output must be a new or empty directory; existing results are never overwritten")
    if source == output:
        raise ValueError("Input and output must differ")
    if plots and importlib.util.find_spec("matplotlib") is None:
        raise ValueError('Plots require matplotlib: python -m pip install ".[plots]"')
    candidates, skipped = [], []
    base = source if source.is_dir() else source.parent
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".csv") if source.is_dir() else [source]
    for path in files:
        if source.is_file() or looks_like_recording(path):
            candidates.append(path)
        else:
            skipped.append(dict(source_path=path.relative_to(base).as_posix(), reason="not_a_mat_recording_header"))
    if not candidates:
        raise ValueError("No candidate mat CSVs found; input must contain Timestamp + sensor columns or numeric headerless rows")
    output.mkdir(parents=True, exist_ok=True)
    if plots:
        (output / "plots").mkdir()
    if save_traces:
        (output / "traces").mkdir()
    audits, features, errors = [], [], []
    started = datetime.now(timezone.utc).isoformat()
    for index, path in enumerate(candidates, 1):
        relative = path.relative_to(base).as_posix()
        # Hash the complete relative path, so same-named files in different folders stay separate.
        record_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()
        identity = dict(record_id=record_id, source_path=relative)
        try:
            result = extract_file(path, config, sensitivity=sensitivity)
        except (RecordingError, OSError) as exc:
            errors.append(dict(identity, error_type=type(exc).__name__, error=str(exc)))
            continue
        result.audit.update(identity)
        for row in result.features:
            row.update(identity)
        if save_traces:
            np.savez_compressed(output / "traces" / f"{record_id}.npz", **result.trace)
        if plots:
            from .plotting import plot_result
            plot_result(result, output / "plots" / f"{record_id}.png")
        audits.append(result.audit)
        features.extend(result.features)
        if index % 25 == 0:
            print(f"Processed {index}/{len(candidates)}", flush=True)
    write_csv(output / "features.csv", features, ["record_id", "source_path", "filename", "participant", "date", "exercise",
              "threshold", "trim", "is_primary", "status", "reason", "cop_speed", "cop_ellipse", "load_cv", "contact_cv", "qc_pass", "qc_flags"])
    write_csv(output / "quality_audit.csv", audits, ["record_id", "source_path", "filename", "sha256", "n_input_frames", "n_frames",
              "header_present", "first_data_row_skipped", "primary_feature_eligible", "qc_pass", "qc_flags"])
    write_csv(output / "processing_errors.csv", errors, ["record_id", "source_path", "error_type", "error"])
    write_csv(output / "skipped_files.csv", skipped, ["source_path", "reason"])
    manifest = dict(package="the-gui-mat-features", version=__version__, started_utc=started,
                    finished_utc=datetime.now(timezone.utc).isoformat(), config=config.to_dict(),
                    sensitivity=sensitivity, plots=plots, save_traces=save_traces,
                    python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                    platform=platform.platform(), candidates=len(candidates), processed=len(audits), errors=len(errors),
                    ignored_non_mat_csvs=len(skipped), primary_eligible=sum(a["primary_feature_eligible"] for a in audits),
                    qc_pass=sum(a["qc_pass"] for a in audits),
                    header_policy="skip_first_line_legacy" if config.legacy_skip_first_line else "auto_preserve_data_rows",
                    input_modified=False, event_recognition="not_performed",
                    qc_policy="flags only; estimates retained; sensitivity variants share primary QC")
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(f"Processed {len(audits)} recordings; {manifest['primary_eligible']} feature-eligible; "
          f"{len(errors)} errors; {len(skipped)} non-mat CSVs ignored. Results: {output}")
    return 2 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline features for 80 x 28 SensingTex mat CSVs")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Extract features from a CSV or recursively from a folder")
    extract.add_argument("input", type=Path)
    extract.add_argument("--output", required=True, type=Path)
    extract.add_argument("--config", type=Path, help="JSON config; omitted fields keep defaults")
    extract.add_argument("--sensitivity", action="store_true", help="Also evaluate thresholds 100/150/200 and end trims 0/0.1")
    extract.add_argument("--plots", action="store_true")
    extract.add_argument("--save-traces", action="store_true")
    extract.add_argument("--legacy-skip-first-line", action="store_true", help="Reproduce the earlier row-skipping behavior, including headerless files")
    demo = commands.add_parser("demo", help="Generate a clearly labelled synthetic recording")
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            print(generate_demo(args.output))
            return 0
        values = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        config = ExtractionConfig.from_dict(values)
        if args.legacy_skip_first_line:
            config = replace(config, legacy_skip_first_line=True)
        if config.legacy_skip_first_line:
            print("Compatibility mode: the first DATA row of headerless files will be skipped.", file=sys.stderr)
        return run_batch(args.input, args.output, config, sensitivity=args.sensitivity,
                         plots=args.plots, save_traces=args.save_traces)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

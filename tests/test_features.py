"""Numerical and failure-path tests. Every fixture is generated synthetic data."""
import csv
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np

from mat_features import ExtractionConfig, extract_arrays, extract_file
from mat_features.cli import run_batch
from mat_features.core import describe_segment, occupied_bouts
from mat_features.demo import generate_demo
from mat_features.recording import RecordingError


def fixture():
    t = 1736942400.0 + np.arange(0, 20, .25)
    raw = np.zeros((len(t), 4))
    raw[:, 0] = 6000
    return t, raw


def save(path, t, raw, header=True):
    np.savetxt(path, np.column_stack((t, raw)), delimiter=",", fmt="%.8f",
               header="Timestamp,"+",".join(f"Sensor_{k}" for k in range(raw.shape[1])) if header else "",
               comments="")


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = ExtractionConfig(rows=2, cols=2)
        self.t, self.raw = fixture()

    def test_header_auto_preserves_rows_and_features(self):
        a, b = self.root / "header.csv", self.root / "plain.csv"
        save(a, self.t, self.raw)
        save(b, self.t, self.raw, False)
        left, right = extract_file(a, self.cfg), extract_file(b, self.cfg)
        self.assertEqual(left.audit["n_frames"], len(self.t))
        self.assertEqual(right.audit["n_frames"], len(self.t))
        self.assertTrue(left.audit["header_present"])
        self.assertFalse(right.audit["header_present"])
        for feature in ("cop_speed", "cop_ellipse", "load_cv", "contact_cv"):
            self.assertEqual(left.features[0][feature], right.features[0][feature])

    def test_legacy_skips_data_only_when_headerless(self):
        for header in (True, False):
            with self.subTest(header=header):
                path = self.root / f"{header}.csv"
                save(path, self.t, self.raw, header)
                result = extract_file(path, replace(self.cfg, legacy_skip_first_line=True))
                self.assertEqual(result.audit["n_frames"], len(self.t)-int(not header))
                self.assertEqual(result.audit["first_data_row_skipped"], int(not header))

    def test_static_features_and_frozen_flag(self):
        result = extract_arrays(self.t, self.raw, self.cfg)
        for name in ("cop_speed", "cop_ellipse", "load_cv", "contact_cv"):
            self.assertEqual(result.features[0][name], 0)
        self.assertIn("identical_occupied_frames", result.audit["qc_flags"])

    def test_known_linear_centroid_speed(self):
        raw = self.raw.copy()
        raw[:, 0] = 6000 - np.arange(len(self.t))*40
        raw[:, 1] = np.arange(len(self.t))*40
        cfg = replace(self.cfg, threshold=0, smoothing_seconds=0)
        result = extract_arrays(self.t, raw, cfg)
        self.assertAlmostEqual(result.features[0]["cop_speed"], (40/6000)/.25, places=12)
        self.assertEqual(result.features[0]["cop_ellipse"], 0)
        self.assertTrue(result.audit["qc_pass"])

    def test_ellipse_and_cv_definitions(self):
        times = np.arange(4.)
        z = np.array([[2, 1, -1, -1], [4, 2, -1, 1], [2, 1, 1, -1], [4, 2, 1, 1.]])
        result = describe_segment(times, z)
        self.assertAlmostEqual(result["cop_ellipse"], np.pi*5.991464547*4/3)
        self.assertAlmostEqual(result["load_cv"], 1/3)
        self.assertAlmostEqual(result["contact_cv"], 1/3)
        self.assertAlmostEqual(result["load_cv_pct"], 100/3)

    def test_no_input_mutation(self):
        before = self.raw.copy()
        extract_arrays(self.t, self.raw, self.cfg)
        np.testing.assert_array_equal(self.raw, before)

    def test_threshold_boundary_included(self):
        self.raw[:, 1] = 150
        self.raw[:, 2] = 149
        r = extract_arrays(self.t, self.raw, self.cfg)
        self.assertTrue(np.all(r.trace["raw_signals"][:, 0] == 6150))
        self.assertTrue(np.all(r.trace["raw_signals"][:, 1] == 2))

    def test_empty_load_is_ineligible_not_frozen(self):
        result = extract_arrays(self.t, self.raw*0, self.cfg)
        self.assertEqual(result.features[0]["status"], "ineligible")
        self.assertNotIn("cop_speed", result.features[0])
        self.assertEqual(result.audit["longest_identical_run_seconds"], 0)

    def test_endpoint_exclusion_and_short_resampling(self):
        t = 1736942400.0 + np.arange(6.)
        result = extract_arrays(t, np.tile([6000, 0, 0, 0], (6, 1)), self.cfg)
        self.assertEqual(result.features[0]["reason"], "too_few_resampled_frames")
        self.assertEqual(len(result.trace["time"]), 5)

    def test_long_gap_and_unoccupied_frame_split_bouts(self):
        t = np.array([0, .5, 1, 1.5, 5, 5.5, 6])
        mask = np.array([1, 1, 0, 1, 1, 1, 1], bool)
        bouts = occupied_bouts(mask, t, 1)
        self.assertEqual([b.tolist() for b in bouts], [[0, 1], [3], [4, 5, 6]])

    def test_longest_interval_and_tie_choose_first(self):
        t = np.r_[np.arange(0, 8, .25), np.arange(20, 28, .25)] + 1736942400
        result = extract_arrays(t, np.tile([6000, 0, 0, 0], (len(t), 1)), self.cfg)
        self.assertEqual(result.features[0]["raw_segment_first_index"], 0)
        self.assertLess(result.trace["time"][-1], 8)
        t[-1] += .25
        result = extract_arrays(t, np.tile([6000, 0, 0, 0], (len(t), 1)), self.cfg)
        self.assertEqual(result.features[0]["raw_segment_first_index"], 32)

    def test_frozen_run_does_not_cross_long_gap(self):
        t = np.array([0, .5, 1, 4, 4.5, 5]) + 1736942400
        result = extract_arrays(t, np.tile([6000, 0, 0, 0], (6, 1)), self.cfg)
        self.assertEqual(result.audit["longest_identical_run_seconds"], 1)

    def test_filename_local_date_and_participant(self):
        stamp = datetime(2025, 1, 15, 23, 30, tzinfo=timezone.utc).timestamp()
        t = stamp + np.arange(len(self.t))*.25
        name = f"{int(stamp*1000)}_synthetic_person_ex_3.csv"
        r = extract_arrays(t, self.raw, self.cfg, filename=name)
        self.assertEqual(r.audit["date"], "2025-01-16")
        self.assertEqual(r.audit["participant"], "synthetic_person")
        self.assertEqual(r.audit["exercise"], 3)
        self.assertTrue(r.audit["filename_date_match"])

    def test_filename_date_mismatch_is_rejected(self):
        name = f"{int((self.t[0]-86400)*1000)}_synthetic_ex_1.csv"
        with self.assertRaisesRegex(RecordingError, "disagrees"):
            extract_arrays(self.t, self.raw, self.cfg, filename=name)
        r = extract_arrays(self.t, self.raw, replace(self.cfg, check_filename_date=False), filename=name)
        self.assertFalse(r.audit["filename_date_match"])

    def test_bad_values_rejected(self):
        for value in (-1, 65536, .5, np.nan, np.inf):
            with self.subTest(value=value):
                raw = self.raw.copy()
                raw[4, 0] = value
                with self.assertRaises(RecordingError):
                    extract_arrays(self.t, raw, self.cfg)

    def test_bad_timestamp_or_shape_rejected(self):
        for time in (self.t[::-1], np.r_[self.t[0], self.t[:-1]], self.t[:2], self.t+np.nan):
            with self.subTest(time=time[:2]):
                with self.assertRaises(RecordingError):
                    extract_arrays(time, self.raw[:len(time)], self.cfg)
        with self.assertRaises(RecordingError):
            extract_arrays(self.t, self.raw[:, :3], self.cfg)

    def test_bad_headers_and_rows_rejected(self):
        for contents in ("", "Timestamp,Sensor_1,Sensor_0,Sensor_2,Sensor_3\n1,1,1,1,1\n",
                         "Timestamp,Sensor_0,Sensor_1,Sensor_2,Sensor_3\n", "1,1,1,1,1\n\n",
                         "1,1,1,1,1\n2,1,1,1\n3,1,1,1,1\n"):
            path = self.root / "bad.csv"
            path.write_text(contents)
            with self.assertRaises(RecordingError):
                extract_file(path, self.cfg)

    def test_sensitivity_keeps_primary_qc(self):
        result = extract_arrays(self.t, self.raw, self.cfg, sensitivity=True)
        self.assertEqual(len(result.features), 6)
        self.assertEqual(sum(r["is_primary"] for r in result.features), 1)
        self.assertEqual(len({r["qc_flags"] for r in result.features}), 1)
        trimmed = next(r for r in result.features if r["threshold"] == 150 and r["trim"] == .1)
        self.assertLess(trimmed["segment_duration"], result.features[0]["segment_duration"])

    def test_invalid_configuration(self):
        for values in ({"typo": 1}, {"trim_fraction": .5}, {"threshold": -1}, {"min_frames": 2},
                       {"rows": True}, {"timezone": "not_a_zone"}, {"smoothing_seconds": float("nan")},
                       {"legacy_skip_first_line": "true"}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    ExtractionConfig.from_dict(values)

    def test_batch_identity_errors_and_metadata_skips(self):
        source = self.root / "source"
        for folder in ("one", "two"):
            (source / folder).mkdir(parents=True)
            save(source / folder / "same.csv", self.t, self.raw)
        (source / "scores.csv").write_text("date,SDT,GUI\n2025-01-15,4,1\n")
        (source / "broken.csv").write_text("Timestamp,Sensor_0\n1,2\n")
        output = self.root / "output"
        code = run_batch(source, output, self.cfg, save_traces=True)
        self.assertEqual(code, 2)
        manifest = json.loads((output / "run_manifest.json").read_text())
        self.assertEqual((manifest["processed"], manifest["errors"], manifest["ignored_non_mat_csvs"]), (2, 1, 1))
        traces = list((output / "traces").glob("*.npz"))
        self.assertEqual(len(traces), 2)
        with np.load(traces[0], allow_pickle=False) as trace:
            self.assertEqual(trace["signals"].shape[1], 4)
        with (output / "features.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertNotEqual(rows[0]["record_id"], rows[1]["record_id"])
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            run_batch(source, output, self.cfg)

    def test_ineligible_batch_keeps_blank_features(self):
        path = self.root / "empty_load.csv"
        save(path, self.t, self.raw*0)
        out = self.root / "out"
        self.assertEqual(run_batch(path, out, self.cfg), 0)
        with (out / "features.csv").open() as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["cop_speed"], "")
        self.assertEqual(row["status"], "ineligible")

    def test_synthetic_demo_plot_and_cli(self):
        source = self.root / "synthetic"
        generate_demo(source)
        result = subprocess.run([sys.executable, "-m", "mat_features", "extract", str(source),
                                 "--output", str(self.root / "results"), "--plots", "--save-traces"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plots = list((self.root / "results" / "plots").glob("*.png"))
        self.assertEqual(len(plots), 1)
        self.assertGreater(plots[0].stat().st_size, 1000)
        with self.assertRaises(ValueError):
            generate_demo(source)

    def test_cli_invalid_input_nonzero(self):
        result = subprocess.run([sys.executable, "-m", "mat_features", "extract", str(self.root / "missing"),
                                 "--output", str(self.root / "results")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Input does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()

# Validation and migration notes — 13 November 2026

## Software checks

The release was exercised on Linux with Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0 and Matplotlib 3.10.8. The 23 automated tests in `tests/test_features.py` pass. They use synthetic fixtures and cover numerical definitions, threshold boundaries, headered/headerless equivalence, legacy row handling, timestamp/date validation, malformed recordings, gaps, frozen maps, segment selection, empty output semantics, collision-free batch identifiers, the CLI, traces and plotting.

An installable wheel was built with setuptools and tested in an isolated virtual environment using the available dependency installation. The console entry point and extraction from outside the source directory were checked. Dependency downloads from a fresh Windows installation were not exercised here. Windows commands use standard Python/Pathlib interfaces; physical mat acquisition and the GUI were not run in this environment. The supplied GUI source files and original dependency list were verified byte-for-byte unchanged.

## Historical recording comparison

All 331 available historical recordings were processed under both header policies. Input SHA-256 hashes were checked against the source manifest and verified unchanged after processing. All recognized filename dates matched frame dates in Europe/Rome. No trainer scores or GUI-use labels entered this validation or feature selection.

| Check | Legacy first-line skipping | Default header detection |
| --- | ---: | ---: |
| Recordings | 331 | 331 |
| Frames analysed | 62,130 | 62,461 |
| Recordings with primary features | 330 | 330 |
| Recordings passing technical QC | 297 | 297 |
| Deadlift recordings passing technical QC | 154 | 154 |

All 331 files are headerless, so the correction preserves one additional original frame per file. The same one recording remains ineligible for primary features, and no recording changes its QC pass/fail decision.

With explicit legacy mode, **all 1,980 earlier feature rows** (330 recordings × six threshold/trim settings) are reproduced within numerical precision. The largest absolute differences against the archived CSV are 8.9 × 10⁻¹⁶ for CoP speed, 5.7 × 10⁻¹⁴ for ellipse area, and less than 1 × 10⁻¹⁶ for either CV. These differences are consistent with floating-point representation and CSV round trips.

## Effect of preserving the first data frame

Of 330 primary-feature recordings, 279 have at least one numerical feature change when the first frame is retained (comparison tolerance: relative 10⁻¹⁰, absolute 10⁻¹⁰).

| Primary descriptor | Median absolute change | Maximum absolute change |
| --- | ---: | ---: |
| CoP speed, cells/s | 0.009292 | 0.623231 |
| CoP ellipse area, cells² | 0.093350 | 17.346175 |
| Total-response CV, ratio | 0.000178 | 0.032980 |
| Contact-count CV, ratio | 0.000306 | 0.033010 |

Adding a frame can change the interval boundary, median resampling step and smoothing boundary values; effects are not restricted to one output sample. These differences should not be dismissed solely because the retained sample count and QC decisions are unchanged.

Use **default header detection for new analyses**. For exact reproduction of previously reported feature-based analyses, explicitly use `--legacy-skip-first-line` and preserve the resulting run manifest. A manuscript adopting the corrected extraction must refresh its feature-based results and frame count. This software release does not recompute treatment-effect statistics, correlations or clinical conclusions. Analyses based solely on trainer scores do not use these mat frames.

## Reproduce the public checks

```text
python -m pip install ".[plots]"
python -m unittest discover -s tests -v
python -m mat_features demo --output demo_data
python -m mat_features extract demo_data --output demo_results --plots --save-traces
```

The historical recordings and participant-level validation outputs are intentionally absent from the public source release. The counts above report developer validation on the available private data; running the public tests alone does not rerun that dataset comparison. The README figure is entirely synthetic.

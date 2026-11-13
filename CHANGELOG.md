# Changelog

## Offline features 0.1.0

- Add `mat_features`, an independent offline Python API and command-line tool.
- Extract four recording-level descriptors, with configurable preprocessing and optional sensitivity settings.
- Support canonical headered exports and historical headerless CSVs.
- **Correct unconditional first-line skipping.** Default processing preserves every numeric data row. Explicit legacy mode reproduces the previous behaviour for comparison.
- Add filename/frame-date checks, source hashes, quality flags, explicit error/ineligible outputs and reproducible configuration records.
- Add optional diagnostic plots, numeric trace archives, synthetic-data generation and numerical/CLI tests.
- Retain the supplied live GUI and Apache-2.0 licence unchanged.

See `docs/VALIDATION.md` for measured agreement with earlier results and the effect of the header correction. This release does not provide validated exercise-event recognition or recompute study-level treatment statistics.

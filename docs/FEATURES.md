# Offline feature definitions and data contract

## Input

One UTF-8 CSV contains one frame per row: Unix timestamp in **seconds**, then 2,240 unsigned 16-bit integer sensor counts in native C-order (80 rows × 28 columns). A canonical header `Timestamp,Sensor_0,...,Sensor_2239` is accepted, as are headerless numeric files. Header spelling is case-insensitive, with outer whitespace ignored; sensor ordering must be exact. UTF-8 BOM and Windows newlines are supported.

Finite numbers, exact column count, strictly increasing timestamps, at least three frames, and sensor values in 0–65,535 are required. Negative values, fractional counts, blank rows and missing values are rejected. The reader does not interpolate corrupt measurements or silently drop rows. The source SHA-256 is computed from the exact bytes parsed.

For names such as `1736942400000_synthetic_person_ex_3.csv`, the 13-digit prefix is interpreted as Unix milliseconds. Its date must equal the first and last frame dates in `Europe/Rome` (configurable). The middle text is the participant label and `_ex_1` to `_ex_4` is the exercise label. Other filenames work without inferred labels. Files crossing local midnight need review; `check_filename_date: false` permits processing but preserves the mismatch in the audit. Use participant identity plus session date when joining external metadata, never date alone. The software does not perform that join.

## Processing, in execution order

1. **Threshold each cell.** Values strictly below `threshold` become zero. A value exactly equal to the threshold is retained. This creates a new array; source bytes and input arrays are unchanged.
2. **Compute four frame signals.** Sum of retained values (total sensor response), count of strictly positive retained cells (contact count), and the response-weighted mean row and column indices (CoP).
3. **Determine occupancy.** A frame is occupied when total response reaches the larger of `min_total_response` and `relative_occupancy` times the median of positive frame totals. Defaults are 5,000 counts and 0.20. The positive-total median uses the whole recording at that threshold.
4. **Split intervals.** An unloaded frame or an adjacent timestamp gap greater than `max_gap_seconds` (default 1.0 s) breaks continuity. Retain intervals containing at least `min_frames` (6) raw frames and spanning at least `min_segment_seconds` (5.0 s). Select the longest duration; exact ties select the first interval. No interpolation crosses a split.
5. **Resample.** Use the selected interval's median timestamp difference as a uniform step and linearly interpolate the four signals. The grid starts at the first selected timestamp and excludes the last raw timestamp, using NumPy `arange` on absolute Unix times for compatibility with the earlier analysis. Floating-point timestamp precision can affect the sample count by one.
6. **Smooth.** Apply `scipy.ndimage.gaussian_filter1d` to each of the four resampled signals, with standard deviation `smoothing_seconds / step`, `mode='nearest'`, and SciPy's default 4-standard-deviation truncation. Default smoothing is 0.25 s; zero disables smoothing. This is offline, two-sided smoothing, not a real-time causal filter.
7. **Optionally trim.** Remove `floor(N × trim_fraction)` samples from each end, after smoothing. Default is zero. At least `min_frames` resampled samples are required to report features. Otherwise the row is explicitly ineligible, even if the raw interval qualified.
8. **Calculate descriptors** from the retained, smoothed signals. Save technical quality flags independently of the feature values.

## Four main descriptors

Let the smoothed CoP positions be `q[k] = (row[k], column[k])`, and let `T` be elapsed time between the first and last retained samples.

| Feature | Calculation | Interpretation |
| --- | --- | --- |
| `cop_speed` | Sum of Euclidean distances between adjacent CoP positions, divided by `T` | Rate of CoP movement within this interval, in grid cells/s |
| `cop_ellipse` | `pi × 5.991464547 × sqrt(max(det(S), 0))`, where `S` is the 2 × 2 sample covariance of the CoP coordinates, denominator `N−1` | Spatial dispersion, in grid cells² |
| `load_cv` | Population standard deviation of smoothed total response, divided by its mean | Relative variation in response, expressed as a ratio |
| `contact_cv` | Population standard deviation of smoothed active-cell count, divided by its mean | Relative variation in contact extent, expressed as a ratio |

`cop_path_length` is the numerator of `cop_speed`. `load_cv_pct` and `contact_cv_pct` multiply their ratio values by 100. A CV of 0.05 is 5%. After interpolation and smoothing, the contact signal can be non-integer although raw contact counts are integers.

The ellipse uses the 95th percentile of a chi-squared distribution with two degrees of freedom. It is a covariance-based dispersion descriptor, not a confidence interval for a treatment effect or a guarantee that 95% of the observed points fall inside it. Collinear/static trajectories yield zero area.

## Coordinates and relationship to the live GUI

Features use **native row/column grid coordinates**, with unit distance per cell index. The GUI display transform (`flipud(P.T)`) is not applied. A rigid index-space rotation or reflection would preserve Euclidean path length and ellipse area; physical distances still require independently validated row and column pitches. No isotropic physical sensor spacing is assumed or inferred.

No body-weight normalization, per-frame peak normalization, baseline subtraction, spatial morphological opening, anatomical left/right identification or physical force conversion is performed offline. The response-weighted centroid divides by the total response; that is the only CoP normalization. `load_cv` and `contact_cv` are normalized by their respective temporal means.

The current GUI thresholds in place before saving CSV values. Values already discarded during acquisition cannot be recovered by a lower offline threshold. Its optional blob filter only affects the displayed map, so the offline centroid may differ from the on-screen centroid when that filter was enabled. The historic recordings and current GUI exports need not share the same acquisition preprocessing. Record such provenance separately when collecting new data.

The internal raw CoP signal uses a denominator of at least 1 to avoid division by zero. Only occupied frames enter feature estimation, and plots hide the centroid in unoccupied frames. Use the saved `occupied` mask when working with raw trace arrays.

## Quality flags

The audit is independent of trainer scores and GUI-use labels. It flags possible acquisition problems; it is not a validated artefact classifier.

| Flag | Default trigger |
| --- | --- |
| `excessive_gap_loss` | Estimated missing time at gaps over 1 s exceeds 10% of the complete recording duration |
| `identical_occupied_frames` | Exactly identical **original sensor arrays** persist continuously under load for at least 2 s |
| `no_eligible_primary_features` | No interval supports a primary-setting feature estimate |
| `short_selected_segment` | The retained primary interval spans less than 10 s |

Estimated missing time sums `max(gap − whole-recording median interval, 0)` over long gaps. Identical-frame runs are broken by unloaded frames and long gaps; empty mats do not count as frozen acquisition. A stationary subject can also produce identical quantized maps, so inspect this flag before excluding a recording.

`qc_pass` is true only when no flags are present. Flagged but otherwise valid features remain in `features.csv`. The primary setting determines the QC screen for all sensitivity variants; this avoids redefining the eligible sample separately for each setting. Neither QC nor segment selection reads clinical outcomes. Files failing input validation are listed in `processing_errors.csv` and have no feature row.

## Important output fields

| Field | Definition |
| --- | --- |
| `record_id` | SHA-256 of the relative source path, unique across different subfolders within the run |
| `source_path` | Source path relative to the input root; retain this when joining exported tables |
| `sha256` | Hash of source bytes; identical copies share this even if their `record_id` differs |
| `n_input_frames`, `n_frames` | Data rows present, and data rows analysed; differ in legacy mode on headerless files |
| `header_present` | Whether a canonical header was detected |
| `first_data_row_skipped` | 1 only when legacy mode drops the first data row of a headerless file |
| `is_primary` | Whether the row uses the configured threshold and trim |
| `status`, `reason` | `ok` or `ineligible`, and an explanation for ineligibility |
| `segment_start`, `segment_end` | Seconds from the **first analysed frame**, after resampling and trimming |
| `raw_segment_first_index`, `raw_segment_last_index` | Inclusive zero-based indices within analysed input frames, before resampling/trimming |
| `n_segment_samples` | Number of retained uniformly spaced samples |
| `occupied_fraction` | Fraction of analysed raw frames above the occupancy gate |
| `n_occupied_bouts`, `n_eligible_bouts` | All occupied intervals and intervals meeting raw duration/frame requirements |
| `hz` | Reciprocal of median timestamp spacing, not a hardware-configured sampling frequency |
| `filename_date_match` | True/False for recognized timestamp-prefixed names, otherwise `not_applicable` |

CSV booleans are `True`/`False`. Missing estimates are empty fields, never substituted with zero. For direct comparison with the old extractor, its `n_occupied_bouts` counted only *eligible* bouts; that corresponds to the new `n_eligible_bouts` field.

Optional NPZ traces contain `raw_time`, `raw_signals` (total response, contact count, CoP row, CoP column), `occupied`, and `start_unix_seconds`. When a raw interval qualifies, they also contain `time`, `signals`, `median_map` and `representative_map`. The latter two use the untrimmed selected raw interval; the representative map is its middle frame. These arrays may exist even if too few resampled points remain for features; consult `status`. Arrays contain no Python objects and can be read with `numpy.load(path, allow_pickle=False)`.

The default batch mode never pools recordings or joins scores. Multiple files on the same date remain distinct. Filenames, relative paths and generated plots may contain participant identifiers; treat generated analysis outputs as study data even though the source package is public.

## Scientific scope

These are reproducible recording-level descriptors. Smaller CoP movement is not universally better during dynamic tasks, and these features alone do not establish improved proprioception or a GUI treatment effect. Task-specific interpretation and annotated exercise boundaries are separate analysis steps. The earlier experimental event proposals are intentionally not exposed as validated recognition in this package.

Reference implementation details: [SciPy Gaussian filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.gaussian_filter1d.html). Release-specific execution checks are in [VALIDATION.md](VALIDATION.md).

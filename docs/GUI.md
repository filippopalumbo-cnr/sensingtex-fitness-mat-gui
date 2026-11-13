# SensingTex Fitness Mat GUI

A Python desktop application for real-time visualization and recording of pressure-map frames from a SensingTex Fitness Mat. The supplied configuration is for an 80 × 28 sensor grid. The GUI displays a heatmap and a pressure-weighted center-of-pressure (CoP) marker; the marker is a grid-coordinate estimate, not a calibrated clinical or force measurement.

The software was developed for research data collection. It has not been validated as a diagnostic or clinical device.

## Features

- Requests active pressure points from the mat over a serial connection and reconstructs an 80 × 28 matrix.
- Displays the pressure map in a separate Matplotlib window, with a configurable colorbar.
- Calculates a CoP marker from the displayed pressure map when its total value reaches the configured minimum.
- Applies a per-cell noise threshold to the map before display and recording.
- Optionally applies a binary morphological opening to the displayed map to suppress small isolated regions.
- Records a host timestamp and 2,240 sensor values per accepted frame in CSV format.

## Hardware and software

- SensingTex Fitness Mat configured as 80 rows × 28 columns. Other dimensions require changes to `ROWS` and `COLS` in `constants.py` and verification of parsing, orientation, and CoP calculations.
- Serial connection to the mat. Choose the port reported by the operating system, such as `COM3` or `/dev/ttyUSB0`.
- Python 3.12 and the packages listed in `requirements.txt`.
- Windows was the original target environment. Other operating systems and serial adapters require verification.

## Installation

From the repository root (the directory containing main.py), create and activate a virtual environment:

```bash
python -m venv .venv
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install the dependencies and launch the application:

```bash
python -m pip install -r requirements.txt
python main.py
```

## Use

1. Connect the mat and identify its serial port.
2. Start the application and enter that port in **COM Port**.
3. Enter a filename base and choose an output directory.
4. Select **Start Recording**. The application opens the serial connection, starts acquisition, and displays the live plot.
5. Use **Enable/Disable Blob Filter** and **Show/Hide Colorbar** to change the visualization.
6. Select **Stop Recording**. The collected rows are written to a CSV file.

The serial worker runs in a background `QThread`; frames are delivered to the GUI through Qt signals. The application does not enforce a fixed sampling frequency. The timestamp is generated on the host when the GUI handles a received frame, not by the mat.

## Serial frame handling

The application opens the configured port at 115,200 baud. It sends `R` to request a map and expects an `N\n` response header, a two-byte big-endian active-point count, and four bytes per point: value high byte, value low byte, x coordinate, and y coordinate. Point values are reconstructed as `(high_byte << 8) | low_byte`. Valid points populate a zero-initialized matrix; absent cells remain zero and out-of-range coordinates are ignored. If a coordinate occurs more than once in a frame, the later value overwrites the earlier one.

The current parser skips the first active point in each frame to work around an anomalous point observed with the mat configuration used during development. This is a device/firmware-specific workaround and should be verified before using a different mat or firmware. Incomplete or invalid frames are discarded; frames that do not produce a valid matrix are not recorded.

## Processing and visualization

The default `NOISE_THRESHOLD` is 150. Before plotting, values below this threshold are set to zero. This operation is applied in place to the reshaped frame array, so it also changes the values subsequently written to CSV.

The optional blob filter is disabled by default. When enabled, it makes a binary mask of the nonzero thresholded cells, applies one binary opening using a two-dimensional four-neighbour cross-shaped structuring element, and masks the values with the result. The filter changes the displayed heatmap and CoP calculation, but it is applied to a new array and does not affect the CSV values.

For display, the selected 80 × 28 matrix is transposed and flipped vertically, producing a 28 × 80 array equivalent to a 90° counterclockwise rotation in NumPy array coordinates. This transform is only used for plotting; the CSV retains the acquisition orientation. The plot uses the `plasma` colormap with fixed limits `vmin=0` and `vmax=1800`. These limits control color mapping only: the data are not divided by 1,800 or normalized frame by frame. Values outside the display range appear at the ends of the color scale.

The CoP marker is calculated from the thresholded map, or from the filtered map when blob filtering is enabled. If the sum of the displayed matrix is below `COP_MIN_TOTAL_PRESSURE` (default 5,000), no marker is shown. Otherwise, for displayed matrix `V` with row index `i` and column index `j`,

```text
x_CoP = sum(i,j) [j * V[i,j]] / sum(i,j) V[i,j]
y_CoP = sum(i,j) [i * V[i,j]] / sum(i,j) V[i,j]
```

The coordinates are sensor-grid indices. The vertical index increases down the displayed image because Matplotlib uses `origin='upper'`. Conversion to millimetres or physical pressure requires a validated spatial mapping and sensor calibration, neither of which is performed by this application.

## CSV format and interpretation

The filename starts with a host timestamp in milliseconds, followed by the user-provided filename base and `.csv`. The CSV contains one row for each valid frame received while recording:

- `Timestamp`: host Unix time in seconds, captured when the GUI handles the frame.
- `Sensor_0` through `Sensor_2239`: the matrix flattened in NumPy's default C (row-major) order.

**The CSV is not an untouched raw sensor stream.** The in-place noise threshold is applied before the row is buffered, so every value below 150 is saved as zero by default. The optional blob filter and plot-orientation transform are not applied to the saved values. The CSV has no participant ID, task label, feedback condition, trainer score, or device-side timestamp. Keep study metadata in a separate, access-controlled file and do not commit participant recordings to this repository.

## Configuration

Edit `constants.py` to change the sensor dimensions, noise threshold, minimum total value for showing CoP, colormap limits, color map, marker size, default serial port, and default save path. The supplied default save path is Windows-specific (`C:/THE/`). The serial worker currently uses a baud rate of 115,200 as a constructor default; changing `DEFAULT_BAUD_RATE` in `constants.py` alone has no effect because that constant is not currently passed to the worker.

Relevant defaults are:

| Setting | Default | Effect |
| --- | ---: | --- |
| `ROWS`, `COLS` | 80, 28 | Sensor matrix dimensions |
| `NOISE_THRESHOLD` | 150 | Zeroes lower-valued cells in both display and saved CSV values |
| `COP_MIN_TOTAL_PRESSURE` | 5,000 | Minimum displayed-map sum for showing CoP |
| `ARTIFACT_FILTER_ENABLED` | `False` | Initial state of optional display filter |
| `VIS_VMAX` | 1,800 | Upper heatmap color scale bound; does not rescale saved data |
| Worker baud rate | 115,200 | Hard-coded default in `Worker`; `DEFAULT_BAUD_RATE` is currently unused |

## Source files

- `main.py`: application entry point.
- `main_window.py`: recording controls, frame handling, visualization preprocessing, and CSV output.
- `plot_window.py`: heatmap, colorbar, and CoP marker.
- `worker.py`: background serial-acquisition thread.
- `sensor_protocol.py`: serial request and frame parser.
- `data_processing.py`: CoP calculation and optional binary morphological opening.
- `constants.py`: dimensions and configuration defaults.

## License

This project is distributed under the Apache License 2.0; see [`LICENSE`](../LICENSE).

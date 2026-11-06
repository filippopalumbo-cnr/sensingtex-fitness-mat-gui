# constants.py
"""Shared constants for the application."""

ROWS = 80  # Rows of the sensor
COLS = 28  # Columns of the sensor
DEBUG = False # Set to True for detailed console output (or move to config)

# Thresholds (centralizing them here)
COP_MIN_TOTAL_PRESSURE = 5000 # Min total pressure sum to show CoP (Adjust as needed)
NOISE_THRESHOLD = 150       # Sensor values below this are treated as noise (Adjust as needed)
COP_MARKER_SIZE = 40           # <<< ADDED: Default size for CoP marker
COLORBAR_INITIALLY_VISIBLE = False

# Visualization Defaults (centralizing them here)
VIS_VMAX = 1800             # Default max value for colormap (Adjust as needed)
VIS_CMAP = 'plasma'           # Default colormap

# Configuration Defaults
DEFAULT_COM_PORT = "COM5"     # <<< ADDED: Default COM Port string
DEFAULT_BAUD_RATE = 115200    # Optional: Define baud rate too if needed elsewhere

DEFAULT_SAVE_PATH = 'C:/THE/'
FILENAME_PREFIX = "aathe_"

# Filtering Defaults
ARTIFACT_FILTER_ENABLED = False # Default state for blob filter
# MIN_BLOB_SIZE = 5 # Conceptual size (controlled by structure element below)
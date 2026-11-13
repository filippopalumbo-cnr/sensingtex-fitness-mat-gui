"""Read both headered GUI CSVs and historical headerless CSVs without row loss."""
import csv
from datetime import datetime
import hashlib
import io
from pathlib import Path
import re
from zoneinfo import ZoneInfo
import numpy as np


class RecordingError(ValueError):
    """Malformed recording; the file must not contribute to feature estimates."""


def numeric_header(first):
    try:
        float(first[0])
        return True
    except (ValueError, IndexError):
        return False


def read_recording(path, config):
    path = Path(path)
    contents = path.read_bytes()
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RecordingError("Expected a UTF-8 numeric CSV") from exc
    if not text.strip():
        raise RecordingError("Empty file")
    lines = text.splitlines()
    if any(not line.strip() for line in lines):
        raise RecordingError("Blank rows are not silently removed")
    first = next(csv.reader([lines[0]]))
    size = config.rows * config.cols
    header_present = not numeric_header(first)
    if header_present:
        expected = ["Timestamp"] + [f"Sensor_{i}" for i in range(size)]
        if [cell.strip().casefold() for cell in first] != [s.casefold() for s in expected]:
            raise RecordingError(f"Header must be Timestamp,Sensor_0,...,Sensor_{size-1} in this order")
    skip = 1 if header_present or config.legacy_skip_first_line else 0
    if len(lines) <= skip:
        raise RecordingError("No data rows")
    try:
        data = np.loadtxt(io.StringIO("\n".join(lines[skip:])), delimiter=",", comments=None, ndmin=2)
    except ValueError as exc:
        raise RecordingError(f"Invalid numeric row or inconsistent column count: {exc}") from exc
    if data.shape[1] != size + 1:
        raise RecordingError(f"Expected {size+1} columns; found {data.shape[1]}")
    metadata = dict(sha256=hashlib.sha256(contents).hexdigest(), source_bytes=len(contents),
                    header_present=header_present, n_input_frames=len(lines)-int(header_present),
                    first_data_row_skipped=int(config.legacy_skip_first_line and not header_present))
    return data[:, 0], data[:, 1:], metadata


def filename_metadata(filename, timestamps, config):
    zone = ZoneInfo(config.timezone)
    try:
        first = datetime.fromtimestamp(float(timestamps[0]), zone).date().isoformat()
        last = datetime.fromtimestamp(float(timestamps[-1]), zone).date().isoformat()
    except (ValueError, OverflowError, OSError) as exc:
        raise RecordingError("Timestamp outside datetime range; timestamps must use Unix seconds") from exc
    result = dict(filename=filename, date=first, last_frame_date=last, participant="", exercise="",
                  filename_date="", filename_date_match="not_applicable")
    stem = Path(filename).stem
    match = re.fullmatch(r"(\d{13})_?(.+)", stem)
    if match:
        stamp, label = match.groups()
        day = datetime.fromtimestamp(int(stamp)/1000, zone).date().isoformat()
        matches = first == last == day
        result.update(filename_date=day, filename_date_match=matches,
                      filename_minus_start_s=int(stamp)/1000-timestamps[0],
                      filename_minus_end_s=int(stamp)/1000-timestamps[-1])
        exercise = re.fullmatch(r"(.+)_ex_([1-4])", label)
        if exercise:
            result.update(participant=exercise[1], exercise=int(exercise[2]))
        if config.check_filename_date and not matches:
            raise RecordingError(f"Filename date {day} disagrees with frame dates {first}..{last} in {config.timezone}")
    return result


def looks_like_recording(path):
    """Directory discovery only; explicit file inputs always undergo full validation."""
    path = Path(path)
    # Timestamp-labelled files are attempted even when their header is corrupt.
    if re.match(r"^\d{13}", path.name):
        return True
    try:
        with path.open(encoding="utf-8-sig") as stream:
            first = next(csv.reader([stream.readline()]))
        return bool(first) and (first[0].strip().casefold() == "timestamp" or numeric_header(first))
    except (UnicodeError, OSError, csv.Error):
        return True  # Report unreadable files as errors, not ignored files.

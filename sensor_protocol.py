# sensor_protocol.py
"""Functions for handling the SensingTex serial communication protocol."""

import serial
import time
import numpy as np
from constants import ROWS, COLS, DEBUG # Import constants

# --- Helper Functions (Specific to Sensor Protocol) ---

def activePointsRequestMap(ser):
    # (Keep the function code exactly as before)
    if DEBUG:
        print("Requesting pressure map")
    data = "R"
    try:
        sentCount = ser.write(data.encode())
        if DEBUG:
            print(f"Sent R as {sentCount} bytes")
        return True
    except serial.SerialException as e:
        print(f"Error writing to serial port: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during write: {e}")
        return False


def activePointsReceiveMap(ser, activePointCount): # Accepts passed count
    # (Keep the LATEST working version of this function)
    # This version skips index 0 and uses passed count
    print(f"--- activePointsReceiveMap (Count = {activePointCount}) ---")
    matrix = np.zeros((ROWS, COLS), dtype=int)
    try:
        original_timeout = ser.timeout
        ser.timeout = 0.5

        print(f"DEBUG: activePointsReceiveMap using passed count = {activePointCount}")

        if not (0 <= activePointCount <= ROWS * COLS):
            print(f"ERROR: Passed activePointCount ({activePointCount}) is outside valid range [0, {ROWS * COLS}]. Discarding frame.")
            ser.flushInput()
            time.sleep(0.01)
            ser.timeout = original_timeout
            return None

        if activePointCount <= 1:
            if activePointCount == 1:
                bytes_to_read = 4
                print(f"DEBUG: Reading and discarding 4 bytes for single bogus point (Count=1)...")
                _ = ser.read(bytes_to_read)
            ser.timeout = original_timeout
            return matrix

        bytes_to_read = activePointCount * 4
        if bytes_to_read > 0:
            print(f"DEBUG: Attempting to read {bytes_to_read} bytes for {activePointCount} points (Timeout={ser.timeout}s)...")
            point_bytes = ser.read(bytes_to_read)
            ser.timeout = original_timeout

            if len(point_bytes) != bytes_to_read:
                print(f"ERROR: Read {len(point_bytes)} bytes, expected {bytes_to_read}. Data truncated? Discarding frame.")
                ser.flushInput()
                return None

            print(f"DEBUG: Raw point_bytes hex (first {min(20, bytes_to_read)} bytes): {point_bytes[:min(20, bytes_to_read)].hex(' ')}")

            processed_points = 0
            # Skip first point (index 0)
            for i in range(1, activePointCount):
                offset = i * 4
                if offset + 4 > len(point_bytes): break

                # Parse bytes [vh, vl, x, y]
                valueHighByte = point_bytes[offset]
                valueLowByte  = point_bytes[offset+1]
                x             = point_bytes[offset+2]
                y             = point_bytes[offset+3]
                value = (valueHighByte << 8) | valueLowByte

                if i < 10:
                    print(f"DEBUG: Point Idx {i}: Raw=[{point_bytes[offset:offset+4].hex(' ')}] -> Parsed(VXY): x={x:3d}, y={y:3d}, val={value:5d}")

                if 0 <= x < ROWS and 0 <= y < COLS:
                     matrix[x][y] = value
                     processed_points += 1
                else:
                     print(f"Warning(VXY): Out-of-bounds coord x={x}, y={y} (Value={value})")

            print(f"DEBUG: Processed {processed_points} valid points (Indices 1 to {activePointCount-1}) out of {activePointCount} reported.")

        ser.timeout = original_timeout
        return matrix

    except serial.SerialTimeoutException as e:
        print(f"Serial timeout during activePointsReceiveMap: {e}")
        try: ser.timeout = original_timeout
        except: pass
        return None
    except Exception as ex:
        print(f"Error in activePointsReceiveMap: {ex}")
        try: ser.timeout = original_timeout
        except: pass
        return None


def activePointsRetrieveMap(ser):
    # (Keep the LATEST working version of this function)
    # This version reads N\n, reads count, passes count to activePointsReceiveMap
    print("--- activePointsRetrieveMap ---")
    try:
        original_timeout = ser.timeout
        ser.timeout = 0.5

        if ser.in_waiting >= 1:
            xbyte1 = ser.read()
            if xbyte1 == b'N':
                start_wait_n = time.time()
                while time.time() - start_wait_n < 0.1:
                     if ser.in_waiting >= 1:
                         xbyte2 = ser.read()
                         if xbyte2 == b'\n':
                             print("DEBUG: N\\n received. Reading count bytes...")
                             ser.timeout = 0.1
                             count_byte_1 = ser.read()
                             count_byte_2 = ser.read()
                             ser.timeout = original_timeout

                             if count_byte_1 and count_byte_2:
                                 activePointCount = (int.from_bytes(count_byte_1, 'big') << 8) | int.from_bytes(count_byte_2, 'big')
                                 print(f"DEBUG: Count bytes read: {count_byte_1.hex()} {count_byte_2.hex()} -> Count = {activePointCount}")

                                 print(f"DEBUG: Calling activePointsReceiveMap with count = {activePointCount}")
                                 result_map = activePointsReceiveMap(ser, activePointCount) # Pass count
                                 ser.timeout = original_timeout
                                 return result_map
                             else:
                                 print("ERROR: Timeout reading count bytes after N\\n.")
                                 ser.flushInput()
                                 return None
                         else:
                             print(f"Protocol error: RetrieveMap expected '\\n' after 'N', but received {xbyte2.hex()}")
                             ser.flushInput()
                             ser.timeout = original_timeout
                             return None
                     time.sleep(0.01)

                print("Protocol error: RetrieveMap received 'N' but timeout waiting for '\\n'")
                ser.flushInput()
                ser.timeout = original_timeout
                return None
            else:
                print(f"Protocol error: RetrieveMap expected 'N' (0x4e) but received {xbyte1.hex()}")
                ser.flushInput()
                ser.timeout = original_timeout
                return None
        else:
            ser.timeout = original_timeout
            return None

    except Exception as ex:
        print(f"Error in activePointsRetrieveMap: {ex}")
        try: ser.timeout = original_timeout
        except: pass
        return None


def getMap(ser):
    # (Keep the function code exactly as before)
    # It calls the other protocol functions in this file
    print("--- getMap ---")
    ser.flushInput()
    time.sleep(0.05)
    if not activePointsRequestMap(ser):
        print("Failed to send map request 'R'.")
        return None

    map_data = None
    start_time = time.time()

    while time.time() - start_time < 0.5:
        map_data = activePointsRetrieveMap(ser)
        if map_data is not None:
            return map_data
        time.sleep(0.01)

    if DEBUG: print(f"Map not received by getMap within timeout.")
    waiting = ser.in_waiting
    if waiting > 0:
        print(f"DEBUG getMap timeout: Discarding {waiting} unexpected bytes: {ser.read(waiting).hex(' ')}")
    return None
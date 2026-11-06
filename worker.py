# worker.py
"""Defines the Worker thread for handling background serial communication."""

import serial
import time
from PyQt5.QtCore import QThread, pyqtSignal
from sensor_protocol import getMap # Import from local module
from constants import DEBUG # Import constants

class Worker(QThread):
    """Handles serial communication in a separate thread."""
    map_data_ready = pyqtSignal(object) # Emit numpy array or None
    error_occurred = pyqtSignal(str)
    port_opened = pyqtSignal(bool)
    status_update = pyqtSignal(str)

    def __init__(self, com_port, baud_rate=115200, parent=None):
        super().__init__(parent)
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.ser = None
        self._is_running = False

    def run(self):
        # (Keep the latest version of the run method)
        # It calls getMap from sensor_protocol
        self._is_running = True
        print("Worker Thread: run() started.")
        self.status_update.emit(f"Attempting to open {self.com_port}...")
        try:
            self.ser = serial.Serial(self.com_port, self.baud_rate, timeout=0.1)
            time.sleep(0.1)
            self.ser.flushInput()
            self.status_update.emit(f"Serial port {self.com_port} opened.")
            self.port_opened.emit(True)
            print(f"Worker Thread: Serial port {self.com_port} opened successfully.")

            while self._is_running and not self.isInterruptionRequested():
                if self.ser and self.ser.is_open:
                    if not self._is_running or self.isInterruptionRequested():
                        print("Worker Thread: Stop requested before getMap(). Breaking loop.")
                        break

                    map_array = getMap(self.ser) # Calls function from sensor_protocol

                    # Emit None if getMap fails, let receiver handle it
                    self.map_data_ready.emit(map_array)

                    if map_array is None and DEBUG:
                         print("Worker: getMap returned None.")

                    # Optional short sleep if getMap doesn't block sufficiently
                    time.sleep(0.01) # Reduce CPU usage if getMap returns quickly on no data

                else:
                    self.error_occurred.emit("Serial port is not open or available.")
                    self._is_running = False
                    break

            print("Worker Thread: Exited main loop.")

        except serial.SerialException as e:
            print(f"Worker SerialException: {e}")
            self.error_occurred.emit(f"Failed to open/read serial port {self.com_port}: {e}")
            self.port_opened.emit(False)
        except Exception as e:
             print(f"Worker unexpected error: {e}")
             self.error_occurred.emit(f"An unexpected error occurred in worker thread: {e}")
             self.port_opened.emit(False)
        finally:
            print("Worker Thread: Entering finally block.")
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.status_update.emit(f"Serial port {self.com_port} closed.")
                print(f"Worker Thread: Serial port {self.com_port} closed.")
            self._is_running = False
            print("Worker Thread: run() finished.")

    def stop(self):
        print("Worker Thread: stop() called.")
        self._is_running = False
        self.requestInterruption()
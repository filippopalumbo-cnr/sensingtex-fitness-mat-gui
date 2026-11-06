# main_window.py
"""Defines the MainWindow class, containing UI controls and main logic."""

import os
import time
import csv
import sys
import numpy as np
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QLabel, QMessageBox, QFileDialog, QStatusBar,
                             QApplication)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
import serial # Only needed for SerialException

# Import local modules
from constants import ROWS, COLS, NOISE_THRESHOLD, DEFAULT_COM_PORT, DEFAULT_SAVE_PATH, FILENAME_PREFIX, ARTIFACT_FILTER_ENABLED, COLORBAR_INITIALLY_VISIBLE
from worker import Worker
from plot_window import PlotWindow
from data_processing import filter_small_blobs

# --- Helper function for resource path (handles PyInstaller bundle) ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # Using frozen checks if running as bundled exe
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
             base_path = sys._MEIPASS
             print(f"DEBUG: Running from PyInstaller bundle, base path: {base_path}")
        else:
             # Not bundled, running in normal Python environment
             # Use directory of *this* file (main_window.py)
             base_path = os.path.dirname(os.path.abspath(__file__))
             print(f"DEBUG: Running from normal Python env, base path: {base_path}")
    except Exception as e:
        print(f"DEBUG: Error determining base path, falling back to '.': {e}")
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
# --- End Helper function ---

class MainWindow(QWidget):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tuscany Health Ecosystem - THE GUI")
        self.setGeometry(100, 100, 500, 250)

        # --- Set Window Icon ---
        try:
            icon_filename = "THE_GUI.ico"
            icon_path = resource_path(icon_filename)
            print(f"DEBUG: Attempting to load window icon from: {icon_path}")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                print(f"DEBUG: Window icon set successfully.")
            else:
                print(f"WARNING: Window icon file not found at: {icon_path}")
        except Exception as e:
            print(f"ERROR setting window icon: {e}")
            # Optionally print traceback for more details
            # import traceback
            # traceback.print_exc()
        # --- End Set Window Icon ---

        # State Variables
        self.is_recording = False
        self.colorbar_visible = COLORBAR_INITIALLY_VISIBLE
        self.artifact_filter_active = ARTIFACT_FILTER_ENABLED
        self.csvLines = []
        self.worker = None
        self.current_filename = ""
        self.serial_port_open = False

        # Create the separate Plot Window (no parent)
        self.plot_window = PlotWindow()

        # --- UI Elements ---
        main_layout = QVBoxLayout(self)
        input_layout = QHBoxLayout()
        button_layout = QHBoxLayout() # Layout for Start/Stop/Toggle buttons

        # Input Fields
        self.com_label = QLabel("COM Port:")
        self.com_input = QLineEdit(DEFAULT_COM_PORT)
        self.filename_label = QLabel("Filename:")
        self.filename_input = QLineEdit(FILENAME_PREFIX)
        self.browse_button = QPushButton("Browse Dir")
        input_layout.addWidget(self.com_label)
        input_layout.addWidget(self.com_input)
        input_layout.addWidget(self.filename_label)
        input_layout.addWidget(self.filename_input)
        input_layout.addWidget(self.browse_button)

        # Buttons
        self.start_button = QPushButton("Start Recording")
        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setEnabled(False)
        cbar_button_text = "Hide Colorbar" if COLORBAR_INITIALLY_VISIBLE else "Show Colorbar"
        self.toggle_colorbar_button = QPushButton(cbar_button_text)
        self.toggle_colorbar_button.setEnabled(False) # Disabled until recording starts
        filter_button_text = "Disable Blob Filter" if ARTIFACT_FILTER_ENABLED else "Enable Blob Filter"
        self.toggle_filter_button = QPushButton(filter_button_text)
        self.toggle_filter_button.setEnabled(False)  # Disabled until recording starts

        # Add buttons to layout
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.toggle_colorbar_button) # Add the new button
        button_layout.addWidget(self.toggle_filter_button)

        # Status Bar
        self.status_bar = QStatusBar()

        # Add layouts/widgets to main layout
        main_layout.addLayout(input_layout)
        main_layout.addLayout(button_layout) # Add the layout containing buttons
        main_layout.addWidget(self.status_bar)

        # --- Connections ---
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.browse_button.clicked.connect(self.browse_directory)
        self.toggle_colorbar_button.clicked.connect(self.on_toggle_colorbar)
        self.toggle_filter_button.clicked.connect(self.on_toggle_artifact_filter)

        # --- Initial Setup ---
        self.save_path = DEFAULT_SAVE_PATH
        try:
            if not os.path.exists(self.save_path):
                os.makedirs(self.save_path)
                print(f"DEBUG: Created default save directory: {self.save_path}")
        except OSError as e:
            # Fallback to current directory if default path fails
            print(f"WARNING: Could not create default save path '{self.save_path}': {e}. Using current directory.")
            self.save_path = os.getcwd()
        self.status_bar.showMessage(f"Ready. Default save directory: {self.save_path}")

    # --- New Slot Method for Filter Button ---
    def on_toggle_artifact_filter(self):
        """Toggles the artifact filter state and updates the button text."""
        self.artifact_filter_active = not self.artifact_filter_active
        if self.artifact_filter_active:
            self.toggle_filter_button.setText("Disable Blob Filter")
            print("DEBUG: Blob filter ENABLED.")
        else:
            self.toggle_filter_button.setText("Enable Blob Filter")
            print("DEBUG: Blob filter DISABLED.")
        # Note: This only changes the state; the filter is applied in update_plot_and_data
     # --- End New Slot Method ---

    # --- New Slot Method for Toggle Button ---
    def on_toggle_colorbar(self):
        if not self.plot_window or not self.plot_window.isVisible():
            print("DEBUG: Toggle colorbar ignored, plot window not visible.")
            return

        # Toggle the state
        self.colorbar_visible = not self.colorbar_visible
        print(f"DEBUG: Toggling colorbar visibility to: {self.colorbar_visible}")

        # Update button text
        if self.colorbar_visible:
            self.toggle_colorbar_button.setText("Hide Colorbar")
        else:
            self.toggle_colorbar_button.setText("Show Colorbar")

        # Call the plot window's method to update visibility
        self.plot_window.set_colorbar_visible(self.colorbar_visible)
    # --- End New Slot Method ---


    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.save_path)
        if directory:
            self.save_path = directory
            self.status_bar.showMessage(f"Save directory set to: {self.save_path}", 5000)


    def start_recording(self):
        print("DEBUG: start_recording called.")
        if self.is_recording: return

        com_port = self.com_input.text()
        base_filename = self.filename_input.text()
        if not base_filename: base_filename = "recording"

        timestamp = str(round(time.time() * 1000))
        self.current_filename = os.path.join(self.save_path, f"{timestamp}_{base_filename}.csv")

        self.status_bar.showMessage(f"Starting recording... Attempting to connect to {com_port}")
        QApplication.processEvents()

        print("DEBUG: Creating Worker...")
        self.worker = Worker(com_port)
        self.worker.map_data_ready.connect(self.update_plot_and_data)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.port_opened.connect(self.handle_port_status)
        self.worker.status_update.connect(self.update_status)
        self.worker.finished.connect(self.on_worker_finished)

        self.csvLines = []
        print("DEBUG: Starting Worker thread...")
        self.worker.start()

        # Show the plot window and set initial colorbar state
        if self.plot_window:
            print(f"DEBUG: Setting initial colorbar visibility to {self.colorbar_visible}")
            self.plot_window.set_colorbar_visible(self.colorbar_visible)
            self.plot_window.show()
            self.plot_window.activateWindow()


    def handle_port_status(self, opened_successfully):
        if opened_successfully:
            self.serial_port_open = True
            self.is_recording = True
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.toggle_colorbar_button.setEnabled(True)
            self.toggle_filter_button.setEnabled(True)
            self.com_input.setEnabled(False)
            self.filename_input.setEnabled(False)
            self.browse_button.setEnabled(False)
            self.status_bar.showMessage(f"Recording started. Saving to {os.path.basename(self.current_filename)}", 5000)
        else:
            self.serial_port_open = False
            self.is_recording = False
            # Ensure buttons are disabled if port failed
            self.start_button.setEnabled(True)  # Allow retry
            self.stop_button.setEnabled(False)
            self.toggle_colorbar_button.setEnabled(False)
            self.toggle_filter_button.setEnabled(False)


    def stop_recording(self):
        if not self.is_recording or not self.worker: return
        print("MainWindow: stop_recording() called.")
        self.status_bar.showMessage("Stopping recording...")
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False) # Keep disabled until worker finishes
        self.toggle_colorbar_button.setEnabled(False) # <<< DISABLE toggle button
        self.toggle_filter_button.setEnabled(False)
        if self.worker: self.worker.stop()


    def on_worker_finished(self):
        """Called when the worker thread has terminated."""
        print("MainWindow: on_worker_finished() called.") # Log entry point
        self.status_bar.showMessage("Worker thread finished. Saving data...")
        QApplication.processEvents() # Update status bar message immediately

        # Ensure recording state is updated BEFORE potentially accessing csvLines for saving
        self.is_recording = False
        self.serial_port_open = False

        # --- START: Saving Logic ---
        if self.csvLines: # Check if any data was collected
            print(f"MainWindow: Saving {len(self.csvLines)} lines to {self.current_filename}") # Log save attempt
            try:
                # Check if directory exists right before saving
                save_dir = os.path.dirname(self.current_filename)
                if not os.path.exists(save_dir):
                    print(f"WARNING: Save directory '{save_dir}' does not exist! Attempting to create.")
                    try:
                        os.makedirs(save_dir)
                        print(f"DEBUG: Created save directory: {save_dir}")
                    except OSError as e:
                        # Raise an error that the outer block can catch
                        raise IOError(f"Failed to create save directory '{save_dir}': {e}")

                # Open file for writing
                with open(self.current_filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    # Add header row
                    # Make sure ROWS and COLS are accessible (they should be via constants import)
                    header = ['Timestamp'] + [f'Sensor_{i}' for i in range(ROWS * COLS)]
                    writer.writerow(header)
                    # Write data rows collected in self.csvLines
                    writer.writerows(self.csvLines)

                # Success message
                self.status_bar.showMessage(f"Recording stopped. Data saved to {os.path.basename(self.current_filename)}", 5000)
                print("MainWindow: Data saved successfully.") # Log success
                # Optional: Show a success popup
                # QMessageBox.information(self, "Save Successful", f"Data saved to:\n{self.current_filename}")

            except IOError as e: # Catch file system/permissions errors specifically
                 error_msg = f"Error saving file: {e}"
                 print(f"MainWindow: {error_msg}") # Log error
                 self.status_bar.showMessage(error_msg, 5000)
                 QMessageBox.critical(self, "File Save Error", f"Could not save data to {self.current_filename}:\n{e}")
            except Exception as e: # Catch any other unexpected errors during save
                 error_msg = f"Unexpected error during save: {e}"
                 print(f"MainWindow: {error_msg}") # Log error
                 import traceback
                 traceback.print_exc() # Print full traceback for unexpected errors
                 self.status_bar.showMessage(error_msg, 5000)
                 QMessageBox.critical(self, "File Save Error", f"An unexpected error occurred during saving:\n{e}")
        else:
             # This block executes if self.csvLines was empty
             print("MainWindow: No data collected or csvLines empty.") # Log this case
             self.status_bar.showMessage("Recording stopped. No data collected or saved.", 5000)
        # --- END: Saving Logic ---

        # --- Clean up UI state ---
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.toggle_colorbar_button.setEnabled(False)
        self.com_input.setEnabled(True)
        self.filename_input.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.toggle_filter_button.setEnabled(False)
        self.worker = None # Release worker instance
        # Reset other state variables
        self.colorbar_visible = COLORBAR_INITIALLY_VISIBLE # Reset from constant
        self.toggle_colorbar_button.setText("Hide Colorbar" if self.colorbar_visible else "Show Colorbar")
        # Use constant for default filter state
        self.artifact_filter_active = ARTIFACT_FILTER_ENABLED
        self.toggle_filter_button.setText("Enable Blob Filter" if not self.artifact_filter_active else "Disable Blob Filter")
        # Clear collected data AFTER attempting save, ready for next run
        self.csvLines.clear()
        print("MainWindow: UI state reset after worker finished.")
        # --- END: Clean up UI state ---


    def update_plot_and_data(self, map_data):
        # It applies threshold, orientation, then calls plot_window.update_plot
        if map_data is None or map_data.size != ROWS * COLS:
             if self.plot_window: self.plot_window.update_plot(None)
             return

        matrix_data = map_data.reshape(ROWS, COLS)
        noise_threshold = NOISE_THRESHOLD
        matrix_data[matrix_data < noise_threshold] = 0

        # --- Apply Blob Filter IF ACTIVE ---
        if self.artifact_filter_active:
            # print("DEBUG: Applying blob filter...") # Optional
            matrix_data = filter_small_blobs(matrix_data)  # Call the function
        # --- End Blob Filter ---

        # Apply Orientation Correction (USE YOUR WORKING VERSION)
        matrix_data_vis = np.flipud(matrix_data.T) # Example

        if self.plot_window:
            self.plot_window.update_plot(matrix_data_vis)

        if self.is_recording and map_data is not None:
            timestamp = time.time()
            # Decide if you want to save original map_data or the filtered matrix_data
            self.csvLines.append([timestamp] + map_data.flatten().tolist())  # Saves original


    def handle_worker_error(self, error_message):
        QMessageBox.critical(self, "Worker Thread Error", error_message)
        self.status_bar.showMessage(f"Error: {error_message}", 5000)
        if not self.serial_port_open: # Reset UI if port never opened
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.toggle_colorbar_button.setEnabled(False)
            self.toggle_filter_button.setEnabled(False)
            self.com_input.setEnabled(True)
            self.filename_input.setEnabled(True)
            self.browse_button.setEnabled(True)
            self.worker = None
            # Reset state from constants
            self.colorbar_visible = COLORBAR_INITIALLY_VISIBLE
            self.toggle_colorbar_button.setText("Hide Colorbar" if self.colorbar_visible else "Show Colorbar")
            self.artifact_filter_active = ARTIFACT_FILTER_ENABLED
            self.toggle_filter_button.setText(
                "Enable Blob Filter" if not self.artifact_filter_active else "Disable Blob Filter")


    def update_status(self, message):
        # (Keep as before)
        self.status_bar.showMessage(message, 3000)


    def closeEvent(self, event):
        # (Keep as before)
        if self.is_recording and self.worker:
            reply = QMessageBox.question(self, 'Confirm Exit',
                                         "Recording is in progress. Stop recording and exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                 self.stop_recording()
                 if self.plot_window: self.plot_window.close()
                 event.accept()
            else:
                 event.ignore()
        else:
             if self.worker and self.worker.isRunning(): self.worker.stop()
             if self.plot_window: self.plot_window.close()
             event.accept()
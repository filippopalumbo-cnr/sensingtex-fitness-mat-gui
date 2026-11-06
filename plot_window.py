# plot_window.py
"""Defines the PlotWindow class using manual axes positioning."""

import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.transforms import Bbox # Import Bbox if needed for manipulation

# Import local modules
from constants import ROWS, COLS, VIS_VMAX, VIS_CMAP, COP_MARKER_SIZE
from data_processing import calculate_cop

class PlotWindow(QWidget):
    """A separate window to display the Matplotlib plot. Uses manual axes positioning."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fitness Mat Plot")
        self.setGeometry(150, 150, 500, 700) # Safe starting position

        # --- Matplotlib Setup ---
        # Consider figsize closer to data aspect ratio to minimize internal whitespace
        self.figure = Figure(figsize=(8, 3.5)) # Example wide figsize
        print(f"DEBUG: Figure created with figsize={self.figure.get_size_inches()}")
        print("DEBUG: Using manual ax.set_position strategy.")

        self.canvas = FigureCanvas(self.figure)
        # --- Create axes WITHOUT specifying position initially ---
        # We will set position manually later
        self.ax = self.figure.add_subplot(111) # Let it add initially
        self.ax.set_axis_off()

        # --- Heatmap and CoP (Keep aspect='equal') ---
        heatmap_shape = (COLS, ROWS) # Confirm this matches transform
        heatmap_origin = 'upper'    # Confirm this matches transform
        self.heatmap = self.ax.imshow(np.zeros(heatmap_shape), cmap=VIS_CMAP,
                                      interpolation='nearest', vmin=0, vmax=VIS_VMAX,
                                      aspect='equal', # Keep aspect ratio
                                      origin=heatmap_origin)
        self.cop_marker, = self.ax.plot([], [], 'wo', markersize=COP_MARKER_SIZE)

        # --- Add colorbar ---
        # This call will likely ADJUST self.ax's position internally
        self.cbar = self.figure.colorbar(self.heatmap, ax=self.ax, fraction=0.07, pad=0.04)

        # --- Define Axes Positions ---
        # We need to get the position AFTER the figure has been drawn once
        # so that the adjustments made by colorbar() are included.
        print("DEBUG: Performing initial draw to calculate axes geometry...")
        self.canvas.draw() # Force initial draw
        self.ax_pos_with_cbar = self.ax.get_position() # Get actual position WITH colorbar space
        print(f"DEBUG: Initial Axes position WITH colorbar captured: {self.ax_pos_with_cbar}")

        # Define Target Axes Position WITHOUT colorbar
        # Make it wider, using most of the figure width minus small margins
        margin = 0.05 # Use slightly larger margin for simpler calculation
        # Position is [left, bottom, width, height]
        self.ax_pos_without_cbar_rect = [margin, margin, 1.0 - (2*margin), 1.0 - (2*margin)]
        print(f"DEBUG: Target Axes position WITHOUT colorbar defined as: {self.ax_pos_without_cbar_rect}")

        # --- REMOVE Subplots Adjust ---
        # self.adjust_params_with_cbar = ...
        # self.adjust_params_without_cbar = ...
        # self.figure.subplots_adjust(...) # Don't use subplots_adjust now

        # --- Layout for the QWidget ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1) # Minimal margins for canvas in window
        layout.addWidget(self.canvas)
        print("DEBUG: PlotWindow __init__ finished.")


    # --- Modified Method to Toggle Colorbar using ax.set_position ---
    def set_colorbar_visible(self, visible):
        if hasattr(self, 'cbar') and self.cbar and hasattr(self.cbar, 'ax'):
            # Check if state actually changed to avoid redundant updates
            current_visibility = self.cbar.ax.get_visible()
            if visible == current_visibility:
                # It might be useful to force apply position state anyway if window resized
                # print(f"DEBUG: Colorbar visibility already {visible}. Re-applying position.")
                pass # Or just return if no change desired on redundant clicks
                # return

            print(f"DEBUG: PlotWindow setting colorbar axes visible: {visible}")
            self.cbar.ax.set_visible(visible) # Hide/show the AXES

            # --- Apply Dynamic Axes Position ---
            try:
                pos_before = self.ax.get_position() # Get position before change
                print(f"DEBUG: Axes position BEFORE set_position: {pos_before}")

                if visible:
                    # Restore original position calculated by colorbar()
                    new_pos = self.ax_pos_with_cbar
                    print(f"DEBUG: Setting axes position for VISIBLE colorbar: {new_pos}")
                else:
                    # Apply the pre-defined wider position
                    new_pos = self.ax_pos_without_cbar_rect
                    print(f"DEBUG: Setting axes position for HIDDEN colorbar: {new_pos}")

                # Manually set the axes position [left, bottom, width, height]
                self.ax.set_position(new_pos)

                pos_after = self.ax.get_position() # Get position immediately after setting
                print(f"DEBUG: Axes position AFTER set_position: {pos_after}")

                self.canvas.draw_idle() # Redraw with new axes position
                print(f"DEBUG: PlotWindow redraw requested after set_position.")

            except Exception as e:
                print(f"ERROR during set_position or redraw: {e}")
                import traceback
                traceback.print_exc()
            # --- End Dynamic Position ---
        else:
            print("DEBUG: PlotWindow has no valid cbar reference to toggle.")
    # --- End Modified Method ---


    # update_plot remains the same
    def update_plot(self, matrix_data_vis):
        # ... (previous code) ...
        if matrix_data_vis is None:
             heatmap_shape = self.heatmap.get_array().shape # Use actual shape
             self.heatmap.set_data(np.zeros(heatmap_shape))
             self.cop_marker.set_visible(False)
             try: self.canvas.draw_idle()
             except Exception as e: print(f"Error during PlotWindow clear draw: {e}")
             return

        try: self.heatmap.set_data(matrix_data_vis)
        except ValueError as e:
            print(f"PlotWindow ValueError setting heatmap data: {e}. Data shape: {matrix_data_vis.shape}")
            return

        cop = calculate_cop(matrix_data_vis)
        if cop:
            self.cop_marker.set_data([cop[0]], [cop[1]])
            self.cop_marker.set_visible(True)
        else:
            self.cop_marker.set_visible(False)

        try: self.canvas.draw_idle()
        except Exception as e: print(f"Error during PlotWindow canvas draw: {e}")
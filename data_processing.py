# data_processing.py
"""Data processing functions like Center of Pressure calculation."""

import numpy as np
from scipy.ndimage import binary_opening, generate_binary_structure
from constants import COP_MIN_TOTAL_PRESSURE # Import constants

def calculate_cop(matrix):
    """Calculate the Center of Pressure (CoP) of the pressure matrix."""
    # (Keep the latest version of this function with the adjusted threshold)
    total_pressure = matrix.sum()
    # print(f"DEBUG calculate_cop: total_pressure = {total_pressure}") # Optional debug

    min_total_pressure_for_cop = COP_MIN_TOTAL_PRESSURE # Use constant

    if total_pressure < min_total_pressure_for_cop:
        return None

    rows, cols = matrix.shape
    # Meshgrid assumes matrix indices map to plot axes as configured in plot_window
    x_indices, y_indices = np.meshgrid(range(cols), range(rows))
    # Note: Ensure the matrix passed here IS the one displayed (correct orientation)
    # If displayed matrix has shape (COLS, ROWS), meshgrid might need adjustment
    # Assuming meshgrid is correct for the shape passed (e.g., if shape is COLS, ROWS)
    # then y_cop calculation uses 0th axis sum, x_cop uses 1st axis sum. Check calculation.

    # Let's assume matrix passed has shape (num_y_pixels, num_x_pixels) matching imshow
    # And meshgrid generates coords where y_indices increase along axis 0, x_indices along axis 1
    y_cop = (y_indices * matrix).sum() / total_pressure # Sum along axis 0 for y
    x_cop = (x_indices * matrix).sum() / total_pressure # Sum along axis 1 for x

    # print(f"Calc CoP on matrix sum {total_pressure:.0f}: X={x_cop:.2f}, Y={y_cop:.2f}")
    return x_cop, y_cop

# --- New Filtering Function ---
def filter_small_blobs(matrix, connectivity=1, iterations=1):
    """
    Removes small isolated regions of non-zero pixels using morphological opening.

    Args:
        matrix (np.ndarray): The 2D pressure matrix (ideally after noise thresholding).
        connectivity (int): Defines neighborhood for erosion/dilation (1=faces, 2=faces+edges+corners).
        iterations (int): How many times to apply erosion/dilation. More iterations remove larger objects.

    Returns:
        np.ndarray: The filtered matrix.
    """
    if matrix is None or matrix.sum() == 0:
        return matrix # Return if empty or all zeros

    # Define structuring element based on connectivity
    structure = generate_binary_structure(rank=matrix.ndim, connectivity=connectivity)
    # Example: structure for connectivity=1 is like: [[0,1,0],[1,1,1],[0,1,0]]
    # Example: structure for connectivity=2 is like: [[1,1,1],[1,1,1],[1,1,1]]

    # Create a binary mask where the matrix is above zero
    # Assumes noise thresholding already applied, so > 0 means "active"
    binary_mask = matrix > 0

    # Perform binary opening: Erosion shrinks objects, Dilation restores remaining ones
    # Small objects removed by erosion aren't restored by dilation.
    opened_mask = binary_opening(binary_mask, structure=structure, iterations=iterations)

    # Apply the filtered mask back to the original matrix
    filtered_matrix = matrix * opened_mask

    # Optional: Debug how much was removed
    removed_pixels = np.count_nonzero(binary_mask) - np.count_nonzero(opened_mask)
    if removed_pixels > 0:
        print(f"DEBUG filter_small_blobs: Removed {removed_pixels} artifact pixels.")

    return filtered_matrix
# --- End New Function ---
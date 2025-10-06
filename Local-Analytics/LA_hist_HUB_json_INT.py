# JSON Histogram Analytics - Updated for Full Hierarchy Support
# Modified to work with Stage > Cell > Module > SubElement > Component structure

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use('Agg')  # Use non-interactive backend
from matplotlib.figure import Figure
import io
import base64
import logging
from typing import List, Dict, Optional
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# Conditional imports for GUI functionality
try:
    import tkinter as tk
    from tkinter import ttk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    logger.info("Tkinter not available - GUI functionality disabled (API mode only)")


# ============================================================================
# DATA PROCESSING FUNCTIONS - Work with in-memory data objects WITH HIERARCHY
# ============================================================================

def extract_hierarchy_from_data(histogram_data_list):
    """
    Extract full hierarchy (Cell, Module, SubElement, Component, Variable) from histogram data objects

    Args:
        histogram_data_list: List of histogram data objects (MonitorKpisResults)

    Returns:
        pandas.DataFrame with columns: Cell, Module, SubElement, Component, Variable
    """
    logger.info(f"Extracting hierarchy from {len(histogram_data_list)} histogram data objects")
    data = []

    seen_combinations = set()

    for hist_obj in histogram_data_list:
        # Extract attributes from the object - support both dict and object access
        if isinstance(hist_obj, dict):
            cell = hist_obj.get('cell') or hist_obj.get('Cell', '')
            module = hist_obj.get('module') or hist_obj.get('Module', '')
            subelement = hist_obj.get('subelement') or hist_obj.get('SubElement', '')
            component = hist_obj.get('component') or hist_obj.get('Component', '')
            variable = hist_obj.get('variable') or hist_obj.get('Variable', '')
        else:
            cell = getattr(hist_obj, 'cell', '') or getattr(hist_obj, 'Cell', '')
            module = getattr(hist_obj, 'module', '') or getattr(hist_obj, 'Module', '')
            subelement = getattr(hist_obj, 'subelement', '') or getattr(hist_obj, 'SubElement', '')
            component = getattr(hist_obj, 'component', '') or getattr(hist_obj, 'Component', '')
            variable = getattr(hist_obj, 'variable', '') or getattr(hist_obj, 'Variable', '')

        combination = (cell, module, subelement, component, variable)
        if combination not in seen_combinations:
            seen_combinations.add(combination)
            data.append({
                "Cell": cell,
                "Module": module,
                "SubElement": subelement,
                "Component": component,
                "Variable": variable
            })
            logger.debug(f"Extracted: Cell={cell}, Module={module}, SubElement={subelement}, Component={component}, Variable={variable}")

    logger.info(f"Successfully extracted {len(data)} unique hierarchy combinations")
    return pd.DataFrame(data)


def extract_starting_dates_from_data(histogram_data_list, cell, module, subelement, component, variable):
    """
    Extract all unique Starting_date values for a specific hierarchy combination

    Args:
        histogram_data_list: List of histogram data objects
        cell: Target cell
        module: Target module
        subelement: Target subelement
        component: Target component
        variable: Target variable

    Returns:
        Sorted list of Starting_date strings
    """
    logger.debug(f"Extracting dates for: {cell}/{module}/{subelement}/{component}/{variable}")
    starting_dates = set()

    for hist_obj in histogram_data_list:
        # Handle both dict and object access
        if isinstance(hist_obj, dict):
            obj_cell = hist_obj.get('cell') or hist_obj.get('Cell', '')
            obj_module = hist_obj.get('module') or hist_obj.get('Module', '')
            obj_subelement = hist_obj.get('subelement') or hist_obj.get('SubElement', '')
            obj_component = hist_obj.get('component') or hist_obj.get('Component', '')
            obj_variable = hist_obj.get('variable') or hist_obj.get('Variable', '')
            obj_date = hist_obj.get('starting_date') or hist_obj.get('Starting_date', '')
        else:
            obj_cell = getattr(hist_obj, 'cell', '') or getattr(hist_obj, 'Cell', '')
            obj_module = getattr(hist_obj, 'module', '') or getattr(hist_obj, 'Module', '')
            obj_subelement = getattr(hist_obj, 'subelement', '') or getattr(hist_obj, 'SubElement', '')
            obj_component = getattr(hist_obj, 'component', '') or getattr(hist_obj, 'Component', '')
            obj_variable = getattr(hist_obj, 'variable', '') or getattr(hist_obj, 'Variable', '')
            obj_date = getattr(hist_obj, 'starting_date', '') or getattr(hist_obj, 'Starting_date', '')

        # Match the target combination
        if (obj_cell == cell and obj_module == module and obj_subelement == subelement and
                obj_component == component and obj_variable == variable):
            if obj_date:
                starting_dates.add(obj_date)

    logger.debug(f"Found {len(starting_dates)} unique starting dates")
    return sorted(starting_dates)


def extract_data_list_from_data(histogram_data_list, cell, module, subelement, component, variable, selected_date):
    """
    Extract Data list for a specific hierarchy combination and date

    Args:
        histogram_data_list: List of histogram data objects
        cell: Target cell
        module: Target module
        subelement: Target subelement
        component: Target component
        variable: Target variable
        selected_date: Target Starting_date

    Returns:
        numpy array of data values
    """
    logger.debug(f"Extracting data for: {cell}/{module}/{subelement}/{component}/{variable} on {selected_date}")

    for hist_obj in histogram_data_list:
        # Handle both dict and object access
        if isinstance(hist_obj, dict):
            obj_cell = hist_obj.get('cell') or hist_obj.get('Cell', '')
            obj_module = hist_obj.get('module') or hist_obj.get('Module', '')
            obj_subelement = hist_obj.get('subelement') or hist_obj.get('SubElement', '')
            obj_component = hist_obj.get('component') or hist_obj.get('Component', '')
            obj_variable = hist_obj.get('variable') or hist_obj.get('Variable', '')
            obj_date = hist_obj.get('starting_date') or hist_obj.get('Starting_date', '')
            obj_data = hist_obj.get('data') or hist_obj.get('Data_list', [])
        else:
            obj_cell = getattr(hist_obj, 'cell', '') or getattr(hist_obj, 'Cell', '')
            obj_module = getattr(hist_obj, 'module', '') or getattr(hist_obj, 'Module', '')
            obj_subelement = getattr(hist_obj, 'subelement', '') or getattr(hist_obj, 'SubElement', '')
            obj_component = getattr(hist_obj, 'component', '') or getattr(hist_obj, 'Component', '')
            obj_variable = getattr(hist_obj, 'variable', '') or getattr(hist_obj, 'Variable', '')
            obj_date = getattr(hist_obj, 'starting_date', '') or getattr(hist_obj, 'Starting_date', '')
            obj_data = getattr(hist_obj, 'data', []) or getattr(hist_obj, 'Data_list', [])

        # Match the target combination and date
        if (obj_cell == cell and obj_module == module and obj_subelement == subelement and
                obj_component == component and obj_variable == variable and obj_date == selected_date):
            data_array = np.array(obj_data)
            logger.debug(f"Found data list with {len(data_array)} values")
            return data_array

    logger.warning(f"No data found for {cell}/{module}/{subelement}/{component}/{variable} on {selected_date}")
    return np.array([])


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def fig_to_base64(fig):
    """
    Convert matplotlib figure to Base64 encoded PNG string

    Args:
        fig: matplotlib Figure object

    Returns:
        Base64 encoded string of PNG image
    """
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    buffer.close()
    return image_base64


# ============================================================================
# MAIN API FUNCTIONS WITH HIERARCHY SUPPORT
# ============================================================================

def generate_histogram_base64(histogram_data_list, params1, params2=None, max_filter=0):
    """
    Generate histogram from histogram data objects with full hierarchy and return as Base64 string

    Args:
        histogram_data_list: List of histogram data objects (MonitorKpisResults)
        params1: Dict with keys: Cell, Module, SubElement, Component, Variable, Date
        params2: Optional second dataset parameters for comparison
        max_filter: Optional maximum value filter (0 = no filter)

    Returns:
        Base64 encoded PNG image string
    """
    logger.info(f"Generating histogram with {len(histogram_data_list)} histogram data objects")
    logger.info(f"Params1: {params1}")
    if params2:
        logger.info(f"Params2: {params2}")
    logger.info(f"Max filter: {max_filter}")

    def get_data(cell, module, subelement, component, variable, date):
        if not all([cell, module, component, variable, date]):
            logger.warning(f"Missing parameters - cell:{cell}, module:{module}, subelement:{subelement}, component:{component}, variable:{variable}, date:{date}")
            return np.array([])

        data = extract_data_list_from_data(histogram_data_list, cell, module, subelement, component, variable, date)
        logger.info(f"Extracted {len(data)} data points for {cell}/{module}/{component}/{variable}")
        return data

    # Convert params to dict if they're Pydantic models
    if hasattr(params1, 'dict'):
        params1 = params1.dict()
    if params2 and hasattr(params2, 'dict'):
        params2 = params2.dict()

    # Get data for both datasets
    logger.info("Getting data for first dataset...")
    data1 = get_data(params1['Cell'], params1['Module'], params1['SubElement'],
                     params1['Component'], params1['Variable'], params1['Date'])
    data2 = np.array([])

    if params2:
        logger.info("Getting data for second dataset...")
        data2 = get_data(params2['Cell'], params2['Module'], params2['SubElement'],
                        params2['Component'], params2['Variable'], params2['Date'])

    logger.info(f"Dataset 1 size: {len(data1)}, Dataset 2 size: {len(data2)}")

    # Apply max filter if specified
    if max_filter > 0:
        logger.info(f"Applying max filter: {max_filter}")
        original_size1 = len(data1)
        data1 = data1[data1 <= max_filter]
        logger.info(f"Dataset 1 filtered: {original_size1} -> {len(data1)} values")

        if len(data2) > 0:
            original_size2 = len(data2)
            data2 = data2[data2 <= max_filter]
            logger.info(f"Dataset 2 filtered: {original_size2} -> {len(data2)} values")

    # Create figure
    logger.info("Creating histogram figure...")
    fig = Figure(figsize=(10, 5), dpi=100)
    ax = fig.add_subplot(111)

    # Build concise legends with hierarchy
    legend1 = f"Set 1: {params1['Module']}/{params1['Component']}/{params1['Variable']} ({params1['Date']})"

    # Plot first dataset
    if len(data1) > 0:
        logger.info(f"Plotting first dataset - {len(data1)} values, mean: {data1.mean():.2f}")
        ax.hist(data1, bins=30, alpha=0.5, label=legend1, color='blue', edgecolor='black')
        ax.axvline(data1.mean(), color='blue', linestyle='--', linewidth=2, label=f"Mean 1: {data1.mean():.2f}")
    else:
        logger.warning("First dataset is empty - no data to plot")

    # Plot second dataset if provided
    if len(data2) > 0:
        legend2 = f"Set 2: {params2['Module']}/{params2['Component']}/{params2['Variable']} ({params2['Date']})"
        logger.info(f"Plotting second dataset - {len(data2)} values, mean: {data2.mean():.2f}")
        ax.hist(data2, bins=30, alpha=0.5, label=legend2, color='green', edgecolor='black')
        ax.axvline(data2.mean(), color='green', linestyle='--', linewidth=2, label=f"Mean 2: {data2.mean():.2f}")

    ax.set_title("Combined Histogram Comparison", fontsize=12, fontweight='bold')
    ax.set_xlabel("Cycle time (s)")
    ax.set_ylabel("Frequency")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Convert to Base64 and cleanup
    logger.info("Converting figure to Base64...")
    base64_image = fig_to_base64(fig)
    fig.clear()
    logger.info(f"Successfully generated histogram Base64 string (length: {len(base64_image)})")
    return base64_image


def get_filtering_options(histogram_data_list):
    """
    Get available filtering options with full hierarchy from histogram data objects

    Args:
        histogram_data_list: List of histogram data objects (MonitorKpisResults)

    Returns:
        pandas.DataFrame with columns: Cell, Module, SubElement, Component, Variable
    """
    logger.info(f"Getting filtering options from {len(histogram_data_list)} histogram data objects")
    result = extract_hierarchy_from_data(histogram_data_list)
    logger.info(f"Successfully retrieved {len(result)} filtering options")
    return result


# Run GUI if this script is executed directly
if __name__ == "__main__":
    if not TKINTER_AVAILABLE:
        print("ERROR: Cannot run GUI mode - tkinter is not available in this environment")
        print("This module is designed to be imported by the FastAPI server.")
    else:
        print("This module is designed to be imported by the FastAPI server.")
        print("To use the API, start the FastAPI server with the main.py file")
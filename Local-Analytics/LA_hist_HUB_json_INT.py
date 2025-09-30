# JSON Histogram Analytics - Refactored for Direct JSON Data Processing
# Modified to accept JSON data objects directly instead of file paths
# Works entirely in-memory without file I/O

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
# DATA PROCESSING FUNCTIONS - Work with in-memory data objects
# ============================================================================

def extract_LCV_from_data(histogram_data_list):
    """
    Extract (Ligne, Component, Variable) combinations from histogram data objects

    Args:
        histogram_data_list: List of histogram data objects (MonitorKpisResults)

    Returns:
        pandas.DataFrame with columns: Ligne, Component, Variable
    """
    logger.info(f"Extracting LCV from {len(histogram_data_list)} histogram data objects")
    data = []

    seen_combinations = set()

    for hist_obj in histogram_data_list:
        # Extract attributes from the object
        # Handle both dict and object access patterns
        if isinstance(hist_obj, dict):
            ligne = hist_obj.get('ligne') or hist_obj.get('Ligne', '')
            component = hist_obj.get('component') or hist_obj.get('Component', '')
            variable = hist_obj.get('variable') or hist_obj.get('Variable', '')
        else:
            ligne = getattr(hist_obj, 'ligne', '') or getattr(hist_obj, 'Ligne', '')
            component = getattr(hist_obj, 'component', '') or getattr(hist_obj, 'Component', '')
            variable = getattr(hist_obj, 'variable', '') or getattr(hist_obj, 'Variable', '')

        # Only process valid PLC lines
        if ligne.startswith("plc_"):
            combination = (ligne, component, variable)
            if combination not in seen_combinations:
                seen_combinations.add(combination)
                data.append({
                    "Ligne": ligne,
                    "Component": component,
                    "Variable": variable
                })
                logger.debug(f"Extracted: Ligne={ligne}, Component={component}, Variable={variable}")

    logger.info(f"Successfully extracted {len(data)} unique LCV combinations")
    return pd.DataFrame(data)


def extract_starting_dates_from_data(histogram_data_list, ligne, component, variable):
    """
    Extract all unique Starting_date values for a specific ligne/component/variable

    Args:
        histogram_data_list: List of histogram data objects
        ligne: Target ligne
        component: Target component
        variable: Target variable

    Returns:
        Sorted list of Starting_date strings
    """
    logger.debug(f"Extracting dates for: {ligne}/{component}/{variable}")
    starting_dates = set()

    for hist_obj in histogram_data_list:
        # Handle both dict and object access
        if isinstance(hist_obj, dict):
            obj_ligne = hist_obj.get('ligne') or hist_obj.get('Ligne', '')
            obj_component = hist_obj.get('component') or hist_obj.get('Component', '')
            obj_variable = hist_obj.get('variable') or hist_obj.get('Variable', '')
            obj_date = hist_obj.get('starting_date') or hist_obj.get('Starting_date', '')
        else:
            obj_ligne = getattr(hist_obj, 'ligne', '') or getattr(hist_obj, 'Ligne', '')
            obj_component = getattr(hist_obj, 'component', '') or getattr(hist_obj, 'Component', '')
            obj_variable = getattr(hist_obj, 'variable', '') or getattr(hist_obj, 'Variable', '')
            obj_date = getattr(hist_obj, 'starting_date', '') or getattr(hist_obj, 'Starting_date', '')

        # Match the target combination
        if obj_ligne == ligne and obj_component == component and obj_variable == variable:
            if obj_date:
                starting_dates.add(obj_date)

    logger.debug(f"Found {len(starting_dates)} unique starting dates")
    return sorted(starting_dates)


def extract_data_list_from_data(histogram_data_list, ligne, component, variable, selected_date):
    """
    Extract Data list for a specific combination and date

    Args:
        histogram_data_list: List of histogram data objects
        ligne: Target ligne
        component: Target component
        variable: Target variable
        selected_date: Target Starting_date

    Returns:
        numpy array of data values
    """
    logger.debug(f"Extracting data for: {ligne}/{component}/{variable} on {selected_date}")

    for hist_obj in histogram_data_list:
        # Handle both dict and object access
        if isinstance(hist_obj, dict):
            obj_ligne = hist_obj.get('ligne') or hist_obj.get('Ligne', '')
            obj_component = hist_obj.get('component') or hist_obj.get('Component', '')
            obj_variable = hist_obj.get('variable') or hist_obj.get('Variable', '')
            obj_date = hist_obj.get('starting_date') or hist_obj.get('Starting_date', '')
            obj_data = hist_obj.get('data') or hist_obj.get('Data', [])
        else:
            obj_ligne = getattr(hist_obj, 'ligne', '') or getattr(hist_obj, 'Ligne', '')
            obj_component = getattr(hist_obj, 'component', '') or getattr(hist_obj, 'Component', '')
            obj_variable = getattr(hist_obj, 'variable', '') or getattr(hist_obj, 'Variable', '')
            obj_date = getattr(hist_obj, 'starting_date', '') or getattr(hist_obj, 'Starting_date', '')
            obj_data = getattr(hist_obj, 'data', []) or getattr(hist_obj, 'Data', [])

        # Match the target combination and date
        if (obj_ligne == ligne and obj_component == component and
                obj_variable == variable and obj_date == selected_date):
            data_array = np.array(obj_data)
            logger.debug(f"Found data list with {len(data_array)} values")
            return data_array

    logger.warning(f"No data found for {ligne}/{component}/{variable} on {selected_date}")
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
# MAIN API FUNCTIONS
# ============================================================================

def generate_histogram_base64(histogram_data_list, params1, params2=None, max_filter=0):
    """
    Generate histogram from histogram data objects and return as Base64 string

    Args:
        histogram_data_list: List of histogram data objects (MonitorKpisResults)
        params1: Dict with keys: ligne, component, variable, date
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

    def get_data(ligne, comp, var, date):
        if not all([ligne, comp, var, date]):
            logger.warning(f"Missing parameters - ligne:{ligne}, comp:{comp}, var:{var}, date:{date}")
            return np.array([])

        data = extract_data_list_from_data(histogram_data_list, ligne, comp, var, date)
        logger.info(f"Extracted {len(data)} data points for {ligne}/{comp}/{var}")
        return data

    # Convert params to dict if they're Pydantic models
    if hasattr(params1, 'dict'):
        params1 = params1.dict()
    if params2 and hasattr(params2, 'dict'):
        params2 = params2.dict()

    # Get data for both datasets
    logger.info("Getting data for first dataset...")
    data1 = get_data(params1['ligne'], params1['component'], params1['variable'], params1['date'])
    data2 = np.array([])

    if params2:
        logger.info("Getting data for second dataset...")
        data2 = get_data(params2['ligne'], params2['component'], params2['variable'], params2['date'])

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
    fig = Figure(figsize=(8, 4), dpi=100)
    ax = fig.add_subplot(111)

    # Build legends
    legend1 = f"Set 1: {params1['ligne']}, {params1['component']}, {params1['variable']}, {params1['date']}"

    # Plot first dataset
    if len(data1) > 0:
        logger.info(f"Plotting first dataset - {len(data1)} values, mean: {data1.mean():.2f}")
        ax.hist(data1, bins=30, alpha=0.5, label=legend1, color='blue', edgecolor='black')
        ax.axvline(data1.mean(), color='blue', linestyle='--', label=f"Mean 1: {data1.mean():.2f}")
    else:
        logger.warning("First dataset is empty - no data to plot")

    # Plot second dataset if provided
    if len(data2) > 0:
        legend2 = f"Set 2: {params2['ligne']}, {params2['component']}, {params2['variable']}, {params2['date']}"
        logger.info(f"Plotting second dataset - {len(data2)} values, mean: {data2.mean():.2f}")
        ax.hist(data2, bins=30, alpha=0.5, label=legend2, color='green', edgecolor='black')
        ax.axvline(data2.mean(), color='green', linestyle='--', label=f"Mean 2: {data2.mean():.2f}")

    ax.set_title("Combined Histogram")
    ax.set_xlabel("Cycle time (s)")
    ax.set_ylabel("Frequency")
    ax.legend()
    ax.grid(True)

    # Convert to Base64 and cleanup
    logger.info("Converting figure to Base64...")
    base64_image = fig_to_base64(fig)
    fig.clear()
    logger.info(f"Successfully generated histogram Base64 string (length: {len(base64_image)})")
    return base64_image


def get_filtering_options(histogram_data_list):
    """
    Get available filtering options from histogram data objects

    Args:
        histogram_data_list: List of histogram data objects (MonitorKpisResults)

    Returns:
        pandas.DataFrame with columns: Ligne, Component, Variable
    """
    logger.info(f"Getting filtering options from {len(histogram_data_list)} histogram data objects")
    result = extract_LCV_from_data(histogram_data_list)
    logger.info(f"Successfully retrieved {len(result)} filtering options")
    return result


# ============================================================================
# GUI FUNCTIONALITY (Optional - requires tkinter)
# ============================================================================

def launch_gui_dual(histogram_data_list):
    """
    Launch GUI with histogram data objects (in-memory)

    Args:
        histogram_data_list: List of histogram data objects
    """
    if not TKINTER_AVAILABLE:
        logger.error("Cannot launch GUI - tkinter is not available in this environment")
        print("ERROR: GUI functionality requires tkinter, which is not available.")
        print("This is expected in Docker/server environments. Use the API endpoints instead.")
        return

    df = extract_LCV_from_data(histogram_data_list)

    if df.empty:
        print("No valid histogram data found!")
        return

    def get_data(ligne, comp, var, date):
        if not all([ligne, comp, var, date]):
            return np.array([])
        return extract_data_list_from_data(histogram_data_list, ligne, comp, var, date)

    def update_all(*args):
        for menu in ['1', '2']:
            update_dependent_menus(menu)
        update_combined_histogram()

    def update_dependent_menus(menu_id):
        ligne = ligne_vars[menu_id].get()
        filtered = df[df["Ligne"] == ligne]
        components = sorted(filtered["Component"].unique())
        component_menus[menu_id]['menu'].delete(0, 'end')
        if components:
            for c in components:
                component_menus[menu_id]['menu'].add_command(
                    label=c,
                    command=lambda c=c, mid=menu_id: (component_vars[mid].set(c), update_variable_and_date(mid))
                )
            component_vars[menu_id].set(components[0])
            update_variable_and_date(menu_id)
        else:
            component_vars[menu_id].set('')
            variable_vars[menu_id].set('')
            date_vars[menu_id].set('')
            variable_menus[menu_id]['menu'].delete(0, 'end')
            date_menus[menu_id]['menu'].delete(0, 'end')

    def update_variable_and_date(menu_id):
        filtered = df[
            (df["Ligne"] == ligne_vars[menu_id].get()) &
            (df["Component"] == component_vars[menu_id].get())
            ]
        variables = sorted(filtered["Variable"].unique())
        variable_menus[menu_id]['menu'].delete(0, 'end')
        if variables:
            for v in variables:
                variable_menus[menu_id]['menu'].add_command(
                    label=v,
                    command=lambda v=v, mid=menu_id: (variable_vars[mid].set(v), update_date(mid))
                )
            variable_vars[menu_id].set(variables[0])
            update_date(menu_id)
        else:
            variable_vars[menu_id].set('')
            date_vars[menu_id].set('')
            date_menus[menu_id]['menu'].delete(0, 'end')

    def update_date(menu_id):
        ligne = ligne_vars[menu_id].get()
        comp = component_vars[menu_id].get()
        var = variable_vars[menu_id].get()

        dates = extract_starting_dates_from_data(histogram_data_list, ligne, comp, var)

        date_menus[menu_id]['menu'].delete(0, 'end')
        if dates:
            for d in dates:
                date_menus[menu_id]['menu'].add_command(
                    label=d,
                    command=lambda d=d, mid=menu_id: (date_vars[mid].set(d), update_combined_histogram())
                )
            date_vars[menu_id].set(dates[0])
            update_combined_histogram()
        else:
            date_vars[menu_id].set('')

    def update_combined_histogram():
        for widget in plot_frame.winfo_children():
            widget.destroy()
        for widget in stats_frames['1'].winfo_children():
            widget.destroy()
        for widget in stats_frames['2'].winfo_children():
            widget.destroy()

        try:
            max_val = float(max_filter_var.get())
        except ValueError:
            max_val = 0

        data1 = get_data(ligne_vars['1'].get(), component_vars['1'].get(),
                         variable_vars['1'].get(), date_vars['1'].get())
        data2 = get_data(ligne_vars['2'].get(), component_vars['2'].get(),
                         variable_vars['2'].get(), date_vars['2'].get())

        if max_val > 0:
            data1 = data1[data1 <= max_val]
            data2 = data2[data2 <= max_val]

        fig = Figure(figsize=(8, 4), dpi=100)
        ax = fig.add_subplot(111)

        legend1 = f"Set 1: {ligne_vars['1'].get()}, {component_vars['1'].get()}, {variable_vars['1'].get()}, {date_vars['1'].get()}"
        legend2 = f"Set 2: {ligne_vars['2'].get()}, {component_vars['2'].get()}, {variable_vars['2'].get()}, {date_vars['2'].get()}"

        if len(data1):
            ax.hist(data1, bins=30, alpha=0.5, label=legend1, color='blue', edgecolor='black')
            ax.axvline(data1.mean(), color='blue', linestyle='--', label=f"Mean 1: {data1.mean():.2f}")
        if len(data2):
            ax.hist(data2, bins=30, alpha=0.5, label=legend2, color='green', edgecolor='black')
            ax.axvline(data2.mean(), color='green', linestyle='--', label=f"Mean 2: {data2.mean():.2f}")

        ax.set_title("Combined Histogram")
        ax.set_xlabel("Cycle time (s)")
        ax.set_ylabel("Frequency")
        ax.legend()
        ax.grid(True)

        canvas = FigureCanvasTkAgg(fig, master=plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        for data, stats_frame in zip([data1, data2], [stats_frames['1'], stats_frames['2']]):
            if len(data):
                stats_text = (
                    f"Count: {len(data)}\n"
                    f"Mean: {data.mean():.2f}\n"
                    f"Median: {np.median(data):.2f}\n"
                    f"Min: {data.min():.2f}\n"
                    f"Max: {data.max():.2f}\n"
                    f"Std Dev: {data.std():.2f}"
                )
                tk.Label(stats_frame, text=stats_text, justify="left", anchor="nw").pack(fill="both", expand=True)

    # Initialize Tkinter GUI
    root = tk.Tk()
    root.title("Compare Two Data Sets")

    tk.Label(root, text="Max Value Filter (optional)").grid(row=0, column=0, sticky="w")
    max_filter_var = tk.StringVar()
    max_filter_entry = tk.Entry(root, textvariable=max_filter_var)
    max_filter_entry.grid(row=0, column=1, sticky="we")
    max_filter_var.trace_add("write", lambda *_: update_combined_histogram())

    ligne_vars, component_vars, variable_vars, date_vars = {}, {}, {}, {}
    ligne_menus, component_menus, variable_menus, date_menus = {}, {}, {}, {}
    stats_frames = {}

    for i, row in enumerate(['1', '2']):
        row_offset = 1 + i * 6

        ligne_vars[row] = tk.StringVar()
        tk.Label(root, text=f"Ligne {row}").grid(row=row_offset, column=0, sticky="w")
        ligne_menus[row] = ttk.OptionMenu(root, ligne_vars[row], "", *sorted(df["Ligne"].unique()),
                                          command=lambda _, r=row: update_dependent_menus(r))
        ligne_menus[row].grid(row=row_offset, column=1)

        component_vars[row] = tk.StringVar()
        tk.Label(root, text="Component").grid(row=row_offset + 1, column=0, sticky="w")
        component_menus[row] = ttk.OptionMenu(root, component_vars[row], '')
        component_menus[row].grid(row=row_offset + 1, column=1)

        variable_vars[row] = tk.StringVar()
        tk.Label(root, text="Variable").grid(row=row_offset + 2, column=0, sticky="w")
        variable_menus[row] = ttk.OptionMenu(root, variable_vars[row], '')
        variable_menus[row].grid(row=row_offset + 2, column=1)

        date_vars[row] = tk.StringVar()
        tk.Label(root, text="Starting_date").grid(row=row_offset + 3, column=0, sticky="w")
        date_menus[row] = ttk.OptionMenu(root, date_vars[row], '')
        date_menus[row].grid(row=row_offset + 3, column=1)

        stats_frames[row] = tk.Frame(root, borderwidth=2, relief="sunken")
        stats_frames[row].grid(row=row_offset, column=2, rowspan=4, sticky="nsew", padx=5, pady=5)

    plot_frame = tk.Frame(root, borderwidth=2, relief="groove")
    plot_frame.grid(row=0, column=3, rowspan=12, sticky="nsew", padx=10, pady=10)

    quit_button = tk.Button(root, text="Quitter", command=root.destroy)
    quit_button.grid(row=20, column=0, columnspan=2, pady=10)

    root.columnconfigure(1, weight=1)
    root.columnconfigure(3, weight=1)
    root.rowconfigure(11, weight=1)

    update_all()
    root.mainloop()
    root.quit()
    root.destroy()


# Run GUI if this script is executed directly
if __name__ == "__main__":
    if not TKINTER_AVAILABLE:
        print("ERROR: Cannot run GUI mode - tkinter is not available in this environment")
        print("This module is designed to be imported by the FastAPI server.")
    else:
        print("This module is designed to be imported by the FastAPI server.")
        print("To use the GUI, load histogram data objects and call launch_gui_dual(histogram_data_list)")
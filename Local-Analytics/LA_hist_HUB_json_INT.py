# JSON Histogram GUI with Filters, Stats, and Dynamic Legends

# This script allows the user to compare two datasets from JSON files via a GUI.
# It features histogram visualization, statistics display, max value filtering,
# and full legends built from the selected input parameters.


import os
import sys
import json
import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# Extract (Ligne, Component, Variable) info from filenames
def extract_LCV(json_output_dir):
    if not os.path.exists(json_output_dir):
        sys.exit("Invalid path: directory does not exist.")
    data = []
    for filename in os.listdir(json_output_dir):
        if filename.startswith("HIST_data_") and filename.endswith(".json"):
            base = filename.replace("HIST_data_", "").replace(".json", "")
            parts = base.split("_")
            if len(parts) >= 3:
                ligne = "_".join(parts[:2])
                variable = parts[-1]
                component = "_".join(parts[2:-1])
                if ligne.startswith("plc_"):
                    data.append({
                        "Ligne": ligne,
                        "Component": component,
                        "Variable": variable
                    })
    return pd.DataFrame(data)


# Read all unique Starting_date values from a given JSON file
def extract_starting_dates(filepath):
    starting_dates = set()

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        # Try to parse as standard JSON first
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "Starting_date" in data:
                starting_dates.add(data["Starting_date"])
                return sorted(starting_dates)
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and "Starting_date" in entry:
                        starting_dates.add(entry["Starting_date"])
                return sorted(starting_dates)
        except json.JSONDecodeError:
            pass

        # If standard JSON parsing fails, try JSONL format (line by line)
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and "Starting_date" in entry:
                        starting_dates.add(entry["Starting_date"])
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"Error reading file {filepath}: {e}")

    return sorted(starting_dates)


# Extract the Data_list for a selected Starting_date in a file
def extract_data_list(filepath, selected_date):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        # Try to parse as standard JSON first
        try:
            data = json.loads(content)
            if isinstance(data, dict) and data.get("Starting_date") == selected_date:
                return data.get("Data_list", [])
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("Starting_date") == selected_date:
                        return entry.get("Data_list", [])
        except json.JSONDecodeError:
            pass

        # If standard JSON parsing fails, try JSONL format (line by line)
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and entry.get("Starting_date") == selected_date:
                        return entry.get("Data_list", [])
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"Error reading file {filepath}: {e}")

    return []


# Main GUI function
def launch_gui_dual(df, json_output_dir):
    def get_file_data(ligne, comp, var, date):
        if not all([ligne, comp, var, date]):
            return np.array([])
        filename = f"HIST_data_{ligne}_{comp}_{var}.json"
        full_path = os.path.join(json_output_dir, filename)
        if not os.path.exists(full_path):
            return np.array([])
        data_list = extract_data_list(full_path, date)
        return np.array(data_list)

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
        filename = f"HIST_data_{ligne_vars[menu_id].get()}_{component_vars[menu_id].get()}_{variable_vars[menu_id].get()}.json"
        full_path = os.path.join(json_output_dir, filename)
        dates = extract_starting_dates(full_path)
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

        data1 = get_file_data(ligne_vars['1'].get(), component_vars['1'].get(), variable_vars['1'].get(), date_vars['1'].get())
        data2 = get_file_data(ligne_vars['2'].get(), component_vars['2'].get(), variable_vars['2'].get(), date_vars['2'].get())

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
        ligne_menus[row] = ttk.OptionMenu(root, ligne_vars[row], "", *sorted(df["Ligne"].unique()), command=lambda _, r=row: update_dependent_menus(r))
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
    if not tk._default_root:
        json_output_dir = os.path.join(
            "./JSON_hist_data/"
        )
        df = extract_LCV(json_output_dir)
        launch_gui_dual(df, json_output_dir)

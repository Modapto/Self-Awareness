import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import argparse


def load_model(model_path):
    """Load the quadratic model from JSON file"""
    with open(model_path, "r") as f:
        model_data = json.load(f)

    intercept = model_data["intercept"]
    coefficients = model_data["coefficients"]

    return intercept, coefficients


def predict_force(intercept, coefficients, extraction_number):
    """Predict force using quadratic model for a given number of extractions"""
    # Create polynomial features manually since we know it's a quadratic model
    # [1, x, x^2]
    x_poly = [1, extraction_number, extraction_number ** 2]

    # Calculate prediction using dot product
    y_pred = intercept
    for i, coef in enumerate(coefficients):
        y_pred += coef * x_poly[i]

    return y_pred


def process_events(events_file, model_path, threshold, interval_minutes=5, db_output='db.json'):
    """
    Process events file, count insertions in 5-minute intervals,
    predict force, and check against threshold
    """
    # Load model
    intercept, coefficients = load_model(model_path)

    # Read events CSV file
    try:
        # First try with semicolon as separator
        df = pd.read_csv(events_file, encoding='utf-8', sep=';')
    except Exception:
        # If that fails, try comma as separator
        try:
            df = pd.read_csv(events_file, encoding='utf-8')
        except Exception as e:
            # If still failing, try to read as raw text
            with open(events_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            print(f"Warning: Could not parse CSV properly. First few lines: {lines[:3]}")
            raise e

    # Print column names for debugging
    print(f"Columns in the events file: {df.columns.tolist()}")

    # Extract timestamp, event type, and KH columns
    # Assuming the format matches what we saw in the byte description
    timestamp_col = [col for col in df.columns if 'Timestamp' in col or 'time' in col.lower()][0] \
        if any('Timestamp' in col or 'time' in col.lower() for col in df.columns) else df.columns[3]

    event_type_col = [col for col in df.columns if 'Event Type' in col or 'event' in col.lower()][0] \
        if any('Event Type' in col or 'event' in col.lower() for col in df.columns) else df.columns[1]

    # Try to identify KH type and KH unique ID columns
    kh_type_col = [col for col in df.columns if 'KH Type' in col][0] \
        if any('KH Type' in col for col in df.columns) else df.columns[4] if len(df.columns) > 4 else None

    kh_id_col = [col for col in df.columns if 'KH Unique ID' in col or 'KH ID' in col][0] \
        if any('KH Unique ID' in col or 'KH ID' in col for col in df.columns) else df.columns[5] if len(
        df.columns) > 5 else None

    # Convert timestamp to datetime if it's not already
    try:
        # First check if it looks like a Unix timestamp (numeric values)
        if pd.api.types.is_numeric_dtype(df[timestamp_col]) or df[timestamp_col].str.isnumeric().all():
            # Convert to int first in case it's stored as string
            timestamps = pd.to_numeric(df[timestamp_col], errors='coerce')
            print(f"Detected Unix timestamps, converting from epoch seconds. Sample: {timestamps.head()}")
            df['datetime'] = pd.to_datetime(timestamps, unit='s')
        else:
            # Try standard datetime parsing
            df['datetime'] = pd.to_datetime(df[timestamp_col])

        print(f"Timestamp conversion successful. Sample dates: {df['datetime'].head()}")
    except Exception as e:
        print(f"Warning: Could not parse timestamp column. Error: {str(e)}")
        print(f"Using row index instead.")
        # If timestamp conversion fails, create artificial timestamps
        df['datetime'] = pd.date_range(start='2023-01-01', periods=len(df), freq='1min')

    # Create time windows (5-minute intervals)
    df['time_window'] = df['datetime'].dt.floor(f'{interval_minutes}min')

    # Filter only insertion events
    insertions_df = df[df[event_type_col] == 1].copy()

    # Group by time window
    window_groups = insertions_df.groupby('time_window')

    # Create data for db.json
    db_data = {
        'metadata': {
            'created_at': datetime.now().isoformat(),
            'threshold': threshold,
            'interval_minutes': interval_minutes,
            'model_path': model_path,
            'events_file': events_file
        },
        'windows': []
    }

    # Process each time window
    running_total = 0
    for time_window, group in window_groups:
        # Get window details
        insertions_in_window = len(group)
        running_total += insertions_in_window

        # Get KH information if available
        kh_info = {}
        if kh_type_col is not None and kh_id_col is not None:
            # Use most common KH type and ID in this window
            if kh_type_col in group.columns:
                kh_types = group[kh_type_col].value_counts()
                if not kh_types.empty:
                    kh_info['type'] = int(kh_types.index[0]) if pd.api.types.is_numeric_dtype(kh_types.index) else str(
                        kh_types.index[0])

            if kh_id_col in group.columns:
                kh_ids = group[kh_id_col].value_counts()
                if not kh_ids.empty:
                    kh_info['id'] = int(kh_ids.index[0]) if pd.api.types.is_numeric_dtype(kh_ids.index) else str(
                        kh_ids.index[0])

        # Get first and last insertion indices
        first_idx = group.index.min()
        last_idx = group.index.max()

        # Convert time_window to string for JSON serialization
        time_window_str = time_window.isoformat() if hasattr(time_window, 'isoformat') else str(time_window)

        # Predict force using the quadratic model
        predicted_force = predict_force(intercept, coefficients, running_total)

        # Take absolute value as mentioned in requirements
        abs_predicted_force = abs(predicted_force)

        # Check if force exceeds threshold
        exceeds_threshold = abs_predicted_force > threshold

        # Create window data
        window_data = {
            'time_window': time_window_str,
            'insertions': {
                'count': insertions_in_window,
                'total': running_total,
                'first_index': int(first_idx),
                'last_index': int(last_idx)
            },
            'force': {
                'predicted': float(abs_predicted_force),
                'exceeds_threshold': bool(exceeds_threshold)
            }
        }

        # Add KH info if available
        if kh_info:
            window_data['kh'] = kh_info

        # Add to database
        db_data['windows'].append(window_data)

        # Print notification if threshold exceeded
        if exceeds_threshold:
            print(f"NOTIFICATION OF WEAR: At {time_window}, after {running_total} total insertions, "
                  f"predicted force {abs_predicted_force:.2f} exceeds threshold of {threshold}")

    # Save database to JSON file
    with open(db_output, 'w') as f:
        json.dump(db_data, f, indent=4)

    print(f"Results saved to database: {db_output}")

    return db_data


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Monitor tool wear based on insertion events')
    parser.add_argument('events_file', help='Path to the events CSV file')
    parser.add_argument('--model', default='quadratic_model.json', help='Path to the model JSON file')
    parser.add_argument('--threshold', type=float, default=150.0, help='Force threshold for wear notification')
    parser.add_argument('--interval', type=int, default=5, help='Time interval in minutes')
    parser.add_argument('--output', default='db.json', help='Path to save results database JSON (default: db.json)')
    parser.add_argument('--csv-output', help='Path to save results as CSV (optional)')

    args = parser.parse_args()

    print(f"Processing events from: {args.events_file}")
    print(f"Using model from: {args.model}")
    print(f"Force threshold: {args.threshold}")
    print(f"Time interval: {args.interval} minutes")

    # Process events and get results
    db_data = process_events(
        args.events_file,
        args.model,
        args.threshold,
        args.interval,
        args.output
    )

    # Print summary
    # print("\nSummary:")
    # print(f"Total time windows analyzed: {len(db_data['windows'])}")
    # exceeds_count = sum(1 for window in db_data['windows'] if window['force']['exceeds_threshold'])
    # print(f"Windows exceeding threshold: {exceeds_count}")
    #
    # if db_data['windows']:
    #     max_force = max(window['force']['predicted'] for window in db_data['windows'])
    #     print(f"Maximum predicted force: {max_force:.2f}")

    # Save as CSV if requested
    if args.csv_output:
        # Convert the JSON structure to a DataFrame
        windows_data = []
        for window in db_data['windows']:
            window_row = {
                'time_window': window['time_window'],
                'insertions_in_window': window['insertions']['count'],
                'total_insertions': window['insertions']['total'],
                'first_index': window['insertions']['first_index'],
                'last_index': window['insertions']['last_index'],
                'predicted_force': window['force']['predicted'],
                'exceeds_threshold': window['force']['exceeds_threshold']
            }

            # Add KH info if available
            if 'kh' in window:
                if 'type' in window['kh']:
                    window_row['kh_type'] = window['kh']['type']
                if 'id' in window['kh']:
                    window_row['kh_id'] = window['kh']['id']

            windows_data.append(window_row)

        csv_df = pd.DataFrame(windows_data)
        csv_df.to_csv(args.csv_output, index=False)
        print(f"Results also saved as CSV: {args.csv_output}")


if __name__ == "__main__":
    main()
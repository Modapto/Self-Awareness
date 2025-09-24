# wear_orchestrator.py
import subprocess
import time
import os
import pandas as pd
import csv
from core.wear_monitor import predict_force, load_model
import json
import glob
import re
from datetime import datetime


class MESOrchestrator:
    def __init__(self, chunk_directory, model_path, threshold=16, interval_minutes=5):
        self.chunk_directory = chunk_directory
        self.model_path = model_path
        self.threshold = threshold
        self.interval_minutes = interval_minutes

        # Load the model
        self.intercept, self.coefficients = load_model(model_path)

        # Track state
        self.current_chunk = 0
        self.total_insertions = 0
        self.server_process = None
        self.notifications_file = "../active_notifications.csv"
        self.empty_notifications_file = "../data/notifications/0notif.csv"

        # Initialize database
        self.db_data = {
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'threshold': threshold,
                'interval_minutes': interval_minutes,
                'model_path': model_path,
                'chunk_directory': chunk_directory,
                'total_chunks_processed': 0
            },
            'chunks': []
        }

        # Initialize empty notifications file with header
        self._create_empty_notifications_file()

        # Track when threshold is first crossed
        self.threshold_crossed = False

    def _create_empty_notifications_file(self):
        """Create an empty notifications file with header"""
        with open(self.notifications_file, 'w', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Header byte (0xfe)", "Issue type (0x01)",
                             "RFID Station ID [1..9]", "Timestamp 8bytes",
                             "KH Type [1..3]", "KH Unique ID [1..999999]"])

        with open(self.empty_notifications_file, 'w', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Header byte (0xfe)", "Issue type (0x01)",
                             "RFID Station ID [1..9]", "Timestamp 8bytes",
                             "KH Type [1..3]", "KH Unique ID [1..999999]"])

    def _start_server(self, events_file, notifications_file):
        """Start the MES server with specific event and notification files"""
        # Kill existing server if running
        if self.server_process:
            self.server_process.terminate()
            time.sleep(1)

        # Start new server
        self.server_process = subprocess.Popen(
            ["MesServer.exe", notifications_file, events_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,  # Line buffered
            universal_newlines=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # For Windows
        )

        # Give server time to initialize and load events
        time.sleep(3)

        # Check if server started properly using non-blocking readline
        try:
            import select
            import sys

            # Non-blocking read for Windows
            if sys.platform == 'win32':
                # For Windows, we'll just wait a fixed time and assume it started
                print("Server started (Windows - output capture limited)")
            else:
                # For Unix-like systems
                ready, _, _ = select.select([self.server_process.stdout], [], [], 0.1)
                if ready:
                    line = self.server_process.stdout.readline()
                    if line:
                        print(f"Server: {line.strip()}")
        except ImportError:
            # select module not available, skip output reading
            pass

        print(f"Started server with events: {events_file}, notifications: {notifications_file}")

    def _run_client_get_event(self):
        """Run client to get an event from register 3091"""
        print("Attempting to run client for getting event...")

        process = subprocess.Popen(
            ["MesClient.exe", "127.0.0.1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )

        # Send commands: 2 (GETREG), 3091 (register)
        commands = "2\n3091\n"
        print(f"Sending commands: {commands.strip()}")

        try:
            stdout, stderr = process.communicate(input=commands, timeout=10)
            print(f"Client stdout: {stdout}")
            print(f"Client stderr: {stderr}")
        except subprocess.TimeoutExpired:
            print("Client timed out!")
            process.kill()
            return None

        # Parse response to get event data
        lines = stdout.split('\n')
        print(f"Response lines: {lines}")

        # Check for no events message first
        for line in lines:
            if "No Saw Insertion/Extraction Events to notify" in line:
                print("No events found (queue empty)")
                return None

        # Then check for actual events
        for line in lines:
            if "Saw Event detected" in line:
                # Extract event type using regex
                match = re.search(r'type --> (\d+)', line)
                if match:
                    event_type = int(match.group(1))

                    # Extract timestamp, KH type, and unique ID from subsequent lines
                    timestamp = None
                    kh_type = None
                    kh_id = None

                    idx = lines.index(line)
                    for next_line in lines[idx + 1:]:
                        if "Timestamp" in next_line:
                            timestamp = next_line.split("-->")[1].strip()
                        elif "KH Type" in next_line:
                            kh_type = int(next_line.split("-->")[1].strip())
                        elif "KH Unique ID" in next_line:
                            kh_id = int(next_line.split("-->")[1].strip())

                    print(
                        f"Extracted event: type={event_type}, timestamp={timestamp}, kh_type={kh_type}, kh_id={kh_id}")
                    return {
                        'event_type': event_type,
                        'timestamp': timestamp,
                        'kh_type': kh_type,
                        'kh_id': kh_id
                    }

        print("No event pattern matched")
        return None

    def _run_client_get_events_block(self, count=10):
        """Run client to get multiple events from register 3091 using GETREGBLOCK"""
        print(f"Attempting to get {count} events using GETREGBLOCK...")

        process = subprocess.Popen(
            ["MesClient.exe", "127.0.0.1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )

        # Send commands: 3 (GETREGBLOCK), 3091 (register), count (number of events)
        commands = f"3\n3091\n{count}\n"
        print(f"Sending commands: {commands.strip()}")

        try:
            stdout, stderr = process.communicate(input=commands, timeout=30)
            print(f"Client stdout: {stdout}")
            if stderr:
                print(f"Client stderr: {stderr}")
        except subprocess.TimeoutExpired:
            print("Client timed out!")
            process.kill()
            return []

        # Parse multiple events from response
        events = []
        lines = stdout.split('\n')

        # Check if we received the expected response
        if not any("Received \"0xfd\" from the server" in line for line in lines):
            print("Did not receive expected GETREGBLOCK response")
            return events

        # Parse events using the pattern from the MesClient output
        current_event = None
        for i, line in enumerate(lines):
            if "Event #" in line:
                if current_event:
                    events.append(current_event)
                current_event = None

            if "Saw Event detected" in line:
                match = re.search(r'type --> (\d+)', line)
                if match:
                    current_event = {
                        'event_type': int(match.group(1)),
                        'timestamp': None,
                        'kh_type': None,
                        'kh_id': None
                    }

            if current_event:
                if "Timestamp" in line:
                    timestamp_str = line.split("-->")[1].strip()
                    current_event['timestamp'] = timestamp_str
                elif "KH Type" in line:
                    kh_type = int(line.split("-->")[1].strip())
                    current_event['kh_type'] = kh_type
                elif "KH Unique ID" in line:
                    kh_id = int(line.split("-->")[1].strip())
                    current_event['kh_id'] = kh_id

            if "No more Saw Insertion/Extraction Events" in line:
                print("No more events to retrieve")
                break

        # Add the last event if it exists
        if current_event:
            events.append(current_event)

        print(f"Retrieved {len(events)} events using GETREGBLOCK")
        for idx, event in enumerate(events):
            print(f"Event {idx + 1}: {event}")

        return events

    def _run_client_clear_register(self, register):
        """Run client to clear a register"""
        print(f"Clearing register {register}...")

        process = subprocess.Popen(
            ["MesClient.exe", "127.0.0.1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )

        # Send commands: 4 (SETREG), register, 0 (low), 0 (high)
        commands = f"4\n{register}\n0\n0\n"
        print(f"Sending clear commands: {commands.strip()}")

        try:
            stdout, stderr = process.communicate(input=commands, timeout=15)
            print(f"Clear stdout: {stdout}")
            print(f"Clear stderr: {stderr}")

            # Check if clearing was successful based on client response
            if "Received \"0x00\" (no errors in the put operation)" in stdout:
                print("Register successfully cleared")
            else:
                print("Warning: Register clear response not as expected")

            return stdout
        except subprocess.TimeoutExpired:
            print("Client timed out during clear!")
            process.kill()
            return None

    def _collect_events_for_interval(self, chunk_file=None):
        """Collect all events from the current chunk"""
        print("Starting to collect events...")
        events = []

        # If chunk_file is provided, determine how many events to expect
        expected_events = None
        if chunk_file:
            expected_events = self._verify_server_loaded_events(chunk_file)
            print(f"Expecting {expected_events} events from chunk file")

        # Use GETREGBLOCK to get all events at once
        if expected_events and expected_events > 0:
            # Add a small buffer to ensure we get all events
            batch_size = expected_events + 5
            print(f"Attempting to get all {expected_events} events in one batch...")

            batch_events = self._run_client_get_events_block(count=batch_size)

            if batch_events:
                events.extend(batch_events)
                print(f"Collected all {len(batch_events)} events in one batch")

                # Clear the register after getting all events
                self._run_client_clear_register(3091)
                time.sleep(0.5)
            else:
                print("Failed to get events in one batch, falling back to smaller batches")
                # Fallback to smaller batches if single batch fails
                batch_size = 50  # Use larger batch size
                empty_batch_count = 0
                max_empty_batches = 2

                while True:
                    batch_events = self._run_client_get_events_block(count=batch_size)

                    if not batch_events:
                        empty_batch_count += 1
                        if empty_batch_count >= max_empty_batches:
                            print("No more events to collect")
                            break
                        time.sleep(1.0)
                        continue
                    else:
                        empty_batch_count = 0
                        events.extend(batch_events)
                        print(f"Collected batch of {len(batch_events)} events. Total so far: {len(events)}")

                        # Clear the register after each batch
                        self._run_client_clear_register(3091)
                        time.sleep(0.5)
        else:
            # If we don't know how many events to expect, use the original logic
            batch_size = 50  # Use larger batch size
            empty_batch_count = 0
            max_empty_batches = 2

            while True:
                batch_events = self._run_client_get_events_block(count=batch_size)

                if not batch_events:
                    empty_batch_count += 1
                    if empty_batch_count >= max_empty_batches:
                        print("No more events to collect")
                        break
                    time.sleep(1.0)
                    continue
                else:
                    empty_batch_count = 0
                    events.extend(batch_events)
                    print(f"Collected batch of {len(batch_events)} events. Total so far: {len(events)}")

                    # Clear the register after each batch
                    self._run_client_clear_register(3091)
                    time.sleep(0.5)

        # Fall back to single event collection if block retrieval had issues
        if not events:
            print("Falling back to single event collection...")
            consecutive_empty_reads = 0
            max_empty_reads = 5

            while True:
                event = self._run_client_get_event()

                if event is None:
                    consecutive_empty_reads += 1
                    print(f"Empty read {consecutive_empty_reads}/{max_empty_reads}")

                    if consecutive_empty_reads >= max_empty_reads:
                        print("No more events to collect")
                        break

                    time.sleep(1.0)
                    continue
                else:
                    consecutive_empty_reads = 0

                events.append(event)
                print(f"Collected event: {event}")

                # Clear the register to get next event
                print("Clearing register 3091...")
                self._run_client_clear_register(3091)
                time.sleep(0.5)

        print(f"Finished collecting. Total events: {len(events)}")
        return events

    def _process_events_for_wear(self, events, chunk_index, chunk_file):
        """Process collected events and check for wear, update database"""
        insertions = [e for e in events if e['event_type'] == 1]
        insertions_count = len(insertions)

        # Create chunk data structure
        chunk_data = {
            'chunk_index': chunk_index,
            'chunk_file': chunk_file,
            'timestamp': datetime.now().isoformat(),
            'events': {
                'total': len(events),
                'insertions': insertions_count,
                'extractions': len([e for e in events if e['event_type'] == 2])
            },
            'insertions_cumulative': self.total_insertions + insertions_count,
            'force': {
                'predicted': 0.0,
                'exceeds_threshold': False
            },
            'kh_info': [],
            'threshold_exceeding_events': []
        }

        # Group KH information
        kh_groups = {}
        for event in events:
            if event['kh_id'] and event['kh_type']:
                key = f"{event['kh_type']}-{event['kh_id']}"
                if key not in kh_groups:
                    kh_groups[key] = {
                        'type': event['kh_type'],
                        'id': event['kh_id'],
                        'insertions': 0,
                        'extractions': 0
                    }
                if event['event_type'] == 1:
                    kh_groups[key]['insertions'] += 1
                else:
                    kh_groups[key]['extractions'] += 1

        chunk_data['kh_info'] = list(kh_groups.values())

        notifications_created = 0
        if insertions:
            # Process each insertion event to check wear
            for idx, insertion_event in enumerate(insertions):
                current_total = self.total_insertions + idx + 1
                current_force = abs(predict_force(self.intercept, self.coefficients, current_total))

                # Check if this event causes force to exceed threshold
                if current_force > self.threshold:
                    # Create notification for this event
                    notification = self._create_notification(insertion_event, current_force)
                    self._save_notification(notification)
                    notifications_created += 1

                    # Add this event to the threshold exceeding events list
                    chunk_data['threshold_exceeding_events'].append({
                        'index_in_chunk': idx,
                        'kh_type': insertion_event['kh_type'],
                        'kh_id': insertion_event['kh_id'],
                        'timestamp': insertion_event['timestamp'],
                        'force_at_event': float(current_force),
                        'cumulative_insertions': current_total
                    })

                    print(
                        f"WEAR NOTIFICATION #{notifications_created} CREATED for KH {insertion_event['kh_type']}-{insertion_event['kh_id']} (Force: {current_force:.2f})")

            # Update total insertions after processing all events
            self.total_insertions += insertions_count

            # Calculate final force for this chunk
            predicted_force = predict_force(self.intercept, self.coefficients, self.total_insertions)
            abs_force = abs(predicted_force)

            chunk_data['force']['predicted'] = float(abs_force)
            chunk_data['force']['exceeds_threshold'] = bool(abs_force > self.threshold)
            chunk_data['notifications_created'] = notifications_created

            print(f"Total insertions: {self.total_insertions}, Final chunk force: {abs_force:.2f}")

            if notifications_created > 0:
                print(f"Created {notifications_created} wear notifications for this chunk")
                self.db_data['chunks'].append(chunk_data)
                return True

        self.db_data['chunks'].append(chunk_data)
        return False

    def _create_notification(self, insertion_event, force):
        """Create a notification for wear"""
        return {
            'header': '0xfe',
            'issue_type': '1',  # Quality issue type 1
            'rfid_station': '6',  # From your example
            'timestamp': insertion_event['timestamp'],
            'kh_type': str(insertion_event['kh_type']),
            'kh_id': str(insertion_event['kh_id'])
        }

    def _save_notification(self, notification):
        """Save notification to file"""
        with open(self.notifications_file, 'a', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                notification['header'],
                notification['issue_type'],
                notification['rfid_station'],
                notification['timestamp'],
                notification['kh_type'],
                notification['kh_id']
            ])

    def _verify_server_loaded_events(self, chunk_file):
        """Verify how many events the server loaded from the chunk file"""
        try:
            df = pd.read_csv(chunk_file, delimiter=';')
            expected_events = len(df)
            print(f"Expected events in chunk: {expected_events}")
            return expected_events
        except Exception as e:
            print(f"Error reading chunk file: {e}")
            return -1

    def _save_database(self, filename='db_orchestrator.json'):
        """Save the database to JSON file"""
        self.db_data['metadata']['total_chunks_processed'] = len(self.db_data['chunks'])
        self.db_data['metadata']['total_insertions'] = self.total_insertions

        # Add summary statistics
        self.db_data['summary'] = {
            'total_events': sum(chunk['events']['total'] for chunk in self.db_data['chunks']),
            'total_insertions': self.total_insertions,
            'total_extractions': sum(chunk['events']['extractions'] for chunk in self.db_data['chunks']),
            'chunks_with_threshold_exceeded': sum(
                1 for chunk in self.db_data['chunks'] if chunk['force']['exceeds_threshold']),
            'notifications_created': sum(chunk.get('notifications_created', 0) for chunk in self.db_data['chunks']),
            'total_threshold_exceeding_events': sum(
                len(chunk.get('threshold_exceeding_events', [])) for chunk in self.db_data['chunks'])
        }

        with open(filename, 'w') as f:
            json.dump(self.db_data, f, indent=4)

        print(f"Database saved to {filename}")

    def run(self):
        """Main orchestration loop"""
        # Get sorted list of chunk files
        chunk_files = sorted(glob.glob(os.path.join(self.chunk_directory, "chunk_*.csv")))

        if not chunk_files:
            print(f"No chunk files found in {self.chunk_directory}")
            return

        print(f"Found {len(chunk_files)} chunk files")

        try:
            for chunk_index, chunk_file in enumerate(chunk_files):
                print(f"\n--- Processing chunk {chunk_index + 1}/{len(chunk_files)} ---")

                # Verify expected events
                expected_events = self._verify_server_loaded_events(chunk_file)
                print("After verify_server_loaded_events")

                # Verify chunk file format
                verify_chunk_file(chunk_file)
                print("After verify_chunk_file")

                # Determine which notifications file to use
                notification_file = self.notifications_file if os.path.exists(self.notifications_file) \
                    else self.empty_notifications_file
                print(f"Using notification file: {notification_file}")

                # Start server with current chunk
                self._start_server(chunk_file, notification_file)
                print("After _start_server")

                # Collect events from this chunk
                events = self._collect_events_for_interval(chunk_file)
                print(f"Collected {len(events)} events from chunk {chunk_index + 1} (expected: {expected_events})")

                if len(events) < expected_events:
                    print(f"WARNING: Missing {expected_events - len(events)} events!")

                # Process events for wear analysis
                if events:
                    wear_detected = self._process_events_for_wear(events, chunk_index, chunk_file)
                    if wear_detected:
                        print(f"WEAR DETECTED in chunk {chunk_index + 1}!")

                # Save database after each chunk
                self._save_database()

                # Optional: simulate real-time by waiting
                # time.sleep(self.interval_minutes * 60)

        except KeyboardInterrupt:
            print("\nStopping orchestrator...")
        except Exception as e:
            print(f"Error in orchestrator: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.server_process:
                self.server_process.terminate()

            # Final database save
            self._save_database()


def verify_chunk_file(chunk_file):
    """Verify that a chunk file is properly formatted"""
    try:
        with open(chunk_file, 'r') as f:
            lines = f.readlines()
            print(f"Chunk file {chunk_file} has {len(lines)} lines (including header)")

            # Check header
            if not lines[0].strip().startswith('Header byte'):
                print(f"WARNING: Chunk file has invalid header: {lines[0]}")

            # Check and count actual data lines
            data_lines = 0
            for i, line in enumerate(lines[1:], 1):
                fields = line.strip().split(';')
                if len(fields) == 6 and fields[0].startswith('0xfe'):
                    data_lines += 1
                    print(f"Valid data line {i}: {fields[1]} (type {fields[1]})")
                else:
                    print(f"WARNING: Line {i} is invalid: {line}")

            print(f"Total valid data lines: {data_lines}")
    except Exception as e:
        print(f"Error verifying chunk file: {e}")


def prepare_chunks(events_file, output_dir, interval_minutes=5):
    """Prepare 5-minute chunk files from the main events file"""
    os.makedirs(output_dir, exist_ok=True)

    # Read the main events file
    df = pd.read_csv(events_file, delimiter=';')

    # Get the timestamp column
    timestamps = df['Timestamp 8bytes'].astype(int)

    # Sort by timestamp to ensure chronological order
    df = df.sort_values('Timestamp 8bytes')
    timestamps = df['Timestamp 8bytes'].astype(int)

    # Define interval in seconds
    interval_seconds = interval_minutes * 60  # 300 seconds

    # Get start time and calculate chunk boundaries
    start_time = timestamps.iloc[0]
    df['chunk'] = (timestamps - start_time) // interval_seconds

    # Save each chunk to a separate file
    for i, group in df.groupby('chunk'):
        chunk_filename = os.path.join(output_dir, f"chunk_{i:04d}.csv")
        group.to_csv(chunk_filename, sep=';', index=False)

        # Calculate actual time span in the chunk
        chunk_start = group['Timestamp 8bytes'].min()
        chunk_end = group['Timestamp 8bytes'].max()
        time_span = chunk_end - chunk_start

        print(f"Created chunk file: {chunk_filename} with {len(group)} events (time span: {time_span} seconds)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='MES Wear Monitoring Orchestrator')
    parser.add_argument('--prepare', action='store_true', help='Prepare chunk files from main events file')
    parser.add_argument('--events', default='58daysevents.csv', help='Main events file')
    parser.add_argument('--chunk-dir', default='chunks', help='Directory for chunk files')
    parser.add_argument('--model', default='quadratic_model.json', help='Path to the model')
    parser.add_argument('--threshold', type=float, default=150.0, help='Force threshold')
    parser.add_argument('--interval', type=int, default=5, help='Interval in minutes')

    args = parser.parse_args()

    if args.prepare:
        print("Preparing chunk files...")
        prepare_chunks(args.events, args.chunk_dir, args.interval)
    else:
        print("Starting MES Orchestrator...")
        orchestrator = MESOrchestrator(
            args.chunk_dir,
            args.model,
            args.threshold,
            args.interval
        )
        orchestrator.run()
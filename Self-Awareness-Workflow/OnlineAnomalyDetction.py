import joblib
import numpy as np
import pandas as pd
import pyreadr
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import warnings
import json
import time
from datetime import datetime
from pathlib import Path
import random
import threading
from queue import Queue
# Add this new import
from OnlineFaultDiagnosis import diagnose_after_anomaly
from OnlinePrognostics import diagnose_and_prognose

warnings.filterwarnings('ignore')


class DataCollector:
    def __init__(self, data: pd.DataFrame, initial_samples: int, samples_per_batch: int = 5):
        self.data = data
        self.initial_index = initial_samples - 20  # Start window_start
        self.current_index = initial_samples  # window_end
        self.samples_per_batch = samples_per_batch
        self.collection_active = True
        self.data_queue = Queue()
        self._collection_thread = None

    def get_initial_window(self) -> pd.DataFrame:
        return self.data.iloc[self.initial_index:self.current_index]

    def start_collection(self, interval: float):
        self._collection_thread = threading.Thread(
            target=self._collect_data_periodic,
            args=(interval,),
            daemon=True
        )
        self._collection_thread.start()

    def _collect_data_periodic(self, interval: float):
        while self.collection_active and self.current_index < len(self.data):
            end_idx = min(self.current_index + self.samples_per_batch, len(self.data))
            new_data = self.data.iloc[self.current_index:end_idx]
            self.data_queue.put(new_data)
            self.current_index = end_idx
            self.initial_index += self.samples_per_batch
            time.sleep(interval)

    def stop_collection(self):
        self.collection_active = False
        if self._collection_thread:
            self._collection_thread.join()

class JSONLogger:
    def __init__(self, base_dir: str = "logs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.data_log = self.base_dir / "data_collection.json"
        self.anomaly_log = self.base_dir / "anomaly_checkpoints.json"

        # Initialize data_log with stream structure
        if not self.data_log.exists():
            with open(self.data_log, 'w') as f:
                json.dump({"data_stream": {"samples": []}}, f)

        # Initialize anomaly log
        if not self.anomaly_log.exists():
            with open(self.anomaly_log, 'w') as f:
                json.dump([], f)

    def log_data_collection(self, timestamp: float, window_start: int, window_end: int, data: pd.DataFrame):
        """Log new data points to the continuous stream"""
        # Create list of samples with indices
        new_samples = []

        # Get the actual range of indices for this window
        actual_indices = range(window_start, window_end)

        # Zip the actual indices with the data rows
        for actual_idx, (_, row) in zip(actual_indices, data.iterrows()):
            sample = {
                "index": actual_idx,  # Use the actual index from the window
                "timestamp": timestamp,
                **row.to_dict()
            }
            new_samples.append(sample)

        # Append new samples to the stream
        with open(self.data_log, 'r+') as f:
            try:
                current_data = json.load(f)
                current_data["data_stream"]["samples"].extend(new_samples)

                # Reset file pointer and write updated data
                f.seek(0)
                f.truncate()
                json.dump(current_data, f, indent=2)
            except json.JSONDecodeError:
                # If file is corrupted, create new structure
                json.dump({"data_stream": {"samples": new_samples}}, f, indent=2)

    def log_anomaly(self, timestamp: float, window_start: int, window_end: int, confidence: float,
                    first_anomaly_index: int = None):
        """Log anomaly detection events"""
        entry = {
            "timestamp": timestamp,
            "window_start": window_start,
            "window_end": window_end,
            "first_anomaly_index": first_anomaly_index,
            "confidence": confidence
        }
        self._append_to_json(self.anomaly_log, entry)

    def _append_to_json(self, file_path: Path, data: dict):
        """Helper method for appending to JSON files"""
        with open(file_path, 'r+') as f:
            try:
                existing = json.load(f)
                existing.append(data)
                f.seek(0)
                f.truncate()
                json.dump(existing, f, indent=2)
            except json.JSONDecodeError:
                json.dump([data], f, indent=2)

    def get_window_data(self, window_start: int, window_end: int) -> list:
        """Utility method to retrieve data for a specific window"""
        with open(self.data_log, 'r') as f:
            try:
                data = json.load(f)
                samples = data["data_stream"]["samples"]
                window_samples = [
                    sample for sample in samples
                    if window_start <= sample["index"] < window_end
                ]
                return window_samples
            except (json.JSONDecodeError, KeyError):
                return []

class OnlineAnomalyDetectorV2:
    def __init__(self, model, scaler, window_size: int = 20, anomaly_threshold: float = 0.5):
        self.model = model
        self.scaler = scaler
        self.window_size = window_size
        self.anomaly_threshold = anomaly_threshold
        self.logger = JSONLogger()
        self.detection_active = True
        self._first_anomaly_index = None

    def get_first_anomaly_index(self):
        return self._first_anomaly_index

    def process_window(self, window_data: pd.DataFrame, window_start: int, window_end: int) -> tuple[bool, float]:
        window_scaled = self.scaler.transform(window_data)
        predictions = self.model.predict(window_scaled)

        #find first anomaly in window
        anomaly_indices = [window_start + i for i, pred in enumerate(predictions) if pred == -1]
        self._first_anomaly_index = min(anomaly_indices) if anomaly_indices else None

        anomaly_count = sum(pred == -1 for pred in predictions)
        anomaly_percentage = anomaly_count / len(predictions)
        is_window_anomalous = anomaly_percentage >= self.anomaly_threshold

        # Log data collection
        self.logger.log_data_collection(
            timestamp=time.time(),
            window_start=window_start,
            window_end=window_end,
            data=window_data
        )

        if is_window_anomalous:
            self.logger.log_anomaly(
                timestamp=time.time(),
                window_start=window_start,
                window_end=window_end,
                first_anomaly_index = self._first_anomaly_index,
                confidence=anomaly_percentage * 100
            )

        return is_window_anomalous, anomaly_percentage


def load_and_prepare_data(fault_free_path: str, faulty_path: str, fault_num: int, sim_run: int):
    fault_free_data = pyreadr.read_r(fault_free_path)
    fault_free_training = list(fault_free_data.values())[0]

    faulty_data = pyreadr.read_r(faulty_path)
    faulty_testing = list(faulty_data.values())[0]

    xmeas_cols = [f'xmeas_{i}' for i in range(1, 42)]
    xmv_cols = [f'xmv_{i}' for i in range(1, 12)]
    process_cols = xmeas_cols + xmv_cols

    X_train = fault_free_training[process_cols].values

    mask = (faulty_testing['faultNumber'] == fault_num) & (faulty_testing['simulationRun'] == sim_run)
    sim_data = faulty_testing[mask][process_cols]

    return X_train, sim_data


def main():
    # Configuration
    FAULT_FREE_PATH = './Datasets/TEP/TEP_FaultFree_Training.RData'
    FAULTY_PATH = './Datasets/TEP/TEP_Faulty_Testing.RData'
    FAULT_NUM = 1
    SIM_RUN = 1
    INITIAL_SAMPLES = random.randint(60, 140)
    SAMPLES_PER_BATCH = 5
    COLLECTION_INTERVAL = 2.0  # seconds

    print(f"\nStarting simulation:")
    print(f"Initial samples: {INITIAL_SAMPLES}")
    print(f"First window: [{INITIAL_SAMPLES - 20}:{INITIAL_SAMPLES}]")
    print("=" * 50)

    # Load and prepare data
    X_train, sim_data = load_and_prepare_data(FAULT_FREE_PATH, FAULTY_PATH, FAULT_NUM, SIM_RUN)

    # Initialize model
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    # Initialize model and scaler
    model_path = Path('saved_models/isolation_forest.pkl')
    scaler_path = Path('saved_models/anomaly_scaler.pkl')
    model_path.parent.mkdir(exist_ok=True)

    if model_path.exists() and scaler_path.exists():
        print("Loading pre-trained Isolation Forest model and scaler...")
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
    else:
        print("Training new Isolation Forest model and scaler...")
        # Initialize and fit scaler
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)

        # Initialize and fit model
        model = IsolationForest(
            n_estimators=100,
            contamination=0.1,
            random_state=42
        )
        model.fit(X_train_scaled)

        # Save both model and scaler
        print("Saving trained model and scaler...")
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)

    # Initialize components
    detector = OnlineAnomalyDetectorV2(model, scaler)
    collector = DataCollector(sim_data, INITIAL_SAMPLES, SAMPLES_PER_BATCH)

    # Process initial window
    initial_window = collector.get_initial_window()
    is_anomaly, confidence = detector.process_window(
        initial_window,
        collector.initial_index,
        collector.current_index
    )

    if is_anomaly:
        print(f"\n=== ANOMALY DETECTED IN INITIAL WINDOW ===")
        print(f"Window: [{collector.initial_index}:{collector.current_index}]")
        print(f"Confidence: {confidence * 100:.2f}%")
        return

    # Start data collection if no anomaly in initial window
    collector.start_collection(COLLECTION_INTERVAL)

    try:
        while detector.detection_active and collector.collection_active:
            if not collector.data_queue.empty():
                new_data = collector.data_queue.get()

                # Get full window (previous + new data)
                window_data = sim_data.iloc[collector.initial_index:collector.current_index]

                # Process window
                is_anomaly, confidence = detector.process_window(
                    window_data,
                    collector.initial_index,
                    collector.current_index
                )

                if is_anomaly:
                    predictions = model.predict(scaler.transform(window_data))
                    anomaly_indices = [collector.initial_index + i for i, pred in enumerate(predictions) if pred == -1]
                    first_anomaly = min(anomaly_indices) if anomaly_indices else collector.initial_index

                    print(f"\n=== ANOMALY DETECTED ===")
                    print(f"Window: [{collector.initial_index}:{collector.current_index}]")
                    print(f"First anomaly index: {first_anomaly}")
                    print(f"Confidence: {confidence * 100:.2f}%")

                    # Trigger fault diagnosis
                    anomaly_data = {
                        'simulation_run': SIM_RUN,
                        'window_end': collector.current_index
                    }
                    diagnose_after_anomaly(anomaly_data)
                    diagnose_and_prognose(anomaly_data)

                    collector.stop_collection()
                    break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
    finally:
        collector.stop_collection()

    print("\nSimulation complete")
    print(f"Final sample index: {collector.current_index}")


if __name__ == "__main__":
    main()
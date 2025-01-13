from PyQt6.QtCore import QObject, QThread, pyqtSignal
from OnlineAnomalyDetction import OnlineAnomalyDetectorV2, DataCollector, load_and_prepare_data
from logger import SystemLogger
import joblib
from pathlib import Path
import time
import random

class MonitoringWorker(QThread):
    """Worker thread for running the anomaly detection monitoring"""
    anomaly_detected = pyqtSignal(int, int)  # Emits (window_end, first_anomaly_index)
    diagnostic_ready = pyqtSignal(str, float)  # Emits fault type and confidence
    error_occurred = pyqtSignal(str)  # Emits error message
    current_index_updated = pyqtSignal(int)  # New signal for current index

    def __init__(self, detector, collector):
        super().__init__()
        self.detector = detector
        self.collector = collector
        self.logger = SystemLogger()
        self.is_running = True

    def handle_anomaly(self, index, confidence):
        """Handle anomaly detection and trigger diagnosis"""
        # Get first anomaly index from detector
        first_anomaly_index = self.detector.get_first_anomaly_index()
        self.anomaly_detected.emit(index, first_anomaly_index)
        self.logger.anomaly_detected(index, confidence * 100)

        # Trigger fault diagnosis
        try:
            anomaly_data = {
                'simulation_run': 1,  # Assuming simulation run 1
                'window_end': index
            }

            # Run diagnosis
            from OnlineFaultDiagnosis import OnlineFaultDiagnoser
            diagnoser = OnlineFaultDiagnoser()
            fault_type, confidence, _ = diagnoser.diagnose_fault(
                anomaly_data['simulation_run'],
                anomaly_data['window_end']
            )

            if fault_type is not None:
                self.logger.diagnostic_result(
                    "Fault 1" if fault_type == 1 else "Normal",
                    confidence * 100
                )
                self.diagnostic_ready.emit(
                    str(fault_type),
                    confidence * 100
                )

        except Exception as e:
            self.logger.error("Fault Diagnosis", str(e))
            self.error_occurred.emit(f"Diagnosis error: {str(e)}")

    def run(self):
        try:
            self.logger.system_start()
            self.collector.start_collection(2.0)  # 2 second interval

            # Process initial window
            initial_window = self.collector.get_initial_window()
            # Emit initial index
            self.current_index_updated.emit(self.collector.current_index)

            is_anomaly, confidence = self.detector.process_window(
                initial_window,
                self.collector.initial_index,
                self.collector.current_index
            )

            if is_anomaly:
                self.handle_anomaly(self.collector.current_index, confidence)
                return

            # Continue monitoring
            while self.is_running and self.collector.collection_active:
                if not self.collector.data_queue.empty():
                    new_data = self.collector.data_queue.get()

                    # Emit current index
                    self.current_index_updated.emit(self.collector.current_index)

                    # Get full window
                    window_data = self.collector.data.iloc[
                                  self.collector.initial_index:self.collector.current_index
                                  ]

                    # Process window
                    is_anomaly, confidence = self.detector.process_window(
                        window_data,
                        self.collector.initial_index,
                        self.collector.current_index
                    )

                    self.logger.monitoring_status(
                        self.collector.initial_index,
                        self.collector.current_index
                    )

                    if is_anomaly:
                        self.handle_anomaly(self.collector.current_index, confidence)
                        break

                time.sleep(0.1)

        except Exception as e:
            self.logger.error("MonitoringWorker", str(e))
            self.error_occurred.emit(str(e))
        finally:
            self.collector.stop_collection()
            self.logger.system_stop()

    def stop(self):
        """Stop the monitoring process"""
        self.is_running = False
        self.collector.stop_collection()

class SystemController(QObject):
    """Main controller for the fault detection system"""

    def __init__(self):
        super().__init__()
        self.logger = SystemLogger()
        self.current_worker = None
        self.initialize_system()

    def initialize_system(self):
        """Initialize the anomaly detection system"""
        try:
            # Load model and scaler
            model_path = Path('../saved_models/isolation_forest.pkl')
            scaler_path = Path('../saved_models/anomaly_scaler.pkl')

            if not (model_path.exists() and scaler_path.exists()):
                # Train new model if needed
                X_train, _ = load_and_prepare_data(
                    '../../Detection/Dataset/TEP/TEP_FaultFree_Training.RData',
                    '../../Detection/Dataset/TEP/TEP_Faulty_Testing.RData',
                    1, 1
                )
                self.train_model(X_train, model_path, scaler_path)

            # Load the model and scaler
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)

            # Initialize detector
            self.detector = OnlineAnomalyDetectorV2(
                self.model,
                self.scaler,
                window_size=20,
                anomaly_threshold=0.5
            )

        except Exception as e:
            self.logger.error("Initialization", str(e))
            raise

    def train_model(self, X_train, model_path, scaler_path):
        """Train and save new model and scaler"""
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

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
        model_path.parent.mkdir(exist_ok=True)
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)

    #start system was hardcoded
    # def start_monitoring(self):
    #     """Start the monitoring process"""
    #     try:
    #         # Load simulation data
    #         _, sim_data = load_and_prepare_data(
    #             '../../Detection/Dataset/TEP/TEP_FaultFree_Training.RData',
    #             '../../Detection/Dataset/TEP/TEP_Faulty_Testing.RData',
    #             1, 1
    #         )
    #
    #         # Initialize collector
    #         collector = DataCollector(
    #             sim_data,
    #             initial_samples=100,  # Configurable initial window
    #             samples_per_batch=5
    #         )
    #
    #         # Create and start worker
    #         self.current_worker = MonitoringWorker(self.detector, collector)
    #         return self.current_worker
    #
    #     except Exception as e:
    #         self.logger.error("Monitoring Start", str(e))
    #         raise
    def start_monitoring(self):
        """Start the monitoring process"""
        try:
            # Load simulation data
            _, sim_data = load_and_prepare_data(
                '../../Detection/Dataset/TEP/TEP_FaultFree_Training.RData',
                '../../Detection/Dataset/TEP/TEP_Faulty_Testing.RData',
                1, 1
            )

            # Generate random initial samples
            initial_samples = random.randint(90, 140)

            # Convert all numeric columns to float type
            numeric_columns = sim_data.select_dtypes(include=['int64', 'float64']).columns
            for col in numeric_columns:
                sim_data[col] = sim_data[col].astype(float)

            # Initialize collector with random initial samples
            collector = DataCollector(
                sim_data,
                initial_samples=initial_samples,  # Use random value
                samples_per_batch=5
            )

            # Create and start worker
            self.current_worker = MonitoringWorker(self.detector, collector)
            return self.current_worker

        except Exception as e:
            self.logger.error("Monitoring Start", str(e))
            raise

    def stop_monitoring(self):
        """Stop the monitoring process"""
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()
        self.current_worker = None

    def run_prognosis(self):
        """Run the prognostics analysis"""
        try:
            # Get the last anomaly data from logs
            with open('logs/anomaly_checkpoints.json', 'r') as f:
                import json
                anomaly_logs = json.load(f)

            if not anomaly_logs:
                return None

            # Use the most recent anomaly
            last_anomaly = anomaly_logs[-1]
            anomaly_data = {
                'simulation_run': 1,  # Assuming simulation run 1
                'window_end': last_anomaly['window_end']
            }

            # Run prognosis
            from OnlinePrognostics import OnlinePrognostics
            prognostics = OnlinePrognostics()
            result = prognostics.estimate_rul(
                current_index=anomaly_data['window_end'],
                simulation_run=anomaly_data['simulation_run']
            )

            self.logger.prognosis_result(
                result['estimated_rul'],
                result.get('timestamp')
            )

            return result

        except Exception as e:
            self.logger.error("Prognosis", str(e))
            raise
#commented version shows rul only once
# import numpy as np
# import torch
# import time
# from pathlib import Path
# import json
# from FD001 import Model, loadData, norm_  # Import the CMAPSS model and utilities
#
#
# class OnlinePrognostics:
#     def __init__(self, cmapss_model_path='../best_model_FD001.pth', logs_dir='logs'):
#         """
#         Initialize the online prognostics system
#         Args:
#             cmapss_model_path: Path to trained CMAPSS model
#             logs_dir: Directory for logging results
#         """
#         try:
#             self.device = "cuda" if torch.cuda.is_available() else "cpu"
#             self.total_trajectory_length = 960  # Total length of TEP trajectory
#
#             # Initialize CMAPSS model
#             self.cmapss_model = Model().to(self.device)
#             self.cmapss_model.load_state_dict(torch.load(cmapss_model_path))
#             self.cmapss_model.eval()
#
#             # Load CMAPSS test data
#             _, _, _, _, self.x_test, self.y_test = loadData("1")
#
#             # Find longest trajectory in CMAPSS dataset
#             self.longest_traj_idx = self._find_longest_trajectory()
#             self.longest_traj = self.x_test[self.longest_traj_idx]
#             self.longest_traj_length = self.longest_traj.size(1)
#
#             # Setup logging
#             self.logs_dir = Path(logs_dir)
#             self.logs_dir.mkdir(exist_ok=True)
#             self.prognostics_log = self.logs_dir / "prognostics_results.json"
#             if not self.prognostics_log.exists():
#                 with open(self.prognostics_log, 'w') as f:
#                     json.dump([], f)
#
#             print("\nOnline Prognostics System Initialized")
#             print(f"Model loaded from: {cmapss_model_path}")
#             print(f"Running on device: {self.device}")
#             print(f"Reference trajectory length: {self.longest_traj_length}")
#
#         except Exception as e:
#             print(f"Error initializing OnlinePrognostics: {str(e)}")
#             raise
#
#     def _find_longest_trajectory(self):
#         """Find index of longest trajectory in CMAPSS dataset"""
#         max_length = 0
#         longest_idx = 0
#
#         for idx, trajectory in enumerate(self.x_test):
#             length = trajectory.size(1)
#             if length > max_length:
#                 max_length = length
#                 longest_idx = idx
#
#         return longest_idx
#
#     def _save_prognostics_result(self, data):
#         """Save prognostics results to JSON file"""
#         try:
#             with open(self.prognostics_log, 'r+') as f:
#                 try:
#                     results = json.load(f)
#                     results.append(data)
#                     f.seek(0)
#                     json.dump(results, f, indent=2)
#                 except json.JSONDecodeError:
#                     json.dump([data], f, indent=2)
#         except Exception as e:
#             print(f"Error saving prognostics result: {str(e)}")
#
#     def estimate_rul(self, current_index, simulation_run):
#         """
#         Estimate RUL based on current position in trajectory
#         Args:
#             current_index: Current sample index in TEP trajectory
#             simulation_run: Current simulation run number
#         Returns:
#             dict containing RUL estimation and calculation details
#         """
#         try:
#             # Calculate remaining portion of trajectory
#             remaining_samples = self.total_trajectory_length - current_index
#             percentage_remaining = (remaining_samples / self.total_trajectory_length) * 100
#
#             # Calculate corresponding position in CMAPSS trajectory
#             cmapss_remaining_samples = int((percentage_remaining / 100) * self.longest_traj_length)
#             cmapss_position = self.longest_traj_length - cmapss_remaining_samples
#
#             # Ensure we don't exceed trajectory bounds
#             cmapss_position = min(max(0, cmapss_position), self.longest_traj_length - 1)
#
#             # Get RUL prediction
#             with torch.no_grad():
#                 prediction = self.cmapss_model(self.longest_traj)
#                 estimated_rul = prediction[0, cmapss_position, 0]
#
#             # Convert normalized RUL back to original scale
#             estimated_rul_original = norm_.y_scaler.inverse_transform([[estimated_rul.cpu().numpy()]])[0][0]
#
#             # Prepare results
#             result = {
#                 'timestamp': time.time(),
#                 'simulation_run': simulation_run,
#                 'current_index': int(current_index),
#                 'total_length': self.total_trajectory_length,
#                 'remaining_samples': int(remaining_samples),
#                 'percentage_remaining': float(percentage_remaining),
#                 'cmapss_reference': {
#                     'trajectory_index': int(self.longest_traj_idx),
#                     'total_length': int(self.longest_traj_length),
#                     'position_used': int(cmapss_position),
#                     'remaining_samples': int(cmapss_remaining_samples)
#                 },
#                 'estimated_rul': float(estimated_rul_original)
#             }
#
#             # Save results
#             self._save_prognostics_result(result)
#
#             return result
#
#         except Exception as e:
#             print(f"Error in RUL estimation: {str(e)}")
#             raise
#
#
# def diagnose_and_prognose(anomaly_data):
#     """
#     Perform fault diagnosis and prognosis after anomaly detection
#     Args:
#         anomaly_data: dict containing:
#             - simulation_run: simulation run number
#             - window_end: last sample index in anomaly window
#     """
#     try:
#         # Initialize prognostics
#         prognostics = OnlinePrognostics()
#
#         # Estimate RUL
#         result = prognostics.estimate_rul(
#             current_index=anomaly_data['window_end'],
#             simulation_run=anomaly_data['simulation_run']
#         )
#
#         # Print results
#         print("\n=== Prognostics Results ===")
#         print(f"Current Position: {result['current_index']} / {result['total_length']}")
#         print(f"Remaining Samples: {result['remaining_samples']}")
#         print(f"Percentage Remaining: {result['percentage_remaining']:.2f}%")
#         print(f"\nCMAPSS Reference:")
#         print(f"Used trajectory {result['cmapss_reference']['trajectory_index']}")
#         print(f"Position: {result['cmapss_reference']['position_used']} / "
#               f"{result['cmapss_reference']['total_length']}")
#         print(f"\nEstimated RUL: {result['estimated_rul']:.2f}")
#
#     except Exception as e:
#         print(f"Error in diagnosis and prognosis: {str(e)}")


import numpy as np
import torch
import time
from pathlib import Path
import json
from datetime import datetime
from FD001 import Model, loadData, norm_  # Import the CMAPSS model and utilities


class OnlinePrognostics:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(OnlinePrognostics, cls).__new__(cls)
        return cls._instance

    def __init__(self, cmapss_model_path='../best_model_FD001.pth', logs_dir='logs'):
        """
        Initialize the online prognostics system
        Args:
            cmapss_model_path: Path to trained CMAPSS model
            logs_dir: Directory for logging results
        """
        # Only initialize once
        if hasattr(self, 'initialized'):
            return

        try:
            self.initialized = True
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.total_trajectory_length = 960  # Total length of TEP trajectory

            # Initialize CMAPSS model
            self.cmapss_model = Model().to(self.device)
            self.cmapss_model.load_state_dict(torch.load(cmapss_model_path))
            self.cmapss_model.eval()

            # Load CMAPSS test data
            _, _, _, _, self.x_test, self.y_test = loadData("1")

            # Find longest trajectory in CMAPSS dataset
            self.longest_traj_idx = self._find_longest_trajectory()
            self.longest_traj = self.x_test[self.longest_traj_idx]
            self.longest_traj_length = self.longest_traj.size(1)

            # Setup logging paths
            self.logs_dir = Path(logs_dir)
            self.logs_dir.mkdir(exist_ok=True)
            self.prognostics_log = self.logs_dir / "prognostics_results.json"
            self.anomaly_log = self.logs_dir / "anomaly_checkpoints.json"

            # Initialize log files if they don't exist
            if not self.prognostics_log.exists():
                with open(self.prognostics_log, 'w') as f:
                    json.dump([], f)
            if not self.anomaly_log.exists():
                with open(self.anomaly_log, 'w') as f:
                    json.dump([], f)

            # Track first run
            self.initial_rul = None
            self.first_anomaly_time = None

            print("\nOnline Prognostics System Initialized")
            print(f"Model loaded from: {cmapss_model_path}")
            print(f"Running on device: {self.device}")
            print(f"Reference trajectory length: {self.longest_traj_length}")

        except Exception as e:
            print(f"Error initializing OnlinePrognostics: {str(e)}")
            raise

    def _find_longest_trajectory(self):
        """Find index of longest trajectory in CMAPSS dataset"""
        max_length = 0
        longest_idx = 0

        for idx, trajectory in enumerate(self.x_test):
            length = trajectory.size(1)
            if length > max_length:
                max_length = length
                longest_idx = idx

        return longest_idx

    def _get_first_anomaly_timestamp(self):
        """Get the timestamp of the first anomaly detection"""
        try:
            with open(self.anomaly_log, 'r') as f:
                anomalies = json.load(f)
                if anomalies:
                    return anomalies[0].get('timestamp')
        except Exception as e:
            print(f"Error reading anomaly log: {str(e)}")
        return None

    def _get_initial_rul_estimate(self):
        """Get the first RUL estimate if it exists"""
        try:
            with open(self.prognostics_log, 'r') as f:
                prognoses = json.load(f)
                if prognoses:
                    return prognoses[0].get('estimated_rul')
        except Exception as e:
            print(f"Error reading prognostics log: {str(e)}")
        return None

    def _save_prognostics_result(self, data):
        """Save prognostics results to JSON file"""
        try:
            with open(self.prognostics_log, 'r+') as f:
                try:
                    results = json.load(f)
                    results.append(data)
                    f.seek(0)
                    f.truncate()
                    json.dump(results, f, indent=2)
                except json.JSONDecodeError:
                    json.dump([data], f, indent=2)
        except Exception as e:
            print(f"Error saving prognostics result: {str(e)}")

    def estimate_rul(self, current_index, simulation_run):
        """
        Estimate RUL based on current position and time since first anomaly
        Args:
            current_index: Current sample index in TEP trajectory
            simulation_run: Current simulation run number
        Returns:
            dict containing RUL estimation and calculation details
        """
        try:
            # Calculate trajectory metrics (needed for both first and subsequent runs)
            remaining_samples = self.total_trajectory_length - current_index
            percentage_remaining = (remaining_samples / self.total_trajectory_length) * 100
            cmapss_remaining_samples = int((percentage_remaining / 100) * self.longest_traj_length)
            cmapss_position = self.longest_traj_length - cmapss_remaining_samples
            cmapss_position = min(max(0, cmapss_position), self.longest_traj_length - 1)

            current_time = time.time()

            # Check if this is a first run
            if self.initial_rul is None:
                # First run: Calculate initial RUL using the model
                with torch.no_grad():
                    prediction = self.cmapss_model(self.longest_traj)
                    estimated_rul = prediction[0, cmapss_position, 0]

                # Convert normalized RUL back to original scale
                self.initial_rul = float(norm_.y_scaler.inverse_transform([[estimated_rul.cpu().numpy()]])[0][0])
                self.first_anomaly_time = self._get_first_anomaly_timestamp() or current_time
                adjusted_rul = self.initial_rul
                time_elapsed = 0
            else:
                # Subsequent runs: Use initial RUL and adjust based on time
                time_elapsed = (current_time - self.first_anomaly_time) / 3600  # Convert to hours
                adjusted_rul = max(0, self.initial_rul - time_elapsed)

            # Prepare results
            result = {
                'timestamp': current_time,
                'simulation_run': simulation_run,
                'current_index': int(current_index),
                'total_length': self.total_trajectory_length,
                'remaining_samples': int(remaining_samples),
                'percentage_remaining': float(percentage_remaining),
                'cmapss_reference': {
                    'trajectory_index': int(self.longest_traj_idx),
                    'total_length': int(self.longest_traj_length),
                    'position_used': int(cmapss_position),
                    'remaining_samples': int(cmapss_remaining_samples)
                },
                'estimated_rul': float(adjusted_rul),
                'base_rul': float(self.initial_rul),
                'time_since_anomaly': float(time_elapsed)
            }

            # Save results
            self._save_prognostics_result(result)

            return result

        except Exception as e:
            print(f"Error in RUL estimation: {str(e)}")
            raise


def diagnose_and_prognose(anomaly_data):
    """
    Perform fault diagnosis and prognosis after anomaly detection
    Args:
        anomaly_data: dict containing:
            - simulation_run: simulation run number
            - window_end: last sample index in anomaly window
    """
    try:
        # Initialize prognostics
        prognostics = OnlinePrognostics()

        # Estimate RUL
        result = prognostics.estimate_rul(
            current_index=anomaly_data['window_end'],
            simulation_run=anomaly_data['simulation_run']
        )

        # Print results
        print("\n=== Prognostics Results ===")
        print(f"Current Position: {result['current_index']} / {result['total_length']}")
        print(f"Remaining Samples: {result['remaining_samples']}")
        print(f"Percentage Remaining: {result['percentage_remaining']:.2f}%")
        print(f"\nCMAPSS Reference:")
        print(f"Used trajectory {result['cmapss_reference']['trajectory_index']}")
        print(f"Position: {result['cmapss_reference']['position_used']} / "
              f"{result['cmapss_reference']['total_length']}")

        if result['time_since_anomaly'] > 0:
            print(f"\nInitial RUL Estimate: {result['base_rul']:.2f}")
            print(f"Time Since First Anomaly: {result['time_since_anomaly']:.2f} hours")
            print(f"Current RUL Estimate: {result['estimated_rul']:.2f}")
        else:
            print(f"\nInitial RUL Estimate: {result['estimated_rul']:.2f}")

    except Exception as e:
        print(f"Error in diagnosis and prognosis: {str(e)}")
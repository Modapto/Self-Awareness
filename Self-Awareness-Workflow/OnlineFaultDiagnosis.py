import torch
import numpy as np
from pathlib import Path
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from BinaryFaultDiagnosis import FaultDiagnosisModel, import_data
import json
import time
from datetime import datetime
import joblib

class OnlineFaultDiagnoser:
    def __init__(self, model_dir='../saved_models',
                 device="cuda" if torch.cuda.is_available() else "cpu"):
        self.device = device
        self.diagnosis_window = 60
        self.model = None
        self.initialize_model(model_dir)
        self.initialize_test_data()
        self.checkpoint_file = Path("logs/faults_diagnosed.json")
        self.checkpoint_file.parent.mkdir(exist_ok=True)
        if not self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'w') as f:
                json.dump([], f)

    def initialize_model(self, model_dir):
        try:
            model = FaultDiagnosisModel().to(self.device)
            checkpoint_path = Path(model_dir) / 'fault_1_model.pt'
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            model.load_state_dict(checkpoint['model_state_dict'])
            model.eval()
            self.model = model
        except Exception as e:
            print(f"Error loading model: {str(e)}")

    def initialize_test_data(self):
        _, full_test_data = import_data(1)
        self.test_data = full_test_data.copy()
        self.feature_cols = [col for col in self.test_data.columns
                             if col not in ['faultNumber', 'simulationRun', 'sample']]
        try:
            scaler_path = Path('saved_models') / 'scaler.pkl'
            self.scaler = joblib.load(scaler_path)
        except Exception as e:
            print("Creating new scaler as fallback")
            self.scaler = MinMaxScaler()
            self.scaler.fit(self.test_data[self.feature_cols])

    def save_diagnosis_checkpoint(self, sim_run, window_start, window_end,
                                  fault_type, confidence, sample_predictions):
        checkpoint = {
            "timestamp": datetime.now().isoformat(),
            "simulation_run": sim_run,
            "window_interval": {
                "start": int(window_start),
                "end": int(window_end)
            },
            "diagnosis": {
                "fault_type": str(fault_type),
                "confidence": float(confidence)
            },
            "sample_predictions": {
                str(k): {
                    "prediction": int(v["prediction"]),
                    "probability": float(v["probability"])
                }
                for k, v in sample_predictions.items()
            }
        }

        with open(self.checkpoint_file, 'r+') as f:
            try:
                checkpoints = json.load(f)
                checkpoints.append(checkpoint)
                f.seek(0)
                json.dump(checkpoints, f, indent=2)
            except json.JSONDecodeError:
                json.dump([checkpoint], f, indent=2)

    def extract_trajectory(self, sim_run, anomaly_window_end):
        window_end = anomaly_window_end
        window_start = max(0, window_end - self.diagnosis_window)

        sim_mask = (self.test_data['simulationRun'] == sim_run) & \
                   (self.test_data['sample'] >= window_start) & \
                   (self.test_data['sample'] <= window_end)

        trajectory = self.test_data[sim_mask].copy()
        if len(trajectory) < self.diagnosis_window:
            print(f"Warning: Got {len(trajectory)} samples, need {self.diagnosis_window}")
            return None, None

        return trajectory[self.feature_cols], trajectory['sample'].values

    def prepare_data(self, trajectory):
        if trajectory is None:
            return None
        scaled_data = self.scaler.transform(trajectory)
        return torch.FloatTensor(scaled_data).to(self.device)

    def diagnose_fault(self, sim_run, anomaly_window_end):
        try:
            trajectory, sample_indices = self.extract_trajectory(sim_run, anomaly_window_end)
            if trajectory is None:
                return None, 0.0, {}

            data = self.prepare_data(trajectory)
            if data is None:
                return None, 0.0, {}

            sample_predictions = {}
            with torch.no_grad():
                for i, sample_idx in enumerate(sample_indices):
                    prob = torch.sigmoid(self.model(data[i:i + 1])).item()
                    is_fault = prob > 0.4
                    sample_predictions[int(sample_idx)] = {
                        'prediction': 1 if is_fault else 0,
                        'probability': prob
                    }

            # Count number of fault predictions
            fault_count = sum(1 for pred in sample_predictions.values() if pred['prediction'] == 1)

            # If we have more than one fault prediction, classify as fault
            is_fault = fault_count > 1

            # Calculate confidence based on the strongest fault signals
            if is_fault:
                # Get the top 5 highest probabilities for fault samples
                fault_probs = sorted([pred['probability'] for pred in sample_predictions.values()
                                      if pred['prediction'] == 1], reverse=True)
                confidence = sum(fault_probs[:5]) / 5 if fault_probs else 0
            else:
                # For normal cases, confidence is proportion of normal predictions
                confidence = (len(sample_predictions) - fault_count) / len(sample_predictions)

            fault_type = 1 if is_fault else "Normal"

            # Save checkpoint
            self.save_diagnosis_checkpoint(
                sim_run,
                sample_indices[0],
                sample_indices[-1],
                fault_type,
                confidence,
                sample_predictions
            )

            return fault_type, confidence, sample_predictions

        except Exception as e:
            print(f"Error in diagnosis: {str(e)}")
            return None, 0.0, {}


def diagnose_after_anomaly(anomaly_data):
    """
    Entry point for fault diagnosis after anomaly detection

    Args:
        anomaly_data: dict containing:
            - simulation_run: int
            - window_end: int (last sample in anomaly window)
    """
    diagnoser = OnlineFaultDiagnoser()

    fault_type, confidence, predictions = diagnoser.diagnose_fault(
        anomaly_data['simulation_run'],
        anomaly_data['window_end']
    )

    if fault_type is not None:
        print(f"\n=== FAULT DIAGNOSIS RESULTS ===")
        print(f"Diagnosis: {'Fault 1' if fault_type == 1 else 'Normal'}")
        print(f"Confidence: {confidence:.2%}")
        print("\nSample predictions:")
        for sample, result in predictions.items():
            print(f"Sample {sample}: {'Fault' if result['prediction'] == 1 else 'Normal'} "
                  f"(Probability: {result['probability']:.3f})")
    else:
        print("Diagnosis failed")
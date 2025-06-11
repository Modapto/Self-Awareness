# Self-Awareness Service

## Overview

This is a comprehensive desktop application that implements three key components for system health monitoring:

- Anomaly Detection
- Fault Diagnostics
- Prognostics (Remaining Useful Life Prediction)

The application provides real-time monitoring and analysis capabilities through a user interface, allowing users to detect anomalies, diagnose faults, and predict remaining useful life.

## Table of Contents
1. [Features](#features)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Components](#components)
6. [Dataset](#dataset)
7. [API](#api)
8. [Events](#events)
9. [Contributing](#contributing)
10. [License](#license)

## Features

- **Real-time Anomaly Detection**: Continuous monitoring system with real-time anomaly detection capabilities
- **Diagnostic Analysis**: Fault diagnosis system with confidence scoring (Prediction Accuracy)
- **Prognostic Predictions**: Remaining Useful Life (RUL) prediction
- **Logging System**: Comprehensive event and system logging for debugging

## Project Structure

```sh
simulator/Self-Awareness-Workflow/
├── Datasets/                  # Dataset storage
├── events/                   # Event logging
├── saved_models/            # Trained model storage
├── ui/                      # User interface components
│   ├── logs/
│   ├── __init__.py
│   ├── app.py              # Main application
│   ├── logger.py           # Logging utilities
│   ├── main_window.py      # Main UI window
│   └── system_controller.py # System control logic
├── __init__.py
├── best_model_FD001.pth    # Pre-trained model for Prognostics
├── BinaryFaultDiagnosis.py # Fault diagnosis implementation
├── FD001.py               
├── OnlineAnomalyDetction.py
├── OnlineFaultDiagnosis.py
└── OnlinePrognostics.py
```

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Modapto/Self-Awareness-Workflow.git
cd Self-Awareness-Workflow
```

2. Install required dependencies:

```bash
pip install -r requirements.txt
```

3. Download and prepare the datasets:

   a. The CMAPSS dataset already exists in the `Datasets` directory.
   b. Download the TEP dataset from Kaggle:
      - Visit: https://www.kaggle.com/datasets/averkij/tennessee-eastman-process-simulation-dataset
      - Download all `*.rData` 4 files and place them in `Self-Awareness-Workflow/Datasets/TEP` directory

## Usage

1. Start the application:

```bash
python ui/app.py
```

2. Launch the monitoring system:
   - Click the "Start System" button in the top right corner
   - The system will automatically begin monitoring for anomalies

3. System Workflow:
   - **Anomaly Detection**: The system continuously monitors for anomalies. When detected, the anomaly index is displayed in the Anomaly Detection card
   - **Fault Diagnosis**: Automatically triggered when an anomaly is detected. Provides diagnostic results with a confidence score
   - **Prognostic Analysis**: Can be manually initiated using the "Run Prognosis" button
     - Displays the Remaining Useful Life (RUL) prediction
     - Shows timestamp of the last prognostic analysis

## Component Specifications

The following section details the specific Python classes, input structures, and output formats for each component.

### Anomaly Detection

**Python Class**: `OnlineAnomalyDetectorV2` in `OnlineAnomalyDetction.py`

**Called**: Manually triggered during system operation after clicking "Start System" button

**Initialization**:

```python
detector = OnlineAnomalyDetectorV2(
    model,           # Trained Isolation Forest model
    scaler,          # StandardScaler for data normalization
    window_size=20,  # Size of the analysis window (int)
    anomaly_threshold=0.5  # Threshold for anomaly detection (float)
)
```

**Main Function**: `process_window()`

**Input**:

```python
# Input parameters
window_data: pd.DataFrame  # DataFrame containing sensor readings for the current window
window_start: int          # Starting index of the window
window_end: int            # Ending index of the window
```

**Output**:

```python
# Return values as tuple(bool, float)
(
    is_window_anomalous,  # Boolean indicating if anomaly was detected
    anomaly_percentage     # Float (0-1) representing confidence of anomaly
)

# Additional output via get_first_anomaly_index()
first_anomaly_index  # Integer representing the index of the first anomaly point
```

**Integration Example**:

```python
# Example of how to integrate anomaly detection
from OnlineAnomalyDetction import OnlineAnomalyDetectorV2

# Initialize detector
detector = OnlineAnomalyDetectorV2(model, scaler)

# Process a window of data
is_anomaly, confidence = detector.process_window(
    window_data,
    window_start,
    window_end
)

# Get the index of first anomalous point if anomaly detected
if is_anomaly:
    first_anomaly_index = detector.get_first_anomaly_index()
    print(f"Anomaly detected at index {first_anomaly_index} with {confidence*100:.2f}% confidence")
```

### Fault Diagnosis

**Python Class**: `OnlineFaultDiagnoser` in `OnlineFaultDiagnosis.py`

**Called**: Automatically triggered when an anomaly is detected

**Entry Point Function**: `diagnose_after_anomaly(anomaly_data)`

**Input**:

```python
# Input dictionary structure
anomaly_data = {
    'simulation_run': int,  # ID of the simulation run
    'window_end': int       # Last sample in anomaly window
}
```

**Output**:

```python
# Return values from diagnoser.diagnose_fault()
(
    fault_type,     # Integer (1) or string ("Normal") indicating the type of fault
    confidence,     # Float (0-1) representing confidence in the diagnosis
    predictions     # Dictionary mapping sample indices to prediction details
)

# predictions format
{
    sample_index: {       # Integer index of the sample
        'prediction': int,  # 1 for fault, 0 for normal
        'probability': float  # Probability of the prediction (0-1)
    }
}
```

**Integration Example**:

```python
# Example of how to integrate fault diagnosis
from OnlineFaultDiagnosis import diagnose_after_anomaly

# After anomaly detection
anomaly_data = {
    'simulation_run': 1,
    'window_end': 150  # Last sample index in anomaly window
}

# Call the diagnosis function
diagnose_after_anomaly(anomaly_data)  # Results are logged and printed
```

### Prognostics

**Python Class**: `OnlinePrognostics` in `OnlinePrognostics.py`

**Called**:

- Manually triggered when user clicks "Run Prognosis" button in the UI

**Entry Point Function**: `diagnose_and_prognose(anomaly_data)`

**Input**:

```python
# Input dictionary structure
anomaly_data = {
    'simulation_run': int,  # ID of the simulation run
    'window_end': int       # Last sample in anomaly window
}
```

**Output**:

```python
# Return dictionary from estimate_rul()
{
    'timestamp': float,        # Unix timestamp of the analysis
    'simulation_run': int,     # Simulation run ID
    'current_index': int,      # Current sample index
    'total_length': int,       # Total simulation length
    'remaining_samples': int,  # Number of samples remaining
    'percentage_remaining': float,  # Percentage of run remaining
    'cmapss_reference': {      # Reference to CMAPSS model mapping
        'trajectory_index': int,    # Index of reference trajectory
        'total_length': int,        # Total length of reference
        'position_used': int,       # Position in reference trajectory
        'remaining_samples': int    # Samples remaining in reference
    },
    'estimated_rul': float,    # Estimated Remaining Useful Life in hours
    'base_rul': float,         # Initial RUL estimate
    'time_since_anomaly': float  # Hours since first anomaly
}
```

**Integration Example**:

```python
# Example of how to integrate prognostics
from OnlinePrognostics import diagnose_and_prognose

# After anomaly detection and diagnosis
anomaly_data = {
    'simulation_run': 1,
    'window_end': 150  # Last sample index in anomaly window
}

# Call the prognostics function
diagnose_and_prognose(anomaly_data)  # Results are logged and printed
```

## Datasets

This project uses two datasets:

### 1. CMAPSS Jet Engine Dataset

The NASA Commercial Modular Aero-Propulsion System Simulation (CMAPSS) dataset can be downloaded from:
https://data.nasa.gov/Aerospace/CMAPSS-Jet-Engine-Simulated-Data/ff5v-kuh6/about_data

### 2. Tennessee Eastman Process (TEP) Dataset

The TEP dataset simulates a chemical process and provides a benchmark platform for process monitoring and control. The dataset can be found at:
- Kaggle: https://www.kaggle.com/datasets/averkij/tennessee-eastman-process-simulation-dataset
- Harvard Dataverse: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/6C3JR1

## API

The deployed web service requires on input as defined below the ***SWAGGER_SERVER_URL***, which points to the URL of the deployed service for the Swagger Documentation.

The service exposes two endpoints under the **8001** port:

- **/anomally-detection (POST):** Receives the dataframe in Base64 encoding about the Sensor Readings to analyze them and a specified timewindow (start and end) and invokes asynchrounously the detection process via the ***process_window()*** function. The API received the request if all input data are validated, it returns a success message about the submission of the request.

- **/prognostics (POST):** Receives the simulation run index and the window end to start the prognosis about the RUL in the specified simulation. It handles asynchrounously the request and returns a success message when the process is successfully invoked and the data are validated.

- **/health (GET):** Implements a health check for the Web Service for monitoring purposes.

## Events

For Detection and Diagnosis tools some events must be generated to inform operators about the faults. To create a new event you can simple do the following:

   ```sh
   # Set the Topics
   self-awareness-diagnosis-topic = 'self-awareness-diagnosis'
   self-awareness-detection-topic = 'self-awareness-detection'
   self-awareness-prognostics-topic = 'self-awareness-prognostics'

   # Initialize the producer
   producer = EventsProducer('kafka.modapto.atc.gr:9092') # Or equivalent, must be provided as environmental variable

   # Example event data - Must be configured for each case
   event_data = {
      "description": "System performance anomaly detected", # Description of failt
      "module": "[This will be based according to DT connected info]",
      "timestamp": "2024-01-24T15:30:45",  # ISO 8601 format - Can be omitted, as it is generated automatically
      "priority": "High", # Low, Mid, High
      "eventType": "System Anomaly", # Can be whatever you want
      "sourceComponent": "Diagnosis", # Or Detection or Prognostics
      "smartService": "Self-Awareness",
      "topic": "self-awareness-diagnosis", # Or self-awareness-detection
      "results": {Object}  # Optional (null if not available) - Can have some results to show to Operators
   }

   # Produce event to a topic
   producer.produce_event('[topic based on detection or diagnosis]', event_data)
   print(f"Event regarding [tool] published successfully!") # Optional

   # Close connection at the end of the process of Self-Awareness - NOTE: Only for components that don't run constantly
   producer.close()
   ```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Dataset Citations

### CMAPSS Dataset

A. Saxena, K. Goebel, D. Simon, and N. Eklund, 'Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation', in the Proceedings of the 1st International Conference on Prognostics and Health Management (PHM08), Denver CO, Oct 2008.

### TEP Dataset

Downs, J.J., Vogel, E.F. A plant-wide industrial process control problem. Computers & Chemical Engineering 17, 245-255 (1993). https://doi.org/10.1016/0098-1354(93)80018-I

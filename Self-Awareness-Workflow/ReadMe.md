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
7. [Events](#events)
8. [Contributing](#contributing)
9. [License](#license)

## Features

- **Real-time Anomaly Detection**: Continuous monitoring system with real-time anomaly detection capabilities
- **Diagnostic Analysis**: Fault diagnosis system with confidence scoring (Prediction Accuracy)
- **Prognostic Predictions**: Remaining Useful Life (RUL) prediction
- **Logging System**: Comprehensive event and system logging for debugging

## Project Structure

```
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

## Components

### 1. Anomaly Detection
- Real-time monitoring of sensors data
- Automatic anomaly detection with index identification
- Continuous status monitoring
- Serves as the trigger for diagnostic analysis

### 2. Diagnostic Results
- Automatically triggered upon anomaly detection
- Provides fault diagnosis with confidence scoring

### 3. Prognostic Analysis
- On-demand Remaining Useful Life (RUL) prediction
- Manual activation through "Run Prognosis" button
- Timestamp tracking of analysis runs
- Clear display of remaining useful life in hours

## Datasets

This project uses two datasets:

### 1. CMAPSS Jet Engine Dataset
The NASA Commercial Modular Aero-Propulsion System Simulation (CMAPSS) dataset can be downloaded from:
https://data.nasa.gov/Aerospace/CMAPSS-Jet-Engine-Simulated-Data/ff5v-kuh6/about_data

### 2. Tennessee Eastman Process (TEP) Dataset
The TEP dataset simulates a chemical process and provides a benchmark platform for process monitoring and control. The dataset can be found at:
- Kaggle: https://www.kaggle.com/datasets/averkij/tennessee-eastman-process-simulation-dataset
- Harvard Dataverse: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/6C3JR1

## Events

For Detection and Diagnosis tools some events must be generated to inform operators about the faults. To create a new event you can simple do the following:

   ```sh
   # Set the Topics
   self-awareness-diagnosis-topic = 'self-awareness-diagnosis'
   self-awareness-detection-topic = 'self-awareness-detection'

   # Initialize the producer
   producer = EventsProducer('kafka.modapto.atc.gr:9092') # Or equivalent, must be provided as environmental variable

   # Example event data - Must be configured for each case
   event_data = {
      "description": "System performance anomaly detected", # Description of failt
      "productionModule": "[This will be based according to DT connected info]",
      "timestamp": "2024-01-24T15:30:45",  # ISO 8601 format - Can be omitted, as it is generated automatically
      "priority": "High", # Low, Mid, High
      "eventType": "System Anomaly", # Can be whatever you want
      "sourceComponent": "Diagnosis", # Or Detection
      "smartService": "Self-Awareness",
      "topic": "self-awareness-diagnosis", # Or self-awareness-detection
      "results": { }  # Optional (null if not available) - Can have some results to show to Operators
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
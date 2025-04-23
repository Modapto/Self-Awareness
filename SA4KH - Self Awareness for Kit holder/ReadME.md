# MODAPTO Wear Monitoring System

This system monitors tool wear using a Manufacturing Execution System (MES) architecture. It tracks insertion/extraction events, predicts tool wear using a quadratic model, and generates notifications when wear thresholds are exceeded.

## Table of Contents
- [Overview](#overview)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Compilation](#compilation)
- [Quick Start](#quick-start)
- [Detailed Workflow](#detailed-workflow)
- [File Formats](#file-formats)
- [Usage Examples](#usage-examples)

## Overview

The system consists of:
1. **MES Server/Client**: C programs for managing and retrieving events
2. **Wear Monitor**: Python script for analyzing events and predicting wear
3. **Wear Orchestrator**: Python script for managing the complete workflow
4. **Event Generator**: Tool for creating test data

## Components

### C Programs
- `MesServer.c`: UDP server that manages event data and notifications
- `MesClient.c`: UDP client for retrieving events from the server

### Python Scripts
- `wear_monitor.py`: Analyzes events, predicts wear using the quadratic model
- `wear_orchestrator.py`: Manages the complete workflow, processes events into manageable chunks (given a time interval)
- `evaluation_wear_monitor.py`: Quick evaluation script for testing the workflow
- `auto_saw_event_gen.py`: Generates event data for testing

### Data Files
- `quadratic_model.json`: Contains the wear prediction model parameters
- `0notif.csv`: Empty notifications file template
- `58daysevents.csv`: Sample event data over 58 days
- `db.json`: Output database with wear analysis results

## Prerequisites

### Required Software
- **C Compiler**: MinGW or GCC
- **Python 3.8+**
- **Python Libraries**:
  ```bash
  pip install pandas numpy
  ```

### Windows Environment
The C programs are designed for Windows (uses Winsock2).

## System Architecture

The wear monitoring system follows a client-server architecture with these components:

```
[Event Data Files] → [MES Server] ↔ [MES Client] → [Wear Analysis] → [Results Database]
       ↑                               ↑                  ↑              ↓
   CSV Events                    UDP Protocol         Algorithm      JSON Database
       ↑                               ↑                  ↑              ↓
Event Generator               Batch Retrieval      Quadratic Model   Notifications
```

## Workflow Description

### 1. Data Flow Overview

The system processes tool wear data through these steps:

1. **Event Generation**: The Kit Holder insertions/extractions are recorded as events
2. **Server Loading**: Events are loaded into the MES server
3. **Client Retrieval**: Client retrieves events via UDP protocol
4. **Wear Analysis**: Algorithm predicts force and detects threshold exceedance
5. **Results Storage**: Analysis results are saved to a json database

### 2. Detailed Process Flow

#### Step 1: Event Data Generation
- **Synthetic Data**: Generated using `auto_saw_event_gen.py`
- **Format**: CSV with timestamps, event types, and Kit Holder information (Kit Holder Type, Kit Holder ID)

#### Step 2: Server Initialization
- Server loads event data and notifications from CSV files
- Maintains queues for events (reg 3091) and notifications (reg 3090)
- Listens on UDP port 30003 for client requests

#### Step 3: Client-Server Communication
- **PING (0x01)**: Test connection
- **GETREG (0x02)**: Get single event/notification
- **GETREGBLOCK (0x03)**: Get multiple events in batch
- **SETREG (0x04)**: Clear register after reading

#### Step 4: Wear Analysis Algorithm
- **Model Loading**: Reads quadratic coefficients from JSON
- **Force Prediction**: Uses cumulative insertions to predict force
- **Threshold Check**: Compares predicted force against given threshold
- **Notification Creation**: Generates alerts when threshold exceeded

#### Step 5: Results Management
- **Database Creation**: Stores analysis in `db.json`
- **Notification Files**: Creates CSV alerts for exceeded thresholds
- **Summary Statistics**: Provides overview of data collected and wear progression


### 3. Algorithm Details

#### Wear Prediction Model
The system uses a quadratic force prediction model:
```
force = intercept + c1*n + c2*n^2
```
where `n` is the cumulative number of insertions.

#### Time Window Processing
- Events are grouped into configurable time intervals (chunks) (default: 5 minutes)
- Analysis is performed per window with cumulative insertion tracking
- Results show progression over time

#### Threshold Detection
- When predicted force exceeds threshold:
  1. Notification is created with KH and wear details

### 4. Integration Points

#### MES Integration
- Uses standard MODAPTO protocols
- Compatible with existing MES infrastructure
- Provides real-time monitoring capability

## Compilation

### Using MinGW (Recommended)
```bash
gcc MesServer.c -o MesServer.exe -lws2_32
gcc MesClient.c -o MesClient.exe -lws2_32
```

## Quick Start

### 1. Quick Evaluation Demo

For a quick demonstration of the wear monitoring system:

```bash
python evaluation_wear_monitor.py 58daysevents.csv --model quadratic_model.json --threshold 16 --output db.json
```

This will:
- Process all events from the 58-day dataset (or any given dataset)
- Analyze wear using the pretrained quadratic model
- Generate notifications when force exceeds 16N
- Save results to `db.json`

### 2. Generate Test Data

To create a new test data:

```bash
python auto_saw_event_gen.py testevents.csv --cycles 1000
```

This generates 1000 insertion/extraction cycles (2000 total events).

## Detailed Workflow

### 1. Data Preparation

Prepare event data in chunks (5-minute intervals):

```bash
python wear_orchestrator.py --prepare --events 58daysevents.csv --chunk-dir chunks
```

### 2. Run the Orchestrator

Start the complete workflow:

```bash
python wear_orchestrator.py --chunk-dir chunks --model quadratic_model.json --threshold 150 --interval 5
```

This will:
1. Process each chunk sequentially as to simulate real data collection in a Production scenario
2. Start MES server with each chunk
3. Retrieve events using MES client
4. Analyze wear and generate notifications
5. Save results to `db_orchestrator.json`

### 3. Manual Server/Client Testing

To test server/client manually:

**Start the Server:**
```bash
MesServer.exe 0notif.csv 58daysevents.csv
```

**Run the Client:**
```bash
MesClient.exe 127.0.0.1
```

Then select options:
- 1: PING (test connection)
- 2: GETREG (get single event)
- 3: GETREGBLOCK (get multiple events)
- 4: SETREG (clear register)

## File Formats and I/O Description

### 1. Input Files

#### Events CSV File (e.g., `58daysevents.csv`)
```
Header byte (0xfe);Saw Event Type (1 Insertion - 2 Extraction);RFID Station ID [1..9];Timestamp 8bytes;KH Type [1..3];KH Unique ID [1..999999]
0xfe;1;6;1743258259;2;123456
0xfe;2;6;1743258287;2;123456
```

- Format: CSV with semicolon separator
- Structure:
  - `Header byte`: Always `0xfe`
  - `Saw Event Type`: `1` for insertion, `2` for extraction
  - `RFID Station ID`: Integer from 1 to 9
  - `Timestamp 8bytes`: UNIX timestamp (epoch seconds)
  - `KH Type`: Integer from 1 to 3
  - `KH Unique ID`: Integer from 1 to 999999

#### Notifications CSV
```
Header byte (0xfe);Issue type (0x01);RFID Station ID [1..9];Timestamp 8bytes;KH Type [1..3];KH Unique ID [1..999999]
```
When wear threshold is exceeded, notifications are generated:
- `Header byte`: Always `0xfe`
- `Issue type`: `1` for wear threshold exceeded
- `RFID Station ID`: Station where issue occurred
- `Timestamp`: Time of detection
- `KH Type`: Tool type
- `KH Unique ID`: Specific tool ID

#### Quadratic Model JSON (`quadratic_model.json`)
```json
{
    "intercept": -15.505737682225398,
    "coefficients": [0.0, 4.6275890442571586e-05, -7.386857113009756e-10],
    "Extraction_Number": 20,
    "Average_ForceZ": "-15.50481245989083"
}
```

- `intercept`: (float) y-intercept of the quadratic model
- `coefficients`: (list) three coefficients [c0, c1, c2] for polynomial equation
- `Extraction_Number`: (integer) reference extraction number
- `Average_ForceZ`: (string) reference force value

#### Command Line Arguments
- `events_file`: Path to events CSV file
- `--model`: Path to quadratic model JSON (default: 'quadratic_model.json')
- `--threshold`: Force threshold value (default: 16.0 for evaluation, 150.0 for regular use)
- `--interval`: Time interval in minutes (default: 5)
- `--output`: Output JSON database path (default: 'db.json')
- `--csv-output`: Optional CSV output path

### 2. Output Files

#### Wear Monitor Database (`db.json`)
Used by the direct wear_monitor.py script:
```json
{
    "metadata": {
        "created_at": "2024-04-22T12:00:00.000000",    # ISO timestamp
        "threshold": 16,                                # (float) force threshold
        "interval_minutes": 5,                          # (integer) time interval
        "model_path": "quadratic_model.json",           # (string) model file path
        "events_file": "58daysevents.csv"               # (string) events file path
    },
    "windows": [
        {
            "time_window": "2024-04-22T12:00:00",       # ISO timestamp
            "insertions": {
                "count": 10,                            # (integer) insertions in this window
                "total": 150,                           # (integer) cumulative insertions
                "first_index": 140,                     # (integer) first event index
                "last_index": 159                       # (integer) last event index
            },
            "force": {
                "predicted": 15.5,                      # (float) predicted force
                "exceeds_threshold": false              # (boolean) threshold exceeded
            },
            "kh": {                                     # (optional) tool info
                "type": 2,                              # (integer) KH type
                "id": 123456                            # (integer) KH unique ID
            }
        }
    ]
}
```

#### Orchestrator Database (`db_orchestrator.json`)
Used by the wear_orchestrator.py script, with additional fields for chunk processing:
```json
{
    "metadata": {
        "created_at": "2024-04-22T12:00:00.000000",    # ISO timestamp
        "threshold": 150,                               # (float) force threshold
        "interval_minutes": 5,                          # (integer) time interval
        "model_path": "quadratic_model.json",           # (string) model file path
        "chunk_directory": "chunks",                    # (string) directory containing chunks
        "total_chunks_processed": 12                    # (integer) number of chunks processed
    },
    "chunks": [                                         # Array of processed chunks
        {
            "chunk_index": 0,                           # (integer) chunk number
            "chunk_file": "chunks/chunk_0000.csv",      # (string) chunk file path
            "timestamp": "2024-04-22T12:00:00",         # ISO timestamp
            "events": {
                "total": 100,                           # (integer) total events in chunk
                "insertions": 50,                       # (integer) insertion events
                "extractions": 50                       # (integer) extraction events
            },
            "insertions_cumulative": 50,                # (integer) cumulative insertions
            "force": {
                "predicted": 15.2,                      # (float) predicted force
                "exceeds_threshold": false              # (boolean) threshold exceeded
            },
            "kh_info": [                                # (array) tool information
                {
                    "type": 2,                          # (integer) KH type
                    "id": 123456,                       # (integer) KH unique ID
                    "insertions": 25,                   # (integer) insertions for this KH
                    "extractions": 25                   # (integer) extractions for this KH
                }
            ],
            "notifications_created": 0,                 # (integer) notifications count
            "threshold_exceeding_events": []            # (array) events that exceeded threshold
        }
    ],
    "summary": {                                        # Summary statistics
        "total_events": 1000,                           # (integer) all events processed
        "total_insertions": 500,                        # (integer) all insertions
        "total_extractions": 500,                       # (integer) all extractions
        "chunks_with_threshold_exceeded": 2,            # (integer) chunks exceeding threshold
        "notifications_created": 5,                     # (integer) all notifications
        "total_threshold_exceeding_events": 5           # (integer) events exceeding threshold
    }
}
```

## Function Description

### 1. Main Processing Functions

#### `process_events(events_file, model_path, threshold, interval_minutes, db_output)`
Main function for processing events and detecting wear.
- **Input:**
  - `events_file`: (string) path to events CSV
  - `model_path`: (string) path to quadratic model JSON
  - `threshold`: (float) force threshold for wear detection
  - `interval_minutes`: (integer) time interval for grouping events
  - `db_output`: (string) path for output JSON database
- **Output:**
  - `db_data`: (dict) complete analysis results
- **Returns:** Dictionary with wear analysis results

```python
def process_events(events_file, model_path, threshold, interval_minutes=5, db_output='db.json'):
    """
    Process events file, count insertions in 5-minute intervals,
    predict force, and check against threshold
    """
    # ... function implementation ...
    return db_data
```

#### `predict_force(intercept, coefficients, extraction_number)`
Calculates predicted force using the quadratic model.
- **Input:**
  - `intercept`: (float) y-intercept of quadratic model
  - `coefficients`: (list) [c0, c1, c2] polynomial coefficients
  - `extraction_number`: (integer) number of extractions
- **Output:**
  - `y_pred`: (float) predicted force value

```python
def predict_force(intercept, coefficients, extraction_number):
    """Predict force using quadratic model for a given number of extractions"""
    # ... function implementation ...
    return y_pred
```

#### `load_model(model_path)`
Loads the quadratic model from JSON file.
- **Input:**
  - `model_path`: (string) path to model JSON file
- **Output:**
  - `intercept`: (float) model intercept
  - `coefficients`: (list) model coefficients

```python
def load_model(model_path):
    """Load the quadratic model from JSON file"""
    # ... function implementation ...
    return intercept, coefficients
```

### 2. Orchestrator Functions

#### `MESOrchestrator.run()`
Main orchestration loop that processes event chunks sequentially.
- **Input:** None (uses class initialization parameters)
- **Output:** Creates `db_orchestrator.json` with complete analysis

#### `MESOrchestrator._collect_events_for_interval(chunk_file)`
Retrieves events from MES server using client.
- **Input:**
  - `chunk_file`: (string) path to current chunk file
- **Output:**
  - `events`: (list) collected events from server

#### `prepare_chunks(events_file, output_dir, interval_minutes)`
Splits large event files into time-based chunks.
- **Input:**
  - `events_file`: (string) path to main events file
  - `output_dir`: (string) directory for chunk files
  - `interval_minutes`: (integer) chunk interval duration
- **Output:** Creates numbered chunk files in output directory

### 3. Event Generation Functions

#### `generate_events(filename, num_cycles)`
Creates synthetic event data for testing.
- **Input:**
  - `filename`: (string) output CSV filename
  - `num_cycles`: (integer) number of insertion/extraction cycles
- **Output:** CSV file with generated events

## Usage Examples

### 1. Quick Evaluation
Process a single events file directly:
```bash
python evaluation_wear_monitor.py 58daysevents.csv --model quadratic_model.json --threshold 16 --output db.json
```

### 2. Generate Test Data
Create synthetic insertion/extraction event data:
```bash
python auto_saw_event_gen.py customevents.csv --cycles 500
```

### 3. Run Complete Orchestrator Workflow
This is the recommended approach for production use:

#### Step 1: Prepare Data Chunks
```bash
python wear_orchestrator.py --prepare --events 58daysevents.csv --chunk-dir chunks --interval 5
```

#### Step 2: Run Orchestrator to Process Chunks
```bash
python wear_orchestrator.py --chunk-dir chunks --model quadratic_model.json --threshold 150 --interval 5
```

### 4. Custom Analysis Options
Monitor with different parameters:
```bash
python wear_monitor.py events.csv --model quadratic_model.json --threshold 20 --interval 5 --output custom_db.json
```

### 5. Export Results to CSV
In addition to JSON output:
```bash
python wear_monitor.py events.csv --csv-output results.csv
```

### 6. Test Client/Server Directly
For manual testing of MES communication:

Terminal 1 (Server):
```bash
MesServer.exe 0notif.csv 58daysevents.csv
```

Terminal 2 (Client):
```bash
MesClient.exe 127.0.0.1
```
Then follow the interactive prompts (1 for PING, 2 for GETREG, etc.)

Deployment
--

## Contributors
Université de Lorraine

## License
This project is licensed under the MIT License - see the LICENSE file for details.


# SA2 - Real-Time Anomaly Detection System

## Overview
SA2 is a real-time anomaly detection system that monitors industrial equipment through MQTT, detects abnormal behavior using statistical thresholds (3σ), and sends alerts via Kafka.

## Architecture
```
MQTT Broker → SA2.py → Kafka → End Users/Systems
                ↓
           Console Alerts
                ↓
           CSV Reports
```

## Installation

### Files Required
- `SA2-kafka.py` - Main SA2 script
- `EventsProducer.py` - Kafka event producer
- `components_list_redg05.json` - Component threshold configuration for ligne REDG CELL_05

## Configuration

### MQTT Settings
Update in `SA2.py`:
```python
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USERNAME = "your_username"
MQTT_PASSWORD = "your_password"
```

### Kafka Settings
Update in `SA2.py`:
```python
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
KAFKA_TOPIC = "modapto-anomaly-alerts"
```

## Monitored Components

The system monitors 31 MQTT topics across production line **REDG CELL_05**:

**Modules**: A21, A22, A23, A24, A25, A26, A27, A28

**Properties Monitored**:
- `diActualVitesse` - Motor speed
- `iActualCurrent` - Motor current

## System Input/Output
### Algorithm Input
**Source**: MQTT messages from production line sensors
**MQTT Message Format**:
```json
{
  "value": 28.0
}
```
**MQTT Topic Structure**:
```
Ligne_reducteur_REDG_CELL_05/A25_R05_Presse_arbre_de_sortie/ZnegAxis/Var_A25/FLOAT/iActualCurrent
```

### Algorithm Output
1. **Console Alert**:
```
============================================================
 ANOMALY DETECTED at 2025-10-03T13:38:10.573165 
   Component: Var_A25
   Property: iActualCurrent
   Value: 28.00
   Range: [-17.67, 22.97]
============================================================
 Kafka alert sent for Var_A25.iActualCurrent
 ```
**2. Output Kafka Event**:
```json
{
  "module": "A25",
  "pilot": "sew",
  "priority": "HIGH",
  "description": "Anomaly detected: Var_A25.iActualCurrent = 28.00 (Expected range: [-17.67, 22.97])",
  "timestamp": "2025-10-03T13:38:10.573165",
  "topic": "modapto-anomaly-alerts",
  "eventType": "ANOMALY_DETECTION",
  "smartService": "SA2",
  "metadata": {
    "component": "Var_A25",
    "property": "iActualCurrent",
    "value": 28.0,
    "low_threshold": -17.67,
    "high_threshold": 22.97,
    "deviation_percentage": 13.45
  }
}
```

## Running the System

### Start Self Awareness 2 API
```bash
uvicorn main:app --reload --port 8000
```

or run as Docker Container with the specified ENV variables.

The API will be available at `http://localhost:8000` with interactive documentation at `http://localhost:8000/docs`

## API Documentation

### Public Endpoints

#### Start Monitoring
**POST** `/monitor/kpis`

Starts a new real-time anomaly detection process that continuously monitors MQTT data streams and publishes anomaly alerts to Kafka.

**Request**: Base64-encoded JSON containing component configurations with thresholds, smart service ID, and module ID.

**Response**: Returns aconfirmation message with the unique process ID

**What it does**: Creates an isolated monitoring process that subscribes to configured MQTT topics, analyzes incoming sensor data against defined thresholds, and automatically sends Kafka events when anomalies are detected.

---

#### Check System Health
**GET** `/health`

Provides health status of all system components and dependencies.

**Response**: Returns the operational status of MQTT connection, Kafka connection, and the SA2 algorithm module, along with an overall system health indicator.

**What it does**: Tests connectivity to MQTT broker and Kafka cluster, verifies module imports, and reports if the system is ready to process monitoring requests.

---

### Protected Endpoints (Requires API Key)

All process management endpoints require authentication via the `X-API-Key` header. The API key must be configured in your environment variables as `PROCESS_MANAGEMENT_API_KEY`.

#### Get Process Information
**GET** `/processes/{process_id}`

Retrieves detailed information about a specific monitoring process.

**Authentication**: Requires `X-API-Key` header with valid API key.

**Parameters**: Process ID obtained from the start monitoring endpoint.

**Response**: Returns process metadata including smart service ID, module ID, start time, and current status (running or stopped).

**What it does**: Checks if the specified process is still active and provides its configuration details and runtime information.

---

#### Stop Monitoring Process
**DELETE** `/processes/{process_id}`

Gracefully terminates a running monitoring process.

**Authentication**: Requires `X-API-Key` header with valid API key.

**Parameters**: Process ID of the monitoring session to stop.

**Response**: Confirms the process was stopped and returns its metadata.

**What it does**: Sends a termination signal to the monitoring process, waits for graceful shutdown (up to 5 seconds), and forcefully kills it if necessary. The process stops listening to MQTT and closes Kafka connections.

---

#### List All Processes
**GET** `/processes`

Retrieves information about all monitoring processes managed by the API.

**Authentication**: Requires `X-API-Key` header with valid API key.

**Response**: Returns total count and detailed list of all processes with their metadata and current status.

**What it does**: Scans all active and stopped monitoring processes, checks their current state, and provides a comprehensive overview of all sessions.

---

## Environment Variables

Set these variables in your `.env` file or system environment:

- **PROCESS_MANAGEMENT_API_KEY**: API key for process management endpoints
- **SWAGGER_SERVER_URL**: Swagger UI URL Endpoint
- **MQTT_BROKER**: MQTT broker address (default: `localhost`)
- **MQTT_PORT**: MQTT broker port (default: `1883`)
- **MQTT_USERNAME**: MQTT authentication username
- **MQTT_PASSWORD**: MQTT authentication password
- **KAFKA_BOOTSTRAP_SERVERS**: Kafka broker addresses (default: `localhost:9092`)
- **KAFKA_TOPIC**: Kafka topic for anomaly events (default: `anomalies_topic`)
- **LOG_LEVEL**: Logging level (default: `INFO`)
- **CORS_DOMAINS**: Allowed CORS origins (default: `http://localhost:8094`)

## Monitoring Workflow

1. **Start**: Call the monitoring endpoint with your component configuration
2. **Monitor**: The system runs continuously, analyzing MQTT data in real-time
3. **Detect**: When anomalies are found, Kafka events are automatically published
4. **Manage**: Use the process ID to check status or stop the monitoring session
5. **Stop**: Call the stop endpoint when monitoring is no longer needed

Each monitoring process is isolated and can run independently with its own configuration, making it possible to monitor multiple systems or production lines simultaneously.
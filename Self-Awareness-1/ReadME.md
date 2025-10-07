# SA1 Self-Awareness Service

## Service Description

The SA1 Self-Awareness Service is a health monitoring system for industrial production components within the MODAPTO ecosystem. It analyzes binary sensor signals from conveyor systems to compute execution time KPIs that reflect component operational health.

**Purpose:** Monitor individual conveyor components over time and generate interpretable execution time metrics for health assessment and comparative analysis. The service processes ON/OFF state transitions from conveyor control signals to calculate meaningful duration metrics.

**Key Features:**
- Execution time KPI computation from sensor data
- Time-series data processing from InfluxDB
- Dual output: JSON files + Kafka events
- Full hierarchy support

---

## Input Requirements

### 1. Component Configuration File

**File:** `components_list_redg05.json`  
**Format:** JSON array with full hierarchy

```json
[
  {
    "Stage": "CELL_05",
    "Cell": "Ligne réducteur REDG",
    "Plc": "plc_100",
    "Module": "A21",
    "subElement": "ROOT",
    "Component": "Ecr_A21_3_L_LOOP_OUT",
    "Property": [
      {
        "Name": "diActualVitesse",
        "Low_thre": 213.5,
        "High_thre": 224.7
      },
      {
        "Name": "iActualCurrent",
        "Low_thre": -500.5,
        "High_thre": 890.7
      }
    ]
  }
]
```

**Field Descriptions:**
- `Stage`: Stage identifier (e.g., "CELL_05")
- `Cell`: Cell name (e.g., "Ligne réducteur REDG")
- `Plc`: PLC identifier (e.g., "plc_100")
- `Module`: Module name (e.g., "A21")
- `subElement`: SubElement classification (e.g., "ROOT", "Conveyor", "Z_Axis")
- `Component`: Component name (e.g., "Ecr_A21_3_L_LOOP_OUT")
- `Property[]`: Array of monitored properties with thresholds

---

## Algorithm Overview

### Signal Processing

1. **Data Extraction**: Query InfluxDB for sensor signals (diActualVitesse, iActualCurrent)
2. **State Detection**: Identify when value > 0 (active) and value = 0 (inactive)
3. **Duration Calculation**: Compute time between active→inactive transitions
4. **Quality Filtering**: 
   - Remove velocity spikes >= 16000
   - Filter durations > 15 seconds (configurable)
5. **Output Generation**: Create JSON files and publish Kafka events

**Key Parameters:**
- `SEUIL_DURATION`: 15 seconds (max allowed duration)
- `start_date` / `end_date`: Analysis time window (format: "DD-MM-YYYY HH:MM:SS")

---

## Output Format

### JSON Files

**Location:** `./JSON_hist_data_updated_vars/`  
**Naming:** `HIST_data_{Component}_{Variable}.json`  
**Format:** NDJSON (newline-delimited JSON)

**Example:**
```json
{
  "Stage": "CELL_05",
  "Cell": "Ligne réducteur REDG",
  "PLC": "plc_100",
  "Module": "A21",
  "SubElement": "ROOT",
  "Component": "Ecr_A21_3_L_LOOP_OUT",
  "Variable": "diActualVitesse",
  "Variable_Type": "velocity",
  "Starting_date": "03-10-2025 08:00:00",
  "Ending_date": "03-10-2025 18:00:00",
  "Data_source": "InfluxDB",
  "Bucket": "Ligne_reducteur_REDG05",
  "Data_list": [2.29, 2.24, 2.23, 2.27, 2.28]
}
```

### Kafka Events

**Topic:** `smart-service-event`  
**Event Types:**
1. "Self-Awareness Monitoring and Storing KPIs Input Configuration" (sent once at start)
2. "Self-Awareness Monitoring and Storing KPIs KPI Results" (sent per component)

**Example Event:**
```json
{
  "description": "SA1 execution time KPI computed for Ecr_A21_3_L_LOOP_OUT",
  "module": "CELL_05_Ligne_réducteur_REDG_plc_100_A21_ROOT_Ecr_A21_3_L_LOOP_OUT",
  "priority": "MID",
  "timestamp": "2025-10-07T10:30:45",
  "eventType": "Self-Awareness Monitoring and Storing KPIs KPI Results",
  "sourceComponent": "Self-Awareness Monitoring and Storing KPIs",
  "smartService": "Self-Awareness",
  "topic": "smart-service-event",
  "results": { /* same as JSON file structure */ }
}
```

---

## API Interface

### Overview

The SA1 service provides a REST API interface built with FastAPI, enabling remote execution and monitoring capabilities. The API uses Base64-encoded JSON for secure data transmission and provides comprehensive health monitoring.

### API Endpoints

#### 1. Self-Awareness KPI Processing

**Endpoint:** `POST /monitor/kpis`  
**Description:** Initiates SA1 processing for component KPI monitoring and analysis  
**Content-Type:** `application/json`

**Request Format:**

```json
{
  "request": "base64_encoded_json_data"
}
```

**Base64 Decoded Payload Structure:**

```json
{
  "components": [
    {
      "Stage": "CELL_05",
      "Cell": "Ligne réducteur REDG",
      "Plc": "plc_100",
      "Module": "A21",
      "subElement": "ROOT",
      "Component": "Ecr_A21_3_L_LOOP_OUT",
      "Property": [
        {
          "Name": "diActualVitesse",
          "Low_thre": 213.5,
          "High_thre": 224.7
        }
      ]
    }
  ],
  "start_date": "03-10-2025 08:00:00",
  "end_date": "03-10-2025 18:00:00", 
  "smartServiceId": "Self-Awareness",
  "moduleId": "SA1_Module"
}
```

**Response:**
```json
{
  "response": "base64_encoded_confirmation_message"
}
```

Processing runs asynchronously. Results published to Kafka.

#### 2. Health Check

**Endpoint:** `GET /health`  
**Description:** Provides comprehensive health status of the SA1 service and its dependencies  
**Content-Type:** `application/json`

**Response Format:**

```json
{
  "status": "healthy|degraded",
  "services": {
    "influxdb": {
      "status": "healthy|unhealthy",
      "connection": true|false,
      "error": "error_message_if_any"
    },
    "kafka": {
      "status": "healthy|unhealthy", 
      "connection": true|false,
      "error": "error_message_if_any"
    },
    "sa1_algorithm": {
      "status": "healthy|unhealthy",
      "import": true|false,
      "callable": true|false,
      "error": "error_message_if_any"
    },
    "events_producer": {
      "status": "healthy|unhealthy",
      "import": true|false,
      "class_available": true|false,
      "error": "error_message_if_any"
    },
    "api": {
      "status": "healthy",
      "connection": true
    }
  },
  "message": "Self Awareness 1 API is running - Status: healthy",
  "timestamp": "2025-01-28T10:30:45.123Z"
}
```

### Environment Configuration

**Required Environment Variables:**

```bash
# InfluxDB Configuration
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_influxdb_token
INFLUXDB_ORG_ID=your_org_id
BUCKET_NAME=Ligne_reducteur_REDG05

# Kafka Configuration  
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# API Configuration
CORS_DOMAINS=http://localhost:8094,http://localhost:3000
SWAGGER_SERVER_URL=http://localhost:8000

# Logging Configuration
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### API Usage Flow

1. **Health Check**: Verify service status with `GET /health`
2. **Prepare Data**: Create component configuration and time range parameters
3. **Encode Request**: Base64 encode the JSON payload
4. **Submit Processing**: Send POST request to `/monitor/kpis`
5. **Monitor Results**: Check Kafka topics for processing results and events

### Asynchronous Processing

The SA1 API operates asynchronously:

- API calls return immediately with task confirmation
- Actual processing runs in background thread pool
- Results are published to Kafka message bus
- JSON files are generated in local storage for additional analysis

### Error Handling

**HTTP Status Codes:**

- `200`: Success - Task initiated successfully
- `400`: Bad Request - Invalid Base64 data or missing fields
- `422`: Validation Error - Invalid request format or data validation failure
- `500`: Internal Server Error - Critical processing failure

---

## Running the Service

### Standalone Execution
```bash
python SA1.py
```

Configure dates in `main()` function:
```python
start_date = "03-10-2025 08:00:00"
end_date = "03-10-2025 18:00:00"
```

### API Execution
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Swagger Documentation:** `http://localhost:8000/docs`

---

## Dependencies

**Required Python Packages:**

- `fastapi`: Web framework for building APIs
- `uvicorn`: ASGI server for running FastAPI applications
- `pydantic`: Data validation using Python type annotations
- `pandas`: Data manipulation and analysis
- `requests`: HTTP requests for InfluxDB API
- `kafka-python`: Kafka client for event publishing
- `urllib3`: HTTP library with SSL handling
- `json`: JSON serialization/deserialization
- `datetime`: Date and time handling
- `os`: Operating system interface
- `logging`: Python logging framework
- `asyncio`: Asynchronous programming support
- `base64`: Base64 encoding/decoding

---

## Hierarchy Structure

```
Stage → Cell → PLC → Module → SubElement → Component → Variable
```

**Supported Variables:**
- `diActualVitesse` (velocity)
- `iActualCurrent` (current)

**Output Compatibility:**  
SA1 output directly consumable by LA Service v2.0.0

---

## Example Console Output

```
Testing connections...
InfluxDB connection successful!
Kafka connection successful!
Processing 32 tags from components_list_redg05.json

Processing tag: g_IO.Ecr_A21_3_L_LOOP_OUT.MEMENTO.diActualVitesse
  Hierarchy: Ligne réducteur REDG > A21 > ROOT > Ecr_A21_3_L_LOOP_OUT
  Retrieved 1250 data points
  Filtered 5 spikes, 1245 data points remaining
  Total cycles before filtering: 450
  Remaining after duration filter (15s): 447
  Created new HIST_data_Ecr_A21_3_L_LOOP_OUT_diActualVitesse.json
  SA1 results sent to PKB

Successfully processed 32 tags
JSON files saved to: ./JSON_hist_data_updated_vars/
Events sent to PKB via Message Bus
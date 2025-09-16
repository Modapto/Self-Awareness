# SA1 Self-Awareness Service

## Service Description

The SA1 Self-Awareness Service is a health monitoring system for industrial production components within the MODAPTO ecosystem. It analyzes binary sensor signals from conveyor systems to compute execution time KPIs that reflect component operational health.

**Purpose:** Monitor individual conveyor components over time and generate interpretable execution time metrics for health assessment and comparative analysis. The service processes ON/OFF state transitions from conveyor control signals to calculate meaningful duration metrics.

**Key Features:**

- **Execution time KPI computation**: Calculates conveyor cycle durations from binary control signals
- **Time-series data processing**: Retrieves sensor data from InfluxDB within configurable time windows
- **Dual output format**: Generates JSON files for Local Analytics and publishes events to Kafka message bus
- **PKB integration**: Sends results to Production Knowledge Base

## Algorithm Overview

### Signal Processing Algorithm

**Location:** Main processing loop in `main()` function  
**Purpose:** Extract execution time KPIs from binary conveyor control signals

**Processing Methodology:**

1. **Data Extraction**: Query InfluxDB for binary control signals ("Move" and "puissance") within specified time range
2. **State Transition Detection**: Identify rising edges (0→1: conveyor start) and falling edges (1→0: conveyor stop)
3. **Execution Time Calculation**: Compute duration between corresponding start/stop pairs for each operational cycle
4. **Quality Filtering**: Apply configurable duration thresholds to remove outliers and sensor noise
5. **Aggregation**: Collect execution times over daily operational periods
6. **Output Generation**: Create structured results in JSON format and Kafka events

**Algorithm Parameters:**

- `SEUIL_DURATION`: Maximum allowed execution duration threshold in seconds (default: 15) - filters out abnormally long cycles that may indicate sensor malfunctions
- `start_date`: Analysis period start time in format "DD-MM-YYYY HH:MM:SS"
- `end_date`: Analysis period end time in format "DD-MM-YYYY HH:MM:SS"
- `BUCKET_NAME`: InfluxDB bucket containing time-series sensor data
- `time_window`: Configurable analysis window supporting both historical analysis and real-time monitoring

## Input Requirements

### 1. Component Configuration File

**File:** `components_list.json`  
**Format:** JSON array of component definitions

```json
[
  {
    "Stage": "CELL_01",
    "Cell": "Prémontage HUB REDG",
    "Plc": "plc_100",
    "Module": "AE1",
    "subElement": "ROOT",
    "Component": "Ecr_AE1_L_Haut_xAxis",
    "Property": [
      {
        "Name": "puissance",
        "Low_thre": 100,
        "High_thre": 500
      },
      {
        "Name": "Move",
        "Low_thre": 10,
        "High_thre": 50
      }
    ]
  }
]
```

**Field Descriptions:**

- `Stage`: Production stage id ("CELL_01")
- `Cell`: Production cell name ("Prémontage HUB REDG")
- `Plc`: PLC id ("plc_100")
- `Module`: Module id within the PLC ("AE1")
- `subElement`: Sub-element classification ("ROOT")
- `Component`: Component name ("Ecr_AE1_L_Haut_xAxis")
- `Property[]`: Array of monitored properties
  - `Name`: Property name ("puissance", "Move", etc.)
  - `Low_thre`: Lower threshold value for property
  - `High_thre`: Upper threshold value for property

### 2. InfluxDB Configuration

**Required Settings:**

- `INFLUXDB_URL`: InfluxDB server endpoint
- `INFLUXDB_TOKEN`: Authentication token for InfluxDB access
- `INFLUXDB_ORG_ID`: Organization ID in InfluxDB
- `BUCKET_NAME`: Target bucket containing sensor data

### 3. Kafka Configuration

**Required Settings:**

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses
- `KAFKA_TOPIC`: Target topic for event publishing (default: "self-awareness-1")

**Event Schema Requirements:**

- `module`: Production module id
- `pilot`: Pilot id (typically "SEW")
- `description`: Event description
- `eventType`: Type of event being published
- `smartService`: Smart service id
- `results`: Structured results payload

## Output Formats

### 1. JSON Files (Local Analysis)

**Location:** `./JSON_hist_data/` directory  
**Naming Convention:** `HIST_data_{PLC}_{Component}_{Variable}.json`

**Example Output:**

```json
{
  "Ligne": "plc_100",
  "Component": "Ecr_AE1_L_Haut",
  "Variable": "xAxis_Move",
  "Starting_date": "07-07-2025 00:00:00",
  "Ending_date": "08-07-2025 23:59:59",
  "Data_source": "InfluxDB",
  "Bucket": "HUB",
  "Data_list": [
    1.9448215,
    1.7083293,
    1.1807646,
    1.9474222,
    0.170447,
    6.1250601,
    5.5623876
  ]
}
```

**Field Descriptions:**

- `Ligne`: PLC id from which data was retrieved
- `Component`: Component name being analyzed
- `Variable`: Specific sensor variable (e.g., "xAxis_Move", "xAxis_puissance")
- `Starting_date`: Analysis period start timestamp
- `Ending_date`: Analysis period end timestamp
- `Data_source`: Source system id ("InfluxDB")
- `Bucket`: InfluxDB bucket name
- `Data_list`: Array of execution durations in seconds (filtered by threshold)

### 2. Kafka Events (PKB Integration)

**Topic:** `self-awareness-1`  
**Event Type:** "SA1 KPI Results"

**Example Event Structure:**

```json
{
  "description": "SA1 execution time KPI computed for Ecr_AE1_L_Haut",
  "module": "HUB_REDG_CELL_05_plc_100_AE1_Ecr_AE1_L_Haut",
  "pilot": "SEW",
  "eventType": "SA1 KPI Results",
  "sourceComponent": "SA1",
  "smartService": "Self-Awareness",
  "topic": "self-awareness-1",
  "timestamp": "2025-01-21T10:30:45Z",
  "results": {
    "Ligne": "plc_100",
    "Component": "Ecr_AE1_L_Haut",
    "Variable": "xAxis_Move",
    "Starting_date": "07-07-2025 00:00:00",
    "Ending_date": "08-07-2025 23:59:59",
    "Data_source": "InfluxDB",
    "Bucket": "HUB",
    "Data_list": [1.9448215, 1.7083293, 1.1807646]
  }
}
```

Additional Setup Event: The service also sends a one-time configuration event ("SA1 Input Configuration") at the beginning of each execution, containing the components configuration and processing parameters.

## Execution Example

### Console Output

```sh
 Testing connections...
 InfluxDB connection successful!
 Kafka connection successful!
 Kafka producer initialized successfully
 Sending components configuration to PKB...
   ↪ Components configuration sent to PKB

 Processing tag: plc_500:.g_IO.Ecr_AE7_L_Haut.STATE.xAxis_puissance
Querying InfluxDB for tag: plc_500:.g_IO.Ecr_AE7_L_Haut.STATE.xAxis_puissance
Time range: 2025-07-07T00:00:00Z to 2025-07-08T23:59:59Z
  ↪ Retrieved 12 data points
  ↪ Total before filtering: 1
  ↪ Remaining after duration filter (15s): 0
  ↪ Saved JSON file: HIST_data_plc_500_Ecr_AE7_L_Haut_xAxis_puissance.json

 Processing tag: plc_500:.g_IO.Ecr_AE7_L_Haut.STATE.xAxis_Move
Querying InfluxDB for tag: plc_500:.g_IO.Ecr_AE7_L_Haut.STATE.xAxis_Move
Time range: 2025-07-07T00:00:00Z to 2025-07-08T23:59:59Z
  ↪ Retrieved 37 data points
  ↪ Total before filtering: 13
  ↪ Remaining after duration filter (15s): 10
  ↪ Saved data to HIST_data_plc_500_Ecr_AE7_L_Haut_xAxis_Move.json
   ↪ SA1 results sent to PKB for Ecr_AE7_L_Haut

 Successfully processed 80 tags
 Results saved to: C:\Users\FR4ABDIL\LocalAnalytics\JSON_hist_data
 Events sent to PKB via Message Bus (topic: self-awareness-1)
 Kafka producer closed
```

## Running the Service

### Prerequisites

1. **Python Environment**: Python 3.7+ with required dependencies
2. **InfluxDB Access**: Running InfluxDB instance with configured authentication
3. **Kafka Cluster**: Available Kafka broker for event publishing
4. **Configuration File**: Valid `components_list.json` file in working directory

### Execution Steps

1. **Configure Environment**: Set InfluxDB and Kafka connection parameters
2. **Prepare Components**: Create or update `components_list.json` configuration
3. **Set Time Range**: Modify `start_date` and `end_date` variables in main function
4. **Execute Service**: Run `python main.py`

### Configuration Parameters

**Time Range Configuration:**

```python
start_date = "07-07-2025 00:00:00"  # Analysis start time
end_date = "08-07-2025 23:59:59"    # Analysis end time
```

**Duration Filtering:**

```python
SEUIL_DURATION = 15  # Maximum duration threshold in seconds
```

**Output Directory:**

```python
json_output_dir = os.path.join(os.getcwd(), "JSON_hist_data")
```

## Implementation Details

### Tag Generation

Components are processed by generating sensor tags in the format:

```sh
{PLC}:.g_IO.{Component}.STATE.{Variable}
```

Example: `plc_100:.g_IO.Ecr_AE1_L_Haut.STATE.xAxis_Move`

### PKB Naming Convention

For Kafka events, component names are formatted as:

```sh
HUB_REDG_CELL_05_{PLC}_{Module}_{Component}
```

Example: `HUB_REDG_CELL_05_plc_100_AE1_Ecr_AE1_L_Haut`

### Duration Calculation Algorithm

```python
def calculate_durations(df, seuil_duration=15):
    """
    Calculate durations between rising ('1') and falling ('0') edges
    
    Process:
    1. Sort data by timestamp
    2. Identify state transitions (0→1: start, 1→0: end)
    3. Calculate duration between start/end pairs
    4. Filter durations exceeding threshold
    """
```

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
      "Module": "AE1",
      "Plc": "plc_100", 
      "Stage": "CELL_01",
      "Cell": "Prémontage HUB REDG",
      "subElement": "ROOT",
      "Component": "Ecr_AE1_L_Haut_xAxis",
      "Property": [
        {
          "Name": "puissance",
          "Low_thre": 100,
          "High_thre": 500
        }
      ]
    }
  ],
  "start_date": "07-01-2025 00:00:00",
  "end_date": "07-01-2025 23:59:59", 
  "smartServiceId": "SA1_SERVICE",
  "moduleId": "HUB_MODULE_01"
}
```

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
BUCKET_NAME=HUB

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

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

### Start Self Awareness 2 with Kafka Integration
```bash
python SA2-kafka.py
```

### Stop the System
Press `Ctrl+C` to stop and generate CSV report.

## Functions & API

### Main Function: `check_anomaly(component, prop_name, value, timestamp)`
**Purpose**: Validates sensor values against configured thresholds

**Input Parameters**:
- `component` (str): Component name (e.g., "Ecr_A25_L_R05")
- `prop_name` (str): Property name (e.g., "iActualCurrent")
- `value` (float): Measured value
- `timestamp` (str): ISO format timestamp

**Logic**:
1. Filters out system codes (value >= 16000)
2. Filters out idle states (value == 0)
3. Compares value against configured low/high thresholds
4. If anomaly detected → Triggers alerts

**Output**: Boolean (True if anomaly detected, False otherwise)

---

### Data Loading: `load_configuration(file_path)`
**Purpose**: Loads component thresholds from JSON configuration

**Input**: Path to `components_list_redg05.json`

**Output**: Populates `threshold_map` dictionary with component thresholds

---

### Kafka Integration: `send_kafka_alert(anomaly_info)`
**Purpose**: Publishes anomaly alerts to Kafka topic

**Kafka Event Schema**: See "Algorithm Output" section above
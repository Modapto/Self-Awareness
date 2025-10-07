import os
import pandas as pd
from datetime import datetime
import json
import requests
import urllib3
from io import StringIO
from kafka import KafkaProducer
import logging


# Configure logging (console only)
def get_log_level():
    """Get log level from environment variable, default to INFO"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    level_mapping = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    return level_mapping.get(log_level, logging.INFO)


logging.basicConfig(
    level=get_log_level(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Disable SSL warnings for internal network
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# InfluxDB Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "influxdb-url-placeholder")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "influxdb-token-placeholder")
INFLUXDB_ORG_ID = os.getenv("INFLUXDB_ORG_ID", "influxdb-org-id-placeholder")
BUCKET_NAME = os.getenv("BUCKET_NAME", "Ligne_reducteur_REDG05")
SEUIL_DURATION = 15  # Threshold in seconds to filter out long durations

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = "self-awareness-monitor-kpis"


# ---------------------------------------------------------------------------------------------------------------------
# EventsProducer Class for Message Bus Integration
class EventsProducer:
    def __init__(self, bootstrap_servers):
        """
        Initialize Kafka Producer with bootstrap servers

        :param bootstrap_servers: List of Kafka broker addresses (comma-separated)
        """
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id='self-awaraness-1',
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        )

    def validate_event_data(self, event_data):
        """
        Validate event data against the required schema

        :param event_data: Dictionary containing event details
        :raises ValueError: If required fields are missing or invalid
        """
        required_fields = ['module', 'priority', 'description', 'timestamp', 'topic', 'eventType', 'sourceComponent',
                           'smartService']

        # Check required fields
        for field in required_fields:
            if field not in event_data or not event_data[field]:
                raise ValueError(f"Missing required field: {field}")

        # Validate priority
        if event_data.get('priority') not in ['LOW', 'MID', 'HIGH']:
            raise ValueError("Invalid priority. Must be LOW, MID, or HIGH")

        return event_data

    def produce_event(self, topic, event_data):
        """
        Produce a Kafka event to the specified topic

        :param topic: Kafka topic to send the event to
        :param event_data: Dictionary containing event details
        """
        # Add timestamp if not provided
        if 'timestamp' not in event_data:
            event_data['timestamp'] = datetime.now(datetime.timezone.utc).isoformat()

        # Make priority uppercase
        if 'priority' in event_data:
            event_data['priority'] = event_data['priority'].upper()

        # Validate event data
        validated_event = self.validate_event_data(event_data)

        try:
            # Produce message to Kafka topic
            self.producer.send(topic, validated_event)

            # Flush to ensure message is sent
            self.producer.flush()

            logger.info(f"Event sent to Message Bus: {event_data.get('eventType', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"Failed to send event to Message Bus: {str(e)}")
            return False

    def close(self):
        """
        Close the Kafka producer
        """
        if self.producer:
            self.producer.flush()
            self.producer.close()


# ---------------------------------------------------------------------------------------------------------------------
# Generate sensor tag strings from a structured JSON file defining the components with FULL HIERARCHY
def generate_tags_from_json(components_data):
    """
    Generate a list of sensor tags from components data.
    Creates tags for both diActualVitesse and iActualCurrent.

    Args:
        components_data (list): List of component dictionaries with hierarchy info.

    Returns:
        list: List of tuples (tag_name, variable_type, hierarchy_info)
              where hierarchy_info is a dict with Stage, Cell, Plc, Module, subElement, Component
    """
    tags = []
    for comp in components_data:
        # Extract hierarchy information
        hierarchy = {
            "Stage": comp.get("Stage", ""),
            "Cell": comp.get("Cell", ""),
            "Plc": comp.get("Plc", ""),
            "Module": comp.get("Module", ""),
            "SubElement": comp.get("subElement", ""),
            "Component": comp.get("Component", "")
        }

        # Check which properties this component has
        for prop in comp.get("Property", []):
            prop_name = prop["Name"]

            if prop_name == "diActualVitesse":
                tag_velocity = f"g_IO.{hierarchy['Component']}.MEMENTO.diActualVitesse"
                tags.append((tag_velocity, 'velocity', hierarchy.copy()))

            elif prop_name == "iActualCurrent":
                tag_current = f"g_IO.{hierarchy['Component']}.MEMENTO.iActualCurrent"
                tags.append((tag_current, 'current', hierarchy.copy()))

    return tags


# ---------------------------------------------------------------------------------------------------------------------
# Generate PKB naming convention from hierarchy data
def generate_pkb_name(hierarchy):
    """
    Generate PKB naming convention: Stage_Cell_Plc_Module_SubElement_Component

    Args:
        hierarchy (dict): Hierarchy information

    Returns:
        str: PKB formatted name
    """
    try:
        # Format: Stage_Cell_Plc_Module_SubElement_Component
        pkb_parts = [
            hierarchy.get('Stage', 'Unknown'),
            hierarchy.get('Cell', 'Unknown').replace(' ', '_'),
            hierarchy.get('Plc', 'Unknown'),
            hierarchy.get('Module', 'Unknown'),
            hierarchy.get('SubElement', 'Unknown'),
            hierarchy.get('Component', 'Unknown')
        ]
        pkb_name = '_'.join(pkb_parts)
        return pkb_name

    except Exception as e:
        logger.error(f"Error generating PKB name: {e}")
        return "Unknown_PKB_Name"


# ---------------------------------------------------------------------------------------------------------------------
# Send components configuration to Message Bus
def send_components_config_to_pkb(producer, components_data, start_date, end_date, input_module, smart_service_id):
    """
    Send components configuration as event to PKB via Message Bus

    Args:
        producer: EventsProducer instance
        components_data: Components configuration data
        start_date: Processing start date
        end_date: Processing end date
        input_module: Input module identifier
        smart_service_id: Smart service identifier
    """
    logger.info("Sending components configuration to PKB...")

    event_data = {
        "description": "Self-Awareness Monitoring and Storing KPIs components configuration for monitoring",
        "module": input_module,
        "priority": "MID",
        "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "eventType": "Self-Awareness Monitoring and Storing KPIs Input Configuration",
        "sourceComponent": "Self-Awareness Monitoring and Storing KPIs",
        "smartService": smart_service_id,
        "topic": KAFKA_TOPIC,
        "results": {
            "type": "components_configuration",
            "processing_period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "total_components": len(components_data),
            "components": components_data
        }
    }

    success = producer.produce_event(KAFKA_TOPIC, event_data)
    if success:
        logger.info("Components configuration sent to PKB")
    else:
        logger.error("Failed to send components configuration to PKB")


# ---------------------------------------------------------------------------------------------------------------------
# Send SA1 results to Message Bus with full hierarchy
def send_sa1_results_to_pkb(producer, hierarchy, record, input_module, smart_service_id):
    """
    Send SA1 results as event to PKB via Message Bus

    Args:
        producer: EventsProducer instance
        hierarchy: Component hierarchy information
        record: SA1 processing results
        input_module: Input module identifier
        smart_service_id: Smart service identifier
    """
    pkb_name = generate_pkb_name(hierarchy)

    event_data = {
        "description": f"Self-Awareness Monitoring and Storing KPIs execution time KPI computed for {record['Component']}",
        "module": pkb_name,
        "priority": "MID",
        "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "eventType": "Self-Awareness Monitoring and Storing KPIs KPI Results",
        "sourceComponent": "Self-Awareness Monitoring and Storing KPIs",
        "smartService": smart_service_id,
        "topic": KAFKA_TOPIC,
        "results": record
    }

    success = producer.produce_event(KAFKA_TOPIC, event_data)
    if success:
        logger.info(f"SA1 results sent to PKB for {record['Component']}")
    else:
        logger.error(f"Failed to send SA1 results to PKB for {record['Component']}")


# ---------------------------------------------------------------------------------------------------------------------
# Query InfluxDB for sensor data within a specific time range
def load_sensor_data_from_influxdb(tag_name, plc, start_date, end_date):
    """
    Load sensor data from InfluxDB for a specific tag and time window.

    Args:
        tag_name (str): Sensor tag in format 'g_IO.Component.MEMENTO.Variable'.
        plc (str): PLC identifier (e.g., "plc_100")
        start_date (str): Start datetime in format '%d-%m-%Y %H:%M:%S'.
        end_date (str): End datetime in format '%d-%m-%Y %H:%M:%S'.

    Returns:
        pd.DataFrame: DataFrame with columns ['tick', 'tag', 'valeur'].
    """
    # Convert dates to RFC3339 format for InfluxDB
    start_dt = datetime.strptime(start_date, "%d-%m-%Y %H:%M:%S")
    end_dt = datetime.strptime(end_date, "%d-%m-%Y %H:%M:%S")

    start_rfc3339 = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_rfc3339 = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(f"Querying InfluxDB for tag: {tag_name}")

    # Flux query matching your structure
    flux_query = f'''
    from(bucket: "{BUCKET_NAME}")
    |> range(start: {start_rfc3339}, stop: {end_rfc3339})
    |> filter(fn: (r) => r["_measurement"] == "plc_data")
    |> filter(fn: (r) => r["PLC"] == "{plc}")
    |> filter(fn: (r) => r.Variable == "{tag_name}")
    |> filter(fn: (r) => r["_field"] == "value")
    |> keep(columns: ["_time", "Variable", "_value"])
    '''

    headers = {
        'Authorization': f'Token {INFLUXDB_TOKEN}',
        'Content-Type': 'application/vnd.flux',
        'Accept': 'application/csv'
    }

    try:
        response = requests.post(
            f"{INFLUXDB_URL}/api/v2/query?orgID={INFLUXDB_ORG_ID}",
            headers=headers,
            data=flux_query,
            verify=False,
            timeout=30
        )

        if response.status_code == 200 and response.text.strip():
            lines = [line for line in response.text.split('\n') if line.strip() and not line.startswith('#')]
            if len(lines) > 1:
                df = pd.read_csv(StringIO('\n'.join(lines)))

                if not df.empty and '_time' in df.columns and '_value' in df.columns:
                    df['tick'] = pd.to_datetime(df['_time'])
                    df['tag'] = tag_name
                    df['valeur'] = pd.to_numeric(df['_value'], errors='coerce')

                    result_df = df[['tick', 'tag', 'valeur']].dropna()
                    logger.info(f"  Retrieved {len(result_df)} data points")
                    return result_df

            logger.warning(f"No data found for tag: {tag_name}")
            return pd.DataFrame(columns=['tick', 'tag', 'valeur'])
        else:
            logger.error(f"InfluxDB query failed: {response.status_code}")
            return pd.DataFrame(columns=['tick', 'tag', 'valeur'])

    except Exception as e:
        logger.error(f"Error querying InfluxDB for tag {tag_name}: {e}")
        return pd.DataFrame(columns=['tick', 'tag', 'valeur'])


# ---------------------------------------------------------------------------------------------------------------------
# Compute the durations between rising and falling edges in the signal with an upper threshold.
def calculate_durations(df, variable_type, seuil_duration=15):
    """
    Calculate the durations between start (value > 0) and stop (value = 0) in the signal.

    Args:
        df (pd.DataFrame): Input DataFrame with 'tick' (datetime) and 'valeur' (signal values).
        variable_type (str): Type of variable - 'velocity' or 'current'
        seuil_duration (int, optional): Maximum allowed duration in seconds. Default is 15.

    Returns:
        pd.DataFrame: DataFrame with valid intervals containing 'start_time', 'end_time', 'duration'.
    """
    if df.empty:
        return pd.DataFrame(columns=['start_time', 'end_time', 'duration'])

    df = df.sort_values(by='tick').reset_index(drop=True)

    # Filter out spike values >= 16000 for velocity only
    if variable_type == 'velocity':
        original_count = len(df)
        df = df[df['valeur'] < 16000].reset_index(drop=True)
        logger.info(f"  Filtered {original_count - len(df)} spikes, {len(df)} data points remaining")

        if df.empty:
            logger.warning("  No data remaining after spike filtering")
            return pd.DataFrame(columns=['start_time', 'end_time', 'duration'])

    # Convert to binary state: >0 means active (1), 0 means inactive (0)
    df['state'] = (df['valeur'] > 0).astype(int)

    active = False
    start_time = None
    intervals = []

    for _, row in df.iterrows():
        tick = row['tick']
        state = row['state']

        if state == 1 and not active:
            # Rising edge: starts
            start_time = tick
            active = True

        elif state == 0 and active:
            # Falling edge: stops
            end_time = tick
            duration = end_time - start_time
            intervals.append({'start_time': start_time, 'end_time': end_time, 'duration': duration})
            active = False

    # Filter out durations above the threshold (expressed in seconds)
    df_result = pd.DataFrame(intervals)
    if not df_result.empty:
        logger.debug(f"  Total cycles before filtering: {len(df_result)}")
        df_result = df_result[df_result["duration"] <= pd.to_timedelta(seuil_duration, unit="s")]
        logger.debug(f"  Remaining after duration filter ({seuil_duration}s): {len(df_result)}")

    return df_result


# ---------------------------------------------------------------------------------------------------------------------
# Test InfluxDB connection
def test_influxdb_connection():
    """Test if InfluxDB is accessible and list available buckets."""
    headers = {
        'Authorization': f'Token {INFLUXDB_TOKEN}',
    }

    try:
        response = requests.get(
            f"{INFLUXDB_URL}/api/v2/buckets?orgID={INFLUXDB_ORG_ID}",
            headers=headers,
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            buckets = response.json()
            logger.info("InfluxDB connection successful!")
            logger.info("Available buckets:")
            for bucket in buckets.get('buckets', []):
                logger.info(f"  - {bucket['name']} (ID: {bucket['id']})")
            return True
        else:
            logger.error(f"InfluxDB connection failed: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Error connecting to InfluxDB: {e}")
        return False


# ---------------------------------------------------------------------------------------------------------------------
# Test Kafka connection
def test_kafka_connection():
    """Test if Kafka is accessible."""
    try:
        producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
        logger.info("Kafka connection successful!")
        producer.close()
        return True
    except Exception as e:
        logger.error(f"Error connecting to Kafka: {e}")
        return False


# ---------------------------------------------------------------------------------------------------------------------
# Main script to process all tags and export results WITH FULL HIERARCHY
def main(input_module="HUB_SA1_Configuration", smart_service_id="Self-Awareness"):
    """
    Main processing function for SA1 with full hierarchy support

    Args:
        input_module: Input module identifier (default: "HUB_SA1_Configuration")
        smart_service_id: Smart service identifier (default: "Self-Awareness")
    """
    # Test connections first
    logger.info("Testing connections...")
    if not test_influxdb_connection():
        logger.error("Cannot proceed without InfluxDB connection. Please check configuration.")
        return

    if not test_kafka_connection():
        logger.warning("Kafka connection failed. PKB events will not be sent.")
        use_kafka = False
    else:
        use_kafka = True

    # Input parameters
    start_date = "03-10-2025 08:00:00"
    end_date = "03-10-2025 18:00:00"

    # Output directory for JSON files
    json_output_dir = os.path.join(os.getcwd(), "JSON_hist_data_updated_vars")
    os.makedirs(json_output_dir, exist_ok=True)

    # Load tag list from JSON definition
    components_file = "components_list_redg05.json"
    if not os.path.exists(components_file):
        logger.error(f"Components file not found: {components_file}")
        return

    # Load components data with full hierarchy
    with open(components_file, "r", encoding="utf-8") as f:
        components_data = json.load(f)

    tags = generate_tags_from_json(components_data)
    logger.info(f"Processing {len(tags)} tags from {components_file}")

    # Initialize Kafka producer if available
    producer = None
    if use_kafka:
        try:
            producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
            logger.info("Kafka producer initialized successfully")

            # Send components configuration to PKB (once per run)
            send_components_config_to_pkb(producer, components_data, start_date, end_date, input_module,
                                          smart_service_id)

        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            use_kafka = False

    # Process each tag
    processed_count = 0
    for tag_name, variable_type, hierarchy in tags:
        logger.info(f"Processing tag: {tag_name}")
        logger.info(
            f"  Hierarchy: {hierarchy['Cell']} > {hierarchy['Module']} > {hierarchy['SubElement']} > {hierarchy['Component']}")

        try:
            # Load data from InfluxDB
            df = load_sensor_data_from_influxdb(tag_name, hierarchy['Plc'], start_date, end_date)

            if df.empty:
                logger.warning("  No data found.")
                continue

            # Parse tag into its components
            try:
                parts = tag_name.split(".MEMENTO.")
                variable = parts[1]
            except Exception as e:
                logger.error(f"Failed to parse tag: {tag_name}, Error: {e}")
                continue

            # Compute durations between active and inactive states
            result_df = calculate_durations(df, variable_type, seuil_duration=SEUIL_DURATION)
            durations = result_df['duration'].dt.total_seconds().tolist() if not result_df.empty else []

            # Create record with full hierarchy
            record = {
                "Stage": hierarchy['Stage'],
                "Cell": hierarchy['Cell'],
                "PLC": hierarchy['Plc'],
                "Module": hierarchy['Module'],
                "SubElement": hierarchy['SubElement'],
                "Component": hierarchy['Component'],
                "Variable": variable,
                "Variable_Type": variable_type,
                "Starting_date": str(start_date),
                "Ending_date": str(end_date),
                "Data_source": "InfluxDB",
                "Bucket": BUCKET_NAME,
                "Data_list": durations
            }

            # Save to JSON file (for LA service)
            json_filename = os.path.join(json_output_dir, f"HIST_data_{hierarchy['Component']}_{variable}.json")

            # Append to existing file or create new (NDJSON format)
            if os.path.exists(json_filename):
                with open(json_filename, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    logger.info(f"  Appended to existing {json_filename}")
            else:
                with open(json_filename, "w", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    logger.info(f"  Created new {json_filename}")

            # Send SA1 results to PKB via Message Bus
            if use_kafka and producer:
                send_sa1_results_to_pkb(producer, hierarchy, record, input_module, smart_service_id)

            processed_count += 1

        except Exception as e:
            logger.error(f"Error processing tag {tag_name}: {e}")

    # Close Kafka producer
    if producer:
        producer.close()
        logger.info("Kafka producer closed")

    logger.info(f"Successfully processed {processed_count} tags")
    logger.info(f"JSON files saved to: {json_output_dir}")
    if use_kafka:
        logger.info(f"Events sent to PKB via Message Bus (topic: {KAFKA_TOPIC})")


# ---------------------------------------------------------------------------------------------------------------------
# Async Function for handling the Self-Awareness-1 algorithmic processing WITH FULL HIERARCHY
def async_self_awareness_monitoring_kpis(components, smart_service, module, start_date, end_date):
    """
    Main async function to handle Self-Awareness-1 monitoring KPIs processing

    Args:
        components: List of component dictionaries with full hierarchy (Stage, Cell, PLC, Module, SubElement, Component, Property data)
        smart_service: Smart service ID
        module: Module ID
        start_date: Analysis start datetime
        end_date: Analysis end datetime

    Returns:
        dict: Event data for Kafka publishing
    """
    try:
        # Convert datetime objects to string format expected by the algorithm
        start_date_str = start_date.strftime("%d-%m-%Y %H:%M:%S") if hasattr(start_date, 'strftime') else str(
            start_date)
        end_date_str = end_date.strftime("%d-%m-%Y %H:%M:%S") if hasattr(end_date, 'strftime') else str(end_date)

        logger.info(f"Starting Self-Awareness-1 KPI processing...")
        logger.info(f"Time range: {start_date_str} to {end_date_str}")
        logger.info(f"Processing {len(components)} components")

        # Test connections first
        logger.info("Testing connections...")
        if not test_influxdb_connection():
            error_msg = "Cannot proceed without InfluxDB connection. Please check configuration."
            logger.error(error_msg)
            return {
                "description": f"Self-Awareness Monitoring and Storing KPIs processing failed: {error_msg}",
                "module": module,
                "priority": "HIGH",
                "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "eventType": "Self-Awareness Monitoring and Storing KPIs Processing Error",
                "sourceComponent": "Self-Awareness Monitoring and Storing KPIs",
                "smartService": smart_service,
                "topic": "self-awareness-monitor-kpis",
                "results": None
            }

        if not test_kafka_connection():
            logger.warning("Kafka connection failed. PKB events will not be sent.")
            use_kafka = False
        else:
            use_kafka = True

        # Generate tags from component data with hierarchy
        tags = generate_tags_from_json(components)
        logger.info(f"Generated {len(tags)} tags for processing")

        # Initialize Kafka producer if available
        producer = None
        if use_kafka:
            try:
                producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
                logger.info("Kafka producer initialized successfully")

                # Send components configuration to PKB (once per run)
                send_components_config_to_pkb(producer, components, start_date_str, end_date_str, module, smart_service)

            except Exception as e:
                logger.error(f"Failed to initialize Kafka producer: {e}")
                use_kafka = False

        # Process each tag
        processed_count = 0
        results_summary = []

        for tag_name, variable_type, hierarchy in tags:
            logger.info(f"Processing tag: {tag_name}")
            logger.info(
                f"  Hierarchy: {hierarchy['Cell']} > {hierarchy['Module']} > {hierarchy['SubElement']} > {hierarchy['Component']}")

            try:
                # Load data from InfluxDB
                df = load_sensor_data_from_influxdb(tag_name, hierarchy['Plc'], start_date_str, end_date_str)

                if df.empty:
                    logger.warning("  No data found.")
                    continue

                # Parse tag into its components
                try:
                    parts = tag_name.split(".MEMENTO.")
                    variable = parts[1]
                except Exception as e:
                    logger.error(f"Failed to parse tag: {tag_name}, Error: {e}")
                    continue

                # Compute durations between active and inactive states
                result_df = calculate_durations(df, variable_type, seuil_duration=SEUIL_DURATION)
                durations = result_df['duration'].dt.total_seconds().tolist() if not result_df.empty else []

                # Create record with full hierarchy
                record = {
                    "Stage": hierarchy['Stage'],
                    "Cell": hierarchy['Cell'],
                    "PLC": hierarchy['Plc'],
                    "Module": hierarchy['Module'],
                    "SubElement": hierarchy['SubElement'],
                    "Component": hierarchy['Component'],
                    "Variable": variable,
                    "Variable_Type": variable_type,
                    "Starting_date": start_date_str,
                    "Ending_date": end_date_str,
                    "Data_source": "InfluxDB",
                    "Bucket": BUCKET_NAME,
                    "Data_list": durations
                }

                # Send SA1 results to PKB via Message Bus
                if use_kafka and producer:
                    send_sa1_results_to_pkb(producer, hierarchy, record, module, smart_service)

                processed_count += 1
                results_summary.append({
                    "component": hierarchy['Component'],
                    "variable": variable,
                    "durations_count": len(durations),
                })

            except Exception as e:
                logger.error(f"Error processing tag {tag_name}: {e}")
                results_summary.append({
                    "component": hierarchy.get('Component', 'Unknown'),
                    "error": str(e)
                })

        # Close Kafka producer
        if producer:
            producer.close()
            logger.info("Kafka producer closed")

        logger.info(f"Successfully processed {processed_count} tags")
        if use_kafka:
            logger.info(f"Events sent to PKB via Message Bus (topic: {KAFKA_TOPIC})")

        # Return success event data
        return {
            "description": f"Self-Awareness Monitoring and Storing KPIs KPI processing completed successfully. Processed {processed_count} tags.",
            "module": module,
            "priority": "MID",
            "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "eventType": "Self-Awareness Monitoring and Storing KPIs Processing Success",
            "sourceComponent": "Self-Awareness Monitoring and Storing KPIs",
            "smartService": smart_service,
            "topic": "self-awareness-monitor-kpis",
            "results": {
                "processed_count": processed_count,
                "total_tags": len(tags),
                "processing_period": {
                    "start_date": start_date_str,
                    "end_date": end_date_str
                },
                "summary": results_summary
            }
        }

    except Exception as e:
        error_msg = f"Critical error in SA1 processing: {str(e)}"
        logger.error(error_msg)

        # Return error event data
        return {
            "description": error_msg,
            "module": module,
            "priority": "HIGH",
            "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "eventType": "Self-Awareness Monitoring and Storing KPIs Processing Error",
            "sourceComponent": "Self-Awareness Monitoring and Storing KPIs",
            "smartService": smart_service,
            "topic": "self-awareness-monitor-kpis",
            "results": None
        }


# Called via API
# if __name__ == "__main__":
#     main()

# to start kafka
#  .\bin\windows\zookeeper-serever-start.bat .\config\zookeeper.properties
#   .\bin\windows\kafka-server-start.bat .\config\server.properties
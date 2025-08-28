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
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://frbrmmodapto-ppi:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "influxdb-token-placeholder")
INFLUXDB_ORG_ID = os.getenv("INFLUXDB_ORG_ID", "0ad195e61f21f83f")
BUCKET_NAME = os.getenv("BUCKET_NAME", "HUB")
SEUIL_DURATION = 15 # Threshold in seconds to filter out long durations

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = "smart-service-event"

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
        required_fields = ['module', 'priority', 'description', 'timestamp', 'topic', 'eventType', 'sourceComponent', 'smartService']

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
            event_data['timestamp'] = datetime.now().isoformat(utc=True)

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
# Generate sensor tag strings from a structured JSON file defining the components.
def generate_tags_from_json(json_file):
    """
    Generate a list of sensor tags from a JSON file describing components.
    Updated to work with new JSON structure.

    Args:
        json_file (str): Path to the JSON file containing component definitions.

    Returns:
        list: List of tag strings formatted as 'PLC:.g_IO.Component.STATE.Property'
    """
    with open(json_file, "r", encoding="utf-8") as f:
        components_data = json.load(f)

    tags = []
    for comp in components_data:
        plc = comp["Plc"]  # e.g., "plc_100"
        component = comp["Component"]  # e.g., "Ecr_AE1_L_Haut"
        component_clean = component.replace("_xAxis", "")

        for prop in comp.get("Property", []):
            prop_name = prop["Name"]  # Get the property name

            # Add xAxis_ prefix to match InfluxDB format
            if prop_name == "puissance":
                var_name = "xAxis_puissance"
            elif prop_name == "Move":
                var_name = "xAxis_Move"
            else:
                var_name = f"xAxis_{prop_name}"

            tag = f"{plc}:.g_IO.{component_clean}.STATE.{var_name}"
            tags.append(tag)

    return tags


# ---------------------------------------------------------------------------------------------------------------------
# Generate PKB naming convention from component data
def generate_pkb_name(tag_name, components_data):
    """
    Generate PKB naming convention: Stage_CELL_Plc_Module_Component

    Args:
        tag_name (str): Original tag name
        components_data (list): Components configuration data

    Returns:
        str: PKB formatted name
    """
    try:
        # Parse tag to extract PLC and component info
        parts = tag_name.split(":.g_IO.")[1].split(".STATE.")
        plc = tag_name.split(":")[0]
        component = parts[0]

        # Find matching component in configuration
        for comp in components_data:
            comp_clean = comp["Component"].replace("_xAxis", "")
            if comp["Plc"] == plc and comp_clean == component:
                # Extract module from component name (e.g., AE1 from Ecr_AE1_L_Haut)
                comp_parts = component.split("_")
                module = comp_parts[1] if len(comp_parts) > 1 else "Unknown"

                # Format: Stage_CELL_Plc_Module_Component
                pkb_name = f"HUB_REDG_CELL_05_{plc}_{module}_{component}"
                return pkb_name

        # Fallback if not found in config
        return f"HUB_REDG_CELL_05_{plc}_Unknown_{component}"

    except Exception as e:
        logger.error(f"Error generating PKB name for {tag_name}: {e}")
        return f"HUB_Unknown_{tag_name.replace(':', '_').replace('.', '_')}"


# ---------------------------------------------------------------------------------------------------------------------
# Send components configuration to Message Bus
def send_components_config_to_pkb(producer, components_data, start_date, end_date):
    """
    Send components configuration as event to PKB via Message Bus

    Args:
        producer: EventsProducer instance
        components_data: Components configuration data
        start_date: Processing start date
        end_date: Processing end date
    """
    logger.info("Sending components configuration to PKB...")

    event_data = {
        "description": "SA1 components configuration for monitoring",
        "module": "HUB_SA1_Configuration",
        "priority": "MID",
        "timestamp": datetime.now().isoformat(utc=True),
        "eventType": "SA1 Input Configuration",
        "sourceComponent": "SA1",
        "smartService": "Self-Awareness",
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
# Send SA1 results to Message Bus
def send_sa1_results_to_pkb(producer, tag_name, record, components_data):
    """
    Send SA1 results as event to PKB via Message Bus

    Args:
        producer: EventsProducer instance
        tag_name: Component tag name
        record: SA1 processing results
        components_data: Components configuration data
    """
    pkb_name = generate_pkb_name(tag_name, components_data)

    event_data = {
        "description": f"SA1 execution time KPI computed for {record['Component']}",
        "module": pkb_name,
        "priority": "MID",
        "timestamp": datetime.now().isoformat(utc=True),
        "eventType": "SA1 KPI Results",
        "sourceComponent": "SA1",
        "smartService": "Self-Awareness",
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
def load_sensor_data_from_influxdb(tag_name, start_date, end_date):
    """
    Load sensor data from InfluxDB for a specific tag and time window.
    Reconstructs the tag format from separate PLC and Variable columns.

    Args:
        tag_name (str): Sensor tag in format 'PLC:.g_IO.Component.STATE.Variable'.
        start_date (str): Start datetime in format '%d-%m-%Y %H:%M:%S'.
        end_date (str): End datetime in format '%d-%m-%Y %H:%M:%S'.

    Returns:
        pd.DataFrame: DataFrame with columns ['tick', 'tag', 'valeur'].
    """
    # Parse the tag to extract PLC and Variable
    try:
        plc_part, variable_part = tag_name.split(":", 1)
        # variable_part is like ".g_IO.Ecr_AE1_L_Haut.STATE.xAxis_puissance"
        # Remove the leading dot
        variable_clean = variable_part[1:] if variable_part.startswith(".") else variable_part

    except Exception as e:
        logger.error(f"Error parsing tag {tag_name}: {e}")
        return pd.DataFrame(columns=['tick', 'tag', 'valeur'])

    # Convert dates to RFC3339 format for InfluxDB
    start_dt = datetime.strptime(start_date, "%d-%m-%Y %H:%M:%S")
    end_dt = datetime.strptime(end_date, "%d-%m-%Y %H:%M:%S")

    start_rfc3339 = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_rfc3339 = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(f"Querying InfluxDB for tag: {tag_name}")
    logger.debug(f"Time range: {start_rfc3339} to {end_rfc3339}")

    # Flux query to get specific PLC and Variable data
    flux_query = f'''
    from(bucket: "{BUCKET_NAME}")
    |> range(start: {start_rfc3339}, stop: {end_rfc3339})
    |> filter(fn: (r) => r.PLC == "{plc_part}")
    |> filter(fn: (r) => r.Variable == "{variable_clean}")
    |> map(fn: (r) => ({{_time: r._time, PLC: r.PLC, Variable: r.Variable, value: string(v: r._value)}}))
    |> yield(name: "result")
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
            # Parse CSV response into DataFrame
            lines = [line for line in response.text.split('\n') if line.strip() and not line.startswith('#')]
            if len(lines) > 1:  # Check if we have data beyond header
                df = pd.read_csv(StringIO('\n'.join(lines)))

                if not df.empty and '_time' in df.columns and 'value' in df.columns:
                    # Reconstruct original tag format and rename columns to match original code
                    df['tick'] = pd.to_datetime(df['_time'])
                    df['tag'] = tag_name  # Use the original tag format
                    df['valeur'] = pd.to_numeric(df['value'], errors='coerce')

                    result_df = df[['tick', 'tag', 'valeur']].dropna()
                    logger.info(f"  ↪ Retrieved {len(result_df)} data points")
                    return result_df

            logger.warning(f"No data found for tag: {tag_name}")
            return pd.DataFrame(columns=['tick', 'tag', 'valeur'])
        else:
            logger.error(f"InfluxDB query failed: {response.status_code} - {response.text}")
            return pd.DataFrame(columns=['tick', 'tag', 'valeur'])

    except Exception as e:
        logger.error(f"Error querying InfluxDB for tag {tag_name}: {e}")
        return pd.DataFrame(columns=['tick', 'tag', 'valeur'])


# ---------------------------------------------------------------------------------------------------------------------
# Compute the durations between rising and falling edges in the signal with an upper threshold.
def calculate_durations(df, seuil_duration=15):
    """
    Calculate the durations between rising ('1') and falling ('0') edges in the sensor signal.

    Args:
        df (pd.DataFrame): Input DataFrame with 'tick' (datetime) and 'valeur' (binary values).
        seuil_duration (int, optional): Maximum allowed duration in seconds. Default is 15.

    Returns:
        pd.DataFrame: DataFrame with valid intervals containing 'start_time', 'end_time', 'duration'.
    """
    if df.empty:
        return pd.DataFrame(columns=['start_time', 'end_time', 'duration'])

    df = df.sort_values(by='tick').reset_index(drop=True)
    df['valeur'] = df['valeur'].astype(int)

    active = False
    start_time = None
    intervals = []

    for _, row in df.iterrows():
        tick = row['tick']
        value = row['valeur']

        if value == 1 and not active:
            start_time = tick
            active = True

        elif value == 0 and active:
            end_time = tick
            duration = end_time - start_time
            intervals.append({'start_time': start_time, 'end_time': end_time, 'duration': duration})
            active = False

    # Filter out durations above the threshold (expressed in seconds)
    df_result = pd.DataFrame(intervals)
    if not df_result.empty:
        logger.debug(f"  Total before filtering: {len(df_result)}")
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
# Async Function for handling the Self-Awareness-1 algorithmic processing
def async_self_awareness_monitoring_kpis(components, smart_service, module, start_date, end_date):
    """
    Main async function to handle Self-Awareness-1 monitoring KPIs processing
    
    Args:
        components: List of component dictionaries with PLC, Component, Property data
        smart_service: Smart service ID
        module: Module ID  
        start_date: Analysis start datetime
        end_date: Analysis end datetime
        
    Returns:
        dict: Event data for Kafka publishing
    """
    try:
        # Convert datetime objects to string format expected by the algorithm
        start_date_str = start_date.strftime("%d-%m-%Y %H:%M:%S") if hasattr(start_date, 'strftime') else str(start_date)
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
                "description": f"SA1 processing failed: {error_msg}",
                "module": module,
                "priority": "HIGH", 
                "timestamp": datetime.now().isoformat(),
                "eventType": "SA1 Processing Error",
                "sourceComponent": "SA1",
                "smartService": smart_service,
                "topic": "smart-service-event",
                "results": None
            }

        if not test_kafka_connection():
            logger.warning("Kafka connection failed. PKB events will not be sent.")
            use_kafka = False
        else:
            use_kafka = True

        # Generate tags from component data
        tags = generate_tags_from_json(components)
        logger.info(f"Generated {len(tags)} tags for processing")

        # Initialize Kafka producer if available
        producer = None
        if use_kafka:
            try:
                producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
                logger.info("Kafka producer initialized successfully")

                # Send components configuration to PKB (once per run)
                send_components_config_to_pkb(producer, components, start_date_str, end_date_str)

            except Exception as e:
                logger.error(f"Failed to initialize Kafka producer: {e}")
                use_kafka = False

        # Process each tag
        processed_count = 0
        results_summary = []
        
        for tag_name in tags:
            logger.info(f"Processing tag: {tag_name}")
            try:
                # Load data from InfluxDB
                df = load_sensor_data_from_influxdb(tag_name, start_date_str, end_date_str)

                if df.empty:
                    logger.warning("   No data found.")
                    continue

                # Parse tag into its components
                try:
                    parts = tag_name.split(":.g_IO.")[1].split(".STATE.")
                    ligne = tag_name.split(":")[0]
                    component = parts[0]
                    variable = parts[1]
                except Exception as e:
                    logger.error(f"Failed to parse tag: {tag_name}, Error: {e}")
                    continue

                # Compute durations between 1-to-0 transitions
                result_df = calculate_durations(df, seuil_duration=SEUIL_DURATION)
                durations = result_df['duration'].dt.total_seconds().tolist() if not result_df.empty else []

                # Create record (enhanced with InfluxDB metadata)
                record = {
                    "Ligne": ligne,
                    "Component": component,
                    "Variable": variable,
                    "Starting_date": start_date_str,
                    "Ending_date": end_date_str,
                    "Data_source": "InfluxDB",
                    "Bucket": BUCKET_NAME,
                    "Data_list": durations
                }

                # Send SA1 results to PKB via Message Bus
                if use_kafka and producer:
                    send_sa1_results_to_pkb(producer, tag_name, record, components)

                processed_count += 1
                results_summary.append({
                    "tag": tag_name,
                    "component": component,
                    "variable": variable,
                    "durations_count": len(durations),
                })

            except Exception as e:
                logger.error(f"Error processing tag {tag_name}: {e}")
                results_summary.append({
                    "tag": tag_name,
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
            "description": f"SA1 KPI processing completed successfully. Processed {processed_count} tags.",
            "module": module,
            "priority": "MID",
            "timestamp": datetime.now().isoformat(),
            "eventType": "SA1 Processing Success",
            "sourceComponent": "SA1", 
            "smartService": smart_service,
            "topic": "smart-service-event",
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
            "timestamp": datetime.now().isoformat(), 
            "eventType": "SA1 Processing Error",
            "sourceComponent": "SA1",
            "smartService": smart_service,
            "topic": "smart-service-event",
            "results": None
        }


# ---------------------------------------------------------------------------------------------------------------------
# Main script to process all tags and export results to individual JSON files per tag + Message Bus
def main():
    SEUIL_DURATION = 15  # Threshold in seconds to filter out long durations

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
    start_date = "07-07-2025 00:00:00"
    end_date = "08-07-2025 23:59:59"

    # Output directory for JSON files
    json_output_dir = os.path.join(os.getcwd(), "JSON_hist_data")
    os.makedirs(json_output_dir, exist_ok=True)

    # Load tag list from JSON definition
    components_file = "components_list.json"
    if not os.path.exists(components_file):
        logger.error(f"Components file not found: {components_file}")
        return

    # Load components data for PKB integration
    with open(components_file, "r", encoding="utf-8") as f:
        components_data = json.load(f)

    tags = generate_tags_from_json(components_file)
    logger.info(f"Processing {len(tags)} tags from {components_file}")

    # Initialize Kafka producer if available
    producer = None
    if use_kafka:
        try:
            producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
            logger.info("Kafka producer initialized successfully")

            # Send components configuration to PKB (once per run)
            send_components_config_to_pkb(producer, components_data, start_date, end_date)

        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            use_kafka = False

    # Process each tag
    processed_count = 0
    for tag_name in tags:
        logger.info(f"Processing tag: {tag_name}")
        try:
            # Load data from InfluxDB
            df = load_sensor_data_from_influxdb(tag_name, start_date, end_date)

            if df.empty:
                logger.warning("  ↪ No data found.")
                continue

            # Parse tag into its components (same as original)
            try:
                parts = tag_name.split(":.g_IO.")[1].split(".STATE.")
                ligne = tag_name.split(":")[0]
                component = parts[0]
                variable = parts[1]
            except Exception as e:
                logger.error(f"Failed to parse tag: {tag_name}, Error: {e}")
                continue

            # Compute durations between 1-to-0 transitions (same as original)
            result_df = calculate_durations(df, seuil_duration=SEUIL_DURATION)
            durations = result_df['duration'].dt.total_seconds().tolist() if not result_df.empty else []

            # Create record (enhanced with InfluxDB metadata)
            record = {
                "Ligne": ligne,
                "Component": component,
                "Variable": variable,
                "Starting_date": str(start_date),
                "Ending_date": str(end_date),
                "Data_source": "InfluxDB",
                "Bucket": BUCKET_NAME,
                "Data_list": durations
            }

            # OUTPUT 1: Save to JSON file (for LA service) - KEEP EXISTING
            safe_tag_name = tag_name.replace(":.g_IO.", "_").replace(".STATE.", "_").replace(".", "_")
            json_filename = os.path.join(json_output_dir, f"HIST_data_{safe_tag_name}.json")

            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
                logger.info(f"  ↪ Saved JSON file: {json_filename}")

            # OUTPUT 2: Send SA1 results to PKB via Message Bus - ADD THIS
            if use_kafka and producer:
                send_sa1_results_to_pkb(producer, tag_name, record, components_data)

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


# Called via API
# if __name__ == "__main__":
#     main()

# to start kafka
#  .\bin\windows\zookeeper-serever-start.bat .\config\zookeeper.properties
#   .\bin\windows\kafka-server-start.bat .\config\server.properties
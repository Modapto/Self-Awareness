import paho.mqtt.client as mqtt
import json
import os
from datetime import datetime, timezone
import pandas as pd
import urllib3
from EventsProducer import EventsProducer
import logging

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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = os.getenv("MQTT_BROKER", "1883")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "anomalies_topic")

CONFIG_FILE = "../config/components_list_redg05.json"

threshold_map = {}
anomalies_list = []
data_buffer = []

MQTT_TOPICS = [
    "Ligne_reducteur_REDG_CELL_05/+/+/+/FLOAT/+",
]

kafka_producer = None


def load_configuration(file_path):
    """Load the JSON configuration and create threshold map."""
    print(f" Loading configuration from {file_path}...")
    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)
    except Exception as e:
        print(f" ERROR loading configuration: {e}")
        return False

    for item in config_data:
        component = item.get("Component")
        module = item.get("Module")

        for prop in item.get("Property", []):
            prop_name = prop.get("Name")
            low_thre = prop.get("Low_thre")
            high_thre = prop.get("High_thre")

            if all([component, prop_name, low_thre is not None, high_thre is not None]):
                key = f"{component}|{prop_name}"
                threshold_map[key] = {
                    "low": float(low_thre),
                    "high": float(high_thre),
                    "component": component,
                    "property": prop_name,
                    "module": module
                }

    print(f" Configuration loaded. {len(threshold_map)} variables configured.")
    return True


def load_configuration_from_dict(config_data):
    """
    Load configuration from dictionary and create threshold map.

    :param config_data: List of component dictionaries with structure:
        [
            {
                "Component": "component_name",
                "Module": "module_name",
                "Property": [
                    {"Name": "prop_name", "Low_thre": 0.0, "High_thre": 100.0},
                    ...
                ]
            },
            ...
        ]
    :return: Dictionary mapping component|property -> threshold info
    """
    logger.info(f" Loading configuration from dictionary...")
    threshold_map_local = {}

    try:
        for item in config_data:
            component = item.get("Component")
            module = item.get("Module")

            for prop in item.get("Property", []):
                prop_name = prop.get("Name")
                low_thre = prop.get("Low_thre")
                high_thre = prop.get("High_thre")

                if all([component, prop_name, low_thre is not None, high_thre is not None]):
                    key = f"{component}|{prop_name}"
                    threshold_map_local[key] = {
                        "low": float(low_thre),
                        "high": float(high_thre),
                        "component": component,
                        "property": prop_name,
                        "module": module
                    }

        logger.info(f" Configuration loaded. {len(threshold_map_local)} variables configured.")
        return threshold_map_local

    except Exception as e:
        logger.error(f" ERROR loading configuration from dict: {e}")
        return None


def parse_mqtt_topic(topic):
    """
    Parse MQTT topic to extract component and property.
    Example: Ligne_reducteur_REDG_CELL_05/A22_R02_Presse_AP3_et_5/Conveyor/Ecr_A22_L_R02/FLOAT/diActualVitesse
    Returns: (component, property_name)
    """
    parts = topic.split('/')
    if len(parts) >= 6:
        component = parts[3]  # e.g., Ecr_A22_L_R02
        prop_name = parts[5]  # e.g., diActualVitesse
        return component, prop_name
    return None, None


def send_kafka_alert(anomaly_info, kafka_producer_param=None, smart_service_id="SA2", module_id="UNKNOWN"):
    """
    Send anomaly alert to Kafka topic using EventsProducer.

    :param anomaly_info: Dictionary containing anomaly details
    :param kafka_producer_param: Optional Kafka producer to use (for concurrent execution)
    :param smart_service_id: Smart Service ID for the event
    :param module_id: Module ID for the event
    """
    # Use provided producer or fall back to global one
    producer = kafka_producer_param if kafka_producer_param is not None else kafka_producer

    if not producer:
        logger.warning("  Kafka producer not initialized. Skipping Kafka alert.")
        return

    try:
        # Determine priority based on deviation magnitude
        deviation_pct = abs(anomaly_info['value'] - anomaly_info.get('expected_value', 0)) / \
                       (anomaly_info['high'] - anomaly_info['low']) * 100 if (anomaly_info['high'] - anomaly_info['low']) > 0 else 0

        if deviation_pct > 50:
            priority = "HIGH"
        elif deviation_pct > 20:
            priority = "MID"
        else:
            priority = "LOW"

        # Construct event data according to the schema
        event_data = {
            "module": module_id,
            "pilot": "SEW",
            "priority": priority,
            "description": f"Anomaly detected: {anomaly_info['component']}.{anomaly_info['property']} = {anomaly_info['value']:.2f} (Expected range: [{anomaly_info['low']:.2f}, {anomaly_info['high']:.2f}])",
            "timestamp": anomaly_info['timestamp'],
            "topic": KAFKA_TOPIC,
            "eventType": "Anomaly detected",
            "smartService": smart_service_id,
            "results": {
                "component": anomaly_info['component'],
                "property": anomaly_info['property'],
                "value": anomaly_info['value'],
                "low_threshold": anomaly_info['low'],
                "high_threshold": anomaly_info['high'],
                "deviation_percentage": round(deviation_pct, 2),
                "component_module": anomaly_info.get('module', 'UNKNOWN')  # Keep component's module as metadata
            }
        }

        # Send to Kafka
        producer.produce_event(KAFKA_TOPIC, event_data)
        logger.info(f" Kafka alert sent for {anomaly_info['component']}.{anomaly_info['property']}")

    except Exception as e:
        logger.error(f"  Error sending Kafka alert: {e}")


def check_anomaly(component, prop_name, value, timestamp, threshold_map_param=None, kafka_producer_param=None,
                  smart_service_id="SA2", module_id="UNKNOWN"):
    """
    Check if value is an anomaly and log it.

    :param component: Component name
    :param prop_name: Property name
    :param value: Measured value
    :param timestamp: Timestamp of the measurement
    :param threshold_map_param: Optional threshold map to use (for concurrent execution)
    :param kafka_producer_param: Optional Kafka producer to use (for concurrent execution)
    :param smart_service_id: Smart Service ID for Kafka events
    :param module_id: Module ID for Kafka events
    :return: Anomaly info dict if anomaly detected, None otherwise
    """
    # Use provided threshold map or fall back to global one
    thresholds = threshold_map_param if threshold_map_param is not None else threshold_map

    key = f"{component}|{prop_name}"
    limits = thresholds.get(key)

    if limits and isinstance(value, (int, float)):
        # Filter out system status codes
        if value >= 16000:
            return None

        # Filter out idle/zero values
        if value == 0:
            return None

        # Check if value is outside thresholds
        if not (limits["low"] <= value <= limits["high"]):
            anomaly_info = {
                'timestamp': timestamp,
                'component': component,
                'property': prop_name,
                'value': value,
                'low': limits['low'],
                'high': limits['high'],
                'module': limits.get('module', 'UNKNOWN'),
                'expected_value': (limits['low'] + limits['high']) / 2  # Middle of range
            }

            # Print alert to console
            logger.info("=" * 60)
            logger.info(f" ANOMALY DETECTED at {timestamp} ")
            logger.info(f"   Component: {component}")
            logger.info(f"   Property: {prop_name}")
            logger.info(f"   Value: {value:.2f}")
            logger.info(f"   Range: [{limits['low']:.2f}, {limits['high']:.2f}]")
            logger.info("=" * 60)

            # Send to Kafka if producer is provided
            if kafka_producer_param:
                send_kafka_alert(anomaly_info, kafka_producer_param, smart_service_id, module_id)

            return anomaly_info
    return None


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker."""
    if rc == 0:
        print(" Connected to MQTT broker successfully!")
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
            print(f" Subscribed to: {topic}")
    else:
        print(f" Failed to connect to MQTT broker. Return code: {rc}")


def on_message(client, userdata, msg):
    """Callback when MQTT message is received."""
    try:
        topic = msg.topic
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Parse the payload (assuming JSON format)
        payload = json.loads(msg.payload.decode())
        value = payload.get('value')
        
        # Parse topic to get component and property
        component, prop_name = parse_mqtt_topic(topic)
        
        if component and prop_name and value is not None:
            # Store in buffer for potential analysis
            data_buffer.append({
                'timestamp': timestamp,
                'component': component,
                'property': prop_name,
                'value': value,
                'topic': topic
            })
            
            # Keep buffer size manageable (last 10000 points)
            if len(data_buffer) > 10000:
                data_buffer.pop(0)
            
            # Check for anomaly
            check_anomaly(component, prop_name, value, timestamp)
            
    except Exception as e:
        print(f"  Error processing message: {e}")


def save_anomalies_report():
    """Save anomalies to CSV."""
    if not anomalies_list:
        print("No anomalies to report.")
        return
    
    # Save to CSV
    df = pd.DataFrame(anomalies_list)
    filename = f"anomalies_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False)
    print(f" Anomalies saved to: {filename}")
    print(f" Total anomalies detected: {len(anomalies_list)}")


def process_mqtt_data_with_config(config_data, smart_service_id="SA2", module_id="UNKNOWN"):
    """
    Process MQTT data for anomaly detection with provided configuration dictionary.
    This function is designed to be called concurrently for multiple requests.
    Uses environment variables for MQTT/Kafka configuration.

    :param config_data: List of component dictionaries (from ComponentData model)
    :param smart_service_id: Smart Service ID for Kafka events (default: "SA2")
    :param module_id: Module ID for Kafka events (default: "UNKNOWN")
    :return: Dictionary with status and results
    """
    logger.info(f" Starting MQTT Anomaly Detection with dictionary configuration...")
    logger.info(f" Smart Service: {smart_service_id}, Module: {module_id}")

    # Load configuration from dictionary
    threshold_map_local = load_configuration_from_dict(config_data)
    if threshold_map_local is None:
        logger.error("Failed to load configuration from dictionary")
        return {"status": "error", "message": "Failed to load configuration"}

    # Initialize Kafka Producer for this instance
    kafka_producer_local = None
    try:
        logger.info(f" Initializing Kafka producer ({KAFKA_BOOTSTRAP_SERVERS})...")
        kafka_producer_local = EventsProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        logger.info(" Kafka producer initialized successfully!")
    except Exception as e:
        logger.warning(f"  Warning: Could not initialize Kafka producer: {e}")
        logger.warning("  Continuing without Kafka integration...")

    # Local data storage for this instance
    anomalies_local = []
    data_buffer_local = []

    def on_connect_local(client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        if rc == 0:
            logger.info(" Connected to MQTT broker successfully!")
            for topic in MQTT_TOPICS:
                client.subscribe(topic)
                logger.info(f" Subscribed to: {topic}")
        else:
            logger.error(f" Failed to connect to MQTT broker. Return code: {rc}")

    def on_message_local(client, userdata, msg):
        """Callback when MQTT message is received."""
        try:
            topic = msg.topic
            timestamp = datetime.now(timezone.utc).isoformat()

            # Parse the payload (assuming JSON format)
            payload = json.loads(msg.payload.decode())
            value = payload.get('value')

            # Parse topic to get component and property
            component, prop_name = parse_mqtt_topic(topic)

            if component and prop_name and value is not None:
                # Store in buffer for potential analysis
                data_buffer_local.append({
                    'timestamp': timestamp,
                    'component': component,
                    'property': prop_name,
                    'value': value,
                    'topic': topic
                })

                # Keep buffer size manageable (last 10000 points)
                if len(data_buffer_local) > 10000:
                    data_buffer_local.pop(0)

                # Check for anomaly using local threshold map and Kafka producer
                anomaly_result = check_anomaly(
                    component, prop_name, value, timestamp,
                    threshold_map_local, kafka_producer_local,
                    smart_service_id, module_id
                )
                if anomaly_result:
                    anomalies_local.append(anomaly_result)

        except Exception as e:
            logger.error(f"  Error processing message: {e}")

    # Set up MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect_local
    client.on_message = on_message_local

    # Set authentication
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        logger.info(f" Using authentication with username: {MQTT_USERNAME}")

    try:
        # Connect to broker
        logger.info(f" Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, int(MQTT_PORT), 60)

        # Start the loop
        logger.info(" Listening for MQTT messages... (Press Ctrl+C to stop)")
        client.loop_forever()

    except KeyboardInterrupt:
        logger.info("\n\n  Stopping MQTT client...")
        client.disconnect()

        # Close Kafka producer
        if kafka_producer_local:
            kafka_producer_local.close()
            logger.info(" Kafka producer closed.")

        logger.info(f" Disconnected. Total anomalies detected: {len(anomalies_local)}")
        return {"status": "success", "anomalies_count": len(anomalies_local), "anomalies": anomalies_local}

    except Exception as e:
        logger.error(f" Error: {e}")
        if kafka_producer_local:
            kafka_producer_local.close()
        return {"status": "error", "message": str(e)}


def main():
    """Main function to run MQTT anomaly detection with Kafka integration."""
    global kafka_producer

    print(" Starting MQTT Anomaly Detection System with Kafka Integration...")

    # Load configuration
    if not load_configuration(CONFIG_FILE):
        return

    # Initialize Kafka Producer
    try:
        print(f" Initializing Kafka producer ({KAFKA_BOOTSTRAP_SERVERS})...")
        kafka_producer = EventsProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        print(" Kafka producer initialized successfully!")
    except Exception as e:
        print(f"  Warning: Could not initialize Kafka producer: {e}")
        print("  Continuing without Kafka integration...")

    # Set up MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    # Set authentication
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        print(f" Using authentication with username: {MQTT_USERNAME}")

    try:
        # Connect to broker
        print(f" Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        # Start the loop
        print(" Listening for MQTT messages... (Press Ctrl+C to stop)")
        client.loop_forever()

    except KeyboardInterrupt:
        print("\n\n  Stopping MQTT client...")
        save_anomalies_report()
        client.disconnect()

        # Close Kafka producer
        if kafka_producer:
            kafka_producer.close()
            print(" Kafka producer closed.")

        print(f" Disconnected. Total anomalies detected: {len(anomalies_list)}")

    except Exception as e:
        print(f" Error: {e}")
        if kafka_producer:
            kafka_producer.close()

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
# Test MQTT connection (exposed for main.py health check)
def test_mqtt_connection():
    """
    Test connection to MQTT broker.

    :return: True if connection successful, False otherwise
    """
    try:
        logger.info(f"Testing MQTT connection to {MQTT_BROKER}:{MQTT_PORT}...")

        # Create test client
        test_client = mqtt.Client()

        # Set authentication if provided
        if MQTT_USERNAME and MQTT_PASSWORD:
            test_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # Flag to track connection result
        connection_successful = False

        def on_connect_test(client, userdata, flags, rc):
            nonlocal connection_successful
            if rc == 0:
                connection_successful = True
                logger.info("✓ MQTT connection test successful")
            else:
                logger.error(f"✗ MQTT connection test failed with code: {rc}")

        test_client.on_connect = on_connect_test

        # Try to connect with timeout
        test_client.connect(MQTT_BROKER, int(MQTT_PORT), 60)
        test_client.loop_start()

        # Wait for connection attempt (max 5 seconds)
        import time
        timeout = 5
        start_time = time.time()
        while not connection_successful and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        # Cleanup
        test_client.loop_stop()
        test_client.disconnect()

        return connection_successful

    except Exception as e:
        logger.error(f"MQTT connection test error: {e}")
        return False


# if __name__ == "__main__":
#     main()

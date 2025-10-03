import paho.mqtt.client as mqtt
import json
from datetime import datetime, timezone
import pandas as pd
from EventsProducer import EventsProducer

# --- MQTT Configuration ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USERNAME = ""
MQTT_PASSWORD = ""

# --- Kafka Configuration ---
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"  # Update with your Kafka broker address
KAFKA_TOPIC = "modapto-anomaly-alerts"

# --- Configuration ---
CONFIG_FILE = "components_list_redg05.json"

# Threshold map and anomaly storage
threshold_map = {}
anomalies_list = []
data_buffer = []  # Store recent data

# MQTT topics - subscribe to all with wildcard
MQTT_TOPICS = [
    "Ligne_reducteur_REDG_CELL_05/+/+/+/FLOAT/+",
]

# Initialize Kafka Producer
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
        sub_element = item.get("subElement")
        
        for prop in item.get("Property", []):
            prop_name = prop.get("Name")
            low_thre = prop.get("Low_thre")
            high_thre = prop.get("High_thre")

            if all([component, prop_name, low_thre is not None, high_thre is not None]):
                # Create key that matches MQTT topic structure
                key = f"{component}|{prop_name}"
                threshold_map[key] = {
                    "low": float(low_thre), 
                    "high": float(high_thre),
                    "component": component,
                    "property": prop_name,
                    "module": module,
                    "subElement": sub_element
                }

    print(f" Configuration loaded. {len(threshold_map)} variables configured.")
    return True


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


def send_kafka_alert(anomaly_info):
    """
    Send anomaly alert to Kafka topic using EventsProducer.
    
    :param anomaly_info: Dictionary containing anomaly details
    """
    global kafka_producer
    
    if not kafka_producer:
        print("  Kafka producer not initialized. Skipping Kafka alert.")
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
            "module": anomaly_info.get('module', 'UNKNOWN'),
            "pilot": "sew",
            "priority": priority,
            "description": f"Anomaly detected: {anomaly_info['component']}.{anomaly_info['property']} = {anomaly_info['value']:.2f} (Expected range: [{anomaly_info['low']:.2f}, {anomaly_info['high']:.2f}])",
            "timestamp": anomaly_info['timestamp'],
            "topic": KAFKA_TOPIC,
            "eventType": "ANOMALY_DETECTION",
            "smartService": "SA2",
            "metadata": {
                "component": anomaly_info['component'],
                "property": anomaly_info['property'],
                "value": anomaly_info['value'],
                "low_threshold": anomaly_info['low'],
                "high_threshold": anomaly_info['high'],
                "deviation_percentage": round(deviation_pct, 2)
            }
        }
        
        # Send to Kafka
        kafka_producer.produce_event(KAFKA_TOPIC, event_data)
        print(f" Kafka alert sent for {anomaly_info['component']}.{anomaly_info['property']}")
        
    except Exception as e:
        print(f"  Error sending Kafka alert: {e}")


def check_anomaly(component, prop_name, value, timestamp):
    """Check if value is an anomaly and log it."""
    key = f"{component}|{prop_name}"
    limits = threshold_map.get(key)
    
    if limits and isinstance(value, (int, float)):
        # Filter out system status codes
        if value >= 16000:
            return False
        
        # Filter out idle/zero values
        if value == 0:
            return False
            
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
                'subElement': limits.get('subElement', 'N/A'),
                'expected_value': (limits['low'] + limits['high']) / 2  # Middle of range
            }
            anomalies_list.append(anomaly_info)
            
            # Print alert to console
            print("=" * 60)
            print(f" ANOMALY DETECTED at {timestamp} ")
            print(f"   Component: {component}")
            print(f"   Property: {prop_name}")
            print(f"   Value: {value:.2f}")
            print(f"   Range: [{limits['low']:.2f}, {limits['high']:.2f}]")
            print("=" * 60)
            
            # Send to Kafka
            send_kafka_alert(anomaly_info)
            
            return True
    return False


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
        print(f"🔌 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
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


if __name__ == "__main__":
    main()

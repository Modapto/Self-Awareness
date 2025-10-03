import paho.mqtt.client as mqtt
import json
from datetime import datetime
import pandas as pd

# --- Configuration ---
CONFIG_FILE = "components_list_redg05.json"
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USERNAME = "sew"
MQTT_PASSWORD = "sewmodapto!"

# Threshold map and anomaly storage
threshold_map = {}
anomalies_list = []
data_buffer = []  # Store recent data for visualization

# MQTT topics based on your data
MQTT_TOPICS = [
    "Ligne_reducteur_REDG_CELL_05/+/+/+/FLOAT/+",  # Subscribe to all with wildcard
]


def load_configuration(file_path):
    """Load the JSON configuration and create threshold map."""
    print(f"⚙️  Loading configuration from {file_path}...")
    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)
    except Exception as e:
        print(f"❌ ERROR loading configuration: {e}")
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
                    "property": prop_name
                }

    print(f"✅ Configuration loaded. {len(threshold_map)} variables configured.")
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
                'high': limits['high']
            }
            anomalies_list.append(anomaly_info)

            # Print alert
            print("=" * 60)
            print(f"🚨 ANOMALY DETECTED at {timestamp} 🚨")
            print(f"   Component: {component}")
            print(f"   Property: {prop_name}")
            print(f"   Value: {value:.2f}")
            print(f"   Range: [{limits['low']:.2f}, {limits['high']:.2f}]")
            print("=" * 60)
            return True
    return False


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker."""
    if rc == 0:
        print("✅ Connected to MQTT broker successfully!")
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
            print(f"📡 Subscribed to: {topic}")
    else:
        print(f"❌ Failed to connect to MQTT broker. Return code: {rc}")


def on_message(client, userdata, msg):
    """Callback when MQTT message is received."""
    try:
        topic = msg.topic
        timestamp = datetime.now().isoformat()

        # Parse the payload (assuming JSON format)
        payload = json.loads(msg.payload.decode())
        value = payload.get('value')

        # Parse topic to get component and property
        component, prop_name = parse_mqtt_topic(topic)

        if component and prop_name and value is not None:
            # Store in buffer for visualization
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
        print(f"⚠️  Error processing message: {e}")


def save_anomalies_report():
    """Save anomalies to CSV."""
    if not anomalies_list:
        print("No anomalies to report.")
        return

    # Save to CSV
    df = pd.DataFrame(anomalies_list)
    filename = f"anomalies_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False)
    print(f"📄 Anomalies saved to: {filename}")
    print(f"📊 Total anomalies detected: {len(anomalies_list)}")


def main():
    """Main function to run MQTT anomaly detection."""
    print("🚀 Starting MQTT Anomaly Detection System...")

    # Load configuration
    if not load_configuration(CONFIG_FILE):
        return

    # Set up MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    # Set authentication if needed
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        print(f"🔐 Using authentication with username: {MQTT_USERNAME}")

    try:
        # Connect to broker
        print(f"🔌 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        # Start the loop
        print("👂 Listening for MQTT messages... (Press Ctrl+C to stop)")
        client.loop_forever()

    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping MQTT client...")
        save_anomalies_report()
        client.disconnect()
        print(f"✅ Disconnected. Total anomalies detected: {len(anomalies_list)}")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
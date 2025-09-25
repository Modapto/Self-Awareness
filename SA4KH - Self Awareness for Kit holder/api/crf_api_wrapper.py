import pandas as pd
from datetime import datetime, timezone
import tempfile
import os
from core.wear_monitor import process_events
from api.EventsProducer import EventsProducer
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

class CRFApiWrapper:

    def __init__(self, kafka_server="kafka.modapto.atc.gr:9092"):
        """Initialize the API wrapper with Kafka connection"""
        self.events_producer = EventsProducer(kafka_server)
        self.topic = 'self-awareness-wear-detection'

    def process_request(self, json_input):
        """
        Process JSON input and return results

        Args:
            json_input (dict): JSON input from MODAPTO system
                Expected format:
                {
                    "parameters": {
                        "threshold": 16.0,
                        "interval_minutes": 5,
                        "model_path": "quadratic_model.json"
                    },
                    "data": [
                        {"Header byte (0xfe)": "0xfe", "Saw Event Type": 1, "RFID Station ID": 6, ...},
                        ...
                    ]
                }

        Returns:
            dict: Results in JSON format
        """
        try:
            params = json_input.get('parameters', {})
            threshold = params.get('threshold', 16.0)
            interval_minutes = params.get('interval_minutes', 5)
            model_path = params.get('model_path', 'quadratic_model.json')
            # Ensure model path is always in data/models directory
            if not model_path.startswith('data/models/'):
                model_path = f'data/models/{model_path}'
            module = params.get('moduleId', 'xxx')
            smart_service = params.get('smartServiceId', 'xxx')

            logger.info(f"Processing CRF wear monitoring request")
            logger.info(f"Parameters: threshold={threshold}, interval_minutes={interval_minutes}, model_path={model_path}")
            logger.info(f"Module: {module}, SmartService: {smart_service}")
            logger.info(f"Input data events count: {len(json_input.get('data', []))}")

            if not os.path.exists(model_path):
                logger.error(f"Model file not found: {model_path}")
                return {"error": f"Model file not found: {model_path}"}

            # Convert JSON data to CSV
            temp_csv = None
            if 'data' in json_input and json_input['data']:
                temp_csv = self._json_to_csv(json_input['data'])

            if not temp_csv:
                logger.error("No valid input data provided for processing")
                return {"error": "No valid input data provided"}

            logger.info(f"Processing events with wear_monitor algorithm")
            try:
                # Process events using wear_monitor
                results = process_events(
                    temp_csv,
                    model_path,
                    threshold,
                    interval_minutes
                )
                logger.info(f"Wear monitor algorithm completed successfully")
            except Exception as e:
                logger.error(f"Error in wear_monitor algorithm: {str(e)}")
                logger.exception("Full traceback:")
                return {"error": f"Wear monitor algorithm failed: {str(e)}"}

            notifications = self._create_notifications(results, json_input['data'])

            logger.info(f"Processing results: {len(notifications)} notifications generated")
            logger.debug(f"Notifications: {notifications}")

            if notifications:
                logger.info(f"Writing {len(notifications)} notifications to file")
                self._write_notifications_file(notifications)

            # Publish wear alert events only when thresholds are exceeded
            logger.info("Publishing wear monitoring event to Kafka")
            self._publish_wear_notifications(notifications, module, smart_service)

            # Clean up temporary file
            if os.path.exists(temp_csv):
                os.remove(temp_csv)

            # No JSON response - only Kafka events and notifications file
            return None

        except Exception as e:
            return {
                "error": f"Error processing request: {str(e)}"
            }

    def _json_to_csv(self, json_data):
        try:
            df = pd.DataFrame(json_data)

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            temp_file_path = temp_file.name
            temp_file.close()

            df.to_csv(temp_file_path, sep=';', index=False)

            print(f"Converted JSON data to CSV: {temp_file_path}")
            return temp_file_path

        except Exception as e:
            print(f"Error converting JSON to CSV: {str(e)}")
            return None

    def _create_notifications(self, results, original_data):
        """Create notifications in the same format as input data for exceeded thresholds"""

        notifications = []

        logger.info(f"Creating notifications from algorithm results")
        logger.debug(f"Algorithm results: {results}")
        logger.info(f"Results contain {len(results.get('windows', []))} windows")

        # Find windows where threshold was exceeded
        threshold_exceeded_count = 0
        for i, window in enumerate(results.get('windows', [])):
            exceeds_threshold = window.get('force', {}).get('exceeds_threshold', False)
            logger.debug(f"Window {i}: exceeds_threshold = {exceeds_threshold}")

            if exceeds_threshold:
                threshold_exceeded_count += 1
                # Find corresponding original data entries for this time window
                # We'll use the insertions indices to map back to original data
                first_idx = window['insertions']['first_index']
                last_idx = window['insertions']['last_index']

                # For now, we'll create one notification entry per exceeded window
                # using the first insertion data from that window
                if first_idx < len(original_data):
                    base_data = original_data[first_idx].copy()

                    # Remove Header byte field if present
                    header_keys = [key for key in base_data.keys() if 'Header byte' in key]
                    for key in header_keys:
                        del base_data[key]

                    # Modify the issue type to indicate wear notification (0x01)
                    # Find the issue type column (could be different names)
                    issue_type_keys = [key for key in base_data.keys() if
                                       'Issue type' in key or 'Event Type' in key or 'Saw Event Type' in key]
                    if issue_type_keys:
                        base_data[issue_type_keys[0]] = 1  # Set to notification type

                    # Convert Unix timestamp to readable datetime
                    timestamp_keys = [key for key in base_data.keys() if
                                      'Timestamp' in key or 'timestamp' in key.lower()]
                    for ts_key in timestamp_keys:
                        try:
                            # Convert Unix timestamp to readable format
                            unix_timestamp = int(base_data[ts_key])
                            readable_datetime = datetime.fromtimestamp(unix_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                            base_data[ts_key] = readable_datetime
                        except (ValueError, TypeError):
                            pass

                    notifications.append(base_data)

        logger.info(f"Found {threshold_exceeded_count} windows exceeding threshold")
        logger.info(f"Created {len(notifications)} notifications")
        return notifications

    def _write_notifications_file(self, notifications, filename="notifications.csv"):
        if not notifications:
            return

        try:
            df = pd.DataFrame(notifications)
            file_exists = os.path.exists(filename)
            mode = 'a' if file_exists else 'w'
            header = not file_exists

            df.to_csv(filename, sep='\t', index=False, mode=mode, header=header)
            print(f"{'Appended' if file_exists else 'Created'} {len(notifications)} notifications to {filename}")

        except Exception as e:
            print(f"Error writing notifications file: {str(e)}")

    def _publish_wear_notifications(self, notifications, module, smart_service):

        logger.info(f"Publishing wear notifications - count: {len(notifications) if notifications else 0}")
        logger.debug(f"Notifications to publish: {notifications}")

        if not notifications:
            logger.info("No notifications found - normal operation, no Kafka events sent")
            return
        else:
            logger.info(f"Publishing {len(notifications)} wear alert notifications")
            for i, notification in enumerate(notifications, 1):
                try:
                    event_data = {
                        "description": f"Tool wear threshold exceeded in station {notification.get('RFID Station ID')}. Immediate attention required.",
                        "module": module,
                        "pilot": "CRF",
                        "eventType": "Tool Wear Exceeded Threshold Alert",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        "topic": self.topic,
                        "smartService": smart_service,
                        "results": notification
                    }

                    logger.info(f"Publishing wear alert {i}/{len(notifications)} to topic: {self.topic}")
                    logger.debug(f"Alert event data: {event_data}")
                    self.events_producer.produce_event(self.topic, event_data)
                    logger.info(f"Wear alert {i}/{len(notifications)} published successfully")

                except Exception as e:
                    logger.error(f"Failed to publish wear alert {i}/{len(notifications)}: {str(e)}")

            logger.info(f"Completed publishing {len(notifications)} wear notification events")

    def close(self):
        if hasattr(self, 'events_producer'):
            self.events_producer.close()
from time import timezone
import pandas as pd
from datetime import datetime
import tempfile
import os
from core.wear_monitor import process_events
from EventsProducer import EventsProducer


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
            module = params.get('moduleId', 'xxx')
            smart_service = params.get('smartServiceId', 'xxx')

            # Convert JSON data to CSV
            temp_csv = None
            if 'data' in json_input and json_input['data']:
                temp_csv = self._json_to_csv(json_input['data'])

            if not temp_csv:
                return {"error": "No valid input data provided"}

            # Process events using wear_monitor
            results = process_events(
                temp_csv,
                model_path,
                threshold,
                interval_minutes
            )

            notifications = self._create_notifications(results, json_input['data'])

            if notifications:
                self._write_notifications_file(notifications)
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

        # Find windows where threshold was exceeded
        for window in results.get('windows', []):
            if window['force']['exceeds_threshold']:
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

        if not notifications:
            try:
                # Create event data with same structure as JSON output
                event_data = {
                    "description": f"No tool wear threshold exceeded. System is operating normally.",
                    "module": module,
                    "pilot": "CRF",
                    "topic": self.topic,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                    "eventType": "Tool Wear Monitoring Normal Operation",
                    "priority": "LOW",
                    "smartService": smart_service,
                    "results": None
                }

                self.events_producer.produce_event(self.topic, event_data)
                print(f"Event of normal operation published")

            except Exception as e:
                print(f"Failed to publish event: {str(e)}")
        else:
            for notification in notifications:
                try:
                    # Create event data with same structure as JSON output
                    event_data = {
                        "description": f"Tool wear threshold exceeded in station {notification.get('RFID Station ID')}. Immediate attention required.",
                        "module": module,
                        "pilot": "CRF",
                        "eventType": "Tool Wear Exceeded Threshold Alert",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        "priority": "HIGH",
                        "topic": self.topic,
                        "smartService": smart_service,
                        "results": notification
                    }

                    self.events_producer.produce_event(self.topic, event_data)
                    print(f"Published wear notification event")

                except Exception as e:
                    print(f"Failed to publish event: {str(e)}")

            print(f"Published {len(notifications)} wear notification events")

    def close(self):
        if hasattr(self, 'events_producer'):
            self.events_producer.close()
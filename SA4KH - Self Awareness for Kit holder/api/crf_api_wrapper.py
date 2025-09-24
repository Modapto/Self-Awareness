import pandas as pd
import tempfile
import os
from core.wear_monitor import process_events
from EventsProducer import EventsProducer


class CRFApiWrapper:
    """API wrapper """

    def __init__(self, kafka_server="kafka.modapto.atc.gr:9092"):
        """Initialize the API wrapper with Kafka connection"""
        self.events_producer = EventsProducer(kafka_server)
        self.topic = 'self-awareness-diagnosis'  # Default topic

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
            # Extract parameters
            params = json_input.get('parameters', {})
            threshold = params.get('threshold', 16.0)
            interval_minutes = params.get('interval_minutes', 5)
            model_path = params.get('model_path', 'quadratic_model.json')
            module = params.get('module', 'CRF-ILTAR')

            # Convert JSON data to temporary CSV
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

            # Send notifications for threshold exceeded events
            self._publish_wear_notifications(results, module)

            # Clean up temporary file
            if os.path.exists(temp_csv):
                os.remove(temp_csv)

            # Return the results as JSON
            return results

        except Exception as e:
            return {
                "error": f"Error processing request: {str(e)}"
            }

    def _json_to_csv(self, json_data):
        """Convert JSON array to CSV file"""
        try:
            df = pd.DataFrame(json_data)

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            temp_file_path = temp_file.name
            temp_file.close()

            # Write to CSV with semicolon separator
            df.to_csv(temp_file_path, sep=';', index=False)

            print(f"Converted JSON data to CSV: {temp_file_path}")
            return temp_file_path

        except Exception as e:
            print(f"Error converting JSON to CSV: {str(e)}")
            return None

    def _publish_wear_notifications(self, results, module):
        """Publish wear notifications using EventsProducer"""
        # Find windows where threshold was exceeded
        exceeded_count = 0
        for window in results.get('windows', []):
            if window['force']['exceeds_threshold']:
                # Determine priority based on how much threshold is exceeded
                force_ratio = window['force']['predicted'] / results['metadata']['threshold']
                priority = "HIGH" if force_ratio > 1.5 else "MEDIUM" if force_ratio > 1.2 else "LOW"

                # Create event data
                event_data = {
                    "description": f"Tool wear threshold exceeded. Force: {window['force']['predicted']:.2f}",
                    "module": module,
                    "priority": priority,
                    "eventType": "Tool Wear Alert",
                    "pilot": "ILTAR-CRF",
                    "timestamp": window['time_window'],
                    "topic": self.topic,
                    "smartService": "Self-Awareness",
                    "results": {
                        "time_window": window['time_window'],
                        "force": window['force']['predicted'],
                        "threshold": results['metadata']['threshold'],
                        "kh_info": window.get('kh', {})
                    }
                }

                try:
                    # Publish event
                    self.events_producer.produce_event(self.topic, event_data)
                    exceeded_count += 1
                    print(f"Published wear notification event for window {window['time_window']}")
                except Exception as e:
                    print(f"Failed to publish event: {str(e)}")

        print(f"Published {exceeded_count} wear notification events")

    def close(self):
        """Close the events producer"""
        if hasattr(self, 'events_producer'):
            self.events_producer.close()
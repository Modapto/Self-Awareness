import json
from kafka import KafkaProducer
from datetime import datetime

class EventsProducer:
    def __init__(self, bootstrap_servers):
        """
        Initialize Kafka Producer with bootstrap servers
        
        :param bootstrap_servers: List of Kafka broker addresses (comma-separated)
        """
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id='self-awareness-producer',
            value_serializer=lambda v: json.dumps(v).encode('utf-8') # Serialize JSON
        )

    def validate_event_data(self, event_data):
        """
        Validate event data against the required schema
        
        :param event_data: Dictionary containing event details
        :raises ValueError: If required fields are missing or invalid
        """
        required_fields = ['productionModule', 'pilot', 'priority', 'description', 'timestamp', 'topic', 'eventType']
        
        # Check required fields
        for field in required_fields:
            if field not in event_data or not event_data[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate priority
        if event_data.get('priority') not in ['LOW', 'MEDIUM', 'HIGH']:
            raise ValueError("Invalid priority. Must be LOW, MEDIUM, or HIGH")
        
        return event_data

    def produce_event(self, topic, event_data):
        """
        Produce a Kafka event to the specified topic
        
        :param topic: Kafka topic to send the event to
        :param event_data: Dictionary containing event details
        """

        # Add timestamp if not provided
        if 'timestamp' not in event_data:
            event_data['timestamp'] = datetime.utcnow().isoformat()

         # Make some fields uppercase
        if 'priority' in event_data:
            event_data['priority'] = event_data['priority'].upper()

        if 'pilot' in event_data:
            event_data['pilot'] = event_data['pilot'].upper()
        
        # Validate event data
        validated_event = self.validate_event_data(event_data)

       
        
        # Convert to JSON string
        event_json = json.dumps(validated_event)
        
        try:
            # Produce message to Kafka topic
            self.producer.send(
                topic,
                event_json
            )
            
            # Flush to ensure message is sent
            self.producer.flush()
            
            return
        
        except Exception as e:
            raise RuntimeError(f"Failed to produce event: {str(e)}")

    def close(self):
        """
        Close the Kafka producer
        """
        if self.producer:
            self.producer.flush()
            self.producer.close()
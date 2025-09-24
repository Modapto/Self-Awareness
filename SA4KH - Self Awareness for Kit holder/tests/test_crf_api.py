import json
from api.crf_api_wrapper import CRFApiWrapper

base_timestamp = 1743258259
test_data = []

for i in range(72000):  # 72000 cycles (128000 total events : corresponds to 30 days of continuous operation)
    # Add insertion event
    test_data.append({
        "Header byte (0xfe)": "0xfe",
        "Saw Event Type": 1,  # 1 for insertion
        "RFID Station ID": 6,
        "Timestamp 8bytes": base_timestamp + (i * 20),  # Each cycle takes 20 seconds total
        "KH Type": 2,
        "KH Unique ID": 123456
    })

    # Add extraction event (10 seconds after insertion)
    test_data.append({
        "Header byte (0xfe)": "0xfe",
        "Saw Event Type": 2,  # 2 for extraction
        "RFID Station ID": 6,
        "Timestamp 8bytes": base_timestamp + (i * 20) + 10,  # 10 seconds after insertion
        "KH Type": 2,
        "KH Unique ID": 123456
    })

test_input = {
    "parameters": {
        "threshold": 16.0,  # threshold to trigger notification
        "interval_minutes": 5,
        "model_path": "quadratic_model.json",
        "module": "CRF-ILTAR"
    },
    "data": test_data
}


def main():
    """Test the CRF API wrapper notification functionality"""
    # Initialize API wrapper with a Kafka server
    api = CRFApiWrapper("localhost:9092")

    try:
        result = api.process_request(test_input)
        print(f"Total windows: {len(result['windows'])}")
        exceeded_count = sum(1 for window in result['windows'] if window['force']['exceeds_threshold'])
        print(f"Windows exceeding threshold: {exceeded_count}")

        if exceeded_count > 0:
            print("\nExample window with exceeded threshold:")
            for window in result['windows']:
                if window['force']['exceeds_threshold']:
                    print(json.dumps(window, indent=2))
                    break
    finally:
        api.close()


if __name__ == "__main__":
    main()
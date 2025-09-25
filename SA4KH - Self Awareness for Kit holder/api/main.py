import json
import sys
import argparse
from api.crf_api_wrapper import CRFApiWrapper

def main():
    """
    Main entry point for CRF API
    Reads JSON from stdin and writes JSON to stdout
    """
    parser = argparse.ArgumentParser(description='CRF Wear Monitoring API')
    parser.add_argument('--kafka-server', default='kafka:9092',
                        help='Kafka server address (default: kafka:9092)')
    parser.add_argument('--input', '-i', type=argparse.FileType('r'), default=sys.stdin,
                        help='Input JSON file (default: stdin)')
    parser.add_argument('--output', '-o', type=argparse.FileType('w'), default=sys.stdout,
                        help='Output JSON file (default: stdout)')

    args = parser.parse_args()

    try:
        # Read input JSON
        input_json = json.load(args.input)

        # Initialize API wrapper
        api = CRFApiWrapper(args.kafka_server)

        try:
            # Process request
            result = api.process_request(input_json)

            # Write output JSON
            json.dump(result, args.output, indent=2)

        finally:
            api.close()

            if args.input is not sys.stdin:
                args.input.close()
            if args.output is not sys.stdout:
                args.output.close()

    except Exception as e:
        error_result = {
            "error": str(e)
        }
        json.dump(error_result, args.output, indent=2)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any
from datetime import datetime
from fastapi.openapi.utils import get_openapi
from api.EventsProducer import EventsProducer
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import base64
import json
import logging
import sys

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Configure logging
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log") if os.path.exists("/app") else logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Import algorithm
from api.crf_api_wrapper import CRFApiWrapper

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up FastAPI application...")
    app.state.executor = ThreadPoolExecutor(max_workers=5)
    logger.info("Application startup complete")
    yield
    # Shutdown
    logger.info("Shutting down FastAPI application...")
    app.state.executor.shutdown()
    logger.info("Application shutdown complete")

app = FastAPI(
    title="Self Awareness Wear-Monitoring API",
    description="Real-time monitoring of Kit-Holder wear of CRF modules",
    version="1.0.0",
    lifespan=lifespan
)

# Set the origins for CORS
def get_cors_origins():
    origins_string = os.getenv("CORS_DOMAINS", "http://localhost:8094") # Default DTM URL
    origins = origins_string.split(",")
    return [origin.strip() for origin in origins if origin.strip()]

# Custom OpenAPI schema to include server URL
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    server_url = os.getenv("SWAGGER_SERVER_URL", "http://localhost:8000")
    openapi_schema["servers"] = [{"url": server_url}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log basic request info
    logger.info(f"=== INCOMING HTTP REQUEST ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    # Log raw request body for POST requests to our endpoints
    if request.method == "POST" and any(path in str(request.url) for path in ["/monitor/kpis"]):
        body = await request.body()
        logger.info(f"Raw request body length: {len(body)}")
        logger.info(f"Raw request body (first 500 chars): {body[:500].decode('utf-8', errors='ignore')}")
        
        # FastAPI consumes the request body, so we need to set it back for the actual handler
        async def receive():
            return {"type": "http.request", "body": body}
        
        request._receive = receive
    
    response = await call_next(request)
    logger.info(f"Response status code: {response.status_code}")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def encode_output_to_base64(output: Dict[str, Any]) -> str:
    """
    Encode a dictionary to a Base64 string.
    """
    json_bytes = json.dumps(output, default=str).encode("utf-8")
    return base64.b64encode(json_bytes).decode("utf-8")

def decode_base64_to_dict(base64_string: str) -> Dict[str, Any]:
    """
    Decode a Base64 string to a dictionary.
    """
    try:
        json_bytes = base64.b64decode(base64_string.encode("utf-8"))
        return json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Error decoding Base64 string: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid Base64 encoded request: {str(e)}")

class Base64Request(BaseModel):
    """Unified input model for Base64 encoded requests"""
    request: str = Field(..., description="Base64 encoded JSON request data")

class ResponseMessage(BaseModel):
    """Unified response model for initiation confirmation"""
    message: str = Field(..., description="Success message")    
    
# ---- Input Models ----
class Parameters(BaseModel):
    threshold: float = Field(..., description="Property name")
    intervalMinutes: int = Field(..., description="Lower threshold value for property")
    modelPath: str = Field(..., description="Path to the trained model file")
    moduleId: str = Field(..., description="Module ID")
    smartServiceId: str = Field(..., description="Smart Service ID")

    model_config = {"populate_by_name": True}
    
class EventData(BaseModel):
    eventType: int = Field(..., description="Saw Event Type", alias="Saw Event Type (1 Insertion - 2 Extraction)")
    rfidStation: int = Field(..., description="RFID Station ID", alias="RFID Station ID [1..9]")
    timestamp: int = Field(..., description="Timestamp of the event", alias="Timestamp 8bytes")  # Changed from datetime to int
    khType: int = Field(..., description="Kit Holder Type", alias="KH Type [1..3]")
    khId: int = Field(..., description="Kit Holder ID", alias="KH Unique ID [1..5]")

    model_config = {"populate_by_name": True}

    def to_algorithm_format(self) -> dict:
        """Convert EventData to algorithm expected format with proper field names"""
        timestamp_unix = int(self.timestamp.timestamp()) if isinstance(self.timestamp, datetime) else self.timestamp

        return {
            "Saw Event Type": self.eventType,
            "RFID Station ID": self.rfidStation,
            "Timestamp": timestamp_unix,
            "KH Type": self.khType,
            "KH ID": self.khId
        }
    
class SelfAwarenessWearInput(BaseModel):
    parameters: Parameters = Field(..., description="Parameters of execution")
    data: List[EventData] = Field(..., description="Event data from Kit Holder modules")

    model_config = {"populate_by_name": True}
    
# --- Utility Functions ---
# Async function to process wear monitoring using CRF API wrapper
async def process_self_awareness_wear_monitoring(data: SelfAwarenessWearInput):
    """
    Process wear monitoring request asynchronously using CRF API wrapper.
    """
    try:
        logger.info("Starting wear monitoring processing")

        # Transform EventData objects to algorithm expected format
        transformed_data = [event.to_algorithm_format() for event in data.data]

        # Log transformed data structure for debugging
        if transformed_data:
            logger.info(f"First transformed event keys: {list(transformed_data[0].keys())}")
            logger.debug(f"First transformed event data: {transformed_data[0]}")

        # Create input for CRF API wrapper in expected format
        crf_input = {
            "parameters": {
                "threshold": data.parameters.threshold,
                "interval_minutes": data.parameters.intervalMinutes,
                "model_path": data.parameters.modelPath,
                "moduleId": data.parameters.moduleId,
                "smartServiceId": data.parameters.smartServiceId
            },
            "data": transformed_data
        }

        logger.info(f"CRF input prepared with {len(transformed_data)} events")

        # Initialize CRF API wrapper and process request in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,  # Use default thread pool
            partial(
                process_crf_request_sync,
                crf_input,
                KAFKA_BOOTSTRAP_SERVERS
            )
        )

        logger.info("CRF wear monitoring processing completed")

        if result and "error" in result:
            logger.error(f"CRF processing error: {result['error']}")
        else:
            logger.info("CRF wear monitoring processed successfully - notifications published to Kafka")

    except Exception as e:
        logger.error(f"Critical error in wear monitoring processing: {str(e)}")

        # Publish critical error event
        try:
            producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)

            critical_error_event = {
                "description": f"Critical error in CRF Wear Monitoring processing: {str(e)}",
                "module": data.parameters.moduleId if data and data.parameters else "unknown",
                "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "priority": "HIGH",
                "eventType": "Critical Wear Monitoring Error",
                "sourceComponent": "CRF Wear Monitoring",
                "smartService": data.parameters.smartServiceId if data and data.parameters else "unknown",
                "topic": "self-awareness-wear-detection",
                "results": None
            }

            producer.produce_event("self-awareness-wear-detection", critical_error_event)
            producer.close()
            logger.info("Critical error event published to Kafka!")
        except Exception as kafka_error:
            logger.error(f"Failed to publish critical error event to Kafka: {str(kafka_error)}")


def process_crf_request_sync(crf_input: dict, kafka_server: str):
    """
    Synchronous wrapper for CRF API processing to be run in thread pool
    """
    try:
        # Initialize CRF API wrapper
        api_wrapper = CRFApiWrapper(kafka_server)

        try:
            # Process the request
            api_wrapper.process_request(crf_input)
        finally:
            # Always close the API wrapper
            api_wrapper.close()

    except Exception as e:
        logger.error(f"Error in CRF API processing: {str(e)}")
        return {"error": str(e)}
            
# --- API Endpoints ---
@app.post("/monitor/wear", response_model=ResponseMessage, tags=["Self Awareness Wear Monitoring of Kit Holders"])
async def self_awareness_wear_monitoring(base64_data: Base64Request):
    """
    Endpoint to start the self-awareness wear monitoring to locate tool wears that exceed thresholds.
    
    Request format: {"request": "base64_encoded_json_data"}
    """
    # Log raw incoming request FIRST - before any validation
    logger.info("=== RAW CRF SELF-AWARENESS - WEAR MONITORING ===")
    logger.info(f"Request type: {type(base64_data)}")
    logger.info(f"Request attributes: {dir(base64_data)}")
    
    if hasattr(base64_data, 'request'):
        logger.info(f"request.request exists: {base64_data.request is not None}")
        logger.info(f"request.request type: {type(base64_data.request)}")
        logger.info(f"request.request length: {len(base64_data.request) if base64_data.request else 'None'}")
        if base64_data.request:
            logger.info(f"Base64 request preview (first 100 chars): {base64_data.request[:100]}")
    else:
        logger.error("request.request attribute missing!")
    
    # Log the entire raw request object
    try:
        logger.info(f"Raw request object: {base64_data}")
        logger.info(f"Raw request dict: {base64_data.model_dump() if hasattr(base64_data, 'model_dump') else 'No model_dump method'}")
    except Exception as e:
        logger.error(f"Error logging raw request: {str(e)}")
        
    try:
        logger.info("=== STARTING REQUEST PROCESSING ===")
        
        # Validate base64_data.request exists before proceeding
        if not hasattr(base64_data, 'request') or base64_data.request is None:
            logger.error("Request validation failed: base64_data.request is missing or None")
            raise HTTPException(status_code=400, detail="Missing 'request' field in Base64Request")
        
        # Decode Base64 request
        decoded_data = decode_base64_to_dict(base64_data.request)
        logger.info("Successfully decoded Base64 request")
        logger.info(f"Decoded data keys: {list(decoded_data.keys()) if decoded_data else 'None'}")
        logger.debug(f"Decoded data structure: {json.dumps(decoded_data, indent=2, default=str)}")
        
        # Parse decoded data into SelfAwarenessWearInput model
        try:
            logger.info("Attempting to parse decoded data into SelfAwarenessWearInput model")
            data = SelfAwarenessWearInput(**decoded_data)
            logger.info("✓ Successfully parsed request data")
        except Exception as e:
            logger.error("✗ Failed to parse decoded data into model")
            logger.error(f"Validation error details: {str(e)}")
            logger.error(f"Validation error type: {type(e).__name__}")

            # Log specific field validation issues if it's a Pydantic validation error
            if hasattr(e, 'errors'):
                logger.error("Detailed validation errors:")
                for error in e.errors():
                    logger.error(f"  Field: {error.get('loc', 'unknown')}")
                    logger.error(f"  Error: {error.get('msg', 'unknown')}")
                    logger.error(f"  Input: {error.get('input', 'unknown')}")

            raise HTTPException(status_code=422, detail=f"Request validation failed: {str(e)}")
            
        # Start the async algorithm processing
        asyncio.create_task(process_self_awareness_wear_monitoring(data))
        
        logger.info("Successfully initialized self-awareness wear monitoring task")
        
        # Return response of successful initiation
        response_data = {"message": "Self-awareness wear monitoring task started successfully"}
        return ResponseMessage(**response_data)
    
    except HTTPException:
        # Re-raise HTTP exceptions (400, 503)
        raise
    except Exception as e:
        logger.error(f"Error in self-awareness monitoring task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error while initializing the self-awareness monitoring kpis algorithm: {str(e)}")
    
@app.get("/health", tags=["Health Check"])
def health_check():
    """
    Health check endpoint for the CRF Wear Monitoring API.
    Tests CRF API wrapper and core components availability.
    """
    logger.info("Health check requested")

    # Test service connections
    services_status = {}
    overall_status = "healthy"

    try:
        # Test import availability without instantiation
        if hasattr(CRFApiWrapper, '__init__') and callable(CRFApiWrapper):
            services_status["crf_api_wrapper"] = {
                "status": "healthy",
                "import": True,
                "class_available": True
            }
        else:
            services_status["crf_api_wrapper"] = {
                "status": "unhealthy",
                "import": True,
                "class_available": False
            }
            overall_status = "degraded"
    except NameError as e:
        logger.error(f"CRF API wrapper not imported: {e}")
        services_status["crf_api_wrapper"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"
    except Exception as e:
        logger.error(f"Error testing CRF API wrapper: {e}")
        services_status["crf_api_wrapper"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"

    try:
        kafka_server = KAFKA_BOOTSTRAP_SERVERS
        services_status["kafka_config"] = {
            "status": "healthy",
            "server": kafka_server,
            "configured": True
        }
    except Exception as e:
        logger.error(f"Error checking Kafka configuration: {e}")
        services_status["kafka_config"] = {
            "status": "unhealthy",
            "configured": False,
            "error": str(e)
        }
        overall_status = "degraded"

    try:
        test_params = Parameters(
            threshold=16.0,
            intervalMinutes=5,
            modelPath="test.json",
            moduleId="test",
            smartServiceId="test"
        )
        services_status["pydantic_models"] = {
            "status": "healthy",
            "validation": True
        }
    except Exception as e:
        logger.error(f"Error testing Pydantic models: {e}")
        services_status["pydantic_models"] = {
            "status": "unhealthy",
            "validation": False,
            "error": str(e)
        }
        overall_status = "degraded"

    services_status["api"] = {
        "status": "healthy",
        "connection": True
    }

    response = {
        "status": overall_status,
        "services": services_status,
        "message": f"CRF Wear Monitoring API is running - Status: {overall_status}",
        "timestamp": datetime.now().isoformat()
    }

    logger.info(f"Health check completed - Overall status: {overall_status}")
    return response
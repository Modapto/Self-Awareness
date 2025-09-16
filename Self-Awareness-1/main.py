from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any
from datetime import datetime
from fastapi.openapi.utils import get_openapi
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
from SA1 import EventsProducer, async_self_awareness_monitoring_kpis, test_influxdb_connection, test_kafka_connection

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
    title="Self Awareness API",
    description="Real-time monitoring and storing capabilities of KPIs",
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

class Base64Response(BaseModel):
    """Unified response model for Base64 encoded results"""
    response: str = Field(..., description="Base64 encoded JSON result")    
    
# ---- Input Models ----
class PropertyData(BaseModel):
    Name: str = Field(..., description="Property name")
    Low_thre: int = Field(..., description="Lower threshold value for property")
    High_thre: int = Field(..., description="Upper threshold value for property")

    model_config = {"populate_by_name": True}
    
class ComponentData(BaseModel):
    Module: str = Field(..., description="Module name")
    Plc: str = Field(..., description="Module identifier")
    Stage: str = Field(..., description="Stage name")
    Cell: str = Field(..., description="Cell name")
    subElement: str = Field(..., description="SubElement name")
    Component: str = Field(..., description="Component name")
    Property: List[PropertyData] = Field(..., description="List of property data")

    model_config = {"populate_by_name": True}
    
class SelfAwarenessKPIInput(BaseModel):
    components: List[ComponentData] = Field(..., description="List of components with properties and thresholds")
    start_date: datetime = Field(..., description='Analysis period start time in format "DD-MM-YYYY HH:MM:SS"')
    end_date: datetime = Field(..., description='Analysis period end time in format "DD-MM-YYYY HH:MM:SS"')
    smartServiceId: str = Field(..., description="Smart Service ID")
    moduleId: str = Field(..., description="Module ID")

    model_config = {"populate_by_name": True}
    
    @field_validator("start_date", "end_date", mode="before")
    def validate_datetime_format(cls, value):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.strptime(value, "%d-%m-%Y %H:%M:%S")
        except ValueError:
            raise ValueError(
                f"Datetime must be in format 'DD-MM-YYYY HH:MM:SS', got '{value}'"
            )

# ---- Output Models ----


# --- Utility Functions ---
# Async function to process grouping maintenance and publish to Kafka
async def process_self_awareness_monitoring_kpis(
    components: List[ComponentData],
    smart_service: str,
    module: str,
    start_date: datetime,
    end_date: datetime):
    """
    Process grouping maintenance request asynchronously and publish results to Kafka.
    """
    try:
        # Convert ComponentData objects to simple list for the algorithm
        component_list = [component.model_dump() for component in components]
        
        # Log component structure after model_dump for debugging
        if component_list:
            logger.info(f"First component keys after model_dump: {list(component_list[0].keys())}")
            logger.debug(f"First component data: {component_list[0]}")
        
        # Run the CPU-intensive algorithm in thread pool
        loop = asyncio.get_event_loop()
        event_data = await loop.run_in_executor(
            None,  # Use default thread pool
            partial(
                async_self_awareness_monitoring_kpis,
                component_list,
                smart_service,
                module,
                start_date,
                end_date
            )
        )
        
        # Get Kafka broker from environment variable and publish event
        producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
        
        # Publish event (success or error) to Kafka topic
        producer.produce_event("smart-service-event", event_data)
        
        # Log appropriate message based on event type
        if 'Error' in event_data.get('eventType', ''):
            logger.error("Error event regarding self-awareness monitoring and storing KPIs published successfully!")
        else:
            logger.info("Event regarding self-awareness monitoring and storing KPIs published successfully!")
        
        producer.close()
        
    except Exception as e:
        logger.error(f"Critical error in async self-awareness monitoring and storing KPIs processing: {str(e)}")
        
        # Last resort: create and publish a critical error event
        try:
            producer = EventsProducer(KAFKA_BOOTSTRAP_SERVERS)
            
            critical_error_event = {
                "description": f"Critical error in Self-Awareness 1 API processing: {str(e)}",
                "module": module,
                "timestamp": datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "priority": "HIGH",
                "eventType": "Critical Processing Error",
                "sourceComponent": "Self-Awareness Monitoring KPIs",
                "smartService": smart_service,
                "topic": "smart-service-event",
                "results": None
            }
            
            producer.produce_event("smart-service-event", critical_error_event)
            producer.close()
            logger.info("Critical error event published to Kafka!")
        except Exception as kafka_error:
            logger.error(f"Failed to publish critical error event to Kafka: {str(kafka_error)}")
            
# --- API Endpoints ---
@app.post("/monitor/kpis", response_model=Base64Response, tags=["Self Awareness monitoring and storing KPIs"])
async def self_awareness_monitor_kpis(base64_data: Base64Request):
    """
    Self-Awareness monitoring and storing KPIs for SEW Plant
    This endpoint accepts a Base64 encoded JSON request, initializes the Self-Awareness monitoring process and returns the results via Kafka event.
    
    Request format: {"request": "base64_encoded_json_data"}
    """
    # Log raw incoming request FIRST - before any validation
    logger.info("=== RAW SELF AWARENESS 1 - MONITOR AND STORING KPIS REQUEST ===")
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
        
        # Parse decoded data into SelfAwarenessKPIInput model
        try:
            logger.info("Attempting to parse decoded data into SelfAwarenessKPIInput model")
            data = SelfAwarenessKPIInput(**decoded_data)
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
        asyncio.create_task(
            process_self_awareness_monitoring_kpis(
                data.components,
                data.smartServiceId,
                data.moduleId,
                data.start_date,
                data.end_date
            )
        )
        
        logger.info("Successfully initialized self-awareness monitoring task")
        
        # Return Base64 encoded response
        response_data = {"message": "Self-awareness monitoring task started successfully"}
        encoded_response = encode_output_to_base64(response_data)
        return Base64Response(response=encoded_response)
    except HTTPException:
        # Re-raise HTTP exceptions (400, 503)
        raise
    except Exception as e:
        logger.error(f"Error in self-awareness monitoring task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error while initializing the self-awareness monitoring kpis algorithm: {str(e)}")
    
@app.get("/health", tags=["Health Check"])
def health_check():
    """
    Health check endpoint for the API.
    Tests connections to InfluxDB and Kafka services, and verifies SA1 module imports.
    """
    logger.info("Health check requested")
    
    # Test service connections
    services_status = {}
    overall_status = "healthy"
    
    try:
        # Test InfluxDB connection
        influxdb_status = test_influxdb_connection()
        services_status["influxdb"] = {
            "status": "healthy" if influxdb_status else "unhealthy",
            "connection": influxdb_status
        }
        if not influxdb_status:
            overall_status = "degraded"
            
    except Exception as e:
        logger.error(f"Error testing InfluxDB connection: {e}")
        services_status["influxdb"] = {
            "status": "unhealthy",
            "connection": False,
            "error": str(e)
        }
        overall_status = "degraded"
    
    try:
        # Test Kafka connection
        kafka_status = test_kafka_connection()
        services_status["kafka"] = {
            "status": "healthy" if kafka_status else "unhealthy",
            "connection": kafka_status
        }
        if not kafka_status:
            overall_status = "degraded"
            
    except Exception as e:
        logger.error(f"Error testing Kafka connection: {e}")
        services_status["kafka"] = {
            "status": "unhealthy",
            "connection": False,
            "error": str(e)
        }
        overall_status = "degraded"
    
    # Test SA1 module and async function import
    try:
        # Verify that the async function is properly imported and callable
        if callable(async_self_awareness_monitoring_kpis):
            services_status["sa1_algorithm"] = {
                "status": "healthy",
                "import": True,
                "callable": True
            }
        else:
            services_status["sa1_algorithm"] = {
                "status": "unhealthy",
                "import": True,
                "callable": False
            }
            overall_status = "degraded"
            
    except NameError as e:
        logger.error(f"SA1 async function not imported: {e}")
        services_status["sa1_algorithm"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"
    except Exception as e:
        logger.error(f"Error checking SA1 async function: {e}")
        services_status["sa1_algorithm"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"
    
    # Test EventsProducer class import
    try:
        if hasattr(EventsProducer, '__init__'):
            services_status["events_producer"] = {
                "status": "healthy",
                "import": True,
                "class_available": True
            }
        else:
            services_status["events_producer"] = {
                "status": "unhealthy", 
                "import": True,
                "class_available": False
            }
            overall_status = "degraded"
            
    except NameError as e:
        logger.error(f"EventsProducer class not imported: {e}")
        services_status["events_producer"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"
    except Exception as e:
        logger.error(f"Error checking EventsProducer class: {e}")
        services_status["events_producer"] = {
            "status": "unhealthy",
            "import": False,
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
        "message": f"Self Awareness 1 API is running - Status: {overall_status}",
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"Health check completed - Overall status: {overall_status}")
    return response
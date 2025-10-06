from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi.openapi.utils import get_openapi
import os
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import logging
import sys
import uuid
from multiprocessing import Process

from SA2_kafka import (
    test_mqtt_connection,
    test_kafka_connection,
    process_mqtt_data_with_config
)

active_processes = {}

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
    lifespan=lifespan,
    docs_url="/real-time/docs",
    redoc_url="/real-time/redoc"
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

app.add_middleware(
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
    """Unified response model for successful operations"""
    message: str = Field(..., description="Success or Error message")

class ProcessStartResponse(BaseModel):
    message: str

class ProcessInfoResponse(BaseModel):
    process_id: str
    smart_service_id: str
    module_id: str
    started_at: str
    status: str

# ---- Input Models ----
class PropertyData(BaseModel):
    Name: str = Field(..., description="Property name")
    Low_thre: float = Field(..., description="Lower threshold value for property")
    High_thre: float = Field(..., description="Upper threshold value for property")

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
    smartServiceId: str = Field(..., description="Smart Service ID")
    moduleId: str = Field(..., description="Module ID")

    model_config = {"populate_by_name": True}

# --- Utility Functions ---
def run_monitoring_process(component_list, smart_service_id, module_id):
    process_mqtt_data_with_config(component_list, smart_service_id, module_id)

# --- API Endpoints ---
@app.post("/real-time/monitor/kpis", response_model=ProcessStartResponse, tags=["Self Awareness Real-time monitoring and storing KPIs"])
async def self_awareness_monitor_kpis(base64_data: Base64Request):
    """
    Self-Awareness real-time monitoring and storing KPIs for SEW Plant
    This endpoint accepts a Base64 encoded JSON request, initializes the Self-Awareness monitoring process and returns the results via Kafka event.

    Request format: {"request": "base64_encoded_json_data"}
    """
    try:
        logger.info(f"Raw request object: {base64_data}")
        logger.info(f"Raw request dict: {base64_data.model_dump() if hasattr(base64_data, 'model_dump') else 'No model_dump method'}")
    except Exception as e:
        logger.error(f"Error logging raw request: {str(e)}")

    try:
        logger.info("=== STARTING REQUEST PROCESSING ===")

        if not hasattr(base64_data, 'request') or base64_data.request is None:
            logger.error("Request validation failed: base64_data.request is missing or None")
            raise HTTPException(status_code=400, detail="Missing 'request' field in Base64Request")

        decoded_data = decode_base64_to_dict(base64_data.request)
        logger.info("Successfully decoded Base64 request")
        logger.info(f"Decoded data keys: {list(decoded_data.keys()) if decoded_data else 'None'}")
        logger.debug(f"Decoded data structure: {json.dumps(decoded_data, indent=2, default=str)}")

        try:
            logger.info("Attempting to parse decoded data into SelfAwarenessKPIInput model")
            data = SelfAwarenessKPIInput(**decoded_data)
            logger.info("Successfully parsed request data")
        except Exception as e:
            logger.error("Failed to parse decoded data into model")
            logger.error(f"Validation error details: {str(e)}")
            logger.error(f"Validation error type: {type(e).__name__}")

            if hasattr(e, 'errors'):
                logger.error("Detailed validation errors:")
                for error in e.errors():
                    logger.error(f"  Field: {error.get('loc', 'unknown')}")
                    logger.error(f"  Error: {error.get('msg', 'unknown')}")
                    logger.error(f"  Input: {error.get('input', 'unknown')}")

            raise HTTPException(status_code=422, detail=f"Request validation failed: {str(e)}")

        process_id = str(uuid.uuid4())
        component_list = [component.model_dump() for component in data.components]

        process = Process(
            target=run_monitoring_process,
            args=(component_list, data.smartServiceId, data.moduleId)
        )
        process.start()

        active_processes[process_id] = {
            "process": process,
            "smart_service_id": data.smartServiceId,
            "module_id": data.moduleId,
            "started_at": datetime.now().isoformat(),
            "status": "running"
        }

        logger.info(f"Successfully started monitoring process: {process_id}")

        return ProcessStartResponse(
            message=f"Self-awareness real-time monitoring task started successfully. Process ID: {process_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in self-awareness monitoring task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error while initializing the self-awareness monitoring kpis algorithm: {str(e)}")

@app.get("/real-time/processes/{process_id}", response_model=ProcessInfoResponse, tags=["Process Management"])
async def get_process_info(process_id: str, x_api_key: Optional[str] = Header(None)):
    """
    Get information about a specific monitoring process.
    Requires API key authentication via X-API-Key header.
    """
    api_key = os.getenv("PROCESS_MANAGEMENT_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured on server")

    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    if process_id not in active_processes:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")

    process_info = active_processes[process_id]
    process = process_info["process"]

    if process.is_alive():
        status = "running"
    else:
        status = "stopped"
        process_info["status"] = status

    return ProcessInfoResponse(
        process_id=process_id,
        smart_service_id=process_info["smart_service_id"],
        module_id=process_info["module_id"],
        started_at=process_info["started_at"],
        status=status
    )

@app.delete("/real-time/processes/{process_id}", tags=["Process Management"])
async def stop_process(process_id: str, x_api_key: Optional[str] = Header(None)):
    """
    Stop a specific monitoring process.
    Requires API key authentication via X-API-Key header.
    """
    api_key = os.getenv("PROCESS_MANAGEMENT_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured on server")

    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    if process_id not in active_processes:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")

    process_info = active_processes[process_id]
    process = process_info["process"]

    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
        logger.info(f"Process {process_id} terminated")

    process_info["status"] = "stopped"

    return {
        "message": f"Process {process_id} stopped successfully",
        "process_id": process_id,
        "smart_service_id": process_info["smart_service_id"],
        "module_id": process_info["module_id"]
    }

@app.get("/real-time/processes", tags=["Process Management"])
async def list_all_processes(x_api_key: Optional[str] = Header(None)):
    """
    List all monitoring processes.
    Requires API key authentication via X-API-Key header.
    """
    api_key = os.getenv("PROCESS_MANAGEMENT_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured on server")

    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    processes_list = []
    for process_id, process_info in active_processes.items():
        process = process_info["process"]
        status = "running" if process.is_alive() else "stopped"
        process_info["status"] = status

        processes_list.append({
            "process_id": process_id,
            "smart_service_id": process_info["smart_service_id"],
            "module_id": process_info["module_id"],
            "started_at": process_info["started_at"],
            "status": status
        })

    return {
        "total_processes": len(processes_list),
        "processes": processes_list
    }

@app.get("/real-time/health", tags=["Health Check"])
def health_check():
    """
    Health check endpoint for SA2 API.
    Tests connections to MQTT and Kafka services.
    """
    logger.info("Health check requested")

    services_status = {}
    overall_status = "healthy"

    try:
        mqtt_status = test_mqtt_connection()
        services_status["mqtt"] = {
            "status": "healthy" if mqtt_status else "unhealthy",
            "connection": mqtt_status
        }
        if not mqtt_status:
            overall_status = "degraded"

    except Exception as e:
        logger.error(f"Error testing MQTT connection: {e}")
        services_status["mqtt"] = {
            "status": "unhealthy",
            "connection": False,
            "error": str(e)
        }
        overall_status = "degraded"

    try:
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

    try:
        if callable(process_mqtt_data_with_config):
            services_status["sa2_algorithm"] = {
                "status": "healthy",
                "import": True,
                "callable": True
            }
        else:
            services_status["sa2_algorithm"] = {
                "status": "unhealthy",
                "import": True,
                "callable": False
            }
            overall_status = "degraded"

    except NameError as e:
        logger.error(f"SA2 function not imported: {e}")
        services_status["sa2_algorithm"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"
    except Exception as e:
        logger.error(f"Error checking SA2 function: {e}")
        services_status["sa2_algorithm"] = {
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
        "message": f"Self Awareness 2 API is running - Status: {overall_status}",
        "timestamp": datetime.now().isoformat()
    }

    logger.info(f"Health check completed - Overall status: {overall_status}")
    return response
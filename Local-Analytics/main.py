from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Dict, List, Any
from datetime import datetime
from fastapi.openapi.utils import get_openapi
import os
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import logging
import sys


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

# Import Local Analytics histogram functions
from LA_hist_HUB_json_INT import get_filtering_options, generate_histogram_base64


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
    title="Local Analytics API",
    description="Generation of filtering options and histograms from JSON Self Awareness Monitoring and Storing KPIs results with full hierarchy support",
    version="2.0.0",
    lifespan=lifespan
)


# Set the origins for CORS
def get_cors_origins():
    origins_string = os.getenv("CORS_DOMAINS", "http://localhost:8094")  # Default DTM URL
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
    logger.info(f"=== INCOMING HTTP REQUEST ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")

    if request.method == "POST":
        body = await request.body()
        logger.info(f"Raw request body length: {len(body)}")
        logger.info(f"Raw request body (first 500 chars): {body[:500].decode('utf-8', errors='ignore')}")

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
    """Encode a dictionary to a Base64 string."""
    json_bytes = json.dumps(output, default=str).encode("utf-8")
    return base64.b64encode(json_bytes).decode("utf-8")


def decode_base64_to_dict(base64_string: str):
    """Decode a Base64 string to a dictionary or list."""
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
    """Unified input model for Base64 encoded responses"""
    response: str = Field(..., description="Base64 encoded JSON response data")


# ---- Input Models WITH FULL HIERARCHY ----

class MonitorKpisResults(BaseModel):
    """JSON histogram data structure model with full hierarchy - matches SA1 output"""
    stage: str = Field(..., description="Stage identifier", alias="Stage")
    cell: str = Field(..., description="Cell name", alias="Cell")
    plc: str = Field(..., description="PLC identifier", alias="PLC")
    module: str = Field(..., description="Module name", alias="Module")
    subelement: str = Field(..., description="SubElement name", alias="SubElement")
    component: str = Field(..., description="Component name", alias="Component")
    variable: str = Field(..., description="Variable name", alias="Variable")
    variable_type: str = Field(..., description="Variable type (velocity/current)", alias="Variable_Type")
    starting_date: str = Field(..., description="Starting date - supports DD-MM-YYYY HH:MM:SS or ISO format",
                               alias="Starting_date")
    ending_date: str = Field(..., description="Ending date - supports DD-MM-YYYY HH:MM:SS or ISO format",
                             alias="Ending_date")
    data_source: str = Field(..., description="Data source (e.g., InfluxDB)", alias="Data_source")
    bucket: str = Field(..., description="Data bucket name", alias="Bucket")
    data: List[float] = Field(..., description="List of data values", alias="Data_list")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


# ---- Request Models for Local Analytics WITH HIERARCHY ----

class HistogramParams(BaseModel):
    """Parameters for histogram generation with full hierarchy"""
    Cell: str = Field(..., description="Cell name")
    Module: str = Field(..., description="Module name")
    SubElement: str = Field(..., description="SubElement name")
    Component: str = Field(..., description="Component name")
    Variable: str = Field(..., description="Variable name")
    Date: str = Field(..., description="Starting date in format 'DD-MM-YYYY HH:MM:SS'")


class HistogramRequest(BaseModel):
    """Request model for histogram generation"""
    histogram_data: List[MonitorKpisResults] = Field(...,
                                                     description="List of histogram JSON data objects with hierarchy")
    params1: HistogramParams = Field(..., description="First dataset parameters")
    params2: HistogramParams = Field(None, description="Optional second dataset parameters for comparison")
    max_filter: float = Field(0, description="Optional maximum value filter (0 = no filter)")


# --- Utility Functions ---
def encode_dataframe_to_base64(df) -> str:
    """Convert pandas DataFrame to Base64 encoded JSON string"""
    json_dict = df.to_dict('records') if not df.empty else []
    return encode_output_to_base64({"filtering_options": json_dict})


# --- API Endpoints ---
@app.post("/filtering-options", response_model=Base64Response, tags=["Local Analytics"])
async def get_analytics_filtering_options(base64_data: Base64Request):
    """
    Get available filtering options (Cell, Module, SubElement, Component, Variable) from histogram JSON data.

    Request format: {"request": "base64_encoded_list_of_histogram_objects"}
    Response format: {"response": "base64_encoded_filtering_options_json"}
    """
    try:
        logger.info("=== LOCAL ANALYTICS - GET FILTERING OPTIONS ===")

        # Validate base64_data.request exists
        if not hasattr(base64_data, 'request') or base64_data.request is None:
            logger.error("Request validation failed: base64_data.request is missing or None")
            raise HTTPException(status_code=400, detail="Missing 'request' field in Base64Request")

        # Decode Base64 request
        try:
            decoded_data = decode_base64_to_dict(base64_data.request)
            logger.info("Successfully decoded Base64 request")
            if isinstance(decoded_data, list):
                logger.info(f"Decoded data is a list with {len(decoded_data)} items")
            else:
                logger.info(f"Decoded data type: {type(decoded_data)}")
        except Exception as e:
            logger.error(f"Failed to decode Base64 request: {str(e)}")
            raise HTTPException(status_code=422, detail=f"Invalid Base64 request: {str(e)}")

        # Parse decoded data into List[MonitorKpisResults]
        try:
            logger.info("Parsing decoded data into List[MonitorKpisResults]")
            if not isinstance(decoded_data, list):
                raise ValueError("Decoded data must be a list of histogram objects")

            filtering_options_list = [MonitorKpisResults(**item) for item in decoded_data]
            logger.info(f"Successfully parsed request with {len(filtering_options_list)} histogram objects")
        except Exception as e:
            logger.error(f"Failed to parse filtering options request: {str(e)}")
            raise HTTPException(status_code=422, detail=f"Filtering options request validation failed: {str(e)}")

        # Convert to dictionaries with alias names
        filtering_options_dicts = [item.model_dump(by_alias=True) for item in filtering_options_list]

        # Extract filtering options from provided data
        filtering_options_df = get_filtering_options(filtering_options_dicts)
        logger.info(f"Found {len(filtering_options_df)} filtering options")

        # Convert DataFrame to Base64 encoded JSON
        base64_response = encode_dataframe_to_base64(filtering_options_df)
        logger.info("Successfully generated filtering options response")

        return Base64Response(response=base64_response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get filtering options: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving filtering options: {str(e)}")


@app.post("/generate-histogram", response_model=Base64Response, tags=["Local Analytics"])
async def generate_analytics_histogram(base64_data: Base64Request):
    """
    Generate histogram visualization from histogram JSON data with full hierarchy support.

    Request format: {"request": "base64_encoded_histogram_request_json"}
    Response format: {"response": "base64_encoded_png_image"}
    """
    try:
        logger.info("=== LOCAL ANALYTICS - GENERATE HISTOGRAM ===")

        # Validate base64_data.request exists
        if not hasattr(base64_data, 'request') or base64_data.request is None:
            logger.error("Request validation failed: base64_data.request is missing or None")
            raise HTTPException(status_code=400, detail="Missing 'request' field in Base64Request")

        # Decode Base64 request
        try:
            decoded_data = decode_base64_to_dict(base64_data.request)
            logger.info("Successfully decoded Base64 request")
            if isinstance(decoded_data, dict):
                logger.info(f"Decoded data keys: {list(decoded_data.keys())}")
        except Exception as e:
            logger.error(f"Failed to decode Base64 request: {str(e)}")
            raise HTTPException(status_code=422, detail=f"Invalid Base64 request: {str(e)}")

        # Parse decoded data into HistogramRequest model
        try:
            logger.info("Parsing decoded data into HistogramRequest model")
            histogram_request = HistogramRequest(**decoded_data)
            logger.info("Successfully parsed histogram request")
        except Exception as e:
            logger.error(f"Failed to parse histogram request: {str(e)}")
            raise HTTPException(status_code=422, detail=f"Histogram request validation failed: {str(e)}")

        logger.info(f"Processing histogram generation with {len(histogram_request.histogram_data)} histogram objects")
        logger.info(f"Params1: {histogram_request.params1}")
        if histogram_request.params2:
            logger.info(f"Params2: {histogram_request.params2}")
        logger.info(f"Max filter: {histogram_request.max_filter}")

        # Generate histogram using the LA function
        logger.info("Calling generate_histogram_base64 function from LA module")
        base64_image = generate_histogram_base64(
            histogram_request.histogram_data,
            histogram_request.params1,
            histogram_request.params2,
            histogram_request.max_filter
        )

        if not base64_image:
            logger.error("Histogram generation returned empty result")
            raise HTTPException(status_code=500, detail="Failed to generate histogram")

        logger.info(f"Successfully generated histogram (Base64 length: {len(base64_image)})")

        return Base64Response(response=base64_image)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate histogram: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating histogram: {str(e)}")


@app.get("/health", tags=["Health Check"])
def health_check():
    """
    Health check endpoint for the Local Analytics API.
    Tests LA functions and core components availability.
    """
    logger.info("Health check requested")

    services_status = {}
    overall_status = "healthy"

    try:
        # Test Local Analytics functions import availability
        from LA_hist_HUB_json_INT import get_filtering_options, generate_histogram_base64
        if callable(get_filtering_options) and callable(generate_histogram_base64):
            services_status["local_analytics"] = {
                "status": "healthy",
                "import": True,
                "functions_available": True
            }
        else:
            services_status["local_analytics"] = {
                "status": "unhealthy",
                "import": True,
                "functions_available": False
            }
            overall_status = "degraded"
    except ImportError as e:
        logger.error(f"Local Analytics functions not imported: {e}")
        services_status["local_analytics"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"

    try:
        # Test Pydantic models with hierarchy
        test_monitor_kpis = MonitorKpisResults(
            stage="CELL_05",
            cell="Ligne réducteur REDG",
            plc="plc_100",
            module="A21",
            subelement="ROOT",
            component="Ecr_A21_3_L_LOOP_OUT",
            variable="diActualVitesse",
            variable_type="velocity",
            starting_date="03-10-2025 08:00:00",
            ending_date="03-10-2025 18:00:00",
            data_source="InfluxDB",
            bucket="Ligne_reducteur_REDG05",
            data_list=[1.0, 2.0, 3.0]
        )
        test_histogram_params = HistogramParams(
            Cell="Ligne réducteur REDG",
            Module="A21",
            SubElement="ROOT",
            Component="Ecr_A21_3_L_LOOP_OUT",
            Variable="diActualVitesse",
            Date="03-10-2025 08:00:00"
        )
        services_status["pydantic_models"] = {
            "status": "healthy",
            "validation": True,
            "models_tested": ["MonitorKpisResults", "HistogramParams", "Base64Request", "Base64Response"]
        }
    except Exception as e:
        logger.error(f"Error testing Pydantic models: {e}")
        services_status["pydantic_models"] = {
            "status": "unhealthy",
            "validation": False,
            "error": str(e)
        }
        overall_status = "degraded"

    # Test base64 encoding/decoding functions
    try:
        test_data = {"test": "data"}
        encoded = encode_output_to_base64(test_data)
        decoded = decode_base64_to_dict(encoded)
        if decoded == test_data:
            services_status["base64_functions"] = {
                "status": "healthy",
                "encoding_decoding": True
            }
        else:
            services_status["base64_functions"] = {
                "status": "unhealthy",
                "encoding_decoding": False,
                "error": "Encoding/decoding mismatch"
            }
            overall_status = "degraded"
    except Exception as e:
        logger.error(f"Error testing base64 functions: {e}")
        services_status["base64_functions"] = {
            "status": "unhealthy",
            "encoding_decoding": False,
            "error": str(e)
        }
        overall_status = "degraded"

    services_status["api"] = {
        "status": "healthy",
        "endpoints": ["/filtering-options", "/generate-histogram", "/health"],
        "connection": True
    }

    response = {
        "status": overall_status,
        "services": services_status,
        "message": f"Local Analytics API with Full Hierarchy Support is running - Status: {overall_status}",
        "timestamp": datetime.now().isoformat()
    }

    logger.info(f"Health check completed - Overall status: {overall_status}")
    return response
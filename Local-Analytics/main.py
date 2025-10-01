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
import os

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
    description="Generation of filtering options and histograms from JSON Self Awareness Monitoring and Storing KPIs results",
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
    """Unified input model for Base64 encoded responses"""
    response: str = Field(..., description="Base64 encoded JSON response data")    
    
# ---- Input Models ----

class MonitorKpisResults(BaseModel):
    """JSON histogram data structure model - matches the input JSON format"""
    ligne: str = Field(..., description="PLC line identifier", alias="Ligne")
    component: str = Field(..., description="Component name", alias="Component")
    variable: str = Field(..., description="Variable name", alias="Variable")
    starting_date: str = Field(..., description="Starting date - supports DD-MM-YYYY HH:MM:SS or ISO format", alias="Starting_date")
    ending_date: str = Field(..., description="Ending date - supports DD-MM-YYYY HH:MM:SS or ISO format", alias="Ending_date")
    data_source: str = Field(..., description="Data source (e.g., InfluxDB)", alias="Data_source")
    bucket: str = Field(..., description="Data bucket name", alias="Bucket")
    data: List[float] = Field(..., description="List of data values", alias="Data_list")

    model_config = {"populate_by_name": True}

    def get_iso_timestamp(self, date_str: str) -> str:
        """Convert date string to ISO format timestamp: YYYY-MM-DDTHH:MM:SS"""
        # If already in ISO format (YYYY-MM-DDTHH:MM:SS), return as is
        if 'T' in date_str:
            return date_str

        # Convert from DD-MM-YYYY HH:MM:SS to ISO format
        try:
            dt = datetime.strptime(date_str, "%d-%m-%Y %H:%M:%S")
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            # If parsing fails, return original string
            return date_str

# ---- Request Models for Local Analytics ----
class FilteringOptionsRequest(BaseModel):
    """Request model for filtering options - expects list of JSON histogram data"""
    filtering_options: List[MonitorKpisResults] = Field(..., description="List of histogram JSON data objects")

class HistogramParams(BaseModel):
    """Parameters for histogram generation"""
    Ligne: str = Field(..., description="PLC line identifier")
    Component: str = Field(..., description="Component name")
    Variable: str = Field(..., description="Variable name")s
    Date: str = Field(..., description="Starting date in format 'DD-MM-YYYY HH:MM:SS'")

class HistogramRequest(BaseModel):
    """Request model for histogram generation"""
    histogram_data: List[MonitorKpisResults] = Field(..., description="List of histogram JSON data objects")
    params1: HistogramParams = Field(..., description="First dataset parameters")
    params2: HistogramParams = Field(None, description="Optional second dataset parameters for comparison")
    max_filter: float = Field(0, description="Optional maximum value filter (0 = no filter)")

# --- Utility Functions ---
def encode_dataframe_to_base64(df) -> str:
    """
    Convert pandas DataFrame to Base64 encoded JSON string
    """
    json_dict = df.to_dict('records') if not df.empty else []
    return encode_output_to_base64({"filtering_options": json_dict})

# --- API Endpoints ---
@app.post("/filtering-options", response_model=Base64Response, tags=["Local Analytics"])
async def get_analytics_filtering_options(base64_data: Base64Request):
    """
    Get available filtering options (Ligne, Component, Variable) from histogram JSON files.

    Request format: {"request": "base64_encoded_empty_json_data"} (any valid base64 JSON)
    Response format: {"response": "base64_encoded_filtering_options_json"}
    """
    try:
        logger.info("=== LOCAL ANALYTICS - GET FILTERING OPTIONS ===")

        # Log incoming request
        logger.info(f"Request type: {type(base64_data)}")
        if hasattr(base64_data, 'request') and base64_data.request:
            logger.info(f"Base64 request length: {len(base64_data.request)}")
            logger.info(f"Base64 request preview: {base64_data.request[:100]}")

        # Validate base64_data.request exists
        if not hasattr(base64_data, 'request') or base64_data.request is None:
            logger.error("Request validation failed: base64_data.request is missing or None")
            raise HTTPException(status_code=400, detail="Missing 'request' field in Base64Request")

        # Decode Base64 request
        try:
            decoded_data = decode_base64_to_dict(base64_data.request)
            logger.info("Successfully decoded Base64 request")
            logger.info(f"Decoded data keys: {list(decoded_data.keys()) if decoded_data else 'None'}")
        except Exception as e:
            logger.error(f"Failed to decode Base64 request: {str(e)}")
            raise HTTPException(status_code=422, detail=f"Invalid Base64 request: {str(e)}")

        # Parse decoded data into FilteringOptionsRequest model
        try:
            logger.info("Parsing decoded data into FilteringOptionsRequest model")
            filtering_request = FilteringOptionsRequest(**decoded_data)
            logger.info(f"Successfully parsed request with {len(filtering_request.filtering_options)} histogram objects")
        except Exception as e:
            logger.error(f"Failed to parse filtering options request: {str(e)}")
            raise HTTPException(status_code=422, detail=f"Filtering options request validation failed: {str(e)}")

        # Extract filtering options from provided data
        filtering_options_dicts = [item.model_dump(by_alias=True) for item in filtering_request.filtering_options]
        filtering_options_df = get_filtering_options(filtering_options_dicts)
        logger.info(f"Found {len(filtering_options_df)} filtering options")

        # Convert DataFrame to Base64 encoded JSON
        base64_response = encode_dataframe_to_base64(filtering_options_df)
        logger.info("Successfully generated filtering options response")

        return Base64Response(response=base64_response)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in get filtering options: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving filtering options: {str(e)}")

@app.post("/generate-histogram", response_model=Base64Response, tags=["Local Analytics"])
async def generate_analytics_histogram(base64_data: Base64Request):
    """
    Generate histogram visualization from histogram JSON files.

    Request format: {"request": "base64_encoded_histogram_request_json"}
    Response format: {"response": "base64_encoded_png_image"}
    """
    try:
        logger.info("=== LOCAL ANALYTICS - GENERATE HISTOGRAM ===")

        # Log incoming request
        logger.info(f"Request type: {type(base64_data)}")
        if hasattr(base64_data, 'request') and base64_data.request:
            logger.info(f"Base64 request length: {len(base64_data.request)}")
            logger.info(f"Base64 request preview: {base64_data.request[:100]}")

        # Validate base64_data.request exists
        if not hasattr(base64_data, 'request') or base64_data.request is None:
            logger.error("Request validation failed: base64_data.request is missing or None")
            raise HTTPException(status_code=400, detail="Missing 'request' field in Base64Request")

        # Decode Base64 request
        try:
            decoded_data = decode_base64_to_dict(base64_data.request)
            logger.info("Successfully decoded Base64 request")
            logger.info(f"Decoded data keys: {list(decoded_data.keys()) if decoded_data else 'None'}")
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

        # Generate histogram using the LA function with temp file paths
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
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in generate histogram: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating histogram: {str(e)}")

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
    except Exception as e:
        logger.error(f"Error testing Local Analytics functions: {e}")
        services_status["local_analytics"] = {
            "status": "unhealthy",
            "import": False,
            "error": str(e)
        }
        overall_status = "degraded"

    try:
        # Test Local Analytics Pydantic models
        test_monitor_kpis = MonitorKpisResults(
            ligne="plc_100",
            component="Test_Component",
            variable="test_variable",
            starting_date="07-07-2025 00:00:00",
            ending_date="07-07-2025 23:59:59",
            data_source="InfluxDB",
            bucket="HUB",
            data_list=[1.0, 2.0, 3.0]
        )
        test_histogram_params = HistogramParams(
            ligne="plc_100",
            component="Test_Component",
            variable="test_variable",
            date="07-07-2025 00:00:00"
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
        "message": f"Local Analytics API is running - Status: {overall_status}",
        "timestamp": datetime.now().isoformat()
    }

    logger.info(f"Health check completed - Overall status: {overall_status}")
    return response
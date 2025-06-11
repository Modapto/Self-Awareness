from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import pickle
from fastapi.openapi.utils import get_openapi
import pandas as pd
import os
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import base64

# Import algorithms
from OnlineAnomalyDetection import OnlineAnomalyDetectorV2
from OnlinePrognostics import OnlinePrognostics 

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.executor = ThreadPoolExecutor(max_workers=5)
    print("ThreadPoolExecutor started with 5 workers")
    
    yield
    
    # Shutdown
    app.state.executor.shutdown(wait=True)
    print("ThreadPoolExecutor shutdown completed")

app = FastAPI(
    title="Self Awareness API",
    description="Real-time monitoring and analysis capabilities through a user interface, allowing users to detect anomalies, diagnose faults, and predict remaining useful life",
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

    server_url = os.getenv("SWAGGER_SERVER_URL", "http://localhost:8001")
    openapi_schema["servers"] = [{"url": server_url}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Input Model ----
class AnomalyDetectionInput(BaseModel):
    window_data_encoded: str  = Field(..., description="Base64 Encoded DataFrame containing sensor readings for the current window")
    window_start: int = Field(..., gt=0, description="Starting index of the window")
    window_end: int = Field(..., gt=0, description="Ending index of the window")

    @field_validator('window_data_encoded')
    def validate_dataframe(cls, v):
        try:
            # Decode and unpickle to validate
            df = pickle.loads(base64.b64decode(v))
            if not isinstance(df, pd.DataFrame):
                raise ValueError("Must be a pandas DataFrame")
            return v
        except Exception as e:
            raise ValueError(f"Invalid DataFrame encoding: {e}")
    
    def get_dataframe(self) -> pd.DataFrame:
        return pickle.loads(base64.b64decode(self.window_data_encoded))

class PrognosticsInput(BaseModel):
    simulation_run: int = Field(..., description="ID of the simulation run")
    window_end: int = Field(..., description="Last sample in anomaly window")

# --- Utility Functions ---
def process_prognostics(data: PrognosticsInput):
    """Background task for prognostics"""
    try:
        # Prognostics processing
        anomaly_data = {
            "simulation_run": data.simulation_run,
            "window_end": data.window_end
        }
        result = OnlinePrognostics.diagnose_and_prognose(anomaly_data)
        
        print(f"Prognostics completed for simulation {data.simulation_run} and window end {data.window_end}")
        print(f"Results: {result}")
    except Exception as e:
        print(f"Error in prognostics processing: {str(e)}")


def process_anomaly_detection(data: AnomalyDetectionInput):
    """Background task for anomaly detection"""
    try:
        # Process the input data
        result = OnlineAnomalyDetectorV2.process_window(
            data.get_dataframe(),
            data.window_start,
            data.window_end
        )
        
        print(f"Anomaly detection completed for window {data.window_start}-{data.window_end}")
        print(f"Results: {result}")
    except Exception as e:
        print(f"Error in anomaly detection processing: {str(e)}")

# ---- Main Endpoints ----
@app.post("/anomaly-detection", tags=["Anomaly Detection"])
async def anomaly_detection(data: AnomalyDetectionInput, background_tasks: BackgroundTasks):
    """
    Anomaly detection algorithm endpoint.
    This endpoint accepts parameters for the anomaly detection algorithm and returns the detected anomalies.
    """
    try:
        # Add the task to background tasks
        background_tasks.add_task(process_anomaly_detection, data)
        
        return {
            "status": "Success",
            "message": "Anomaly detection started"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting anomaly detection: {str(e)}")

@app.post("/prognostics", tags=["Prognostics"])
async def prognostics(data: PrognosticsInput, background_tasks : BackgroundTasks):
    """
    Predictive maintenance algorithm endpoint.
    This endpoint accepts parameters for the specified index and returns the predicted remaining useful life.
    """
    try:
       # Add the task to background tasks
        background_tasks.add_task(process_prognostics, data)
        
        return {
            "status": "Success",
            "message": "Prognostics started",
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting anomaly detection: {str(e)}")

@app.get("/health")
def health_check():
    """
    Health check endpoint for the API.
    """
    return {"status": "healthy"}
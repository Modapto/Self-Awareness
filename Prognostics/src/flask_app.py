import torch
from data_processing import loadData, norm_
from model import Model
from flask import Flask, request, Response, jsonify
from flask_swagger import swagger
from flask_swagger_ui import get_swaggerui_blueprint
import requests
import json
from waitress import serve
from logs import extended_logger
import os
from dotenv import load_dotenv
import time
from main import process, min_engine_index, max_engine_index


device = "cuda" if torch.cuda.is_available() else "cpu"

host       = '0.0.0.0'
port       = 8568
verbose    = 0
pretty     = False


app = Flask(__name__)

# -------------------------------------------------------------------------------------------------------------- #

@app.route('/prognostics/analysis', methods=['GET'])
def selfAwarenessProcess():
    """
    Endpoint to predict the Remaining Useful Life (RUL) for a given engine index.
    ---
    tags:
      - Analysis
    parameters:
      - name: engine_index
        in: query
        type: integer
        required: true
        description: Index of the engine to analyze.
    responses:
      200:
        description: Successfully retrieved RUL prediction.
        schema:
          type: object
          properties:
            RUL_prediction:
              type: string
              description: Predicted Remaining Useful Life.
            engine_index:
              type: string
              description: Engine index used for the prediction.
            UNIX_timestamp:
              type: string
              description: Timestamp of the prediction.
      400:
        description: Missing or invalid engine index.
    """
    
    # Extract 'index' from query parameters
    engine_index = int(request.args.get('engine_index'))
    
    x_test, _ = loadData("4")
    best_model = Model().to(device)
    best_model.load_state_dict(torch.load('../models/best_model_FD004.pth', map_location=device))
    best_model.eval()

    min_engine_index = 1
    max_engine_index = len(x_test)
    
    # Check if 'index' is provided
    if engine_index is None or engine_index <= min_engine_index or engine_index >= max_engine_index:
        return jsonify({"error": f"Missing 'engine_index' parameter or engine index out of limits ({min_engine_index},{max_engine_index})"}), 400
    
    else:
        with torch.no_grad():
            y_pred = best_model(x_test[engine_index].float())
            rul_prediction = norm_.y_scaler.inverse_transform(y_pred[-1, -1].cpu().numpy().reshape(-1, 1))[0, 0]
            extended_logger.info('\n Estimated Remaining useful life value: {}'.format(rul_prediction))
        
        # we must return a RUL prediction, and a timestamp
        # Get the current UNIX timestamp
        current_timestamp = int(time.time())
        
        # return payload
        return jsonify({
            "RUL_prediction": str(rul_prediction),
            "engine_index": str(engine_index),
            "UNIX_timestamp": str(current_timestamp)
        }), 200
        

@app.route('/prognostics/analysis/v2', methods=['GET'])
def selfAwarenessProcessV2():
    """
    Endpoint to predict the Remaining Useful Life (RUL) for a given engine index using an alternative method.
    ---
    tags:
      - Analysis
    parameters:
      - name: engine_index
        in: query
        type: integer
        required: true
        description: Index of the engine to analyze.
    responses:
      200:
        description: Successfully retrieved RUL prediction.
        schema:
          type: object
          properties:
            RUL_prediction:
              type: string
              description: Predicted Remaining Useful Life.
            engine_index:
              type: string
              description: Engine index used for the prediction.
            UNIX_timestamp:
              type: string
              description: Timestamp of the prediction.
      400:
        description: Missing or invalid engine index, or index out of bounds.
    """
    
    # Extract 'index' from query parameters
    engine_index = int(request.args.get('engine_index'))
    
    # Check if 'index' is provided
    if engine_index is None:
        return jsonify({"error": f"Missing 'engine_index' parameter "}), 400
    
    else:
        rul_prediction = process(engine_index)
        
        # we must return a RUL prediction, and a timestamp
        # Get the current UNIX timestamp
        current_timestamp = int(time.time())
        
        if rul_prediction == "error":
            return jsonify({"error": f"'engine_index' out of max bounds, try a lower value "}), 400
        
        else:
            # return payload
            return jsonify({
                "RUL_prediction": str(rul_prediction),
                "engine_index": str(engine_index),
                "UNIX_timestamp": str(current_timestamp)
            }), 200

  # Swagger documentation route
@app.route('/prognostics/swagger')
def get_swagger():
    """
    Generates the Swagger specification for this API.
    ---
    tags:
      - Documentation
    responses:
      200:
        description: Swagger specification in JSON format.
    """
    swag = swagger(app)
    swag['info']['version'] = "1.0"
    swag['info']['title'] = "Prognostics"
    return jsonify(swag)

# Swagger UI route
SWAGGER_URL = '/swagger-ui'
API_URL = '/swagger'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Prognostics"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# -------------------------------------------------------------------------------------------------------------- #
if __name__ == "__main__":
    app.run(host=host, port=port)
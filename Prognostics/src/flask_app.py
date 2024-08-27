import torch
from data_processing import loadData, norm_
from model import Model
from flask import Flask, request, Response, jsonify
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

@app.route('/analysis', methods=['GET'])
def selfAwarenessProcess():
    
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
            "UNIX_timestamp": str(current_timestamp)
        }), 200
        

@app.route('/analysis/v2', methods=['GET'])
def selfAwarenessProcessV2():
    
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
                "UNIX_timestamp": str(current_timestamp)
            }), 200
    
# -------------------------------------------------------------------------------------------------------------- #
if __name__ == "__main__":
    app.run(host=host, port=port)
# Prognostics Subcomponent

## Overview

This subcomponent, part of the Self-awareness component, focuses on prognostics by predicting the Remaining Useful Life (RUL) for jet engines using sensor data. It uses a deep learning model combining Multilayer Perceptron (MLP) and Long Short-Term Memory (LSTM) layers for RUL estimation. 

The model is trained on the CMAPSS Jet Engine Simulated Data provided by NASA.

## Table of Contents
1. [Installation](#installation)
2. [Usage](#usage)
3. [Contributor](#contributor)
4. [License](#license)

## Installation

1. Clone the repository: 
```bash    
git clone https://github.com/Modapto/Self-Awareness.git
cd Prognostics
```
2. Build the Docker image:
```bash
docker build -t prognostics_modapto .
```
3.  Deploy the container:
```bash
docker run -dp 127.0.0.1:8568:8568 prognostics_modapto
```

## Usage

Requests must include field "engine_index" as querystring argument. See the following examples.
In these examples, it is assumed that you are testing from where you have deployed the image, hence the address is "localhost".
If the container is in a remote machine, replace "localhost" with the IP address of that machine.

1. Via CLI:
```bash
   curl --request GET \
  --url 'http://localhost:8568/analysis?engine_index=12'
   ```

2. Via Python script:
```python
   import requests

   url = "http://localhost:8568/analysis"

   querystring = {"engine_index":"12"}

   payload = ""

   response = requests.request("GET", url, data=payload, params=querystring)

   print(response.text)
   ```

This script loads the pre-trained model and prompts the user to enter a specific engine index.
If no input is provided, it defaults to engine index 57 (press Enter to use the default).

3. Response:

The response from the requests will look like this:
```json
   {
	"RUL_prediction": "113.60893",
   "Engine_index": "12",
	"UNIX_timestamp": "1724759975"
   }
   ```

-- 

## Contributor

Ilias Abdouni, Université de Lorraine

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Dataset Citation

A. Saxena, K. Goebel, D. Simon, and N. Eklund, ‘Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation’, in the Proceedings of the 1st International Conference on Prognostics and Health Management (PHM08), Denver CO, Oct 2008.
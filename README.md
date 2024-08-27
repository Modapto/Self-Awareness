# Prognostics Subcomponent

## Overview

This subcomponent, part of the Self-awareness component, focuses on prognostics by predicting the Remaining Useful Life (RUL) for jet engines using sensor data. It uses a deep learning model combining Multilayer Perceptron (MLP) and Long Short-Term Memory (LSTM) layers for RUL estimation. 

The model is trained on the CMAPSS Jet Engine Simulated Data provided by NASA.

## Table of Contents
1. [Installation](#installation)
2. [Usage](#usage)
3. [Deployment](#deployment)
4. [Contributor](#contributor)
5. [License](#license)

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

1. Ensure the CMAPSS dataset is placed in the correct directory.

2. Make predictions:
```bash
   python src/main.py
   ```
This script loads the pre-trained model and prompts the user to enter a specific engine index.
If no input is provided, it defaults to engine index 57 (press Enter to use the default).

3. The script will output the estimated Remaining Useful Life (RUL) for the selected engine.

## Deployment

-- 

## Contributor

Ilias Abdouni, Université de Lorraine

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Dataset Citation

A. Saxena, K. Goebel, D. Simon, and N. Eklund, ‘Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation’, in the Proceedings of the 1st International Conference on Prognostics and Health Management (PHM08), Denver CO, Oct 2008.
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
git clone https://github.com/ilinii/remaining_useful_life_prediction.git
cd remaining_useful_life_prediction
```
2. Install the required packages:
```bash
pip install -r requirements.txt
```
3.  Download the dataset:
The CMAPSS Jet Engine Simulated Data can be downloaded from:
https://data.nasa.gov/Aerospace/CMAPSS-Jet-Engine-Simulated-Data/ff5v-kuh6/about_data

After downloading, place the dataset files in a `Datasets/Cmapss/` directory within the project folder.

## Usage

1. Ensure the CMAPSS dataset is placed in the correct directory.

2. Make predictions:
```bash
   python src/main.py
   ```

This script loads the pre-trained model and makes predictions for a specific engine (default is engine index 57).

## Deployment

-- 

## Contributor

Ilias Abdouni, Université de Lorraine

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Dataset Citation

A. Saxena, K. Goebel, D. Simon, and N. Eklund, ‘Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation’, in the Proceedings of the 1st International Conference on Prognostics and Health Management (PHM08), Denver CO, Oct 2008.
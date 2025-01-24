"""
Binary fault detection for TEP using simple neural network architecture.
Each model is trained for a specific fault (binary classification: normal vs fault).
"""
import pyreadr
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import torch
from torch.utils.data import Dataset, DataLoader
import torch.nn as nn
from torch.nn import BCEWithLogitsLoss
from torch.optim.lr_scheduler import ReduceLROnPlateau
import numpy as np
from sklearn.metrics import precision_score, recall_score, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit
import os
import copy
from tqdm import tqdm
import pickle

# Check GPU availability
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

def import_data(fault_number):
    """Import data for binary classification (normal vs specific fault)"""
    # Read normal data
    normal_train_data = pyreadr.read_r('../Datasets/TEP/TEP_FaultFree_Training.RData')['fault_free_training']
    normal_test_data = pyreadr.read_r('../Datasets/TEP/TEP_FaultFree_Testing.RData')['fault_free_testing']

    normal_train_data['faultNumber'] = 0
    normal_test_data['faultNumber'] = 0

    # Read faulty data for specific fault
    faulty_train_data = pyreadr.read_r('../Datasets/TEP/TEP_Faulty_Training.RData')['faulty_training']
    faulty_train_data = faulty_train_data[faulty_train_data['faultNumber'] == fault_number].reset_index(drop=True)

    # Update labels (0 for normal, 1 for fault) with transition point
    faulty_train_data.loc[faulty_train_data['sample'] >= 20, 'faultNumber'] = 1
    faulty_train_data.loc[faulty_train_data['sample'] < 20, 'faultNumber'] = 0

    # Read and process test data
    faulty_test_data = pyreadr.read_r('../Datasets/TEP/TEP_Faulty_Testing.RData')['faulty_testing']
    faulty_test_data = faulty_test_data[faulty_test_data['faultNumber'] == fault_number].reset_index(drop=True)

    # Update test labels with different transition point
    faulty_test_data.loc[faulty_test_data['sample'] >= 160, 'faultNumber'] = 1
    faulty_test_data.loc[faulty_test_data['sample'] < 160, 'faultNumber'] = 0

    # Combine data
    training_data = pd.concat([normal_train_data, faulty_train_data], ignore_index=True)
    test_data = pd.concat([normal_test_data, faulty_test_data], ignore_index=True)

    # Convert to float32 for GPU compatibility
    training_data['faultNumber'] = training_data['faultNumber'].astype('float32')
    test_data['faultNumber'] = test_data['faultNumber'].astype('float32')

    return training_data, test_data

def normalize_data(train, val, test, feature_columns, save_dir='saved_models'):
    """Normalize the data using MinMaxScaler and save the scaler"""
    # Create save directory if it doesn't exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    scaler = MinMaxScaler()

    train_normalized = pd.DataFrame(scaler.fit_transform(train), columns=feature_columns)
    val_normalized = pd.DataFrame(scaler.transform(val), columns=feature_columns)
    test_normalized = pd.DataFrame(scaler.transform(test), columns=feature_columns)

    # Save the scaler
    scaler_path = os.path.join(save_dir, 'scaler.pkl')
    with open(scaler_path, 'wb') as f:
        pickle.dump(scaler, f)
    print(f"Scaler saved to {scaler_path}")

    return train_normalized, val_normalized, test_normalized, scaler

class BinaryFaultDataset(Dataset):
    """Dataset class for fault diagnosis"""
    def __init__(self, x_data, y_data):
        self.x_data = torch.FloatTensor(x_data).to(device)
        self.y_data = torch.FloatTensor(y_data).reshape(-1, 1).to(device)
        self.len = len(x_data)

    def __getitem__(self, index):
        return self.x_data[index], self.y_data[index]

    def __len__(self):
        return self.len

class FaultDiagnosisModel(nn.Module):
    """Simple neural network for binary fault diagnosis"""
    def __init__(self, input_size=52):
        super(FaultDiagnosisModel, self).__init__()

        self.model = nn.Sequential(
            nn.Linear(input_size, 90),
            nn.ReLU(),
            nn.Linear(90, 45),
            nn.ReLU(),
            nn.Linear(45, 1)  # Binary classification
        )

    def forward(self, x):
        return self.model(x)

def save_model(model, optimizer, epoch, metrics, fault_number, save_dir='saved_models'):
    """Save model checkpoint with metrics"""
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    checkpoint = {
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'epoch': epoch,
        'metrics': metrics
    }

    path = os.path.join(save_dir, f'fault_{fault_number}_model.pt')
    torch.save(checkpoint, path)
    print(f"Model saved to {path}")

def load_model(fault_number, model_dir='saved_models'):
    """Load saved model for inference"""
    model = FaultDiagnosisModel().to(device)
    optimizer = torch.optim.Adam(model.parameters())

    path = os.path.join(model_dir, f'fault_{fault_number}_model.pt')

    if os.path.exists(path):
        checkpoint = torch.load(path)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        epoch = checkpoint['epoch']
        metrics = checkpoint['metrics']
        print(f"Loaded model from epoch {epoch} with metrics: {metrics}")
    else:
        raise FileNotFoundError(f"No saved model found for fault {fault_number}")

    return model, optimizer

def train_model(model, train_loader, val_loader, criterion, optimizer, epochs, fault_number):
    """Train the model with validation and early stopping"""
    best_model = copy.deepcopy(model)
    best_val_loss = float('inf')
    patience = 20
    patience_counter = 0

    scheduler = ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=10, min_lr=1e-5)

    history = {'train_loss': [], 'val_loss': [], 'precision': [], 'recall': []}

    for epoch in range(epochs):
        # Training phase
        model.train()
        train_loss = 0.0

        for x, y in tqdm(train_loader, desc=f'Epoch {epoch + 1}/{epochs}'):
            optimizer.zero_grad()
            outputs = model(x).squeeze(-1)
            loss = criterion(outputs, y.squeeze(-1))
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * x.size(0)

        train_loss /= len(train_loader.dataset)
        history['train_loss'].append(train_loss)

        # Validation phase
        model.eval()
        val_loss = 0.0
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for x, y in val_loader:
                outputs = model(x).squeeze(-1)
                val_loss += criterion(outputs, y.squeeze(-1)).item() * x.size(0)
                preds = (torch.sigmoid(outputs) > 0.4).float()
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(y.cpu().numpy())

        val_loss /= len(val_loader.dataset)
        history['val_loss'].append(val_loss)

        # Calculate metrics
        precision = precision_score(all_labels, all_preds)
        recall = recall_score(all_labels, all_preds)
        conf_matrix = confusion_matrix(all_labels, all_preds)

        history['precision'].append(precision)
        history['recall'].append(recall)

        # Update scheduler
        scheduler.step(val_loss)

        # Early stopping check
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model = copy.deepcopy(model)
            patience_counter = 0

            # Save best model
            metrics = {
                'val_loss': val_loss,
                'precision': precision,
                'recall': recall
            }
            save_model(model, optimizer, epoch, metrics, fault_number)
        else:
            patience_counter += 1

        if patience_counter >= patience:
            print(f"Early stopping triggered at epoch {epoch}")
            break

        if epoch % 10 == 0:
            print(f'Epoch {epoch + 1}/{epochs}')
            print(f'Train Loss: {train_loss:.4f}')
            print(f'Val Loss: {val_loss:.4f}')
            print(f'Precision: {precision:.4f}')
            print(f'Recall: {recall:.4f}')
            print(f'Confusion Matrix:\n{conf_matrix}')

    return best_model, history

def predict_online(model, scaler, data_window):
    """Make predictions for online fault diagnosis"""
    model.eval()

    # Normalize the data window using the saved scaler
    normalized_data = scaler.transform(data_window)
    data_tensor = torch.FloatTensor(normalized_data).to(device)

    with torch.no_grad():
        outputs = model(data_tensor)
        probabilities = torch.sigmoid(outputs)
        predictions = (probabilities > 0.4).float()

    return predictions.cpu().numpy(), probabilities.cpu().numpy()

if __name__ == "__main__":
    # Parameters
    fault_to_diagnose = 1  # Change this to train for different faults
    batch_size = 64
    epochs = 500
    learning_rate = 0.005

    # Load and preprocess data
    print(f"Training model for Fault {fault_to_diagnose}")
    df_train, df_test = import_data(fault_to_diagnose)

    # Prepare feature columns
    feature_columns = df_train.columns[3:]  # Exclude faultNumber, simulationRun, sample

    # Split training data using GroupShuffleSplit
    splitter = GroupShuffleSplit(test_size=0.2, n_splits=1, random_state=42)
    train_idx, val_idx = next(splitter.split(df_train, groups=df_train['simulationRun']))

    # Prepare training and validation data
    train_data = df_train.iloc[train_idx]
    val_data = df_train.iloc[val_idx]

    # Extract features and labels
    X_train = train_data[feature_columns]
    y_train = train_data['faultNumber']
    X_val = val_data[feature_columns]
    y_val = val_data['faultNumber']
    X_test = df_test[feature_columns]
    y_test = df_test['faultNumber']

    # Normalize data
    X_train_norm, X_val_norm, X_test_norm, scaler = normalize_data(
        X_train, X_val, X_test,
        feature_columns,
        save_dir='saved_models'  # specify your save directory here
    )# Create data loaders
    train_dataset = BinaryFaultDataset(X_train_norm.values, y_train.values)
    val_dataset = BinaryFaultDataset(X_val_norm.values, y_val.values)
    test_dataset = BinaryFaultDataset(X_test_norm.values, y_test.values)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    test_loader = DataLoader(test_dataset, batch_size=batch_size)

    # Initialize model and training components
    model = FaultDiagnosisModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = BCEWithLogitsLoss()

    # Train model
    best_model, history = train_model(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        criterion=criterion,
        optimizer=optimizer,
        epochs=epochs,
        fault_number=fault_to_diagnose
    )

    # Example of loading model for online prediction
    loaded_model, _ = load_model(fault_to_diagnose)

    # Example of online prediction with a sample window
    sample_window = X_test.iloc[:20]  # Example window size of 20
    predictions, probabilities = predict_online(loaded_model, scaler, sample_window)
    print("\nOnline Prediction Example:")
    print("Predictions:", predictions)
    print("Probabilities:", probabilities)
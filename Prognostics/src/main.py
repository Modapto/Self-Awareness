import torch
from data_processing import loadData, norm_
from model import Model


device = "cuda" if torch.cuda.is_available() else "cpu"

# init variables
min_engine_index = 1
max_engine_index = None  # This will be set later after loading the data


def process(engine_index):
    
    x_test, _ = loadData("4")
    best_model = Model().to(device)
    best_model.load_state_dict(torch.load('models/best_model_FD004.pth'))
    best_model.eval()

    min_engine_index = 1
    max_engine_index = len(x_test)
    
    with torch.no_grad():
        y_pred = best_model(x_test[engine_index].float())
    rul_prediction = norm_.y_scaler.inverse_transform(y_pred[-1, -1].cpu().numpy().reshape(-1, 1))[0, 0]
    
    print('\n Estimated Remaining useful life value: {}'.format(rul_prediction))
    
    return rul_prediction


if __name__ == "__main__":
    x_test, _ = loadData("4")
    best_model = Model().to(device)
    best_model.load_state_dict(torch.load('models/best_model_FD004.pth'))
    best_model.eval()

    min_engine_index = 1
    max_engine_index = len(x_test)

    while True:
        try:
            engine_index = int(input(
                f"Enter engine index (range {min_engine_index}-{max_engine_index}, default 57): ").strip() or "57")
            if min_engine_index <= engine_index <= max_engine_index:
                break
            else:
                raise ValueError(f"Engine index must be between {min_engine_index} and {max_engine_index}")
        except ValueError as e:
            print(f"Invalid input: {e}")


    with torch.no_grad():
        y_pred = best_model(x_test[engine_index].float())
    rul_prediction = norm_.y_scaler.inverse_transform(y_pred[-1, -1].cpu().numpy().reshape(-1, 1))[0, 0]
    print('\n Estimated Remaining useful life value: {}'.format(rul_prediction))
import torch
from data_processing import loadData, norm_
from model import Model

device = "cuda" if torch.cuda.is_available() else "cpu"

if __name__ == "__main__":
    x_test, _ = loadData("4")
    best_model = Model().to(device)
    best_model.load_state_dict(torch.load('models/best_model_FD004.pth'))
    best_model.eval()
    engine_index = 57
    with torch.no_grad():
        y_pred = best_model(x_test[engine_index].float())
    rul_prediction = norm_.y_scaler.inverse_transform(y_pred[-1, -1].cpu().numpy().reshape(-1, 1))[0, 0]
    print('\n Estimated Remaining useful life value: {}'.format(rul_prediction))
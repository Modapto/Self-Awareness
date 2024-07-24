import torch
import torch.nn as nn

class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()
        self.mlp1 = nn.Linear(24, 100)
        self.mlp2 = nn.Linear(100, 50)
        self.mlp3 = nn.Linear(50, 50)
        self.mlp4 = nn.Linear(50, 50)
        self.rnn1 = nn.LSTM(input_size=50, hidden_size=60, num_layers=1, batch_first=True)
        self.mlp5 = nn.Linear(60, 30)
        self.mlp6 = nn.Linear(30, 30)
        self.mlp7 = nn.Linear(30, 1)
        self.activation = nn.Tanh()

    def forward(self, x):
        o = self.activation(self.mlp1(x))
        o = self.activation(self.mlp2(o))
        o = self.activation(self.mlp3(o))
        f1 = self.activation(self.mlp4(o))
        self.rnn1.flatten_parameters()
        f2, _ = self.rnn1(f1)
        o = self.activation(self.mlp5(f2))
        o = self.activation(self.mlp6(o))
        o = self.activation(self.mlp7(o))
        return o
import pandas as pd
import plotly.graph_objects as go

from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import GroupShuffleSplit

import numpy as np
import copy

import torch
from torch.utils.data import Dataset, DataLoader
import torch.nn as nn
import torch.nn.functional as F
import sys

device = "cuda" if torch.cuda.is_available() else "cpu"



def import_(nb):

  # define column names
  index_names = ['ID', 'cycle']
  setting_names = ['set_1', 'set_2', 'set_3']
  sensor_names = ['sig_{}'.format(i) for i in range(1,22)] 
  col_names = index_names + setting_names + sensor_names

  # read data 
  # change path bellow !!
  train = pd.read_csv(('../Datasets/Cmapss/train_FD00' + nb + '.txt'), sep='\s+', header=None,
                      names=col_names)  # changed the separator from \s+ to ' ' because it doesn't need regex to consider multiple spaces, thus faster

  x_test = pd.read_csv(('../Datasets/Cmapss/test_FD00' + nb + '.txt'), sep='\s+', header=None,
                       names=col_names)
  y_test = pd.read_csv(('../Datasets/Cmapss/RUL_FD00' + nb + '.txt'), sep='\s+', header=None,
                       names=['RUL'])

  test_last_element = pd.concat([x_test.groupby('ID').last().reset_index(), y_test], axis=1)

  test = x_test.merge(test_last_element, left_on= col_names, right_on=col_names, how='left')

  return train, test

def addRUL_(df):

  # Max cycle of each engine
  grouped = df.groupby('ID')
  max_cycle = grouped["cycle"].max()

  #Add max Cycle to data
  result_df = df.merge(max_cycle.to_frame('max_cycle'), left_on='ID', right_index=True)

  #Calculate RUL and add it as ne column

  result_df["RUL"] = result_df["max_cycle"] - result_df["cycle"]
  result_df["RUL"].values[result_df["RUL"].values > 130] = 130
  # Drop max cycle column
  result_df = result_df.drop(["max_cycle"], axis=1)

  return result_df

def norm_(train, test):

  global x_scaler,y_scaler
  x_scaler = MinMaxScaler()
  y_scaler = MinMaxScaler()

  train[train.columns.difference(['ID','RUL'])] = x_scaler.fit_transform(train[train.columns.difference(['ID','RUL'])])
  train.loc[:,'RUL'] = y_scaler.fit_transform(train.loc[:,'RUL'].values.reshape(-1,1))
  
  test[test.columns.difference(['ID','RUL'])] = x_scaler.transform(test[test.columns.difference(['ID','RUL'])])
  test.loc[:,'RUL'] = y_scaler.transform(test.loc[:,'RUL'].values.reshape(-1,1))
  
  norm_.x_scaler = x_scaler
  norm_.y_scaler = y_scaler
  return train, test


def split_(df):

  train_inds, val_inds = next(GroupShuffleSplit(test_size=.25, n_splits=4, random_state = 7).split(df, groups=df['ID']))

  train = df.iloc[train_inds]
  val = df.iloc[val_inds]

  return train ,val

def tosequence_(df):

    X_reshaped = [] # create an empty list for input sequences 
    y_reshaped = [] # create an empty list for output sequences

    grouped = df.groupby('ID')
    
    for i in grouped.groups.keys(): # for each engine, reshape to (1, number of cycle, number of features)

      out = grouped.get_group(i)

      out = out.drop(['ID'], axis=1) #delete the ID column 

      X =  pd.DataFrame(out.iloc[:,:-1])
      y = out.iloc[:,-1:]

      X_reshaped.append(X.values.reshape(1, X.shape[0],  X.shape[1]))  
      y_reshaped.append(y.values.reshape(1, y.shape[0], y.shape[1]))


    return X_reshaped, y_reshaped

def loadData(num):
    df_train, df_test = import_(num) # import data
    df_train = addRUL_(df_train) # add RUL to dataset
    df_test["RUL"].values[df_test["RUL"].values > 130] = 130
    df_train, df_test = norm_(df_train, df_test) #normalize data
    df_test.drop("cycle",axis = 1, inplace=True)
    df_train.drop("cycle",axis = 1, inplace=True)

    train ,val = split_(df_train) # split to train and validation based on engine ID
    x_train,y_train = tosequence_(train) # convert 2D signals to sequences 
    x_val,y_val = tosequence_(val)
    x_test,y_test = tosequence_(df_test)


    x_train = [torch.from_numpy(item).float() for item in x_train]
    x_train = [x.to(device) for x in x_train]
    y_train = [torch.from_numpy(item).float() for item in y_train]
    y_train = [x.to(device) for x in y_train]

    x_val = [torch.from_numpy(item).float() for item in x_val]
    x_val = [x.to(device) for x in x_val]
    y_val = [torch.from_numpy(item).float() for item in y_val]
    y_val = [x.to(device) for x in y_val]

    x_test = [torch.from_numpy(item).float() for item in x_test]
    x_test = [x.to(device) for x in x_test]
    y_test = [torch.from_numpy(item).float() for item in y_test]
    y_test = [x.to(device) for x in y_test]

    return x_train, y_train, x_val, y_val, x_test, y_test

class data_(Dataset):

    def __init__(self, x_train, y_train):
      self.len = len(x_train)
      self.x_data = x_train
      self.y_data = y_train

    def __getitem__(self, index):
      return self.x_data[index], self.y_data[index]

    def __len__(self):
      return self.len

def pad_(x,y):
  X_lengths = [seq.size(1) for seq in x_train]
  longest_seq = max(X_lengths)
  padded_x =[torch.zeros(1, longest_seq,24) for i in range(len(x_train))]
  padded_y =[torch.zeros(1, longest_seq,24) for i in range(len(x_train))]
  for i, x_len in enumerate(X_lengths):
    m_seq = longest_seq - x_train[i].size(1)
    padded_x[i] = torch.cat((x_train[i], torch.zeros(1, m_seq,24).to(device)), 1).squeeze(0)
    padded_y[i] = torch.cat((y_train[i], torch.zeros(1, m_seq,1).to(device)), 1).squeeze(0)
  return padded_x,padded_y


def train_(model, loss, epochs, opt, train_loader, val_loader, print_all_epochs = True):

  bestmod = copy.deepcopy(model)
  bestvalloss = 99999999.

  train_.train_loss_list = []
  train_.val_loss_list =[]

  for epoch in range(1, epochs+1):
    train_loss = 0.
    val_loss = 0.

    model.train()

    for x, y in train_loader:
 
      opt.zero_grad()

      y_hat = model(x)  # forward path 
      cur_loss = loss(y_hat, y) #calculate loss between prediction and real value 
      cur_loss.backward() #backprop

      train_loss += cur_loss.item() #sum the losses
      opt.step()

    train_loss /= float(len(train_loader.dataset)) # mean of the loss
    train_.train_loss_list.append(train_loss)

    model.eval()

    with torch.no_grad():
      for x, y in val_loader:
        y_hat = model(x)
        cur_loss = loss(y_hat, y) 
        val_loss += cur_loss.item()


    val_loss /= float(len(val_loader.dataset))
    train_.val_loss_list.append(val_loss)

    if val_loss < bestvalloss :
        bestvalloss = val_loss

        print(f"best val loss {bestvalloss}")
        bestmod = copy.deepcopy(model)

    if epoch%10==0 or epoch < 6 or print_all_epochs: print("epoch %d , train_loss %f , val_loss %f" % (epoch, train_loss, val_loss))

    sys.stdout.flush()

  return bestmod

def plot_training_history():
  
  fig = go.Figure()
  df = pd.DataFrame(pd.DataFrame(list(zip(train_.train_loss_list, train_.val_loss_list)),columns = ["Train","Val"]))
  fig.add_trace(go.Scatter(x= df.index, y=df.iloc[:,0], name='train'))
  fig.add_trace(go.Scatter(x= df.index, y=df.iloc[:,1], name='val'))
  fig.show()

def predict_(model,x):
  
  y = []
  f_e1 = []
  f_e2 = []
  for e in x:
    y.append(model(e.float()))
    f_e1.append(f1)
    f_e2.append(f2)
  return y, f_e1 ,f_e2

def evaluate_train_(y_pred,y_true, plot_prediction_vs_real = False ):

  global score, mae, rmse
  score = 0.
  mae = torch.zeros(len(y_true))
  rmse = torch.zeros(len(y_true))

  loss = nn.L1Loss()
  mse = nn.MSELoss()
  global ypred ,ytrue
  ypred = []
  ytrue = []

  for i in range(len(y_true)):

    ypred.append(y_pred[i].view(y_pred[i].size(-2),-1))
    ytrue.append(y_true[i].view(y_true[i].size(-2),-1))

    ypred[-1] = torch.tensor(norm_.y_scaler.inverse_transform(ypred[-1].cpu().detach().numpy()))
    ytrue[-1] = torch.tensor(norm_.y_scaler.inverse_transform(ytrue[-1].cpu().detach().numpy()))

    mae[i] = loss(ypred[-1],ytrue[-1])
    rmse[i] = mse(ypred[-1],ytrue[-1])

    error = ypred[-1] - ytrue[-1] # compute the error
    for z in  range(error.shape[0]): # for each point inside sequence   
      score += torch.where( error[z] < 0., torch.exp(-error[z] /13 )- 1, torch.exp(error[z]/10) - 1) # compute the error 

  mae = torch.mean(mae.float())
  rmse = torch.sqrt(torch.mean(rmse.float()))

  print(f"MAE = {mae}")
  print(f"RMSE = {rmse}")
  print(f"Score = {score}")

  if plot_prediction_vs_real:
    fig = go.Figure()
    for i in range(len(ytrue)):
      df = pd.DataFrame()
      df['true'] = ytrue[i].cpu().detach().numpy().ravel()
  
      df['pred'] = ypred[i].cpu().detach().numpy().ravel()

      fig.add_trace(go.Scatter(x= df.index, y=df['true'] , name='true '+str(i),line=dict(color='royalblue', width=3)))
      fig.add_trace(go.Scatter(x= df.index, y=df['pred'] , name='pred'+str(i),line=dict(color='firebrick', width=3)))

    fig.update_layout(title='Real Vs Predicted RUL',
                   xaxis_title='Cycles',
                   yaxis_title='RUL')
    fig.show()

def evaluate_test_(y_pred,y_true):

  global score, mae, rmse
  score = 0.

  mae = torch.zeros(len(y_true))
  rmse = torch.zeros(len(y_true))


  loss = nn.L1Loss()
  mse = nn.MSELoss()

  ypred = []
  ytrue = []

  for i in range(len(y_pred)):

    ypred.append(torch.cat([y_pred[i][0,-1]]))
    ytrue.append(torch.cat([y_true[i][0,-1]])) 


    ypred[-1] = torch.tensor(norm_.y_scaler.inverse_transform(ypred[-1].cpu().detach().numpy().reshape(-1, 1)))
    ytrue[-1] = torch.tensor(norm_.y_scaler.inverse_transform(ytrue[-1].cpu().detach().numpy().reshape(-1, 1)))

    mae[i] = loss(ypred[-1],ytrue[-1])
    rmse[i] = mse(ypred[-1],ytrue[-1])
    
    error = ypred[-1] - ytrue[-1] # compute the error
    for z in  range(error.shape[0]): # for each point inside sequence   
      score += torch.where( error[z] < 0., torch.exp(-error[z] /13 )- 1, torch.exp(error[z]/10) - 1) # compute the error

  mae = torch.mean(mae.float())
  rmse = torch.sqrt(torch.mean(rmse.float()))

  print(f"MAE = {mae}")
  print(f"RMSE = {rmse}")
  print(f"Score = {score}")


# Model architecture 

class Model(nn.Module):
    def __init__(self):
        super(Model,self).__init__()

        self.mlp1 = nn.Linear(24,100)
        self.mlp2 = nn.Linear(100,50)
        self.mlp3 = nn.Linear(50,50)
        self.mlp4 = nn.Linear(50,50)

        self.rnn1 = nn.LSTM(input_size=50, hidden_size= 60, num_layers = 1, batch_first=True)
        
        self.mlp5 = nn.Linear(60,30)
        self.mlp6 = nn.Linear(30,30)
        self.mlp7 = nn.Linear(30,1)

        self.activation = nn.Tanh()
        
    def forward(self,x):

        o = self.activation(self.mlp1(x))
        o = self.activation(self.mlp2(o))
        o = self.activation(self.mlp3(o))

        global f1 , f2
        f1 = self.activation(self.mlp4(o))
        
        self.rnn1.flatten_parameters() 
        f2,_ = self.rnn1(f1)
        o = self.activation(self.mlp5(f2))
        o = self.activation(self.mlp6(o))
        o = self.activation(self.mlp7(o))
        return o


if __name__ == "__main__":
    x_train, y_train, x_val, y_val, x_test, y_test = loadData("1")  # load the dataset which number is entred

    x_train, y_train = pad_(x_train, y_train)  # pad train corpus so you can change batch numbers

    x_val = [x.squeeze(0) for x in x_val]
    y_val = [x.squeeze(0) for x in y_val]

    train_corpus = data_(x_train, y_train)  # corpus preparation
    val_corpus = data_(x_val, y_val)

    # hyper parameters
    batch_size = 5
    epochs = 500
    learning_rate = 0.0001

    train_loader = DataLoader(dataset=train_corpus, batch_size=batch_size, shuffle=True)  # corpus preparation
    val_loader = DataLoader(dataset=val_corpus, batch_size=1)

    num_model_runs = 1  # Number of models to train
    num_eval_runs = 1  # Number of evaluations per model
    best_mean_rmse = float('inf')
    best_mean_score = float('inf')
    best_model = None

    for model_run in range(num_model_runs):
        print(f"Model Run {model_run + 1}/{num_model_runs}")

        model = Model().to(device)
        opt = torch.optim.Adam(model.parameters(), lr=learning_rate)
        loss = nn.MSELoss()

        final_model = train_(model=model, loss=loss, epochs=epochs, opt=opt, train_loader=train_loader,
                             val_loader=val_loader)
        plot_training_history()
        # Multiple evaluations for this model
        rmse_list = []
        score_list = []
        for eval_run in range(num_eval_runs):
            y_pred_test, _, _ = predict_(final_model, x_test)
            evaluate_test_(y_pred_test, y_test)
            rmse_list.append(rmse.item())
            score_list.append(score.item())

        current_mean_rmse = np.mean(rmse_list)
        current_mean_score = np.mean(score_list)
        current_std_rmse = np.std(rmse_list)
        current_std_score = np.std(score_list)

        print(f"Model {model_run + 1} - Mean RMSE: {current_mean_rmse:.4f} ± {current_std_rmse:.4f}, "
              f"Mean Score: {current_mean_score:.4f} ± {current_std_score:.4f}")

        # Update best model based on mean RMSE
        if current_mean_rmse < best_mean_rmse:
            best_mean_rmse = current_mean_rmse
            best_mean_score = current_mean_score
            best_model = copy.deepcopy(final_model)
            print(f"New best model found! Mean RMSE: {best_mean_rmse:.4f}, Mean Score: {best_mean_score:.4f}")

    print(f"\nBest model - Mean RMSE: {best_mean_rmse:.4f}, Mean Score: {best_mean_score:.4f}")

    # Save the best model
    torch.save(best_model.state_dict(), 'best_model_FD001.pth')
    print("Best model saved as 'best_model_FD004.pth'")
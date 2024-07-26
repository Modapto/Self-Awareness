import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"

def import_(nb):
    index_names = ['ID', 'cycle']
    setting_names = ['set_1', 'set_2', 'set_3']
    sensor_names = ['sig_{}'.format(i) for i in range(1, 22)]
    col_names = index_names + setting_names + sensor_names

    train = pd.read_csv(f'./Datasets/Cmapss/train_FD00{nb}.txt', sep='\s+', header=None, names=col_names)
    x_test = pd.read_csv(f'./Datasets/Cmapss/test_FD00{nb}.txt', sep='\s+', header=None, names=col_names)
    y_test = pd.read_csv(f'./Datasets/Cmapss/RUL_FD00{nb}.txt', sep='\s+', header=None, names=['RUL'])

    test_last_element = pd.concat([x_test.groupby('ID').last().reset_index(), y_test], axis=1)
    test = x_test.merge(test_last_element, left_on=col_names, right_on=col_names, how='left')

    return train, test

def addRUL_(df):
    grouped = df.groupby('ID')
    max_cycle = grouped["cycle"].max()
    result_df = df.merge(max_cycle.to_frame('max_cycle'), left_on='ID', right_index=True)
    result_df["RUL"] = result_df["max_cycle"] - result_df["cycle"]
    result_df["RUL"].values[result_df["RUL"].values > 130] = 130
    result_df = result_df.drop(["max_cycle"], axis=1)
    return result_df

def norm_(train, test):
    x_scaler = MinMaxScaler()
    y_scaler = MinMaxScaler()

    train[train.columns.difference(['ID', 'RUL'])] = x_scaler.fit_transform(
        train[train.columns.difference(['ID', 'RUL'])])
    train.loc[:, 'RUL'] = y_scaler.fit_transform(train.loc[:, 'RUL'].values.reshape(-1, 1))
    test[test.columns.difference(['ID', 'RUL'])] = x_scaler.transform(test[test.columns.difference(['ID', 'RUL'])])
    test.loc[:, 'RUL'] = y_scaler.transform(test.loc[:, 'RUL'].values.reshape(-1, 1))

    norm_.x_scaler = x_scaler
    norm_.y_scaler = y_scaler
    return train, test

def tosequence_(df):
    X_reshaped = []
    y_reshaped = []
    grouped = df.groupby('ID')

    for i in grouped.groups.keys():
        out = grouped.get_group(i)
        out = out.drop(['ID'], axis=1)
        X = pd.DataFrame(out.iloc[:, :-1])
        y = out.iloc[:, -1:]
        X_reshaped.append(X.values.reshape(1, X.shape[0], X.shape[1]))
        y_reshaped.append(y.values.reshape(1, y.shape[0], y.shape[1]))
    return X_reshaped, y_reshaped

def loadData(num):
    df_train, df_test = import_(num)
    df_train = addRUL_(df_train)
    df_test["RUL"].values[df_test["RUL"].values > 130] = 130
    df_train, df_test = norm_(df_train, df_test)
    df_test.drop("cycle", axis=1, inplace=True)
    df_train.drop("cycle", axis=1, inplace=True)
    x_test, y_test = tosequence_(df_test)
    x_test = [torch.from_numpy(item).float().to(device) for item in x_test]
    y_test = [torch.from_numpy(item).float().to(device) for item in y_test]
    return x_test, y_test
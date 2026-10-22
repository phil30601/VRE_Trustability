

import numpy as np
import pandas as pd


def train_test_split(x_data, y_data, type, test, masterList):


#split dataset  


    if type == 'cell':
        cell_test = test
        cell_train = np.array([x for x in masterList.keys() if x not in cell_test])
        x_train, y_train =  x_data.loc[pd.IndexSlice[cell_train, : ], :] , y_data.loc[pd.IndexSlice[cell_train, :]]
        x_test, y_test = x_data.loc[pd.IndexSlice[cell_test, : ], :] , y_data.loc[pd.IndexSlice[cell_test, :]]
        print('Training list: ', cell_train)
        print('Testing list: ', cell_test) 
    elif type == 'cycle':
        #assuming one cell
        # max_cycle = int(x_data.iloc[x_data.reset_index()['cycle'].idxmax()].name)
        cycles = x_data.reset_index()['cycle'].unique()



        cycle_test = list(test)
        cycle_train = list(np.array([x for x in cycles if x not in cycle_test]))
        print('Training list: ', cycle_train)
        print('Testing list: ', cycle_test) 
        
        x_train, y_train =  x_data.loc[pd.IndexSlice[cycle_train], :] , y_data.loc[pd.IndexSlice[cycle_train]]
        x_test, y_test = x_data.loc[pd.IndexSlice[cycle_test], :] , y_data.loc[pd.IndexSlice[cycle_test]]

    return x_train, y_train, x_test, y_test

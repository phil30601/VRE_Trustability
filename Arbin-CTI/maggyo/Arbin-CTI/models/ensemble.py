#This file is used to load the ensemble model and make predictions based on the provided input data.

import joblib
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import RobustScaler
import pickle
import warnings
warnings.filterwarnings('ignore') 

#load the ensemble model
model = []
num_models = 5
for i in range(num_models):
    model.append(tf.keras.models.load_model(r"D:\source\repos\maggyo\Arbin-CTI\models\ensemble\model_" + str(i)))

#load in feature scaler, model parameters, and reference voltages
scaler = pickle.load(open(r"D:\source\repos\maggyo\Arbin-CTI\parameters\scaler.pkl", 'rb'))
model_params = pickle.load(open(r"D:\source\repos\maggyo\Arbin-CTI\parameters\cell_params.pkl", 'rb'))
reference_voltage = pickle.load(open(r"D:\source\repos\maggyo\Arbin-CTI\parameters\reference_voltages.pkl", 'rb'))

#import feature conversion

#input_datas: 
#Rows: data up to 8 seconds before
#Columns: 0-Voltage   1-Power   2-Current 3-ChargeCapacity  4-ChargeEnergy    5-Throughput;
       
def predict(input_datas, channel_num):
    
    channel_num = str(channel_num+1)
    input_datas = np.reshape(input_datas, (5,6))

    #['Energy', 'Capacity', 'Voltage-8', 'Energy-8', 'Power-8']
    input_data =[input_datas[0,4]/model_params["nom_energy"]*100, input_datas[0,3]/model_params["nom_cap"]*100, 
                input_datas[4,0], input_datas[4,4]/model_params["nom_energy"]*100, 
                input_datas[4,1]]
    print(input_data)

    #reshape into model inputtable array
    input_data = np.reshape(input_data, (1,5))
    input_data = scaler.transform(input_data)
    
    num_models = 5
    yPred_list = []
    for i in range(num_models): #make predictions
        
        yPred_list.append(model[i].predict(input_data[0:1,:]).flatten())
        
    yPred = np.array(yPred_list).mean(axis = 0)
 
    return yPred[0]

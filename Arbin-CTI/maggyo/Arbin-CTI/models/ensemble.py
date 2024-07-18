import joblib
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import RobustScaler
import pickle
# import gpflow#
import warnings
warnings.filterwarnings('ignore') 

# model_path = 'baseline'
model = []
num_models = 5
for i in range(num_models):
    model.append(tf.keras.models.load_model(r"D:\source\repos\maggyo\Arbin-CTI\models\ensemble\model_" + str(i)))


scaler = pickle.load(open(r"D:\source\repos\maggyo\Arbin-CTI\parameters\scaler.pkl", 'rb'))
model_params = pickle.load(open(r"D:\source\repos\maggyo\Arbin-CTI\parameters\cell_params.pkl", 'rb'))
reference_voltage = pickle.load(open(r"D:\source\repos\maggyo\Arbin-CTI\parameters\reference_voltages.pkl", 'rb'))


#import feature conversion

#input_datas: rows of data up to 8 seconds before
# 0Voltage   1Power   2Current 3ChargeCapacity  4ChargeEnergy    5Throughput;
       
def predict(input_datas, channel_num):
    
    channel_num = str(channel_num+1)
    input_datas = np.reshape(input_datas, (5,6))

                    
                    #['Energy', 'Power', 'Energy-8', 'Power-8', 'Capacity*Overpotential-8']

    #input_data = [input_datas[0,4]/model_params["nom_energy"]*100, input_datas[0,1], input_datas[4,4]/model_params["nom_energy"]*100, input_datas[4,1], 0]
    
    #Model-2023-11-09 ['Voltage', 'Throughput', 'Energy', 'Capacity', 'Power’]
    #input_data =[input_datas[0,0], input_datas[0,5], 
    #            input_datas[0,4]/model_params["nom_energy"]*100, input_datas[0,3]/model_params["nom_cap"]*100, 
    #            input_datas[0,1]]
    
    #Model-2023-11-29 ['Throughput', 'Energy', 'Voltage-8', 'Energy-8', 'Power-8']
    # input_data =[input_datas[0,5], input_datas[0,4]/model_params["nom_energy"]*100, 
    #             input_datas[4,0], input_datas[4,4]/model_params["nom_energy"]*100, 
    #             input_datas[4,1]]
    # print(input_data)

    #Model-2024-04-15 ['Energy', 'Capacity', 'Voltage-8', 'Energy-8', 'Power-8']
    input_data =[input_datas[0,4]/model_params["nom_energy"]*100, input_datas[0,3]/model_params["nom_cap"]*100, 
                input_datas[4,0], input_datas[4,4]/model_params["nom_energy"]*100, 
                input_datas[4,1]]
    print(input_data)

    #try:
    #    input_data[4] = input_datas[4,3]/model_params["nom_cap"]*100 * reference_voltage[channel_num](input_datas[4,3]/model_params["nom_cap"]*100)
    #except Exception as e:
    #    print('failed ' + e)
    #    return
    
    #reshape into model inputtable array
    input_data = np.reshape(input_data, (1,5))
    # print(input_data)
    input_data = scaler.transform(input_data)
    
    num_models = 5
    yPred_list = []
    for i in range(num_models):
        
        yPred_list.append(model[i].predict(input_data[0:1,:]).flatten())
        
    yPred = np.array(yPred_list).mean(axis = 0)
 
    return yPred[0]

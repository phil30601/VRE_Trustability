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
    model.append(tf.keras.models.load_model(r"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\models\ensemble\model_" + str(i)))


scaler = pickle.load(open(r"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\scaler.pkl", 'rb'))

model_params = pickle.load(open(r"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\cell_params.pkl", 'rb'))
reference_voltage = pickle.load(open(r"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\reference_voltages.pkl", 'rb'))




#import feature conversion

#input_datas: rows of data up to 8 seconds before
# Voltage   Power   Current ChargeCapacity  ChargeEnergy    Throughput;
       
def predict(input_datas, channel_num):
    
    channel_num = str(channel_num+1)
    input_datas = np.reshape(input_datas, (5,6))

                    
                    #['Voltage', 'Energy', 'Power', 'Current*Overpotential', 'Power-8']

    input_data = [input_datas[0,0], input_datas[0,4], input_datas[0,1], 0, input_datas[1,4]]
    
    try:
        input_data[4] = input_datas[0,2]* reference_voltage[channel_num](input_datas[0,3]/model_params["nom_cap"]*100)
    except Exception as e:
        print(e)
        return
        # print("failed")
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

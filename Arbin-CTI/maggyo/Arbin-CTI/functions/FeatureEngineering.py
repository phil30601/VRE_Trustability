import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from scipy import integrate
import pandas as pd
from scipy.interpolate import interp1d


#get charging data from data
def preprocessing_charging_data(masterInput):
    xData = masterInput[masterInput.Current < 0].dropna()[['Time', 'Voltage', 'Current', 'Energy', 'Capacity']]
    yData = masterInput[masterInput.Current < 0].dropna()[['NEP']]

    #Create throughput feature
    throughput = masterInput.groupby('C-rate', sort = True)['Capacity'].apply(lambda x: x.diff().abs().cumsum())
    throughput.rename("Throughput", inplace= True)
    throughput = throughput[masterInput.Current < 0]
    xData = pd.concat([xData, throughput], axis = 1)
    return xData, yData

##create constant current dataaset
def create_CC_data(x_data,  y_data):
    xCC =  x_data[(x_data['Current'] < 0) & (x_data['Voltage'] < 4.19)]
    yCC =  y_data[(x_data['Current'] < 0) & (x_data['Voltage'] < 4.19)]

    yCC = yCC[xCC.index.get_level_values(1) >= 0]
    xCC = xCC[xCC.index.get_level_values(1) >= 0]

    xCC.replace([np.inf, -np.inf], np.nan, inplace=True)
    #yCC.replace([np.inf, -np.inf], np.nan, inplace=True, axis = 1)
    xCC.dropna(inplace = True, axis = 1)
    xCC.dropna(inplace = True, axis = 0)



    from scipy.signal import savgol_filter

    # xCC['Current'] = xCC.groupby(['C-rate', 'cycle'], sort = True).size
    temp = (xCC.groupby(x_data.index.names, sort = True).apply(lambda g: savgol_filter(g.Voltage, 21, 1)))
    xCC['Voltage'] = pd.concat(pd.DataFrame(temp.loc[(i)]) for i in temp.index).to_numpy()

    temp = (xCC.groupby(x_data.index.names, sort = True).apply(lambda g: savgol_filter(g.Current, 21, 1)))
    xCC['Current'] = pd.concat(pd.DataFrame(temp.loc[(i)]) for i in temp.index).to_numpy()

    return xCC, yCC


#create features for charging
def create_charging_features(x_data, y_data, fReference, cell_params):
    

    #overpotential
    # temp = x_data.groupby(x_data.index.names).apply(lambda g: abs(integrate.cumulative_trapezoid(g.Current, x=g.Time, initial = 0)))/3600


    # x_data['Capacity'] =  pd.concat(pd.DataFrame(temp.loc[(i)]) for i in temp.index).to_numpy()

    socData = x_data['Capacity'].apply(lambda x: x/cell_params["nom_cap"]*100)
    socData[socData < 0] = 0
    socData[socData > 100] = 100
    # print(socData)
    x_data['Capacity'] = socData
    # print(x_data(capacity))

    def eta_volt(subset, volt, reference, cap):
        a = subset.index[1]
        return volt - reference[a[0], 0](cap)

    def eta_cap(subset, volt, reference, cap):
        a = subset.index[1]
        return cap - reference[a[0], 1](volt)

    # print('okay')
    temp = x_data.groupby(x_data.index.names).apply(lambda g: eta_volt(g, g.Voltage, fReference, g.Capacity))
    temp.index = temp.index.droplevel(2).droplevel(2)
    x_data['Overpotential'] =  temp


    # temp = x_data.groupby(x_data.index.names).apply(lambda g: eta_cap(g, g.Voltage, fReference, g.Capacity))
    # temp.index = temp.index.droplevel(2).droplevel(2)
    # x_data['Cap_overpotential'] = temp

    # dq_dv
    # global funcs 
    # funcs = x_data.groupby(x_data.index.names).apply(lambda g: interp1d(g.Voltage, g.Capacity, kind = 'cubic', fill_value='extrapolate'))

    # def funcslist(a, volt, cap):
    #     global funcs
    #     x = funcs.loc[a.index[1]]
    #     dq_dv = (cap - x(volt - 0.0005)) / 0.0005
    #     dq_dv[volt - 0.0005 < min(volt)] = 0
    #     return dq_dv

    # dq_dv = x_data.groupby(x_data.index.names).apply(lambda g: funcslist(g, g.Voltage, g.Capacity))
    # dq_dv.index = dq_dv.index.droplevel(2).droplevel(2)

    # x_data['dQ_dV'] = dq_dv

    ###CHECK  ADFJASDKFJASKDFJASD
    # x_data['Capacity'] = x_data['Capacity']/cell_params["nom_cap"]*100
    x_data['Energy'] = x_data['Energy'].abs()/cell_params["nom_energy"]*100
    x_data['Throughput'] = x_data['Throughput']/cell_params["nom_cap"]*100



    #create derivative feature
    derivInput = x_data.groupby(x_data.index.names).diff().fillna(0)
    derivInput.columns = [ "d" + col + "/dt"  for col in x_data.columns]
    x_data = pd.concat((x_data, derivInput), axis = 1)
    del derivInput
    x_data.drop(['dTime/dt', 'dCurrent/dt', 'dThroughput/dt'], axis = 1, inplace = True )

    #Create multiplication features
    # pidx = np.indices((x_data.shape[1], x_data.shape[1])).reshape(2,-1).T
    # uniqueIdx ={tuple(sorted(item)) for item in pidx}
    # pidx = np.array(list(uniqueIdx)).T
    # colNames =  [ "*".join( [ x_data.columns[i[0]], x_data.columns[i[1]]  ]) for i in uniqueIdx ] 
    # #multInput = pd.CCFrame(inputCC.values[:, pidx[0]] * inputCC.values[:, pidx[1]] , columns=colNames, axis = "index")
    # # print(pidx[0])
    # multInput = np.multiply(x_data.iloc[:, pidx[0]], x_data.iloc[:, pidx[1]])
    # multInput.columns = colNames
    # x_data = pd.concat([x_data, multInput], axis = 1)

    x_data['Capacity*Current'] = x_data['Capacity']*x_data['Current']
    x_data['Power'] = x_data['Voltage']*x_data['Current']
    x_data['Current*Energy'] =  x_data['Energy']*x_data['Current']
    x_data['Power*Overpotential'] = x_data['Power']*x_data['Overpotential']
    x_data['Voltage*Overpotential'] = x_data['Voltage']*x_data['Overpotential']
    x_data['Current*Overpotential'] = x_data['Current']*x_data['Overpotential']
    # x_data['Current*Cap_overpotential'] = x_data['Current']*x_data['Cap_overpotential']

    x_data['Energy*Overpotential'] = x_data['Energy']*x_data['Overpotential']
    x_data['Capacity*Overpotential'] = x_data['Capacity']*x_data['Overpotential']
    # x_data['Capacity*Cap_overpotential'] = x_data['Capacity']*x_data['Cap_overpotential']
    # x_data['Overpotential*Cap_overpotential'] = x_data['Overpotential']*x_data['Cap_overpotential']
    # x_data['CE*Capacity'] = x_data['Capacity']*x_data['CE']
    # x_data['VE*Capacity'] = x_data['Capacity']*x_data['VE']
    # x_data['VE*Voltage'] = x_data['Voltage']*x_data['VE']
    # x_data['EE*Capacity'] = x_data['Capacity']*x_data['EE']
    # x_data['EE*Overpotential'] = x_data['Overpotential']*x_data['EE']
    # x_data['VE*Overpotential'] = x_data['Overpotential']*x_data['VE']
    x_data['Capacity*dEnergy/dt'] = x_data['Capacity']*x_data['dEnergy/dt']


    # x_data['Cycle*Capacity'] = x_data.index.get_level_values(0)*x_data['Capacity']
    # x_data['Cycle*Energy'] = x_data.index.get_level_values(0)*x_data['Energy']
    # x_data['Cycle*Overpotential'] = x_data.index.get_level_values(0)*x_data['Overpotential']
    # x_data['Cycle*Voltage'] = x_data.index.get_level_values(0)*x_data['Voltage']
    # x_data['Cycle*Cap_overpotential'] = x_data.index.get_level_values(0)*x_data['Cap_overpotential']

    #Create log features
    # logInput = np.log(abs(x_data))
    # logInput.columns = [ "log " + col  for col in logInput.columns]
    # logInput.head()

    #Create exp features
    # expInput = np.exp(x_data)
    # expInput.columns = [ "exp " + col  for col in expInput.columns]


    # x_data = pd.concat([x_data, multInput, logInput, expInput], axis = 1)


    # x_data.drop(('Capacity'), axis = 1, inplace=True)


    #x_data.head()

    x_data.replace([np.inf, -np.inf], np.nan, inplace=True)
    #y_data.replace([np.inf, -np.inf], np.nan, inplace=True, axis = 1)
    x_data.dropna(inplace = True, axis = 1)
    x_data.dropna(inplace = True, axis = 0)
    y_data.dropna(inplace= True)



    lagInput = x_data.copy()
    nameList = x_data.columns
    for i in range(8,0,-2):	

        names = [ name + '-'+str(i) for name in nameList]
        lagInput[names] = x_data.groupby(x_data.index.names)[nameList].shift(i)




    print(x_data.shape)
    
    # print(~lagInput.isnull().any(axis=1))
    y_data = y_data[~lagInput.isnull().any(axis=1)]
    lagInput.dropna(inplace=True, axis = 0)
    x_data = lagInput
    # print(x_data.shape)

    return x_data, y_data

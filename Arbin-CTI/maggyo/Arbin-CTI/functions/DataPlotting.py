import matplotlib
from matplotlib import pyplot as plt
import numpy as np
import math
import warnings


def plot_voltage_distribution(x_data, y_data, cellNum, cycle, masterList):

    fig, axs = plt.subplots(2,5, figsize = (10,10))
    # cmap = plt.cm.viridis(np.linspace(0,1,4))
    # for i in range(figDim[0]):
    #     for j in range(figDim[1]):
    #         axs[i, j].set_prop_cycle('color', cmap)


    w = 0.05

    volt_pop = y_data.copy()
    n = math.ceil((volt_pop.max() - volt_pop.min())/w)


    for i in range(axs.shape[0]):
        for j in range(axs.shape[1]):
            # volt_sample = xCC.loc[cellNum, 5]['Voltage'].to_numpy()
            volt_sample = y_data.loc[cellNum,cycle].to_numpy()

            axs[i,j].hist(volt_sample, bins = n, label = cellNum)
            if(i == 1):
                axs[i,j].set_xlabel('Anode voltage')
            axs[i,j].set_title(str(cellNum) +  ', ' + str(masterList[cellNum]) + 'C')

            # axs[i,j].set_xticks([3.5, 3.75, 4, 4.25])
            axs[i,j].set_xticks([-0.1, 0, 0.1, 0.2, 0.3])
            cellNum+=1
            # break
            
    # plt.ylabel('Frequency')
    # plt.legend()

#accepts whole datafrmae, where cellNum and cols specify what to plot
def plot_multiple_cycles_one_cell(x_data, y_data, cellNum, cols, c_rate):


    matplotlib.rc('xtick', labelsize=12) 
    matplotlib.rc('ytick', labelsize=12) 

    #Plot the features
    maxCycles = x_data.loc[cellNum].index.unique().max()
    cmap = plt.cm.viridis(np.linspace(0,1, maxCycles))

    

    #Specify how to distribute the plots
    if len(cols) == 6:
        figDim = [2,3]
    else:
        figDim = [1,1]

    figDim = [int(np.ceil(len(cols)/3)), 3]
    if(len(cols) == 1):
        figDim = [1,1]
        fig, axs = plt.subplots(figDim[0],figDim[1], figsize = (6,4.5))
        axs.set_prop_cycle('color', cmap)
        
    
        for cycle in range(1, maxCycles,1):
            try:
                axs.plot(x_data.loc[cellNum, cycle][cols], y_data.loc[cellNum, cycle][:])
            except:
                warnings.warn("cannot plot cell #" + str(cellNum) + ", cycle " + str(cycle))

        #axs.set_yticks([-0.1, -0.05, 0, 0.05, 0.1])
        axs.set_yticks([-0.2, 0, 0.2, 0.4, 0.6, 0.8])
        
        axs.set_xlabel(cols[0])
        plt.setp(axs, ylabel='Anode V')


    else:
        fig, axs = plt.subplots(figDim[0],figDim[1], figsize = (10,50))
        
        for i in range(figDim[0]):
            for j in range(figDim[1]):
                axs[i, j].set_prop_cycle('color', cmap)

        i = 0
        j = 0

    

        for index, col in enumerate(x_data[cols]):
            if(j == figDim[1]):
                j = 0
                i+=1
                if i == figDim[0]: break
            for cycle in range(1, maxCycles,2):
                try:
                    axs[i,j].plot(x_data.loc[cellNum, cycle][col], y_data.loc[cellNum, cycle][:])
                    axs[i,j].set_yticks([-0.1, -0.05, 0, 0.05, 0.1])
                    if(np.any(x_data.loc[cellNum,cycle]['Voltage'] < 3.3)):
                        print(cycle)
                except:
                    warnings.warn("cannot plot cell #" + str(cellNum) + ", cycle " + str(cycle))
            if j != 0:
                axs[i,j].set_yticks([])
            axs[i,j].set_xlabel(col, fontsize=8)
            j+=1
            #time.sleep(2)  

        plt.setp(axs[:, 0], ylabel='Anode V')
       
        # axs.set_yticks([-0.1, -0.05, 0, 0.05, 0.1])

    sm = plt.cm.ScalarMappable(cmap= plt.get_cmap('viridis'), norm=plt.Normalize(vmin=1, vmax= maxCycles))
    legLabel = np.array( np.arange(1, maxCycles, 5))
    fig.colorbar(sm, ticks = legLabel, label = 'Cycles', ax = axs, orientation = 'vertical', fraction = .1)
    fig.suptitle('Cell ' + str(cellNum) + ', Charged at ' + c_rate + 'C') 


def plot_one_cycle_multiple_cells(x_data, y_data, cycle, cell_train, cell_test, cols):

    #Plot the features

    matplotlib.rc('xtick', labelsize=12) 
    matplotlib.rc('ytick', labelsize=12) 

    #Specify how to distribute the plots
    figDim = [int(np.ceil(len(cols)/3)), 3]
    if(len(cols) == 1):
        figDim = [1,1]

    fig, axs = plt.subplots(figDim[0],figDim[1], figsize = (10,50))
    cmap = plt.cm.viridis(np.linspace(0,1,len(cell_train)+len(cell_test)))
    for i in range(figDim[0]):
        for j in range(figDim[1]):
            axs[i, j].set_prop_cycle('color', cmap)


    i = 0
    j = 0

 

    # cols = ['Voltage', 'Energy', 'dVoltage/dt', 'Time', 'Overpotential', 'Capacity']
    # cols = use_cols


    for index, col in enumerate(x_data[cols]):
        if(j == figDim[1]):
            j = 0
            i+=1
            if i == figDim[0]: break
        for cellNum in cell_train:
            try:
                axs[i,j].plot(x_data.loc[cellNum, cycle][col], y_data.loc[cellNum, cycle][:])
                # print(cellNum)
                # axs[i,j].plot(x_data.loc[cellNum, cycle][col], x_data.loc[cellNum, cycle]['Voltage'])
            except:
                print('failed ' + str(cellNum) + ' ' + str(cycle))
        for cellNum in cell_test:
            try:
                axs[i,j].plot(x_data[col].loc[cellNum, cycle],  y_data.loc[cellNum, cycle], 'r')
                # print('fail')
            except:
                print('fail')
        if j != 0:
            axs[i,j].set_yticks([])
        axs[i,j].set_xlabel(col, fontsize=8)
        # axs[i,j].set_ylim([-0.05, 0.05])
        j+=1

        plt.setp(axs[:, 0], ylabel='Anode V')   
        sm = plt.cm.ScalarMappable(cmap= plt.get_cmap('viridis'), norm=plt.Normalize(vmin=min(cell_train), vmax= max(cell_train)))
        

    legLabel = cell_train
    fig.colorbar(sm, ticks = legLabel, label = 'Cell', ax = axs, orientation = 'vertical', fraction = .1)
    fig.suptitle('Cycle ' + str(cycle)) 
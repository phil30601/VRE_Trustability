# Arbin-CTI

Updated code is located in the DynamicCharging folder.

This program uses C# to make calls to ML models built in Python for dynamically charging your batteries. To use your own model on a set of cells, follow these steps:

1. Modify ChannelConfig.txt using the explained format to record information about the cell.
2. Put your model (usually saved as .pkl) in the "models" folder with a "predict" function.
3. Modify the input_data block of your model based on the features of your model.
  \  a. If you model requires features like overpotential that rely on activation cycles, run Get_Activation.ipynb
  \  b. Modify scaler.pkl based on the features loaded in (stop cti and restart it when neccessary)
4. Check that your cell was added in the Console.
5. Change the scaler.pkl in parameters folder
6. Visualize your 2E cell performance using Visualize_2E_Data.ipynb

If you want to test other configurations without disturbing the DynamicCharging code, you can create a copy of the DynamicCharging solution and develop from there. Please do not use the same channels for the two solutions if you plan on writing outputs to a text file however.
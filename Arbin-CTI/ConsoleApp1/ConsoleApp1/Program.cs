/*
* ==============================================================================
* Filename: ArbinClientTests
* Description: This file contains test methods for testing various functions of ArbinClient class.
* DynamicML is the main code file which is used for running the 2E cycling procedure. Program.cs is used for testing purposes and therefore will not save any data.
* ==============================================================================
*/
using System;
using System;
using System.Collections.Generic;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ArbinCTI.Core;
using ArbinCTI.Core.Control;
using ArbinCTI.Core.Inteface;
//using CsvHelper;
using Python.Runtime;

namespace ArbinCTI.Core
{
    /// <summary>
    /// <para>The <see cref="ArbinCTI.Core"/> Provide connection service.</para>
    /// <para><see cref="ArbinClient"/> is used to connect to CTI.</para>
    /// <see cref="ArbinCommand"/> contains the basic information of the CTI return packet, which is the main base class for all command classes.
    /// </summary>
    public class ArbinClientTests
    {
        private ArbinClient client;
        private MyArbinControl ctrl;
        MyTestData testData;
        private bool? connected;
        static string[] lines = File.ReadAllLines(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\TestConfig.txt");
        private readonly string MyIP = lines[0];
        private readonly string UserName = lines[1];
        private readonly string Password = lines[2];
        private readonly string Schedule = lines[3];
        private readonly string SerialNumber = lines[4];
        private float NominalCapacity = float.Parse(lines[5]);
        private readonly int WrongChnlIndex = int.Parse(lines[9]);
        readonly static DateTime A = DateTime.Now;
        readonly static string B = A.ToString("yy/MM/dd HH/mm/ss");
        readonly static string TestName = lines[6] + B;

        readonly string channelNumbers = lines[7] + " " + lines[8];
        private readonly List<ushort> Chnl_3E = new List<ushort>();
        private readonly List<ushort> Chnl_2E = new List<ushort>();
        private readonly List<ushort> Chnl = new List<ushort>();

        private List<Battery> BatteryList = new List<Battery>();

        private DateTime channelConfigLastModified = DateTime.Now;

        public class Battery
        {
            private ushort channelNum;
            private string cellType;
            private float current;
            private double voltage;
            private double time;
            private double prevTime;
            private double throughput;
            private string modelName;
            private int countChanges;

            private double threshold;

            private double[,] input_datas = new double[5, 6];



            public Battery(ushort chnl, string cell, string model, double curr, double threshold)
            {
                this.channelNum = chnl;
                this.cellType = cell;
                this.modelName = model;
                this.current = (float)curr;
                this.prevTime = -1;
                this.threshold = threshold;
                this.countChanges = 0;
            }

            public ushort ChannelNum
            {
                get { return channelNum; }
                set { channelNum = value; }
            }
            public string CellType
            {
                get { return cellType; }
                set { cellType = value; }
            }

            public string ModelName
            {
                get { return modelName; }
                set { modelName = value; }
            }

            public float Current { get { return current; } set { current = value; } }
            public double Voltage { get { return voltage; } set { voltage = value; } }
            public double Time { get { return time; } set { time = value; } }
            public double PrevTime { get { return prevTime; } set { prevTime = value; } }

            public double Throughput { get { return throughput; } set { throughput = value; } }
            public double Threshold { get { return threshold; } set { threshold = value; } }

            public int CountChanges { get { return countChanges; } set { countChanges = value; } }

            public double GetInputDatas(int i, int j)
            { return input_datas[i, j]; }
            public void SetInputDatas(int i, int j, double value)
            {
                input_datas[i, j] = value;
            }

            public double[,] GetInputDatas()
            {
                return input_datas;
            }

        }

        public class MyTestData
        {
            public ArbinCommandLoginFeed LoginFeed { get; set; }
            public ArbinCommandAssignScheduleFeed ScheduleFeed { get; set; }
            public ArbinCommandLogicConnectFeed LogicConnectFeed { get; set; }
            public ArbinCommandStartChannelFeed StartChannelFeed { get; set; }
            public ArbinCommandBrowseDirectoryFeed BrowseDirectoryFeed { get; set; }
            public ArbinCommandStopChannelFeed StopChannelFeed { get; set; }
            public ArbinCommandGetSerialNumberFeed GetSerialNumberFeed { get; set; }
            public ArbinCommandResumChanneleFeed resumChanneleFeed { get; set; }
            public ArbinCommandNewOrDeleteFeed NewOrDeleteFeed { get; set; }
            public ArbinCommandJumpChannelFeed JumpChannelFeed { get; set; }
            public ArbinCommandGetStartDataFeed GetStartDataFeed { get; set; }
            public ArbinCommandGetChannelDataFeed GetChannelDataFeed { get; set; }
            public ArbinCommandSetMetaVariableFeed SetMetaVariableFeed { get; set; }
            public ArbinCommandUpLoadFileFeed UpLoadFileFeed { get; set; }
            public ArbinCommandSendMsgToCTIFeed SendMsgToCTIFeed { get; set; }
        }
        public class MyArbinControl : ArbinControl
        {
            public MyTestData TestData { get; }
            public delegate void UploadFileFeedbackEvent(ArbinCommandUpLoadFileFeed feedback);
            public event UploadFileFeedbackEvent UploadFileFeedback;

            public override void OnGetStatusExtendInformationBack(ArbinCommandGetChannelInfoExFeed cmd)
            {

            }
            public override void OnGetResumeDataBack(ArbinCommandGetResumeDataFeed cmd)
            {

            }

            public override void OnGetChannelsDataMinimalistModeFeedBack(ArbinCommandGetChannelDataMinimalistModeFeed cmd)
            {

            }
            public override void OnCheckFileBack(ArbinCommandCheckFileFeed cmd)
            {

            }
            public override void OnGetChannelsDataSimpleModeFeedBack(ArbinCommandGetChannelDataSimpleModeFeed cmd)
            {

            }
            public override void OnAssignFileFeedBack(ArbinCommandAssignFileFeed cmd)
            {

            }
            public override void OnUpdateParametersBack(ArbinCommandUpdateParameterFeed cmd)
            {
            }
            public override void OnDownLoadFileBack(ArbinCommandDownLoadFileFeed cmd)
            {

            }
            public override void OnApplyForUDPCommunicationFeedBack(ArbinCommandApplyForUDPCommunicationFeed cmd)
            {
                //throw new NotImplementedException();
            }
            public override void OnGetMetaVariablesFeedBack(ArbinCommandGetMetaVariablesFeed cmd)
            {
                //throw new NotImplementedException();
            }
            public override void OnConvertToAnonymousOrNamedTOBack(ArbinCommandConvertToAnonymousOrNamedTOFeed cmd)
            {
                //throw new NotImplementedException();
            }
            public override void OnSetIntervalTimeLogDataFeedBack(ArbinCommandSetIntervalTimeLogDataFeed cmd)
            {
                //throw new NotImplementedException();
            }

            public override void OnNewFolderBack(ArbinCommandNewFolderFeed cmd)
            {
                //throw new NotImplementedException();
            }

            public MyArbinControl(MyTestData testData)
            {
                TestData = testData;
            }
            public override void OnAssignScheduleFeedBack(ArbinCommandAssignScheduleFeed cmd)
            {
                Console.WriteLine("adsf");
                TestData.ScheduleFeed = cmd;
            }
            public override void OnBrowseDirectoryBack(ArbinCommandBrowseDirectoryFeed cmd)
            {
                TestData.BrowseDirectoryFeed = cmd;
            }
            public override void OnGetChannelsDataFeedBack(ArbinCommandGetChannelDataFeed cmd)
            {
                TestData.GetChannelDataFeed = cmd;
            }
            public override void OnGetSerialNumberFeedBack(ArbinCommandGetSerialNumberFeed cmd)
            {
                TestData.GetSerialNumberFeed = cmd;
            }
            public override void OnGetStartDataBack(ArbinCommandGetStartDataFeed cmd)
            {
                TestData.GetStartDataFeed = cmd;
            }
            public override void OnJumpChannelFeedBack(ArbinCommandJumpChannelFeed cmd)
            {
                TestData.JumpChannelFeed = cmd;
            }
            public override void OnLogicConnectFeedBack(ArbinCommandLogicConnectFeed cmd)
            {
                TestData.LogicConnectFeed = cmd;
            }
            public override void OnNewOrDeleteBack(ArbinCommandNewOrDeleteFeed cmd)
            {
                TestData.NewOrDeleteFeed = cmd;
            }
            public override void OnResumeChannelFeedBack(ArbinCommandResumChanneleFeed cmd)
            {
                TestData.resumChanneleFeed = cmd;
            }
            public override void OnSendMsgToCTIBack(ArbinCommandSendMsgToCTIFeed cmd)
            {
                TestData.SendMsgToCTIFeed = cmd;
            }
            public override void OnSetMetaVariableFeedBack(ArbinCommandSetMetaVariableFeed cmd)
            {
                TestData.SetMetaVariableFeed = cmd;
            }
            public override void OnStartAutomaticCalibrationBack(ArbinCommandStartAutomaticCalibrationFeed cmd)
            {

            }
            public override void OnStartChannelFeedBack(ArbinCommandStartChannelFeed cmd)
            {
                TestData.StartChannelFeed = cmd;
            }
            public override void OnStopChannelFeedBack(ArbinCommandStopChannelFeed cmd)
            {
                TestData.StopChannelFeed = cmd;
            }
            public override void OnUpdateMetaVariableAdvancedFeedBack(ArbinCommandUpdateMetaVariableAdvancedFeed cmd)
            {
            }
            public override void OnUpLoadFileBack(ArbinCommandUpLoadFileFeed cmd)
            {
            }
            public override void OnUserLoginFeedBack(ArbinCommandLoginFeed cmd)
            {
                TestData.LoginFeed = cmd;
            }
            public override void OnContinueChannelFeedBack(ArbinCommandContinueChannelFeed cmd)
            {
                throw new NotImplementedException();
            }
            public override void OnDeleteFileBack(ArbinCommandDeleteFileFeed cmd)
            {
                throw new NotImplementedException();
            }
        }


        public void pythonSetup()
        {
            //setup for Python.NET
            var pathToVirtualEnv = @"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\venv";
            var path = Environment.GetEnvironmentVariable("PATH").TrimEnd(';');

            path = string.IsNullOrEmpty(path) ? pathToVirtualEnv : path + ";" + pathToVirtualEnv;
            Environment.SetEnvironmentVariable("PYTHONPATH", $"{pathToVirtualEnv}\\Lib\\site-packages;{pathToVirtualEnv}\\Lib", EnvironmentVariableTarget.Process);

            string pythonDll = @"C:\Users\Arbin\AppData\Local\Programs\Python\Python310\python310.dll";
            Environment.SetEnvironmentVariable("PYTHONNET_PYDLL", pythonDll);
            Runtime.PythonDLL = pythonDll;

            try
            {
                PythonEngine.Initialize();
            }
            catch (Exception e)
            {
                Console.WriteLine();
                Console.WriteLine(e.ToString());
            }

            string additional = $"{pathToVirtualEnv};{pathToVirtualEnv}\\Lib\\site-packages;{pathToVirtualEnv}\\Lib";
            PythonEngine.PythonPath = PythonEngine.PythonPath + ";" + additional;
            PythonEngine.PythonPath = PythonEngine.PythonPath + ";" + @"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI";

            using (Py.GIL())
            {
                dynamic os = Py.Import("os");
                dynamic sys = Py.Import("sys");
                sys.path.append(os.path.dirname(os.path.expanduser(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\models\ensemble"))); //add paths 
                sys.path.append(os.path.dirname(os.path.expanduser(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\models\gp")));
            }
        }

        public double modelPrediction(int index)
        {
            //obtain model predictions and return predicted anode potential
            using (Py.GIL())
            {
                var watch = System.Diagnostics.Stopwatch.StartNew();

                dynamic os = Py.Import("os");
                dynamic sys = Py.Import("sys");
                sys.path.append(os.path.dirname(os.path.expanduser(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\models\" +
                    BatteryList[index].ModelName.Substring(0, BatteryList[index].ModelName.Length - 3)))); //add paths 
                var fromFile = Py.Import(Path.GetFileNameWithoutExtension(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\models\" + BatteryList[index].ModelName));


                dynamic np = Py.Import("numpy");

                // Call the predict function with real-time input data
                PyObject data = np.fromiter(BatteryList[index].GetInputDatas(), "double"); //will this copy be removed from memory???
                int chan = BatteryList[index].ChannelNum - 1;
                PyObject ch = chan.ToPython();

                //for (int i = 0; i < 5; i++)
                //{
                //    for (int j = 0; j < 6; j++)
                //        Console.Write(BatteryList[index].GetInputDatas()[i, j] + " ");
                //    Console.WriteLine();
                //}

                //Random random = new Random();
                //double[,] values = new double[5,6];
                //for (int i = 0; i < 5; ++i)
                //    for(int j = 0; j<6; j++)
                //     values[i,j] = random.NextDouble()/1000;
                //data = np.fromiter(values, "double");

                object result = fromFile.InvokeMethod("predict", data, ch);
                double temp = double.Parse(result.ToString());


                watch.Stop();
                var elapsedTime = watch.ElapsedMilliseconds;
                //Console.WriteLine("One prediction for channel " + (BatteryList[index].ChannelNum) + " took " + elapsedTime + " milliseconds");

                return temp;

            }
        }


        /// <summary>
        /// This method implements the dynamic charging protocol for 3E and 2E cells.
        /// It can handle both 3E and 2E dynamic charging cells.
        /// </summary>
        /// 

        public void startCTI()
        {
            //setup connection
            testData = new MyTestData();
            ctrl = new MyArbinControl(testData);
            ctrl.Start();
            client = new ArbinClient();
            client.OnConnectionChanged += (IArbinSocket Socket, ArbinSocketEventArgSet.SocketConnectionEventArgs e) =>
            {
                connected = e.Connected;
            };
            ctrl.ListenSocketRecv(client);
            int number = client.ConnectAsync(MyIP, 9031, 1000, out int err);
            bool temp = false;
            while (true)
            {
                if (connected.HasValue)
                {
                    ctrl.PostLogicConnect(client, true);
                    temp = ctrl.PostUserLogin(client, UserName, Password);
                    Console.WriteLine("Login successful");
                    break;
                }
            }
            connected = client.IsConnected();
            ctrl.PostGetChannelsData(client,
           (uint)ArbinCommandGetChannelDataFeed.GET_CHANNELS_INFO_NEED_TYPE.THIRD_PARTY_GET_CHANNELS_INFO_NEED_TYPE_AUX);
        }
        public void threeEandtwoE()
        {
            startCTI();

            DateTime dateTime = DateTime.UtcNow.Date;
            string fileDate = dateTime.ToString("MMddyyyy");


            while (true)
            {
                //if successfully connected, will begin data measurement
                if (testData.GetChannelDataFeed != null)
                {
                    pythonSetup();


                    double throughput = 0;



                    ctrl.PostGetChannelsData(client,
                    (uint)ArbinCommandGetChannelDataFeed.GET_CHANNELS_INFO_NEED_TYPE.THIRD_PARTY_GET_CHANNELS_INFO_NEED_TYPE_AUX);

                    //initialize current to starting value. Assumes cells are not charging at time of program start.

                    Random random = new Random();
                    int unactiveTracker = 0;
                    int timeTracker = 0;
                    //MAKE SURE TO STOP THE CODE WHEN YOU ARE DONE USING THE CHANNEL
                    while (true)
                    {



                        //obtain data
                        ctrl.PostGetChannelsData(client,
                        (uint)ArbinCommandGetChannelDataFeed.GET_CHANNELS_INFO_NEED_TYPE.THIRD_PARTY_GET_CHANNELS_INFO_NEED_TYPE_AUX);

                        for (int index = 0; index < BatteryList.Count; index++)
                        {

                            float anodeVoltage = 1000f; //default value

                            ctrl.PostGetChannelsData(client,
                            (uint)ArbinCommandGetChannelDataFeed.GET_CHANNELS_INFO_NEED_TYPE.THIRD_PARTY_GET_CHANNELS_INFO_NEED_TYPE_AUX);

                            ushort channelNum = (ushort)(BatteryList[index].ChannelNum - 1);
                            BatteryList[index].Throughput = BatteryList[index].Throughput + 2 * Math.Abs(testData.GetChannelDataFeed.m_Channels[0].Current) / 3600; //count two seconds



                            if ("Finished" == testData.GetChannelDataFeed.m_Channels[channelNum].Status.ToString())
                            {
                                //check roughly every minute
                                if (unactiveTracker >= 120)
                                {
                                    Console.WriteLine("Not monitoring channel " + (channelNum + 1).ToString());
                                    unactiveTracker = 0;
                                }
                                unactiveTracker++;
                                continue;
                            }



                            if (BatteryList[index].CellType.Equals("2E")) //only modify for 2 electrode cells
                            {

                                //if (BatteryList[index].GetInputDatas(0,0) == 0) // still unfilled
                                //{
                                //    Console.WriteLine(timeTracker + " " + index);
                                //    //populate first columns for past data retrieval
                                //    BatteryList[index].SetInputDatas(4 - timeTracker, 0, testData.GetChannelDataFeed.m_Channels[channelNum].Voltage);
                                //    BatteryList[index].SetInputDatas(4 - timeTracker, 1, testData.GetChannelDataFeed.m_Channels[channelNum].Power);
                                //    BatteryList[index].SetInputDatas(4 - timeTracker, 2, testData.GetChannelDataFeed.m_Channels[channelNum].Current);
                                //    BatteryList[index].SetInputDatas(4 - timeTracker, 3, testData.GetChannelDataFeed.m_Channels[channelNum].ChargeCapacity);
                                //    BatteryList[index].SetInputDatas(4 - timeTracker, 4, testData.GetChannelDataFeed.m_Channels[channelNum].ChargeEnergy);
                                //    BatteryList[index].SetInputDatas(4 - timeTracker, 5, BatteryList[index].Throughput);


                                //    //get measurements every 2 seconds

                                //    if (index == BatteryList.Count - 1) // update 
                                //    {
                                //        timeTracker++; //will not be able to handle cases where a cell is resumed mid charging.

                                //    }


                                //    continue;
                                //}


                                //update past data array
                                for (int j = BatteryList[index].GetInputDatas().GetUpperBound(0); j >= 0; j--)
                                {
                                    for (int k = 0; k < BatteryList[index].GetInputDatas().GetUpperBound(1) + 1; k++)
                                    {
                                        if (j == 0)
                                            BatteryList[index].SetInputDatas(j, k, 0);
                                        else
                                            BatteryList[index].SetInputDatas(j, k, BatteryList[index].GetInputDatas(j - 1, k));

                                    }
                                }

                                //get present measurements
                                BatteryList[index].SetInputDatas(0, 0, testData.GetChannelDataFeed.m_Channels[channelNum].Voltage);
                                BatteryList[index].SetInputDatas(0, 1, testData.GetChannelDataFeed.m_Channels[channelNum].Power);
                                BatteryList[index].SetInputDatas(0, 2, testData.GetChannelDataFeed.m_Channels[channelNum].Current);
                                BatteryList[index].SetInputDatas(0, 3, testData.GetChannelDataFeed.m_Channels[channelNum].ChargeCapacity);
                                BatteryList[index].SetInputDatas(0, 4, testData.GetChannelDataFeed.m_Channels[channelNum].ChargeEnergy);
                                BatteryList[index].SetInputDatas(0, 5, BatteryList[index].Throughput);
                            }

                            String step = testData.GetChannelDataFeed.m_Channels[channelNum].StepAndCycle;
                            int start = step.IndexOf("]") + 1;
                            int end = step.IndexOf(":") - start;
                            int stepIndex = Int32.Parse(step.Substring(start, end));
                            bool change = false;

                            start = step.IndexOf("[")+1;
                            end = step.IndexOf("]")-1;
                            int cycleIndex = Int32.Parse(step.Substring(start, end));

                            if (("Discharge" == testData.GetChannelDataFeed.m_Channels[channelNum].Status.ToString()) && BatteryList[index].CountChanges > 0)
                            {
                                BatteryList[index].CountChanges = 0;
                                BatteryList[index].Current = 0.00318f; //adjust current value back to 1C
                                change = true;
                                Console.WriteLine("Reset charging current for channel " + (channelNum + 1).ToString());
                            }
                            //change in value should be at least one second
                            else if (("Charge" == testData.GetChannelDataFeed.m_Channels[channelNum].Status.ToString()) && (stepIndex == 10))

                            {

                                if (BatteryList[index].CellType.Equals("2E")) //TO DO: ALLOW PRESSURE TOO
                                {
                                    // Console.WriteLine(stepIndex);
                                    // Console.WriteLine(channelNum + 1);
                                    anodeVoltage = (float)modelPrediction(index);
                                }
                                else if (BatteryList[index].CellType.Equals("3E"))
                                {
                                    anodeVoltage = testData.GetChannelDataFeed.m_Channels[channelNum].Auxs[0][0].Value;
                                }

                                if ((BatteryList[index].GetInputDatas(4, 0) != 0.0) && (testData.GetChannelDataFeed.m_Channels[channelNum].TestTime - BatteryList[index].PrevTime >= 8.0) &&
                                     (BatteryList[index].CountChanges < 2) && (anodeVoltage <= BatteryList[index].Threshold) && (testData.GetChannelDataFeed.m_Channels[channelNum].Voltage > 3.32))
                                {

                                    BatteryList[index].CountChanges = BatteryList[index].CountChanges + 1;
                                    BatteryList[index].Current = BatteryList[index].Current - 0.000954f; //adjust current value //step size = 0.3c
                                    change = true;
                                    Console.WriteLine("Update charging current for channel " + (channelNum + 1).ToString());
                                }

                            }



                            if (change) //update meta variable
                            {
                                BatteryList[index].PrevTime = testData.GetChannelDataFeed.m_Channels[channelNum].TestTime;

                                //List<ArbinCommandGetMetaVariablesFeed.MetaVariableInfo> myVariableList = new List<ArbinCommandGetMetaVariablesFeed.MetaVariableInfo>();
                                //myVariableList.Add(new ArbinCommandGetMetaVariablesFeed.MetaVariableInfo()
                                //{
                                //    //make sure to edit TestConfig.txt so the desired channel is changed (watch out, ArbinCTI uses zero-indexing!)

                                //    m_Channel = channelNum,
                                //    m_MV_DataType = TE_DATA_TYPE.MP_DATA_TYPE_METAVALUE,
                                //    m_MV_MetaCode = (ushort)TE_METAVARIABLE_CODE.MetaCode_MV_UD1
                                //});

                                ////assign the current value
                                //bool test = ctrl.PostUpdateMetaVariableAdvanced(client, new List<MetaVariableInfo>() { new MetaVariableInfo()
                                //{
                                //    m_ChannelIndexInGlobal = channelNum,
                                //    m_MV_MetaCode = 52,
                                //    m_fMV_Value = BatteryList[index].Current,
                                //}
                                //}, out int nError);


                                //while (testData.SetMetaVariableFeed == null) //make sure meta variable was changed
                                //{
                                //    if (testData.SetMetaVariableFeed != null)
                                //    {
                                //        Console.WriteLine(testData.SetMetaVariableFeed.Result == ArbinCommandSetMetaVariableFeed.SET_MV_RESULT.CTI_SET_MV_SUCCESS);
                                //    }

                                //    //ctrl.PostGetChannelsData(client,
                                //    //(uint)ArbinCommandGetChannelDataFeed.GET_CHANNELS_INFO_NEED_TYPE.THIRD_PARTY_GET_CHANNELS_INFO_NEED_TYPE_AUX);
                                //    break;
                                //}
                            }

                            BatteryList[index].Voltage = testData.GetChannelDataFeed.m_Channels[channelNum].Voltage;
                            BatteryList[index].Time = testData.GetChannelDataFeed.m_Channels[channelNum].TestTime;

                            string myfile = @"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\Output_Data\threeEandTwoE_charging_output_" + fileDate + "_" + "Channel_" + BatteryList[index].ChannelNum + ".txt";

                            //var configPersons = new CsvConfiguration(CultureInfo.InvariantCulture)
                            //{
                            //    HasHeaderRecord = true;
                            //};
                            //using (var stream = File.Open(myfile, FileMode.Append))
                            //using (var writer = new StreamWriter(stream))
                            //using (var csv = new CsvWriter(writer, configPersons))
                            //{
                            //    csv.WriteRecords(myPersonObjects);
                            //}



                            Console.Write(testData.GetChannelDataFeed.m_Channels[channelNum].TestTime.ToString("0.0000") + "\t\t\t");
                            Console.Write(stepIndex + "\t\t\t");
                            Console.Write(cycleIndex + "\t\t\t");
                            Console.Write(testData.GetChannelDataFeed.m_Channels[channelNum].Voltage.ToString("0.0000") + "\t\t\t");
                            Console.Write(testData.GetChannelDataFeed.m_Channels[channelNum].Current.ToString("0.0000") + "\t\t\t");
                            Console.Write(testData.GetChannelDataFeed.m_Channels[channelNum].Current.ToString("0.0000") + "\t\t\t");
                            Console.WriteLine(anodeVoltage + "\t\t\t");
                        }



                        determineChannels(); //update channels, if needed


                        //Check every 20 seconds
                        Thread.Sleep(2000);
                    }
                }
            }





        }

        /// <summary>
        /// This method determines channels to operate by looking for updates in the ChannelConfig file.
        /// </summary>
        public void determineChannels()
        {



            //cases: cell is added, so it dosn't exist previously
            //       cell is deleted, so the index should be identified and removed

            string[] lines = File.ReadAllLines(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\ChannelConfig.txt");
            if (DateTime.Compare(channelConfigLastModified, File.GetLastWriteTime(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\ChannelConfig.txt")) != 0)
            { //modified file
                channelConfigLastModified = File.GetLastWriteTime(@"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\ChannelConfig.txt");
                Console.WriteLine("Reading ChannelConfig.txt for changes");

                List<bool> check = new List<bool>();
                for (int i = 0; i < BatteryList.Count; i++)
                    check.Add(false);
                //foreach (var val in check)
                //    Console.WriteLine(val);

                List<int> addCells = new List<int>(); //store line index to add
                bool removeCells = false; //store cell indices to remove
                for (int i = 0; i < lines.Length; i++)
                {
                    string[] words = lines[i].Split(' ');
                    if (words[0].Length == 0)
                        break;

                    bool exists = false;
                    for (int j = 0; j < Chnl.Count; j++)
                    {
                        if (Chnl[j] == ushort.Parse(words[0])) // cell exists
                        {

                            exists = true;
                            check[j] = true;
                            break;
                        }
                    }
                    if (!exists) // cell in text does not exist, so we add it
                    {
                        addCells.Add(i);
                    }
                }

                for (int i = check.Count - 1; i > -1; i--)
                {
                    if (!check[i]) // cell was no longer present in ChannelConfig
                    {
                        Console.WriteLine("Removing channel " + BatteryList[i].ChannelNum);
                        check.RemoveAt(i);
                        BatteryList.RemoveAt(i);
                        removeCells = true;
                    }
                }

                for (int i = 0; i < addCells.Count; i++) //add cells
                {
                    string[] words = lines[addCells[i]].Split(' ');
                    Console.WriteLine("Adding channel " + words[0]);
                    BatteryList.Add(new Battery(ushort.Parse(words[0]), words[1], words[2], float.Parse(words[3]), double.Parse(words[4])));
                }

                if ((addCells.Count > 0) || (removeCells)) //update list of tracked channels
                {
                    Chnl.Clear();
                    for (int i = 0; i < BatteryList.Count; i++)
                    {
                        Chnl.Add(BatteryList[i].ChannelNum);
                    }
                    Console.WriteLine("Channels are now " + String.Join(", ", Chnl));
                }



            }


        }

    }

    internal class TestClass
    {
        static void Main(string[] args)
        {
            ArbinClientTests tests = new ArbinClientTests();


            //run real-time ML prediction module
            //tests.realTimeMachineLearning();

            //run real-time current adjustment module. Uses 3E measurement to adjust current
            //tests.determineChannels();
            //tests.dynamicCharging();

            //tests.startCTI();
            tests.threeEandtwoE();


        }
    }

}
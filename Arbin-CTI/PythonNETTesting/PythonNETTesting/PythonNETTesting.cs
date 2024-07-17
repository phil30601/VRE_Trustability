/*
* ==============================================================================
* Filename: ArbinClientTests
* Description: This file contains test methods for testing various functions of ArbinClient class.
* ==============================================================================
*/
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.IO;
using Python.Runtime;

namespace ArbinCTI.Core
{
    /// <summary>
    /// <para>The <see cref="ArbinCTI.Core"/> Provide connection service.</para>
    /// <para><see cref="ArbinClient"/> is used to connect to CTI.</para>
    /// <see cref="ArbinCommand"/> contains the basic information of the CTI return packet, which is the main base class for all command classes.
    /// </summary>
    [TestClass()]
    public class ArbinClientTests
    {
        private bool? connected;
        static string[] lines = File.ReadAllLines("../../../TestConfig.txt");
        private readonly string MyIP = lines[0];
        private readonly string UserName = lines[1];
        private readonly string Password = lines[2];
        private readonly string Schedule = lines[3];
        private readonly string SerialNumber = lines[4];
        private float NominalCapacity = float.Parse(lines[5]);
        private readonly int WrongChnlIndex = int.Parse(lines[8]);
        readonly static DateTime A = DateTime.Now;
        readonly static string B = A.ToString("yy/MM/dd HH/mm/ss");
        readonly static string TestName = lines[6] + B;




        /// <summary>
        /// This is a test project for CTI.
        /// experiment with obtaining real-time measurements.
        /// </summary>
        [TestMethod]
        public void runPythonCode()
        {
            Thread.Sleep(1000);
            //Runtime.PythonDLL = @"C:\Users\Arbin\AppData\Local\Programs\Python\Python310\python310.dll";

            var pathToVirtualEnv = @"C:\Users\Arbin\source\repos\maggyo\Arbin-CTI\venv";

            var path = Environment.GetEnvironmentVariable("PATH").TrimEnd(';');
            path = string.IsNullOrEmpty(path) ? pathToVirtualEnv : path + ";" + pathToVirtualEnv;
            Environment.SetEnvironmentVariable("PATH", path, EnvironmentVariableTarget.Process);
            Environment.SetEnvironmentVariable("PYTHONHOME", pathToVirtualEnv, EnvironmentVariableTarget.Process);

            Environment.SetEnvironmentVariable("PYTHONPATH", $"{pathToVirtualEnv}\\Lib\\site-packages;{pathToVirtualEnv}\\Lib", EnvironmentVariableTarget.Process);

            Console.WriteLine("asdf");
            //PythonEngine.PythonPath = Environment.GetEnvironmentVariable("PYTHONPATH", EnvironmentVariableTarget.Process);
            //PythonEngine.PythonHome = pathToVirtualEnv;

            Console.WriteLine(Environment.GetEnvironmentVariable("PYTHONHOME"));
            Console.WriteLine(Environment.GetEnvironmentVariable("PYTHONPATH"));
            Console.WriteLine(Environment.GetEnvironmentVariable("PATH"));

            string pythonDll = @"C:\Users\Arbin\AppData\Local\Programs\Python\Python310\python310.dll";
            Environment.SetEnvironmentVariable("PYTHONNET_PYDLL", pythonDll);
            try
            {
                PythonEngine.Initialize();
            }
            catch (Exception e)
            {
                Console.WriteLine(e.ToString());
            }

            Console.WriteLine("asdf");

            //FileInfo f = new FileInfo("TestConfig.txt");
            //Console.WriteLine(f.FullName);


            //string pythonDll = @"C:\Users\Arbin\AppData\Local\Programs\Python\Python310\python310.dll";
            //Environment.SetEnvironmentVariable("PYTHONNET_PYDLL", pythonDll);
            //PythonEngine.Initialize();


            using (Py.GIL())
            {
                PythonEngine.RunSimpleString("asdf");
                //PythonEngine.Initialize();

                /*
                dynamic module = Py.Import("../../../model_prediction.py");


                dynamic predict = module.predict;

                // Call the predict function with real-time input data
                double[] input_data = { 0.1, 0.2, 0.3, 0.4, 0.5 };
                double prediction = predict(input_data);
                */
            }
            Thread.Sleep(10000);

        }
    }

    class TestClass
    {
        static void Main(string[] args)
        {
            ArbinClientTests tests = new ArbinClientTests();


            tests.runPythonCode();


        }
    }

}
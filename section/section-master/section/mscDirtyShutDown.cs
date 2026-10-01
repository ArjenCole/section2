using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace section
{ 
    
    public static class mscDirtyShutDown
    {
        private class pmcRecords
        {
            public List<pmcRecord> Records = new List<pmcRecord>();
            public pmcRecords()
            {
                //json反序列化需要
            }
            public string Json()
            {
                var tJSS = new JavaScriptSerializer();
                string json = tJSS.Serialize(this);
                return json;
            }
        }
        private class pmcRecord
        {
            //DateTime TimeStamp;
            public string FilePath;
            public string BackupPath;
            public string ProcessInfo;

            public pmcRecord()
            {
                //json反序列化需要
            }
            public pmcRecord(string pFilePath,string pBackupPath)
            {
                FilePath = pFilePath;
                BackupPath = pBackupPath;
                ProcessInfo = getProcessInfo(Process.GetCurrentProcess());
            }

        }

        private static string recordsFilePath = Application.StartupPath + @"\mDirtyShutDown.json";
        private static pmcRecords records = new pmcRecords();



        public static void Init()
        {
            getRecords();
        }

        public static void AddRecord(string pOpenPath, string pBackupPath)
        {
            if ((pOpenPath != "") || (pBackupPath != "")) 
            {
                addRecord(pOpenPath, pBackupPath);
            }
        }

        public static string CheckDirty(string pOpenPath, string pBackupPath = "")
        {
            string tBackupPath = "";
            if (isDitry(pOpenPath, out tBackupPath)) 
            {
                delRecord(pOpenPath);
                if (openBackup())
                {
                    return tBackupPath;
                }
            }
            
            return "";
        }
        public static void Close(string pOpenPath)
        {
            delRecord(pOpenPath);
        }

        private static bool openBackup()
        {
            if (MessageBox.Show("检测到异常退出,是否打开备份文件?", "提示", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
               return true;//打开备份文件夹
            return false;
        }

        private static void addRecord(string pOpenPath, string pBackupPath)
        {
            pmcRecord tpmR = new pmcRecord(pOpenPath, pBackupPath);
            records.Records.Add(tpmR);

            saveRecords();
        }
        private static void delRecord(string pOpenPath)
        {
            string tOpenPath = pOpenPath;
            if (pOpenPath == "") tOpenPath = records.Records.Last().FilePath;
            pmcRecords tpmRs = new pmcRecords();
            foreach (var fe in records.Records)
            {
                if (fe.FilePath != tOpenPath)
                {
                    tpmRs.Records.Add(fe);
                }
            }
            records = tpmRs;

            saveRecords();
        }

        private static bool isDitry(string pOpenPath, out string tBackupPath)
        {
            tBackupPath = "";
            if (pOpenPath == "") //不带文件打开软件时
            {
                for (int i = records.Records.Count - 1; i >= 0; i--)
                {
                    if (!isRunning(records.Records[i].ProcessInfo))
                    {
                        tBackupPath = records.Records[i].BackupPath;
                        return true;
                    }
                }
                return false;
            }
            for (int i = records.Records.Count - 1; i >= 0; i--)//带文件打开软件时
            {
                pmcRecord feR = records.Records[i];
                if ((feR.FilePath == pOpenPath) && (!isRunning(feR.ProcessInfo))) 
                {
                    tBackupPath = feR.BackupPath;
                    return true;
                }
            }
            return false;
        }

        private static bool isRunning(string pProcessInfo)
        {
            Process[] ps = Process.GetProcesses();

            string tProcess = "";
            try
            {
                foreach (Process feP in ps)
                {
                    tProcess += "  " + feP.ProcessName;
                    if (getProcessInfo(feP) == pProcessInfo)
                        return true;
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(tProcess+ " " +ex.Message);
            }

            return false;

        }

        private static string getProcessInfo(Process pProcess)
        {
            if (!pProcess.ProcessName.Contains("section")) return "";
            return pProcess.Id.ToString() + "_" + pProcess.ProcessName + "_" + pProcess.StartTime.ToString();
        }

        private static void getRecords()
        {
            if (!File.Exists(recordsFilePath)) saveRecords();
            using (StreamReader tSR = new StreamReader(recordsFilePath))
            {
                string json = tSR.ReadLine();
                var serializer1 = new JavaScriptSerializer();
                records = serializer1.Deserialize<pmcRecords>(json);
            }

        }

        private static void saveRecords()
        {
            string saveStr = records.Json();
            using (StreamWriter tSW = new StreamWriter(recordsFilePath, false))
                tSW.WriteLine(saveStr);
        }
    }

    
}

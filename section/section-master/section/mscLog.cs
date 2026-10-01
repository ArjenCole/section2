using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace section
{
    public static class mscLog
    {
        private static DateTime startTimeStamp, endTimeStamp;
        private static StreamWriter log;
        public static string Path = System.Windows.Forms.Application.StartupPath + @"\Log\" + DateTime.Now.ToString("yyMMddhhmmss") + "Run.Log";

        public static void Start()
        {
            //Init();
            startTimeStamp = DateTime.Now;
            Write("记录自软件版本：" + System.Reflection.Assembly.GetExecutingAssembly().GetName().Version.ToString());
        }
        public static void OpenFile(string ts = "??")
        {
            if (mscCtrl.DC != null) Write("打开文件：" + ts + mscCtrl.DC.Name.ToString());
        }
        public static void End()
        {
            endTimeStamp = DateTime.Now;
            Write("结束记录，耗时 " + (endTimeStamp - startTimeStamp).ToString());
        }
        public static void Clear()
        {
            if (File.Exists(Path))
            {
                FileInfo fi = new FileInfo(Path);
                if (fi.Attributes.ToString().IndexOf("ReadOnly") != -1)
                    fi.Attributes = FileAttributes.Normal;
                File.Delete(Path);
            }
        }

        private static void Init()
        {
            mscMslns.CheckPath(Path);
            log = new StreamWriter(Path, true);
        }
        private static void Dispose()
        {
            log.Dispose();
        }
        public static void Write(string pLog)
        {
            Init();
            log.WriteLine("[" + DateTime.Now.ToString() + "] " + pLog);
            Dispose();
        }
        
    }
}

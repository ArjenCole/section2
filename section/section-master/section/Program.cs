using section.mcEmail;
using System;
using System.Collections.Generic;
using System.Configuration;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows.Forms;

namespace section
{
    static class Program
    {
        /// <summary>
        /// 应用程序的主入口点。
        /// </summary>
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Thread t = new Thread(ShowCover);
            t.Start();

            mscLog.Start();
            mscLog.Write("mscDirtyShutDown.Init()");
            mscDirtyShutDown.Init();
            mscLog.Write("FormMdi formMdi = new FormMdi(args)");
            FormMdi formMdi = new FormMdi(args);
            mscLog.Write("Application.Run(formMdi);");
            //mscCtrl.Regedit();
            Application.Run(formMdi);

            mscLog.End();

            SendLog();

            Environment.Exit(0);
        }
        static void ShowCover()
        {
            
            FormCover formCover = new FormCover();
            formCover.ShowDialog();
            
            if (mscCtrl.formMdi.InvokeRequired)
            {
                Action<string> actionDelegate = (x) => { mscCtrl.formMdi.Activate(); };
                mscCtrl.formMdi.Invoke(actionDelegate, string.Empty);
            }
            mscCtrl.Regedit();
        }

        static void SendLog()
        {
            if (!mscCheckInternet.CheckServeStatus("www.163.com")) return;//无网络则不发送
            if (!File.Exists(mscLog.Path)) return;
            string tUserName = Environment.UserName;
            string tHostName = System.Net.Dns.GetHostName();
            //if (tHostName == "DESKTOP-Crane" || tHostName == "jinhe") return;
            mscEmail.SendEmail(tUserName, tHostName, mscLog.Path);
            mscLog.Clear();
        }
    }
}

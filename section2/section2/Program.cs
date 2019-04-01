using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Windows.Forms;
using section2.FmTool;

namespace section2
{
    static class Program
    {
        /// <summary>
        /// 应用程序的主入口点。
        /// </summary>
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            Thread t = new Thread(ShowCover);
            t.Start();
            mscCtrl.fmMain = new FmMain();
            Application.Run(mscCtrl.fmMain);

            Environment.Exit(0);
        }
        static void ShowCover()
        {

            FmCover fmCover = new FmCover();
            fmCover.ShowDialog();

            if (mscCtrl.fmMain.InvokeRequired)
            {
                Action<string> actionDelegate = (x) => { mscCtrl.fmMain.Activate(); };
                mscCtrl.fmMain.Invoke(actionDelegate, string.Empty);
            }
        }
    }
}

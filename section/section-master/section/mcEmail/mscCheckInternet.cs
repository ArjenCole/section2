using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.NetworkInformation;
using System.Text;

namespace section.mcEmail
{
    public class mscCheckInternet
    {
        /// <summary>
        /// 检测网络连接状态
        /// </summary>
        /// <param name="urls"></param>
        public static bool CheckServeStatus(string pUrls)
        {
            string[] urls = pUrls.Split(new char[] { ';' });
            int errCount = 0;//ping时连接失败个数

            if (!LocalConnectionStatus())
            {
                Console.WriteLine("网络异常~无连接");
                return false;
            }
            else if (!MyPing(urls, out errCount))
            {
                if ((double)errCount / urls.Length >= 0.3)
                {
                    Console.WriteLine("网络异常~连接多次无响应");
                    return false;
                }
                else
                {
                    Console.WriteLine("网络不稳定");
                    return true;
                }
            }
            else
            {
                Console.WriteLine("网络正常");
                return true;
            }
        }

        [System.Runtime.InteropServices.DllImport("winInet.dll")]
        private static extern bool InternetGetConnectedState(ref int dwFlag, int dwReserved);
        private const int INTERNET_CONNECTION_MODEM = 1;
        private const int INTERNET_CONNECTION_LAN = 2;
        /// <summary>
        /// 判断本地的连接状态
        /// </summary>
        /// <returns></returns>
        private static bool LocalConnectionStatus()
        {
            System.Int32 dwFlag = new Int32();
            if (!InternetGetConnectedState(ref dwFlag, 0))
            {
                Console.WriteLine("LocalConnectionStatus--未连网!");
                return false;
            }
            else
            {
                if ((dwFlag & INTERNET_CONNECTION_MODEM) != 0)
                {
                    Console.WriteLine("LocalConnectionStatus--采用调制解调器上网。");
                    return true;
                }
                else if ((dwFlag & INTERNET_CONNECTION_LAN) != 0)
                {
                    Console.WriteLine("LocalConnectionStatus--采用网卡上网。");
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Ping命令检测网络是否畅通
        /// </summary>
        /// <param name="urls">URL数据</param>
        /// <param name="errorCount">ping时连接失败个数</param>
        /// <returns></returns>
        private static bool MyPing(string[] urls, out int errorCount)
        {
            bool isconn = true;
            Ping ping = new Ping();
            errorCount = 0;
            try
            {
                PingReply pr;
                for (int i = 0; i < urls.Length; i++)
                {
                    pr = ping.Send(urls[i]);
                    if (pr.Status != IPStatus.Success)
                    {
                        isconn = false;
                        errorCount++;
                    }
                    Console.WriteLine("Ping " + urls[i] + "    " + pr.Status.ToString());
                }
            }
            catch
            {
                isconn = false;
                errorCount = urls.Length;
            }
            //if (errorCount > 0 && errorCount < 3)
            //  isconn = true;
            return isconn;
        }

    }
}

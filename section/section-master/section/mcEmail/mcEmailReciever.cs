using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Mail;
using System.Net.Sockets;
using System.Text;

namespace section.mcEmail
{
    class mcEmailReciever
    {
        string POPServer;
        string user;
        string pwd;
        NetworkStream ns;
        StreamReader sr;
        /// <summary>
        /// 解码
        /// </summary>
        /// <param name="code"></param>
        /// <returns></returns>
        private string Decode(string[] strss)  //=?utf-8?B?5Lqy54ix55qEIDExNzg3NzIxMjNxcWNv?=
        {
            //获取标题的编码方式
            Encoding b = Encoding.GetEncoding(strss[1]);
            string code = strss[3];
            string decode = "";
            byte[] byteCode = null;
            if (strss[2].ToUpper() == "B")
            {
                byteCode = DecodeBase64(ref strss[3]);
            }
            else if (strss[2].ToUpper() == "Q")
            {
                byteCode = DecodeQP(ref strss[3]);
            }
            try
            {
                decode = b.GetString(byteCode);
            }
            catch
            {
                decode = code;
            }
            if (decode.Contains("\0"))
                decode = decode.Replace("\0", "");
            return decode;
        }
        //对邮件标题解码  quoted-printable
        /// <summary>
        ///  quoted-printable  解码 
        /// </summary>
        /// <param name="code"></param>
        /// <returns></returns>
        private byte[] DecodeBase64(ref string code)
        {
            string st = code + "000";//
            string strcode = st.Substring(0, (st.Length / 4) * 4);
            return Convert.FromBase64String(strcode);
        }
        //对邮件标题解码  quoted-printable
        /// <summary>
        ///  quoted-printable  解码 
        /// </summary>
        /// <param name="code"></param>
        /// <returns></returns>
        private byte[] DecodeQP(ref string code)//=E6=AC=A2=E8=BF=8E=E6=88=90=E4=B8=BA=E7=8C=AA=E5=85=AB=E6=88=92=E7=BD=91=E7=AB=99=E4=BC=9A=E5=91=98=E3=80=82
        {
            string[] textArray1 = code.Split(new char[] { '=' });
            byte[] buf = new byte[textArray1.Length];
            try
            {
                for (int i = 0; i < textArray1.Length; i++)
                {
                    if (textArray1[i].Trim() != string.Empty)
                    {
                        byte[] buftest = new byte[2];
                        buf[i] = (byte)int.Parse(textArray1[i].Substring(0, 2), System.Globalization.NumberStyles.HexNumber);
                    }
                }
            }
            catch
            {
                return null;
            }
            return buf;
        }
        /// <summary>
        /// 接收邮件服务器相关信息
        /// </summary>
        /// <param name="server">参数 pop邮件服务器地址  </param>
        /// <param name="user">参数 登录到pop邮件服务器的用户名  </param>
        /// <param name="pwd">参数  登录到pop邮件服务器的密码</param>
        /// <returns>无返回</returns>
        public mcEmailReciever(string server, string _user, string _pwd)
        {
            POPServer = server;
            user = _user;
            pwd = _pwd;
        }
        /// <summary>
        /// 登陆服务器
        /// </summary>
        private void Connect()
        {
            TcpClient sender = new TcpClient(POPServer, 110);
            Byte[] outbytes;
            string input;
            string readuser = string.Empty;
            string readpwd = string.Empty;
            try
            {
                ns = sender.GetStream();
                sr = new StreamReader(ns, Encoding.Default);
                sr.ReadLine();
                //检查密码
                input = "user " + user + "\r\n";
                outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
                ns.Write(outbytes, 0, outbytes.Length);
                readuser = sr.ReadLine();
                input = "pass " + pwd + "\r\n";
                outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
                ns.Write(outbytes, 0, outbytes.Length);
                readpwd = sr.ReadLine();
                //Console.WriteLine(sr.ReadLine() );

            }
            catch
            {
                Console.WriteLine("用户名或密码错误");
            }
        }
        /// <summary>
        /// 为了读到数据流中的正确信息，重新建的一个方法（只是在读邮件详细信息是用到《即GetNewMessages（）方法中用到，这样就可以正常显示邮件正文的中英文》）
        /// </summary>
        /// <param name="tcpc"></param>
        private void Connecttest(TcpClient tcpc)
        {
            Byte[] outbytes;
            string input;
            string readuser = string.Empty;
            string readpwd = string.Empty;
            try
            {
                ns = tcpc.GetStream();
                sr = new StreamReader(ns);
                sr.ReadLine();
                //Console.WriteLine(sr.ReadLine() );
                input = "user " + user + "\r\n";
                outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
                ns.Write(outbytes, 0, outbytes.Length);

                readuser = sr.ReadLine();

                input = "pass " + pwd + "\r\n";
                outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
                ns.Write(outbytes, 0, outbytes.Length);
                readpwd = sr.ReadLine();
            }
            catch
            {
                Console.WriteLine("用户名或密码错误");
            }
        }
        //断开与服务器的连接
        private void Disconnect()
        {
            //"quit"  即表示断开连接
            string input = "quit" + "\r\n";
            Byte[] outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
            ns.Write(outbytes, 0, outbytes.Length);
            //关闭数据流
            ns.Close();
        }
        /// <summary>
        /// 获取邮件数目
        /// </summary>
        /// <returns>返回  int  邮件数目</returns>
        private int GetNumberOfNewMessages()
        {
            Byte[] outbytes;
            string input;
            int countmail;
            try
            {
                Connect();
                //"stat"向邮件服务器 表示要取邮件数目
                input = "stat" + "\r\n";
                //将string input转化为7位的字符，以便可以在网络上传输
                outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
                ns.Write(outbytes, 0, outbytes.Length);
                string thisResponse = sr.ReadLine();
                if (thisResponse.Substring(0, 4) == "-ERR")
                {
                    return -1;
                }
                string[] tmpArray;
                //将从服务器取到的数据以“”分成字符数组
                tmpArray = thisResponse.Split(' ');
                //断开与服务器的连接
                Disconnect();
                //取到的表示邮件数目
                countmail = Convert.ToInt32(tmpArray[1]);
                return countmail;
            }
            catch
            {
                Console.WriteLine("Could not connect to mail server");
                return -1;//表示读邮件时  出错，将接收邮件的线程 阻塞5分钟
            }
        }
        /// <summary>
        /// 处理标题
        /// </summary>
        /// <param name="listSubject">标题传，可能被编码成多行</param>
        /// <param name="msg"></param>
        private void ProcessSubject(List<string> listSubject, MailMessage msg)
        {
            if (listSubject.Count > 0)//有标题
            {
                string msgsubj = listSubject[0].Trim(); //=?utf-8?B?5Lqy54ix55qEIDExNzg3NzIxMjNxcWNv?=
                if (msgsubj.Length > 11 && msgsubj.StartsWith("=?") && msgsubj.EndsWith("?="))
                {
                    foreach (string strPartSubject in listSubject)
                        msg.Subject += Decode(strPartSubject.Split('?'));
                }
                else
                    msg.Subject = msgsubj;
            }
        }
        /// <summary>
        /// 获取所有新邮件
        /// </summary>
        /// <returns>  返回 ArrayList</returns>
        public List<MailMessage> GetNewMessages()
        {
            int newcount = GetNumberOfNewMessages();
            List<MailMessage> newmsgs = new List<MailMessage>();
            try
            {
                TcpClient tcpc = new TcpClient(POPServer, 110);
                Connecttest(tcpc);

                for (int n = 1; n < newcount + 1; n++)
                {
                    if (n == 36)
                    {
                        int i = 0;
                    }
                    //=?utf-8?Q?=E6=AC=A2=E8=BF=8E=E6=88=90=E4=B8=BA=E7=8C=AA=E5=85=AB=E6=88=92=E7=BD=91=E7=AB=99=E4=BC=9A=E5=91=98=E3=80=82?=
                    ArrayList msglines = GetRawMessage(tcpc, n);
                    MailMessage msg = new MailMessage();
                    List<string> listSubject = GetMessageSubject(msglines);
                    ProcessSubject(listSubject, msg);
                    //取发邮件者的邮件地址 
                    msg.From = GetMessageFrom(msglines);
                    //取邮件正文
                    string msgbody = GetMessageBody(msglines);
                    msg.Body = msgbody;

                    newmsgs.Add(msg);

                    //将收到的邮件保存到本地，调用另一个类的保存邮件方法，不使用此功能

                    //    Filesr.Savefile("subject:"+msg.Subject+"\r\n"+"sender:"+msg.From+"\r\n"+"context:"+msg.Body,"mail"+n+".txt");
                }
                //断开与服务器的连接
                Disconnect();
                return newmsgs;
            }
            catch
            {
                //    System.Windows.Forms.MessageBox.Show("读取邮件出错，请重试");
                return newmsgs;
            }
        }
        /// <summary>
        /// 从服务器读邮件信息
        /// </summary>
        /// <param name="tcpc"></param>
        /// <param name="messagenumber"></param>
        /// <returns></returns>
        private ArrayList GetRawMessage(TcpClient tcpc, int messagenumber)
        {
            Byte[] outbytes;
            string input;
            string line = "";
            input = "retr " + messagenumber.ToString() + "\r\n";
            outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
            ns.Write(outbytes, 0, outbytes.Length);
            ArrayList msglines = new ArrayList();
            StreamReader srtext = new StreamReader(tcpc.GetStream(), Encoding.Default);
            //每份邮件以英文“.”结束
            do
            {
                //char[]c= System.(srtext.ReadLine());
                line = srtext.ReadLine();
                msglines.Add(line);
            } while (line != ".");
            msglines.RemoveAt(msglines.Count - 1);
            return msglines;
        }
        /// <summary>
        ///获取邮件标题 
        /// </summary>
        /// <param name="msglines"></param>
        /// <returns></returns>
        private List<string> GetMessageSubject(ArrayList msglines)
        {
            IEnumerator msgenum = msglines.GetEnumerator();
            List<string> lis = new List<string>();
            bool find = false;
            while (msgenum.MoveNext())
            {
                string line = (msgenum.Current as string).Trim();
                if (line.StartsWith("Subject:"))
                {
                    find = true;
                    string subjectContent = line.Substring(8, line.Length - 8);
                    lis.Add(subjectContent);
                }
                else if (find)//找到标题后
                {
                    if (!line.Contains(":") && line.StartsWith("=?") && line.EndsWith("?="))//后面的行附属于标题
                        lis.Add(line);
                    else
                        break;
                }
            }
            return lis;
        }
        /// <summary>
        /// 获取邮件的发送人地址
        /// </summary>
        /// <param name="msglines"></param>
        /// <returns></returns>
        private MailAddress GetMessageFrom(ArrayList msglines)
        {
            IEnumerator msgenum = msglines.GetEnumerator();
            List<string> listDisplayName = new List<string>();
            List<string> listAddress = new List<string>();
            bool findDisplayName = false;
            bool findAddress = false;
            bool isOnlyAddress = false;
            while (msgenum.MoveNext())
            {

                string line = (msgenum.Current as string).ToLower().Trim();
                if (line.StartsWith("from:"))
                {
                    //From:service@001job.com
                    //"From:QQ邮箱管理员" <10000@qq.com>
                    // From: =?GBK?B?zNSxps34?= <register@vip.mail.taobao.com>

                    int endIndex = line.IndexOf(">");
                    if (endIndex == -1)
                        endIndex = line.Length;
                    int addressBegin = line.IndexOf("<");
                    if (addressBegin == -1)//没有常规地址部分
                    {
                        if (line.Contains("@"))//该来自信息没有标题,只有地址
                        {
                            findAddress = true;
                            isOnlyAddress = true;
                            listAddress.Add(line.Substring(5).Trim());
                        }
                        else
                        {
                            findDisplayName = true;
                            listDisplayName.Add(line);
                        }
                    }
                    else if (addressBegin > -1)//有地址部分,也就有标题部分
                    {
                        findDisplayName = true;
                        findAddress = true;
                        listDisplayName.Add(line.Substring(5, addressBegin - 5).Trim());
                        listAddress.Add(line.Substring(addressBegin + 1, endIndex - addressBegin - 1).Trim());
                    }
                }
                else if (isOnlyAddress)//只有地址
                {
                    if (line.Length == 0)
                        break;
                    else if (line.Contains(":"))
                        break;
                    else
                        listAddress.Add(line);
                }
                else if (findDisplayName)
                {
                    if (findAddress)//已到地址
                    {
                        if (line.Contains(":"))
                            break;
                        else
                        {
                            int endIndex = line.IndexOf(">");
                            if (endIndex == -1)
                                endIndex = line.Length;
                            listAddress.Add(line.Substring(0, endIndex).Trim());
                        }
                    }
                    else//没有找到过地址
                    {
                        int endIndex = line.IndexOf(">");
                        if (endIndex == -1)
                            endIndex = line.Length;
                        int addressBegin = line.IndexOf("<");
                        if (addressBegin == -1)//没有地址部分
                            listDisplayName.Add(line);
                        else if (addressBegin > -1)//有地址部分
                        {
                            findAddress = true;
                            listDisplayName.Add(line.Substring(0, addressBegin).Trim());
                            listAddress.Add(line.Substring(addressBegin + 1, endIndex - addressBegin - 1).Trim());
                        }
                    }
                }
            }
            string strAddress = "";
            string strDisplayName = "";
            if (listDisplayName.Count > 0)//有标题
            {
                string strPartDisplayName1 = listDisplayName[0].Trim(); //=?utf-8?B?5Lqy54ix55qEIDExNzg3NzIxMjNxcWNv?=
                if (strPartDisplayName1.Length > 11 && strPartDisplayName1.StartsWith("=?") && strPartDisplayName1.EndsWith("?="))
                {
                    foreach (string strPartDisplayName in listDisplayName)
                        strDisplayName += Decode(strPartDisplayName.Split('?'));
                }
                else
                    strDisplayName = strPartDisplayName1;
            }
            foreach (string strPartAddress in listAddress)
            {
                strAddress += strPartAddress;
            }
            return new MailAddress(strAddress);
        }
        /// <summary>
        /// 获取邮件正文
        /// </summary>
        /// <param name="msglines"></param>
        /// <returns></returns>
        private string GetMessageBody(ArrayList msglines)
        {
            string body = "";
            string line = " ";
            IEnumerator msgenum = msglines.GetEnumerator();
            while (line.CompareTo("") != 0)
            {
                msgenum.MoveNext();
                line = (string)msgenum.Current;
            }
            while (msgenum.MoveNext())
            {
                body = body + (string)msgenum.Current + "\r\n";
            }
            return body;
        }
        /// <summary>
        ///根据输入的数字，删除相应编号的邮件
        /// </summary>
        /// <param name="messagenumber">参数 删除第几封邮件  </param>
        /// <returns>返回  bool true成功；false  失败</returns>
        private bool DeleteMessage(int messagenumber)
        {
            Connect();
            Byte[] outbytes;
            string input;
            byte[] backmsg = new byte[25];
            string msg = string.Empty;

            try
            {
                input = "dele " + messagenumber.ToString() + "\r\n";
                outbytes = System.Text.Encoding.ASCII.GetBytes(input.ToCharArray());
                ns.Write(outbytes, 0, outbytes.Length);
                ns.Read(backmsg, 0, 25);
                msg = System.Text.Encoding.Default.GetString(backmsg, 0, backmsg.Length);
                Disconnect();
                if (msg.Substring(0, 3) == "+OK")
                {
                    return true;
                }
                return false;
            }
            catch (Exception e)
            {
                return false;
            }
        }

    }
}

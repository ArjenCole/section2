using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Mail;
using System.Runtime.InteropServices;
using System.Text;

namespace section.mcEmail
{
    public static class mscEmail
    {
        public static void SendEmail(string pTitle, string pBody, string pPath = "")
        {
            //if (!mscCheckInternet.CheckServeStatus("www.163.com")) return;
            mcEmailSender tEmail = new mcEmailSender("section_supviser@163.com", "section_supviser@163.com", pBody, pTitle, "section163");//PassWord填写的是授权码而不是密码
            if (pPath != "") 
                tEmail.Attachments(pPath);//@"E:\code\Products\section\section1.2.0.170607_alpha\section\bin\Debug\Inventory\EleInventory.stn"
            tEmail.Send();
        }
        public static void AcceptEmail()
        {
            //if (!mscCheckInternet.CheckServeStatus("www.163.com")) return;
            mcEmailReciever pope = new mcEmailReciever("pop.163.com", "section_supviser@163.com", "section163");
            List<MailMessage> listMailMessage = pope.GetNewMessages();
            Console.WriteLine(listMailMessage.Count.ToString());
            foreach (MailMessage feMM in listMailMessage)
            {
                Console.WriteLine(feMM.Subject);
                var t = feMM.Attachments[0];
            }
            Console.ReadLine();
        }



    }
}

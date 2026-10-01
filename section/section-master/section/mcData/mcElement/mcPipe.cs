using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcPipe
    {
        public string Mat;//材质
        public double Dn;//mm
        public double Content;//含量

        public mcPipe(string pMat = "Ⅱ级混凝土管", double pDn = 600, double pContent = 1)
        {
            Mat = pMat;
            Dn = pDn;
            Content = pContent;
        }
        public mcPipe(XElement pXE)
        {
            Mat = pXE.Element("Mat").Value;
            Dn = mscMslns.ToDouble(pXE.Element("Dn").Value);
            Content = mscMslns.ToDouble(pXE.Element("Content").Value);
        }
    }
}

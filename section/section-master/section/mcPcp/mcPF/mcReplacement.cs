using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcReplacement : ItoXML
    {
        public string Name = "中粗砂";
        public double H = 200;
        public mcReplacement() { }
        public mcReplacement(string pName, double pH)
        {
            Name = pName; H = pH;
        }
        public mcReplacement(XElement pXE)
        {
            Name = pXE.Element("Name").Value;
            H = mscMslns.ToDouble(pXE.Element("H").Value);
        }
        public XElement toXML()
        {
            return new XElement("msReplacement",
                            new XElement("Name", Name),
                            new XElement("H", H)
                            );
        }
    }
}

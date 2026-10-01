using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    //围护构件
    [Serializable]//序列化类
    public class mcEclsCpnt : ItoXML
    {
        public double H;//此级围护的高度，大于0为固定值，否则为均分值
        public double stepWidth;//平台宽度
        private string name;
        public string Name
        {
            set { Cpnt = mscMslns.DeepClone(mscInventory.Ecpnti[value]); name = value; }
        }
        public mcComponent Cpnt;
        public string Tag;

        public mcEclsCpnt(string pName, double pH = -1, double pWidth = 1)
        {
            Name = pName; H = pH; stepWidth = pWidth;
        }
        public mcEclsCpnt(XElement pXE)
        {
            name = pXE.Element("name").Value;
            H = mscMslns.ToDouble(pXE.Element("H").Value);
            stepWidth = mscMslns.ToDouble(pXE.Element("stepWidth").Value);
            Cpnt = new mcComponent(pXE.Element("mcComponent"));
        }
        public XElement toXML()
        {
            XElement rtXE = new XElement(this.ToString().Replace("section.", ""),
                new XElement("name", name),
                new XElement("H", H),
                new XElement("stepWidth", stepWidth)
                );
            rtXE.Add(Cpnt.toXML());
            return rtXE;
        }
    }
}

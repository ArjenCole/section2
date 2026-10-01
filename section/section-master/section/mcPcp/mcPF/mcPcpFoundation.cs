using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    //换填有一个列表，基础只能有一种
    [Serializable]//序列化类
    public class mcPcpFoundation : mcNameList<mcReplacement>
    {
        public const string Multi_PFTxt = "多地基原则";
        public mcComponent Foundation;
        public mcPcpFoundation()
        {
            Name = "新地基原则";
            Foundation = mscInventory.Fcpnti.First().Value;
        }
        public mcPcpFoundation(XElement pXE)
        {
            Name = pXE.Element("Name").Value;
            IEnumerable<XElement> elements = from ele in pXE.Elements("msReplacement")
                                             select ele;
            mList.Clear();
            foreach (XElement feXE in elements)
            {
                mList.Add(new mcReplacement(feXE));
            }
            Foundation = new mcComponent(pXE.Element("Foundation").Element("mcComponent"));
        }
        //换填总厚度
        public double TiA
        {
            get
            {
                double tmpValue = 0;
                foreach (mcReplacement femsR in mList)
                {
                    tmpValue += femsR.H;
                }
                return tmpValue;
            }
        }
        public override XElement toXML()
        {
            XElement rtXE = new XElement(this.ToString().Replace("section.", ""),
                               new XElement("Name", Name)
                           );
            XElement baseXml = base.toXML();
            foreach (XElement feXE in baseXml.Nodes())
            {
                if (feXE.Name == "Name") { continue; }
                rtXE.Add(feXE);
            }
            rtXE.Add(new XElement("Foundation", Foundation.toXML()));
            return rtXE;
        }

    }


}

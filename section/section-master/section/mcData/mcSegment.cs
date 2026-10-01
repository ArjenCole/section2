using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcSegment : mcNameList<mcUnit>
    {
        public mcSegment()
        {
            Name = "新建标段";
            mList = new List<mcUnit>();
        }
        public mcSegment(XElement pXE)
        {
            Name = pXE.Element("Name").Value;
            IEnumerable<XElement> elements = from ele in pXE.Elements("mcUnit")
                                             select ele;
            mList = new List<mcUnit>();
            foreach (XElement feXE in elements)
            {
                mcUnit tmE = new mcUnit(Name, feXE);
                mList.Add(tmE);
            }
        }
        public mcUnit Unit(string pUnitName)
        {
            return mList.Find(t => t.Name == pUnitName);
        }
        public List<string> UnitNames
        {
            get
            {
                List<string> rtListStr = new List<string>();
                foreach (mcUnit femS in mList)
                {
                    rtListStr.Add(femS.Name);
                }
                return rtListStr;
            }
        }

    }
}

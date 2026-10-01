using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcUnit : mcNameList<mcElement>
    {
        public string OwnerName;
        public mcUnit(string pOwnerName)
        {
            Name = "新建单位工程";
            OwnerName = pOwnerName;
            mList = new List<mcElement>();
        }
        public mcUnit(string pOwnerName, XElement pXE)
        {
            Name = pXE.Element("Name").Value;
            OwnerName = pOwnerName;

            IEnumerable<XElement> elements = from ele in pXE.Elements("mcElement")
                                             select ele;
            mList = new List<mcElement>();
            foreach (XElement feXE in elements)
            {
                mList.Add(mcElement.NewElement(feXE));
            }
        }
        public mcElement Element(int pIdx)
        {
            if (mList.Count == 0) { return null; }
            if (mList.Count < pIdx + 1) { return null; }
            return mList[pIdx];
        }
        public void SetmEx(int pIdx, mcElement pmE)
        {
            if (Count < pIdx + 1)
            {
                Add(pmE);
            }
            else
            {
                mList[pIdx] = pmE;
            }
        }
    }
}

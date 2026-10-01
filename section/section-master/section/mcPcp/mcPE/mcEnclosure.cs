using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    //围护做法——包含多个围护构件
    [Serializable]//序列化类
    public class mcEnclosure : mcNameList<mcEclsCpnt>
    {
        public const string MultiScpntTxt = "多级围护";

        public double MinDepth;
        private string eCpntCat;
        public string ECpntCat
        {
            get { return eCpntCat; }
            set { setECpnt(value); eCpntCat = value; }
        }
        private void setECpnt(string pCat)
        {
            string tmpStr = pCat;
            if (pCat == MultiScpntTxt) { tmpStr = mscInventory.Ecpnti.First().Key; }
            mList.Clear();
            mList.Add(new mcEclsCpnt(tmpStr));
        }
        public mcComponent WSCpnt;//止水构件

        public mcEnclosure()
        {
            MinDepth = 0;
            ECpntCat = mscInventory.Ecpnti.First().Key;
            WSCpnt = mscInventory.WScpnti.First().Value;
        }
        public mcEnclosure(XElement pXE)
        {
            MinDepth = mscMslns.ToDouble(pXE.Element("MinDepth").Value);
            eCpntCat = pXE.Element("eCpntCat").Value;
            IEnumerable<XElement> elements = from ele in pXE.Elements("mcEclsCpnt")
                                             select ele;
            mList.Clear();
            foreach (XElement feXE in elements)
            {
                mList.Add(new mcEclsCpnt(feXE));
            }
            WSCpnt = new mcComponent(pXE.Element("WSCpnt").Element("mcComponent"));
        }

        public string EclsDis()
        {
            if (ECpntCat == MultiScpntTxt)
                return ECpntCat;
            else
                return mList.First().Cpnt.Discribe();
        }
        public string WSDis()
        {
            return WSCpnt.Discribe();
        }
        /// <summary>
        /// 固定高度的做法层厚度
        /// </summary>
        /// <returns>所有固定高度层总厚度</returns>
        public double FixedH()
        {
            double rtH = 0;
            for (int i = 0; i < mList.Count; i++)
            {
                rtH += Math.Max(mList[i].H, 0);
            }
            return rtH;
        }
        /// <summary>
        /// 固定高度的做法层层数
        /// </summary>
        /// <returns>层数</returns>
        public double FixedCnt()
        {
            int rtCnt = 0;
            for (int i = 0; i < mList.Count; i++)
            {
                if (mList[i].H >= 0) { rtCnt++; }
            }
            return rtCnt;
        }

        public override XElement toXML()
        {
            XElement rtXE = new XElement(this.ToString().Replace("section.", ""),
                new XElement("MinDepth", MinDepth),
                new XElement("eCpntCat", eCpntCat)
                );
            XElement baseXml = base.toXML();
            foreach (XElement feXE in baseXml.Nodes())
            {
                if (feXE.Name == "Name") { continue; }
                rtXE.Add(feXE);
            }
            rtXE.Add(new XElement("WSCpnt", WSCpnt.toXML()));
            return rtXE;
        }
    }
}

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcE5 : mcElement//拖拉管
    {
        public mcE5()
        {
            unit = "m";
        }
        public mcE5(XElement pXE)
        {
            readXE(pXE);
            unit = "m";
        }
        public mcE5(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            GetData(pData, pDicPE, pDicPF);
            unit = "m";
        }

        public override string Specification()
        {
            string tStr = string.Empty;
            foreach (mcPipe femP in mList)
            {
                if (femP.Content == 0) { }
                else if (femP.Content == 1)
                {
                    tStr += "+D" + mscMslns.ToString(femP.Dn) + mscMslns.ToString(femP.Mat);
                }
                else
                {
                    tStr += "+" + mscMslns.ToString(femP.Content) + "×D" + mscMslns.ToString(femP.Dn) + mscMslns.ToString(femP.Mat);
                }
            }
            if (tStr.StartsWith("+")) { tStr = tStr.Remove(0, 1); }
            tStr += " 牵引管";
            return tStr;
        }
        public override List<KeyValuePair<string, Rectangle>> OntologyShape()
        {
            List<KeyValuePair<string, Rectangle>> rtList = new List<KeyValuePair<string, Rectangle>>();

            mcAtlas At = new mcAtlas(this);

            Rectangle outsideEllipse = new Rectangle(-Convert.ToInt16(mList.First().Dn / 2.0 + At.t), Convert.ToInt16(At.C1), Convert.ToInt16(mList.First().Dn + At.t * 2), Convert.ToInt16(mList.First().Dn + At.t * 2));
            rtList.Add(new KeyValuePair<string, Rectangle>("Ellipse", outsideEllipse));
            Rectangle insideEllipse = new Rectangle(-Convert.ToInt16(mList.First().Dn / 2.0), Convert.ToInt16(At.t + At.C1), Convert.ToInt16(mList.First().Dn), Convert.ToInt16(mList.First().Dn));
            rtList.Add(new KeyValuePair<string, Rectangle>("Ellipse", insideEllipse));
            return rtList;
        }

        protected override Dictionary<string, mcQ> getDQ()
        {
            if (AmountD == 0) { return null; }
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            rtD = mscGroove.PlusDic_StrmcQ(rtD, cal_pipes("拖拉管"));//加上管材
            rtD = mscGroove.MultDic_StrmcQ(rtD, AmountD);//×管道长度
            return rtD;
        }

    }
}

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcE2 : mcElement//包封埋管
    {
        public mcE2(XElement pXE)
        {
            readXE(pXE);
            unit = "m";
        }
        public mcE2(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            GetData(pData, pDicPE, pDicPF);
            unit = "m";
            Param.Add("包封宽 m", "1.5");
            Param.Add("包封高 m", "1.0");
        }
        public override double rtSizeB()
        {
            return mscMslns.ToDouble(Param["包封宽 m"]);
        }
        public override double rtSizeH()
        {
            return mscMslns.ToDouble(Param["包封高 m"]);
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
            tStr += " 包封";
            return tStr;
        }
        public override List<KeyValuePair<string, Rectangle>> OntologyShape()
        {
            List<KeyValuePair<string, Rectangle>> rtList = new List<KeyValuePair<string, Rectangle>>();

            mcAtlas At = new mcAtlas(this);

            Rectangle pack = new Rectangle(-Convert.ToInt16(SizeB * 1000 / 2.0), Convert.ToInt16(At.C1), Convert.ToInt16(SizeB * 1000), Convert.ToInt16(SizeH * 1000));
            rtList.Add(new KeyValuePair<string, Rectangle>("Rectangle", pack));
            Rectangle found = new Rectangle(-Convert.ToInt16((SizeB * 1000 + At.a * 2) / 2.0), Convert.ToInt16(0), Convert.ToInt16(SizeB * 1000 + At.a * 2), Convert.ToInt16(At.C1));
            rtList.Add(new KeyValuePair<string, Rectangle>("Rectangle", found));
            return rtList;
        }
        public override Dictionary<string, mcQ> cal_found()
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            mcPcpEnclosure mainPE = mscCtrl.DC.PE[mainPEname];//取出该元素的主围护原则
            mcAtlas At = new mcAtlas(this);

            double remainDepth = DepthD + (At.t + At.C1) / 1000.0;
            double foundAngle = mainPE.FoundAngle;
            #region 计算垫层并扣减
            double tmpFound = At.C1 / 1000.0 * (SizeB + At.a / 1000.0 * 2);
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "垫层|混凝土|m3", new mcQ(tmpFound));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "垫层|模板|m2", new mcQ(At.C1 / 1000.0 * 2));

            tmpFound = (-1) * Math.Min(remainDepth, (At.C1 + At.C2) / 1000.0) * (SizeB + (At.t * 2 + At.a * 2) / 1000.0);
            remainDepth -= Math.Min(remainDepth, (At.C1 + At.C2) / 1000.0);
            mcQ tmpQ = new mcQ(tmpFound);//垫层扣减

            rtD = mscGroove.PlusDic_StrmcQ(rtD, "垫层|" + mainPE.Cush.Name + "|m3", tmpQ);
            #endregion
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "包封|混凝土|m3", new mcQ(SizeB * SizeH));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "包封|模板|m2", new mcQ(SizeH * 2));

            double half = (-1) * SizeB * Math.Min(remainDepth, SizeH / 2.0);
            remainDepth -= Math.Min(remainDepth, SizeH / 2.0);
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "回填|" + mainPE.DockL + "|m3", new mcQ(half));

            half = (-1) * SizeB * Math.Min(remainDepth, SizeH / 2.0);
            remainDepth -= Math.Min(remainDepth, SizeH / 2.0);
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "回填|" + mainPE.DockH + "|m3", new mcQ(half));
            return rtD;
        }
        public override Dictionary<string, mcQ> cal_pipes(string Cat = "管材")
        {
            Dictionary<string, mcQ> rtDic = new Dictionary<string, mcQ>();
            foreach (mcPipe femP in mList)
            {
                mcE1 tmE1 = new mcE1(new string[] { "", "直埋管道", "0", "0", this.mainPEname, "", "" }, null, null);
                tmE1.mList[0] = femP;
                mcAtlas tAt = new mcAtlas(tmE1);
                double tR = (femP.Dn / 2.0 + tAt.t) / 1000.0;
                rtDic = mscGroove.PlusDic_StrmcQ(rtDic, "包封|混凝土|m3", new mcQ(-Math.PI * tR * tR * femP.Content));
            }

            rtDic = mscGroove.PlusDic_StrmcQ(rtDic, base.cal_pipes());

            return rtDic;


        }
    }
}

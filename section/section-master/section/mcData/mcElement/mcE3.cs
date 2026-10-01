using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcE3 : mcElement//箱涵
    {
        public mcE3()
        {
            unit = "m";
            initParam();
        }
        public mcE3(XElement pXE)
        {
            readXE(pXE);
            unit = "m";
        }
        public mcE3(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            GetData(pData, pDicPE, pDicPF);
            unit = "m";
            mList.Clear();
            initParam();
        }
        private void initParam()
        {
            Param.Add("净宽 m(含内壁厚度)", "3.5");
            Param.Add("净高 m", "2.0");
            Param.Add("底板厚 mm", "400");
            Param.Add("顶板厚 mm", "300");
            Param.Add("外壁厚 mm", "350");
            Param.Add("内壁 道", "0");
            Param.Add("内壁厚 mm", "250");
            Param.Add("含钢量 kg/m3", "150");
        }
        public override double rtSizeB()
        {
            return mscMslns.ToDouble(Param["净宽 m(含内壁厚度)"]) + mscMslns.ToDouble(Param["外壁厚 mm"]) * 2 / 1000.0;
        }
        public override double rtSizeH()
        {
            return mscMslns.ToDouble(Param["净高 m"]) + mscMslns.ToDouble(Param["底板厚 mm"]) / 1000.0 + mscMslns.ToDouble(Param["顶板厚 mm"]) / 1000.0;
        }

        public override string Specification()
        {
            string tStr = mscMslns.ToString(Param["净宽 m(含内壁厚度)"]) + "×" + mscMslns.ToString(Param["净高 m"]) + "箱涵";
            return tStr;
        }
        public override List<KeyValuePair<string, Rectangle>> OntologyShape()
        {
            List<KeyValuePair<string, Rectangle>> rtList = new List<KeyValuePair<string, Rectangle>>();

            mcAtlas At = new mcAtlas(this);
            double bt = mscMslns.ToDouble(Param["底板厚 mm"]);
            double tt = mscMslns.ToDouble(Param["顶板厚 mm"]);
            double ot = mscMslns.ToDouble(Param["外壁厚 mm"]);
            double it = mscMslns.ToDouble(Param["内壁厚 mm"]);
            double ic = mscMslns.ToDouble(Param["内壁 道"]);


            Rectangle outsideRect = new Rectangle(-Convert.ToInt32(SizeB * 1000 / 2.0), Convert.ToInt32(At.C1), Convert.ToInt32(SizeB * 1000), Convert.ToInt32(SizeH * 1000));
            rtList.Add(new KeyValuePair<string, Rectangle>("Rectangle", outsideRect));
            Rectangle found = new Rectangle(-Convert.ToInt32((SizeB * 1000 + At.a * 2) / 2.0), Convert.ToInt32(0), Convert.ToInt32(SizeB * 1000 + At.a * 2), Convert.ToInt32(At.C1));
            rtList.Add(new KeyValuePair<string, Rectangle>("Rectangle", found));

            double wph = (SizeB * 1000 - ot * 2 - ic * it) / (ic + 1);
            for (int i = 0; i <= ic; i++)
            {
                double tX = ot + (wph + it) * i - SizeB * 1000 / 2.0;
                double tY = bt + At.C1;
                double tH = SizeH * 1000 - bt - tt;
                double tW = wph;
                Rectangle insideRect = new Rectangle(Convert.ToInt32(tX), Convert.ToInt32(tY), Convert.ToInt32(tW), Convert.ToInt32(tH));
                rtList.Add(new KeyValuePair<string, Rectangle>("Rectangle", insideRect));
            }

            return rtList;
        }

        public override Dictionary<string, mcQ> cal_found()
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            mcPcpEnclosure mainPE = mscCtrl.DC.PE[mainPEname];//取出该元素的主围护原则
            mcAtlas At = new mcAtlas(this);

            double bt = mscMslns.ToDouble(Param["底板厚 mm"]) / 1000.0;
            double tt = mscMslns.ToDouble(Param["顶板厚 mm"]) / 1000.0;
            double ot = mscMslns.ToDouble(Param["外壁厚 mm"]) / 1000.0;
            double it = mscMslns.ToDouble(Param["内壁厚 mm"]) / 1000.0;
            double ic = mscMslns.ToDouble(Param["内壁 道"]);
            if (!Param.Keys.Contains("含钢量 kg/m3")) Param.Add("含钢量 kg/m3", "150");
            double refRate = mscMslns.ToDouble(Param["含钢量 kg/m3"]) / 1000.0;

            double remainDepth = DepthD + (At.t + At.C1) / 1000.0;

            #region 计算垫层并扣减
            double tmpFound = At.C1 / 1000.0 * (SizeB + At.a / 1000.0 * 2);
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|垫层|m3", new mcQ(tmpFound));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|垫层模板|m2", new mcQ(At.C1 / 1000.0 * 2));

            tmpFound = (-1) * Math.Min(remainDepth, (At.C1 + At.C2) / 1000.0) * (SizeB + (At.t * 2 + At.a * 2) / 1000.0);
            remainDepth -= Math.Min(remainDepth, (At.C1 + At.C2) / 1000.0);
            mcQ tmpQ = new mcQ(tmpFound);//垫层扣减

            rtD = mscGroove.PlusDic_StrmcQ(rtD, "垫层|" + mainPE.Cush.Name + "|m3", tmpQ);
            #endregion
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|底板|m3", new mcQ(SizeB * bt));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|底板模板|m2", new mcQ(bt * 2));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|箱涵壁|m3", new mcQ((SizeH - bt) * ot * 2 + (SizeH - bt - tt) * ic * it));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|箱涵壁模板|m2", new mcQ((SizeH - bt) * 2 * 2 + (SizeH - bt - tt) * ic * 2));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|顶板|m3", new mcQ((SizeB - ot * 2) * tt));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|顶板模板|m2", new mcQ(SizeB - ot * 2));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "箱涵|钢筋|t", new mcQ(refRate * (rtD["箱涵|底板|m3"].Q + rtD["箱涵|箱涵壁|m3"].Q + rtD["箱涵|顶板|m3"].Q)));

            double half = (-1) * SizeB * Math.Min(remainDepth, SizeH / 2.0);
            remainDepth -= Math.Min(remainDepth, SizeH / 2.0);
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "回填|" + mainPE.DockL + "|m3", new mcQ(half));

            half = (-1) * SizeB * Math.Min(remainDepth, SizeH / 2.0);
            remainDepth -= Math.Min(remainDepth, SizeH / 2.0);
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "回填|" + mainPE.DockH + "|m3", new mcQ(half));
            return rtD;
        }
    }
}

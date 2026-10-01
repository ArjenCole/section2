using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcE7 : mcElement
    {
        public mcE7()
        {

        }
        public mcE7(XElement pXE)
        {
            readXE(pXE);
        }
        public mcE7(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            GetData(pData, pDicPE, pDicPF);
            unit = "个";
            mList.Clear();
            Param.Add("-名称", "自定义构筑物");
            Param.Add("-单位", "个");

        }
        public override double rtSizeB()
        {
            return 0;
        }
        public override double rtSizeH()
        {
            return 0;
        }

        public override string Specification()
        {
            try
            {
                return Param["-名称"];
            }
            catch
            {
                return "未找到名称参数";
            }
        }
        protected override Dictionary<string, mcQ> getDQ()
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, section.mcQ>();
            if (AmountD == 0) return rtD;
            foreach (string  feKey in Param.Keys)
            {
                if (feKey.StartsWith("-")) continue;
                mcQ tmQ = new section.mcQ(Param[feKey]);
                rtD.Add(feKey, tmQ);
            }
            if(Param.Keys.Contains("-井筒 个")&& Param.Keys.Contains("-井筒 m3/m"))
            {
                double th = 0.4;//默认最小井筒高度
                double tC = mscMslns.ToDouble(Param["-井筒 个"]);
                double tQ = mscMslns.ToDouble(Param["-井筒 m3/m"]);
                if (Param.Keys.Contains("-井高 m"))
                    th = Math.Max(mscMslns.ToDouble(this.Depth) - mscMslns.ToDouble(Param["-井高 m"]), th);
                rtD.Add("构筑物|井筒|m3", new mcQ(tC * th * tQ));

            }
            rtD = mscGroove.MultDic_StrmcQ(rtD, AmountD);//×数量
            return rtD;
        }

    }
}

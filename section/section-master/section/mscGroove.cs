using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;


namespace section
{
    [Serializable]//序列化类
    public static class mscGroove
    {
        public static mcElement mE;

        private static mcPcpEnclosure mainPE;
        private static mcAtlas At;

        public static Dictionary<string, mcQ> Cal(mcElement pmE)
        {
            mE = pmE;
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            Dictionary<string, mcQ> rtNull = new Dictionary<string, mcQ>();

            if (mE.AmountD == 0) { return rtNull; }
            if (!mscCtrl.DC.PE.Keys.Contains(mE.mainPEname)) { return rtNull; }

            At = new mcAtlas(mE);
            mainPE = mE.showPEname==mcPcpEnclosure.Multi_PETxt? mscCtrl.DC.PE[mE.mainPEname]: mscCtrl.DC.PE[mE.showPEname];//沟槽回填、管道基础、支撑等按照主要原则计算
            foreach (string femPEname in mE.PEname.Keys)
            {
                if (!mscCtrl.DC.PE.Keys.Contains(femPEname)) { return rtNull; }
                foreach (string femPFname in mE.PFname.Keys)
                {
                    if (!mscCtrl.DC.PF.Keys.Contains(femPFname)) { return rtNull; }
                    mcPcpEnclosure tPE = mscCtrl.DC.PE[femPEname];
                    mcPcpFoundation tPF = mscCtrl.DC.PF[femPFname];
                    At.C1 = At.C1 == 0 ? tPE.Cush.H : At.C1;
                    double grooveDepth = mE.DepthD + D10E3(tPF.TiA + At.t + At.C1);
                    mcEnclosure tEcls = tPE.ChoiceEcls(grooveDepth);//选择围护做法
                    Dictionary<string, mcQ> tmpQ = cal_groove(tPE, tEcls, tPF, grooveDepth);//计算断面工程量
                    if (tmpQ.Count == 0) { return rtNull; }//覆土不足，不再进一步计算
                    tmpQ = PlusDic_StrmcQ(tmpQ, cal_precipitation(tPE, tEcls, tPE.Excvt, tPF, grooveDepth));//计算降水
                    tmpQ = PlusDic_StrmcQ(tmpQ, cal_Ecpnts(tEcls, grooveDepth, mE.AmountD, "F"));//计算围护
                    tmpQ = PlusDic_StrmcQ(tmpQ, cal_Fcpnts(tPF.Foundation, grooveDepth, mE.AmountD));//计算特殊地基
                    tmpQ = MultDic_StrmcQ(tmpQ, mE.PEname[femPEname] * mE.PFname[femPFname]);//断面*系数
                    rtD = PlusDic_StrmcQ(rtD, tmpQ);
                }
            }
            double tmpDepth = mE.DepthD + D10E3(At.t + At.C1);
            mcEnclosure tmpEcls = mainPE.ChoiceEcls(tmpDepth);
            rtD = PlusDic_StrmcQ(rtD, cal_Ecpnts(tmpEcls, tmpDepth, mE.AmountD, "Z"));//计算支撑-计算支撑时不考虑换填层厚度

            //rtD = PlusDic_StrmcQ(rtD, mE.cal_found());//加上基础，扣除占土
            //rtD = PlusDic_StrmcQ(rtD, mE.cal_pipes());//加上管材
            //rtD = MultDic_StrmcQ(rtD, mE.Amount);//×管道长度
            return rtD;
        }
        #region 计算工程量
        /// <summary>
        /// 计算多级围护做法总体工程量
        /// </summary>
        /// <param name="pmEcls">选中的围护做法</param>
        /// <param name="pmPF">选中的地基处理原则</param>
        /// <param name="cof1">围护做法的占比系数</param>
        /// <param name="cof2">地基处理的占比系数</param>
        /// <returns>工程量字典</returns>
        private static Dictionary<string, mcQ> cal_groove(mcPcpEnclosure pmPE, mcEnclosure pmEcls, mcPcpFoundation pmPF, double pDepth)
        {
            Dictionary<string, mcQ> rtDic = new Dictionary<string, mcQ>();

            List<mcReplacement> Backfill = new List<mcReplacement>();//分层回填列表
            #region 编写分层回填列表

            pDepth = Math.Max(0, pDepth);
            double remainDepth = pDepth;

            for (int i = pmPF.mList.Count - 1; i >= 0; i--)//把换填加入回填列表
            {
                ///Backfill.Add(D10E3(pmPF.mList[i]));
                Backfill.Add(new mcReplacement("换填|" + pmPF.mList[i].Name + "|m3", minH(D10E3(pmPF.mList[i].H), remainDepth, out remainDepth)));
            }
            remainDepth = pDepth - D10E3(pmPF.TiA);
            if (remainDepth < 0)
                remainDepth = 0;

            Backfill.Add(new mcReplacement("垫层|" + mainPE.Cush.Name + "|m3", minH(D10E3(At.C1 + At.C2), remainDepth,out remainDepth)));
            Backfill.Add(new mcReplacement("回填|" + mainPE.DockL + "|m3", minH(mE.SizeH / 2 + D10E3(At.t - At.C2), remainDepth,out remainDepth)));
            Backfill.Add(new mcReplacement("回填|" + mainPE.DockH + "|m3", minH(mE.SizeH / 2 + D10E3(At.t), remainDepth,out remainDepth)));
            Backfill.Add(new mcReplacement("回填|" + mainPE.Cover50 + "|m3", minH(0.5, remainDepth,out remainDepth)));
            //if(pDepth - pmPF.TiA - mE.SizeH - D10E3(At.t * 2 + At.C1) - 0.5 < 0) { return rtDic; }
            Backfill.Add(new mcReplacement("回填|" + mainPE.Cover + "|m3", minH(pDepth  - mE.SizeH - D10E3(pmPF.TiA + At.t * 2 + At.C1) - 0.5, remainDepth,out remainDepth)));
            #endregion

            double Bcurrent = At.grooveB == 0 ? mE.SizeB + D10E3(At.t * 2 + At.a * 2 + At.workwidth * 2) : D10E3(At.grooveB);
            double Hcurrent = 0;
            double slope = 0;
            int step = pmEcls.mList.Count - 1;
            List<double> stepHeight = splitHbyStep(pmEcls, pDepth);//分级标高

            #region 根据标高递推计算回填
            for (int i = 0; i < Backfill.Count; i++)
            {
                double Htarget = Hcurrent + Backfill[i].H;//设定此层回填的目标标高
                do
                {
                    var t = Math.Min(Htarget, stepHeight[step]);
                    double Hdelta = Math.Min(Htarget, stepHeight[step]) - Hcurrent;//确定标高向上移动的距离
                    slope = pmEcls.mList[step].Cpnt.param["A"].Key.StartsWith("放坡系数") ? mscMslns.ToDouble(pmEcls.mList[step].Cpnt.param["A"].Value) : 0;
                    mcQ tmpQ = new mcQ(Trapezoid(Bcurrent, Hdelta, slope));//计算梯形断面面积
                    rtDic = PlusDic_StrmcQ(rtDic, "开挖|" + mainPE.Excvt + "|m3", tmpQ);//计入挖方
                    rtDic = PlusDic_StrmcQ(rtDic, Backfill[i].Name, tmpQ);//计入对应回填量
                    Hcurrent = Hcurrent + Hdelta;//标高向上移动
                    Bcurrent += Hdelta * slope * 2;//当前标高宽度计算
                    if ((Hcurrent == stepHeight[step]) && (step > 0))  //判断是否处于分级标高
                    {
                        step--;//围护分级选择向上移动
                        if ((stepHeight[step] != stepHeight[step + 1]) && stepHeight[step + 1] != 0)
                            Bcurrent += pmEcls.mList[step].stepWidth * 2;//根据围护的平台宽度放大当前标高的宽度
                    }
                }
                while (Hcurrent - Htarget < -0.0001);
                //while (Math.Round(Hcurrent,2) < Math.Round(Htarget,2));
            }
            #endregion
            return rtDic;
        }
        public static double minH(double pH, double pRDepth,out double opRDepth)
        {
            double rtDouble = 0;
            if (pH <= 0)
            {
                rtDouble = 0;
                opRDepth = pRDepth;
            }
            else if (pRDepth <= pH)
            {
                rtDouble = pRDepth;
                opRDepth = 0;
            }
            else
            {
                rtDouble = pH;
                opRDepth = pRDepth - pH;
            }
            return rtDouble;
        }
        /// <summary>
        /// 划分分级围护的标高范围
        /// </summary>
        /// <param name="pmEcls">围护做法</param>
        /// <param name="pDepth">沟槽总埋深</param>
        /// <returns></returns>
        public static List<double> splitHbyStep(mcEnclosure pmEcls, double pDepth)
        {
            List<double> rtList = new List<double>();
            double height = 0;
            for (int i = pmEcls.mList.Count - 1; i >= 0; i--)
            {
                var t = pmEcls.FixedH();
                var v = pmEcls.FixedCnt();
                double h = pmEcls.mList[i].H >= 0 ? pmEcls.mList[i].H : (pDepth - pmEcls.FixedH()) / (pmEcls.mList.Count - pmEcls.FixedCnt());
                height += h;
                rtList.Insert(0, Math.Max(0, height));
            }
            return rtList;
        }
        /// <summary>
        /// 计算围护工程量
        /// </summary>
        /// <param name="pmEcls">选中的围护做法</param>
        /// <param name="pDepth">沟槽深度</param>
        /// <param name="pCount">长度</param>
        /// <param name="pCat">工程量种类 围护/支撑</param>
        /// <returns></returns>
        private static Dictionary<string, mcQ> cal_Ecpnts(mcEnclosure pmEcls, double pDepth, double pCount, string pCat = "F")
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            foreach (mcEclsCpnt femEC in pmEcls.mList)
            {
                double h = femEC.H >= 0 ? femEC.H : (pDepth - pmEcls.FixedH()) / (pmEcls.mList.Count - pmEcls.FixedCnt());
                rtD = PlusDic_StrmcQ(rtD, femEC.Cpnt.Q(h, D10E3(mE.SizeB + At.t * 2 + At.a * 2 + At.workwidth * 2), pCount, pCat));
            }
            rtD = PlusDic_StrmcQ(rtD, pmEcls.WSCpnt.Q(pDepth, D10E3(mE.SizeB + At.t * 2 + At.a * 2 + At.workwidth * 2), pCount, "F"));
            return rtD;
        }
        private static Dictionary<string, mcQ> cal_Fcpnts(mcComponent pmC, double pDepth, double pCount)
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            double Bbottom = At.grooveB == 0 ? mE.SizeB + D10E3(At.t * 2 + At.a * 2 + At.workwidth * 2) : D10E3(At.grooveB);
            rtD = pmC.Q(pDepth, Bbottom, pCount);
            return rtD;
        }

        /// <summary>
        /// 计算降水
        /// </summary>
        /// <param name="pmEcls">选中的围护做法</param>
        /// <param name="pName">当前围护原则中挖土方的类别名称</param>
        /// <param name="pmPF">当前地基原则</param>
        /// <param name="pDepth">沟槽深度</param>
        /// <returns></returns>
        public static Dictionary<string, mcQ> cal_precipitation(mcPcpEnclosure pmPE, mcEnclosure pmEcls, string pName, mcPcpFoundation pmPF, double pDepth)
        {
            Dictionary<string, mcQ> rtDic = new Dictionary<string, mcQ>();
            if ((mainPE.deepwell.elevation >= 0) && (pDepth > mainPE.deepwell.elevation))
                rtDic.Add("降水|深井|座", new mcQ(Math.Ceiling(mE.AmountD / mainPE.deepwell.gap) * mainPE.deepwell.sides / mE.AmountD));
            else if ((mainPE.bigwell.elevation >= 0) && (pDepth > mainPE.bigwell.elevation))
                rtDic.Add("降水|大口径井点|座", new mcQ(Math.Ceiling(mE.AmountD / mainPE.bigwell.gap) * mainPE.bigwell.sides / mE.AmountD));
            else if ((mainPE.jetwell.elevation >= 0) && (pDepth > mainPE.jetwell.elevation))
                rtDic.Add("降水|喷射井点|根", new mcQ(Math.Ceiling(mE.AmountD / mainPE.jetwell.gap) * mainPE.jetwell.sides / mE.AmountD));
            else if ((mainPE.lightwell.elevation >= 0) && (pDepth > mainPE.lightwell.elevation))
                rtDic.Add("降水|轻型井点|根", new mcQ(Math.Ceiling(mE.AmountD / mainPE.lightwell.gap) * mainPE.lightwell.sides / mE.AmountD));
            else if (mainPE.wetsoild.elevation >= 0)
            {
                if(pDepth>1)
                {
                    Dictionary<string, mcQ> tD = cal_groove(pmPE, pmEcls, pmPF, pDepth - 1);
                    mcQ tmQ = new mcQ();
                    if (tD.Keys.Contains("开挖|" + pName + "|m3"))
                        tmQ = tD["开挖|" + pName + "|m3"];
                    rtDic.Add("降水|湿土排水|m3", new mcQ(tmQ.Q));
                }
            }
            return rtDic;
        }

        #endregion

        #region 计算工具函数
        /// <summary>
        /// 工程量字典求和
        /// </summary>
        /// <param name="p1"></param>
        /// <param name="p2"></param>
        /// <returns></returns>
        public static Dictionary<string, mcQ> PlusDic_StrmcQ(Dictionary<string, mcQ> p1, Dictionary<string, mcQ> p2)
        {
            Dictionary<string, mcQ> rtDic = new Dictionary<string, mcQ>();
            if (p1 == null) { p1 = new Dictionary<string, mcQ>(); }
            foreach (string Key in p1.Keys)
            {
                if (rtDic.Keys.Contains(Key))
                {
                    rtDic[Key] = PlusmcQ(rtDic[Key], p1[Key]);
                }
                else
                {
                    rtDic.Add(Key, p1[Key]);
                }
            }
            if (p2 == null) { p2 = new Dictionary<string, mcQ>(); }
            foreach (string Key in p2.Keys)
            {
                if (rtDic.Keys.Contains(Key))
                {
                    rtDic[Key] = PlusmcQ(rtDic[Key], p2[Key]);
                }
                else
                {
                    rtDic.Add(Key, p2[Key]);
                }
            }
            return rtDic;
        }
        public static Dictionary<string, mcQ> PlusDic_StrmcQ(Dictionary<string, mcQ> pD, string pName, mcQ pmQ)
        {
            Dictionary<string, mcQ> rtDic = mscMslns.DeepClone(pD);
            if (rtDic.Keys.Contains(pName))
            {
                rtDic[pName] = PlusmcQ(rtDic[pName], pmQ);
            }
            else
            {
                rtDic.Add(pName, pmQ);
            }
            return rtDic;
        }
        public static Dictionary<string, mcQ> MultDic_StrmcQ(Dictionary<string, mcQ> pDQ, double pCoe)
        {
            foreach (string feKey in pDQ.Keys)
            {
                pDQ[feKey].Mult(pCoe);
            }
            return pDQ;
        }
        /// <summary>
        /// 工程量类求和
        /// </summary>
        /// <param name="p1"></param>
        /// <param name="p2"></param>
        /// <returns></returns>
        private static mcQ PlusmcQ(mcQ p1, mcQ p2)
        {
            mcQ rtmQ = new mcQ();
            rtmQ.Q = p1.Q + p2.Q;

            return rtmQ;
        }

        /// <summary>
        /// 梯形断面面积
        /// </summary>
        /// <param name="pB">下底宽</param>
        /// <param name="pH">高</param>
        /// <param name="pSlope">放坡系数</param>
        /// <returns></returns>
        private static double Trapezoid(double pB, double pH, double pSlope)
        {
            double tmpBupper = pB + pH * pSlope * 2;
            return ((pB + tmpBupper) * pH / 2.0);
        }

        public static double D10E3(double p)
        {
            return p / 1000.0;
        }
        public static mcReplacement D10E3(mcReplacement p)
        {
            mcReplacement rtp = mscMslns.DeepClone(p);
            rtp.Name = "换填|" + p.Name + "|m3";
            rtp.H = D10E3(p.H);
            return rtp;
        }
        #endregion

        #region 工程量字典排序
        public static IOrderedEnumerable<KeyValuePair<string,mcQ>> OrderDQ(Dictionary<string, mcQ> pDQ)
        {
            return from objDic in pDQ orderby order(objDic.Key) select objDic;
            //return from objDic in pDQ orderby order(objDic.Key) descending select objDic; 降序
        }
        private static int order(string pKey)
        {
            Dictionary<string, int> ivk = new Dictionary<string, int>();
            ivk.Add("开挖", 01);
            ivk.Add("换填", 10);
            ivk.Add("垫层", 20);
            ivk.Add("回填", 21);
            ivk.Add("围护", 30);
            ivk.Add("支撑", 31);
            ivk.Add("降水", 32);
            ivk.Add("包封", 39);
            ivk.Add("管道基础", 40);
            ivk.Add("管材", 41);
            ivk.Add("顶管", 42);
            ivk.Add("拖拉管", 43);
            ivk.Add("箱涵", 44);
            string[] tStr = pKey.Split(new[] { "|" }, StringSplitOptions.None);
            if (tStr.Length == 0) { return 10000; }
            if (ivk.Keys.Contains(tStr[0]))
                return ivk[tStr[0]];
            else
                return 10000;
        }
        #endregion
    }
    [Serializable]//序列化类
    public class mcQ
    {
        public double Q = 0;
        public string Exp = string.Empty;
        public mcQ(string pQ , string pExp = "")
        {
            Q = mscMslns.ToDouble(pQ);
        }
        public mcQ(double pQ = 0, string pExp = "")
        {
            Q = pQ;
        }
        public void Mult(double pCoefficient)
        {
            Q *= pCoefficient;
        }
    }
}

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public abstract class mcElement : mcNameList<mcPipe>
    {
        #region 基本属性字段
        public string Category { get; set; }//类别：管道 配件 井…
        protected string unit = string.Empty;//单位
        public string Unit {
            get
            {
                if (Param.Keys.Contains("-单位")) unit = Param["-单位"];
                return unit;
            }
        }

        public string Depth
        {
            get { return depthS; }
            set
            {
                depthS = value;
                DepthD = mscMslns.ToDouble(mscExp.Eval(depthS));
            }
        }
        private string depthS;
        public double DepthD;

        public string Amount
        {
            get { return amountS; }
            set
            {
                amountS = value;
                AmountD = mscMslns.ToDouble(mscExp.Eval(amountS));
            }
        }
        private string amountS;
        public double AmountD;

        private string showpename = string.Empty;//显示围护类型
        public string showPEname
        {
            get { return showpename; }
            set
            {
                if (value == showpename) { return; }
                showpename = value;
                if (value != mcPcpEnclosure.Multi_PETxt)
                {
                    if (PEname == null)
                        PEname = new Dictionary<string, double>();
                    else
                        PEname.Clear();
                    PEname.Add(showpename, 1);
                }
            }
        }
        private string showpfname = string.Empty;//显示地基类型
        public string showPFname
        {
            get { return showpfname; }
            set
            {
                if (value == showpfname) { return; }
                showpfname = value;
                if (value != mcPcpFoundation.Multi_PFTxt)
                {
                    if (PFname == null)
                        PFname = new Dictionary<string, double>();
                    else
                        PFname.Clear();
                    PFname.Add(showpfname, 1);
                }
            }
        }
        public Dictionary<string, double> PEname = new Dictionary<string, double>();//key原则名称value占比系数
        public string mainPEname = string.Empty;//主要围护原则
        public Dictionary<string, double> PFname = new Dictionary<string, double>();//key原则名称value占比系数
        //包封埋管、矩形井、箱涵
        public double SizeB { get { return rtSizeB(); } }
        public double SizeH { get { return rtSizeH(); } }
        public virtual double rtSizeB() { return 0; }
        public virtual double rtSizeH() { return 0; }
        //其他自定义属性
        public Dictionary<string, string> Param = new Dictionary<string, string>();
        //直埋管道、包封埋管、顶管、牵引管
        public string Source { get; set; }//字符串来源 用于识别
        #endregion

        public mcElement()
        {
            Name = "";
            Category = string.Empty;
            Depth = "0";
            Amount = "0";
            mList = new List<mcPipe>();
        }
        protected void readXE(XElement pXE)
        {
            Name = pXE.Element("Name").Value;
            Category = pXE.Element("Category").Value;
            Depth = mscMslns.ToString(pXE.Element("Depth").Value);
            Amount = mscMslns.ToString(pXE.Element("Amount").Value);
            showPEname = pXE.Element("showPEname").Value;
            showPFname = pXE.Element("showPFname").Value;
            mainPEname = pXE.Element("mainPEname").Value;
            Source = pXE.Element("Source").Value;
            IEnumerable<XElement> elements = from ele in pXE.Elements("PEname")
                                             select ele;
            PEname = new Dictionary<string, double>();
            foreach (XElement feXE in elements)
            {
                PEname.Add(feXE.Element("key").Value, mscMslns.ToDouble(feXE.Element("value").Value));
            }
            elements = from ele in pXE.Elements("PFname")
                       select ele;
            PFname = new Dictionary<string, double>();
            foreach (XElement feXE in elements)
            {
                PFname.Add(feXE.Element("key").Value, mscMslns.ToDouble(feXE.Element("value").Value));
            }

            elements = from ele in pXE.Elements("Param")
                       select ele;
            Param = new Dictionary<string, string>();
            foreach (XElement feXE in elements)
            {
                Param.Add(feXE.Element("key").Value, mscMslns.ToString(feXE.Element("value").Value));
            }

            elements = from ele in pXE.Elements("msPipe")
                       select ele;
            mList = new List<mcPipe>();
            foreach (XElement feXE in elements)
            {
                mcPipe tmP = new mcPipe(feXE);
                mList.Add(tmP);
            }
        }

        public Dictionary<string, mcQ> DQ
        {
            get { return getDQ(); }
        }
        protected virtual Dictionary<string, mcQ> getDQ()
        {
            Dictionary<string, mcQ> rtD = mscGroove.Cal(this);
            if (rtD.Count == 0) { return rtD; }//说明覆土不足
            rtD = mscGroove.PlusDic_StrmcQ(rtD, cal_found());//加上基础，扣除占土
            rtD = mscGroove.PlusDic_StrmcQ(rtD, cal_pipes());//加上管材
            rtD = mscGroove.MultDic_StrmcQ(rtD, AmountD);//×管道长度
            return rtD;
        }
        public double TotalPrice
        {
            get
            {
                double rtDouble = 0;
                Dictionary<string, mcQ> tDQ = DQ;
                foreach (string feKey in tDQ.Keys)
                    rtDouble += mscCtrl.getPrice(feKey) * tDQ[feKey].Q;
                return rtDouble;
            }
        }
        public virtual Dictionary<string, mcQ> cal_found() { return null; }
        public virtual Dictionary<string, mcQ> cal_pipes(string Cat = "管材")
        {
            Dictionary<string, mcQ> rtDic = new Dictionary<string, mcQ>();
            foreach (mcPipe femP in mList)
                rtDic = mscGroove.PlusDic_StrmcQ(rtDic, Cat + "|" + femP.Mat + " Dn" + mscMslns.ShowDouble(femP.Dn) + "|m", new mcQ(femP.Content));
            return rtDic;
        }

        public virtual string Specification() { return null; }
        public virtual List<KeyValuePair<string, Rectangle>> OntologyShape() { return null; }

        public override XElement toXML()
        {
            XElement rtXE = new XElement("mcElement",
                    new XElement("Name", Name),//元素名称
                    new XElement("Category", Category),
                    new XElement("Depth", Depth),
                    new XElement("Amount", Amount),
                    new XElement("showPEname", showPEname),
                    new XElement("showPFname", showPFname),
                    new XElement("mainPEname", mainPEname),
                    new XElement("SizeB", SizeB),
                    new XElement("SizeH", SizeH),
                    new XElement("Source", Source)
                );
            foreach (string feKey in PEname.Keys)
            {
                rtXE.Add(new XElement("PEname",
                            new XElement("key", feKey),
                            new XElement("value", PEname[feKey].ToString())
                            )
                        );
            }
            foreach (string feKey in PFname.Keys)
            {
                rtXE.Add(new XElement("PFname",
                            new XElement("key", feKey),
                            new XElement("value", PFname[feKey].ToString())
                            )
                        );
            }
            foreach (mcPipe femP in mList)
            {
                rtXE.Add(new XElement("msPipe",
                            new XElement("Mat", femP.Mat),
                            new XElement("Dn", femP.Dn),
                            new XElement("Content", femP.Content)
                            )
                        );
            }
            foreach (string feKey in Param.Keys)
            {
                rtXE.Add(new XElement("Param",
                           new XElement("key", feKey),
                           new XElement("value", Param[feKey].ToString())
                           )
                       );
            }
            return rtXE;

        }
        public void GetData(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            if (pData.Count() == 7)
            {
                Name = mscMslns.ToString(pData[0]);
                Category = mscMslns.ToString(pData[1]);
                Depth = mscMslns.ToString(pData[2]);
                Amount = mscMslns.ToString(pData[3]);
                showPEname = mscMslns.ToString(pData[4]);
                showPFname = mscMslns.ToString(pData[5]);
                Source = mscMslns.ToString(pData[6]);
            }
            PEname = pDicPE; if (PEname == null) { PEname = new Dictionary<string, double>(); PEname.Add(mscCtrl.DC.PE.First().Key, 1); }
            PFname = pDicPF; if (PFname == null) { PFname = new Dictionary<string, double>(); PFname.Add(mscCtrl.DC.PF.First().Key, 1); }
            if (showPEname == string.Empty) { showPEname = mscCtrl.DC.PE.First().Key; }
            if (showPFname == string.Empty) { showPFname = mscCtrl.DC.PF.First().Key; }
            if (showPEname == mcPcpEnclosure.Multi_PETxt)
            {
                if (mainPEname == string.Empty)
                    mainPEname = PEname.First().Key;
            }
            else
            {
                mainPEname = showPEname;
            }
            Add(new mcPipe());

        }
        public mcPipe Pipe(int pIdx)
        {
            if (mList.Count == 0) { return null; }
            if (mList.Count < pIdx + 1) { return null; }
            return mList[pIdx];
        }

        public static Dictionary<string, string> typeDic = new Dictionary<string, string>()
        {
            {"", "mcE0"},
            {"直埋管道", "mcE1"},
            {"包封埋管", "mcE2"},
            {"箱涵", "mcE3"},
            {"顶管", "mcE4"},
            {"牵引管", "mcE5"},
            {"管廊", "mcE6"},
            {"构筑物", "mcE7"}
        };
        public string Type
        {
            get { return typeDic.Keys.Contains(Category) ? typeDic[Category] : "mcE0"; }
        }

        public void SetPE(Dictionary<string, double> pPEname, string pShowPEname, string pMainPEname)
        {
            double restPct = 0;
            PEname.Clear();
            foreach (string feKey in pPEname.Keys)
                if (mscCtrl.DC.PE.Keys.Contains(feKey))
                    PEname.Add(feKey, pPEname[feKey]);
                else
                    restPct += pPEname[feKey];
            if (PEname.Count == 0)
                PEname.Add(mscCtrl.DC.PE.First().Key, 1);
            PEname[PEname.First().Key] += restPct;
            showpename = (mscCtrl.DC.PE.Keys.Contains(pShowPEname) || pShowPEname == mcPcpEnclosure.Multi_PETxt) ? pShowPEname : PEname.First().Key;
            mainPEname = mscCtrl.DC.PE.Keys.Contains(pMainPEname) ? pMainPEname : PEname.First().Key;
        }
        public void SetPF(Dictionary<string, double> pPFname, string pShowPFname)
        {
            double restPct = 0;
            PFname.Clear();
            foreach (string feKey in pPFname.Keys)
                if (mscCtrl.DC.PF.Keys.Contains(feKey))
                    PFname.Add(feKey, pPFname[feKey]);
                else
                    restPct += pPFname[feKey];
            if (PFname.Count == 0)
                PFname.Add(mscCtrl.DC.PF.First().Key, 1);
            PFname[PFname.First().Key] += restPct;
            showpfname = (mscCtrl.DC.PF.Keys.Contains(pShowPFname) || pShowPFname == mcPcpFoundation.Multi_PFTxt) ? pShowPFname : PFname.First().Key;
        }
        public static mcElement NewElement(string pCat, object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            string tType = typeDic.Keys.Contains(pCat) ? typeDic[pCat] : "mcE0";
            switch (tType)
            {
                case "mcE1":
                    mcE1 tmE1 = new mcE1(pData, pDicPE, pDicPF);
                    return tmE1;
                case "mcE2":
                    mcE2 tmE2 = new mcE2(pData, pDicPE, pDicPF);
                    return tmE2;
                case "mcE3":
                    mcE3 tmE3 = new mcE3(pData, pDicPE, pDicPF);
                    return tmE3;
                case "mcE4":
                    mcE4 tmE4 = new mcE4(pData, pDicPE, pDicPF);
                    return tmE4;
                case "mcE5":
                    mcE5 tmE5 = new mcE5(pData, pDicPE, pDicPF);
                    return tmE5;
                case "mcE6":
                    mcE6 tmE6 = new mcE6(pData, pDicPE, pDicPF);
                    return tmE6;
                case "mcE7":
                    mcE7 tmE7 = new mcE7(pData, pDicPE, pDicPF);
                    return tmE7;
                default:
                    mcE0 tmE0 = new mcE0(pData, pDicPE, pDicPF);
                    return tmE0;
            }
        }
        public static mcElement NewElement(XElement pXE)
        {
            string tCat = pXE.Element("Category").Value;
            string tType = typeDic.Keys.Contains(tCat) ? typeDic[tCat] : "mcE0";
            switch (tType)
            {
                case "mcE1":
                    mcE1 tmE1 = new mcE1(pXE);
                    return tmE1;
                case "mcE2":
                    mcE2 tmE2 = new mcE2(pXE);
                    return tmE2;
                case "mcE3":
                    mcE3 tmE3 = new mcE3(pXE);
                    return tmE3;
                case "mcE4":
                    mcE4 tmE4 = new mcE4(pXE);
                    return tmE4;
                case "mcE5":
                    mcE5 tmE5 = new mcE5(pXE);
                    return tmE5;
                case "mcE6":
                    mcE6 tmE6 = new mcE6(pXE);
                    return tmE6;
                case "mcE7":
                    mcE7 tmE7 = new mcE7(pXE);
                    return tmE7;
                default:
                    mcE0 tmE0 = new mcE0(pXE);
                    return tmE0;
            }

        }

    }
    



}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{

    //围护原则——按埋深包含多个围护做法
    [Serializable]//序列化类
    public class mcPcpEnclosure : mcNameList<mcEnclosure>
    {
        public const string Multi_PETxt = "多围护原则";
        public bool ConFound = true;//是否 砼基础
        public string Excvt = "Ⅲ类土";//开挖
        public int FoundAngle = 120;//基础角度 °
        public mcReplacement Cush=new mcReplacement();//垫层

        public string DockL = "中粗砂";//坞塝 管道下半
        public string DockH = "中粗砂";//坞塝 管道上半
        public string Cover50 = "中粗砂";//管顶50
        public string Cover = "素土";//覆土

        //public double wetsoild = 0;
        //public double lightwell = 3.5;
        //public double jetwell = 6;
        //public double bigwell = 10;
        //public double deepwell = 15;
        public mcPrecipitation wetsoild = new mcPrecipitation("wetsoild", 0, 0, 0);
        public mcPrecipitation lightwell = new mcPrecipitation("lightwell", 3.5, 1.2, 2);
        public mcPrecipitation jetwell = new mcPrecipitation("jetwell", 6, 2.5, 2);
        public mcPrecipitation bigwell = new mcPrecipitation("bigwell", 10, 10, 2);
        public mcPrecipitation deepwell = new mcPrecipitation("deepwell", 15, 20, 1);

        public enum GrooveWidth
        {
            WorkWidth,
            B,
        };
        public GrooveWidth grooveWidth = GrooveWidth.WorkWidth;
        public Dictionary<string, Dictionary<int, double>> WorkWidth = new Dictionary<string, Dictionary<int, double>>();
        public Dictionary<string, Dictionary<int, double>> GrooveB = new Dictionary<string, Dictionary<int, double>>();

        public mcPcpEnclosure()
        {
            Name = "新围护原则";
            WorkWidth = mscMslns.DeepClone(mscInventory.WorkWidth);
            GrooveB = mscMslns.DeepClone(mscInventory.GrooveB);
            Add(new mcEnclosure());
        }
        public mcPcpEnclosure(XElement pXE)
        {
            Name = pXE.Element("Name").Value;
            ConFound = Convert.ToBoolean(pXE.Element("ConFound").Value);
            Excvt = pXE.Element("Excvt").Value;
            FoundAngle = Convert.ToInt16(pXE.Element("FoundAngle").Value);
            Cush = new mcReplacement(pXE.Element("Cush").Element("msReplacement"));
            DockL = pXE.Element("DockL").Value;
            DockH = pXE.Element("DockH").Value;
            Cover50 = pXE.Element("Cover50").Value;
            Cover = pXE.Element("Cover").Value;
            //wetsoild.elevation = mscMslns.ToDouble(pXE.Element("wetsoild").Value);
            wetsoild = new mcPrecipitation(pXE.Element("wetsoild"));
            //lightwell.elevation = mscMslns.ToDouble(pXE.Element("lightwell").Value);
            lightwell = new mcPrecipitation(pXE.Element("lightwell"));
            //jetwell.elevation = mscMslns.ToDouble(pXE.Element("jetwell").Value);
            jetwell = new mcPrecipitation(pXE.Element("jetwell"));
            //bigwell.elevation = mscMslns.ToDouble(pXE.Element("bigwell").Value);
            bigwell = new mcPrecipitation(pXE.Element("bigwell"));
            //deepwell.elevation = mscMslns.ToDouble(pXE.Element("deepwell").Value);
            deepwell = new mcPrecipitation(pXE.Element("deepwell"));
            grooveWidth = (GrooveWidth)Enum.Parse(typeof(GrooveWidth), pXE.Element("grooveWidth").Value);
            #region 读取工作面宽度表格信息
            var tXEs = pXE.Elements("WorkWidth").Elements();
            WorkWidth.Clear();
            foreach (XElement feXE in tXEs) 
            {
                string tName = mscMslns.ToString(feXE.Name);
                Dictionary<int, double> tDic = new Dictionary<int, double>();
                foreach(XElement feXE1 in feXE.Elements())
                {
                    string tKey = mscMslns.ToString(feXE1.Name);
                    tKey = tKey.Replace("d", "");
                    tDic.Add(Convert.ToInt16(tKey), mscMslns.ToDouble(feXE1.Value));
                }
                WorkWidth.Add(tName, tDic);
            }
            #endregion
            #region 读取沟槽宽度表格信息
            tXEs = pXE.Elements("GrooveB").Elements();
            GrooveB.Clear();
            foreach (XElement feXE in tXEs)
            {
                string tName = mscMslns.ToString(feXE.Name);
                Dictionary<int, double> tDic = new Dictionary<int, double>();
                foreach (XElement feXE1 in feXE.Elements())
                {
                    string tKey = mscMslns.ToString(feXE1.Name);
                    tKey = tKey.Replace("d", "");
                    tDic.Add(Convert.ToInt16(tKey), mscMslns.ToDouble(feXE1.Value));
                }
                GrooveB.Add(tName, tDic);
            }
            #endregion

            IEnumerable<XElement> elements = from ele in pXE.Elements("mcEnclosure")
                                             select ele;
            mList.Clear();
            foreach (XElement feXE in elements)
            {
                mList.Add(new mcEnclosure(feXE));
            }
        }

        /// <summary>
        /// 根据沟槽深度选择围护原则做法
        /// </summary>
        /// <param name="pDepth">沟槽深度</param>
        /// <returns>适用围护做法</returns>
        public mcEnclosure ChoiceEcls(double pDepth)
        {
            int idx = 0;
            for (int i = 0; i <= mList.Count - 1; i++)
            {
                if (mList[i].MinDepth > pDepth)
                {
                    break;
                }
                idx = i;
            }
            return mList[idx];
        }
        /// <summary>
        /// 降水描述
        /// </summary>
        /// <returns></returns>
        public string DiscribePreciptitation()
        {
            string re_str = "";
            double current_depth = double.MaxValue;
            if (deepwell.elevation >= 0)
            {
                current_depth = deepwell.elevation;
                re_str = "深度" + current_depth.ToString() + "m以上，采用深井降水；";
            }
            if (bigwell.elevation >= 0)
            {
                current_depth = bigwell.elevation;
                re_str = "深度" + current_depth.ToString() + "m以上，采用大口径井点降水；" + Environment.NewLine + re_str;
            }
            if (jetwell.elevation >= 0)
            {
                current_depth = jetwell.elevation;
                re_str = "深度" + current_depth.ToString() + "m以上，采用喷射井点降水；" + Environment.NewLine + re_str;
            }
            if (lightwell.elevation >= 0)
            {
                current_depth = lightwell.elevation;
                re_str = "深度" + current_depth.ToString() + "m以上，采用轻型井点降水；" + Environment.NewLine + re_str;
            }
            if (wetsoild.elevation >= 0)
            {
                if (current_depth > 0)
                    re_str = current_depth == double.MaxValue ? "湿土排水" : "深度" + current_depth.ToString() + "m以下，采用湿土排水；" + Environment.NewLine + re_str;
                else
                    re_str = "不采用湿土排水；" + Environment.NewLine + re_str;
            }
            if (re_str.EndsWith("\r\n")) { re_str = re_str.Remove(re_str.Length - 4, 4); };
            if (re_str.EndsWith("；")) { re_str = re_str.Remove(re_str.Length - 1, 1); };
            if (re_str != String.Empty) { re_str += "。"; }
            return re_str;
        }
        public string DiscribePreciptitationShort()
        {
            string re_str = "";
            if (deepwell.elevation >= 0)
                re_str = "深井";
            if (bigwell.elevation >= 0)
                re_str = "大口径井点/" + re_str;
            if (jetwell.elevation >= 0)
                re_str = "喷射井点/" + re_str;
            if (lightwell.elevation >= 0)
                re_str = "轻型井点/" + re_str;
            if (wetsoild.elevation >= 0)
                re_str = "湿土排水/" + re_str;
            if (re_str.EndsWith("/")) { re_str = re_str.Remove(re_str.Length - 1, 1); };
            return re_str;
        }

        public override XElement toXML()
        {
            XElement rtXE = new XElement(this.ToString().Replace("section.", ""),
                new XElement("Name", Name),//元素名称
                new XElement("ConFound", ConFound),
                new XElement("Excvt", Excvt),
                new XElement("FoundAngle", FoundAngle),
                new XElement("Count", Count),
                new XElement("Cush", Cush.toXML()),
                new XElement("DockL", DockL),
                new XElement("DockH", DockH),
                new XElement("Cover50", Cover50),
                new XElement("Cover", Cover),
                new XElement(wetsoild.toXML()),
                new XElement(lightwell.toXML()),
                new XElement(jetwell.toXML()),
                new XElement(bigwell.toXML()),
                new XElement(deepwell.toXML()),
                new XElement("grooveWidth", grooveWidth.ToString())
                );
            #region 保存工作面宽度信息
            XElement WorkWidthXE = new XElement("WorkWidth", null);
            foreach(string feKey in WorkWidth.Keys)
            {
                XElement tXE = new XElement(feKey, null);
                foreach(KeyValuePair<int,double> feKVP in WorkWidth[feKey])
                {
                    tXE.Add(new XElement("d" + mscMslns.ToString(feKVP.Key), feKVP.Value));
                }
                WorkWidthXE.Add(tXE);
            }
            rtXE.Add(WorkWidthXE);
            #endregion
            #region 保存沟槽宽度信息
            XElement GrooveBXE = new XElement("GrooveB", null);
            foreach (string feKey in GrooveB.Keys)
            {
                XElement tXE = new XElement(feKey, null);
                foreach (KeyValuePair<int, double> feKVP in GrooveB[feKey])
                {
                    tXE.Add(new XElement("d" + mscMslns.ToString(feKVP.Key), feKVP.Value));
                }
                GrooveBXE.Add(tXE);
            }
            rtXE.Add(GrooveBXE);
            #endregion
            XElement baseXml = base.toXML();
            foreach(XElement feXE in baseXml.Nodes())
            {
                if (feXE.Name == "Name") { continue; }
                rtXE.Add(feXE);
            }
            return rtXE;
        }
    }

    [Serializable]//序列化类
    public class mcPrecipitation:ItoXML
    {
        public string name;
        public double elevation;
        public double gap;
        public double sides;
        public mcPrecipitation(string pName, object pEle, object pGap, object pSides)
        {
            name = pName;
            elevation = mscMslns.ToString(pEle) != "-" ? mscMslns.ToDouble(pEle) : -1;
            gap = mscMslns.ToDouble(pGap);
            sides = mscMslns.ToDouble(pSides);
        }
        public mcPrecipitation(string pName, double pEle, double pGap, double pSides = 2)
        {
            name = pName;
            elevation = pEle;
            gap = pGap;
            sides = pSides;
        }
        public mcPrecipitation(XElement pXE)
        {
            name = pXE.Name.ToString();
            string tStr = pXE.Value;
            string[] t = tStr.Split(new[] { "|" }, StringSplitOptions.None);
            elevation = mscMslns.ToDouble(t[0]);
            if (t.Count() == 3)
            {
                gap = mscMslns.ToDouble(t[1]);
                sides = mscMslns.ToDouble(t[2]);
            }
            else
            {
                switch(name)
                {
                    case "wetsoild":
                        gap = 0;sides = 0;
                        break;
                    case "lightwell":
                        gap = 1.2; sides = 2;
                        break;
                    case "jetwell":
                        gap = 2.5; sides = 2;
                        break;
                    case "bigwell":
                        gap = 10; sides = 2;
                        break;
                    case "deepwell":
                        gap = 20; sides = 1;
                        break;
                }
            }
        }
        public XElement toXML()
        {
            XElement rtXE = new XElement(name, elevation.ToString() + "|" + gap.ToString() + "|" + sides.ToString());
            return rtXE;
        }
    }

}

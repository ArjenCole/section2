using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;
using section2.mcStruct;

namespace section2.mcP
{
    public class mcPE:macDicRange<mcPEn>
    {
        #region 下拉框数据源
        /*
        public static string[] sExvCat = new[] { "Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石" };
        public static string[] sDockPos = new[] { "至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高" };
        public static string[] sFndMat = new[] { "采用混凝土基础", "不采用混凝土基础" };
        public static string[] sFndAgl = new[] { "90", "120", "150", "180" };
        */
        #endregion
        #region 属性及参数
        /*
        public string ExvCat = "Ⅰ、Ⅱ类土";
        public string DockPos = "至管顶50cm";
        public string DockMat = "中粗砂";
        public string CovMat = "中粗砂";

        public string FndMat = "采用混凝土基础";
        public string FndAgl = "120";
        public string CuhMat = "中粗砂";
        public string CuhThk = "200";
        */
        #endregion

        public mcPB PB = new mcPB();
        public mcDicRange<mcCpt> PD = new mcDicRange<mcCpt>();
        public List<mcPW> PW = new List<mcPW>();

        public mcPE()
        {
            this.SetName("围护原则");
            init();
        }
        public mcPE(string pName)
        {
            this.SetName(pName);
            init();
        }
        public void init()
        {
            this.Add(new mcPEn());
        }

        public mcQ Fc1() { return new mcQ("垫层", choseMat("Fc1")); }
        public mcQ Fc2() { return new mcQ("垫层", choseMat("Fc2")); }
        public mcQ Fr1() { return new mcQ("回填", choseMat("Fr1")); }
        public mcQ Fr2() { return new mcQ("回填", choseMat("Fr2")); }
        public mcQ Fc3() { return new mcQ("回填", choseMat("Fr3")); }
        public mcQ Fc4() { return new mcQ("回填", choseMat("Fc4")); }
        private string choseMat(string pPos)
        {
            Dictionary<string, string> tD = new Dictionary<string, string>();
            tD.Add("Fc1", PB.CuhMat);
            tD.Add("Fc2", PB.CuhMat);
            tD.Add("Fr1", PB.DockMat);
            tD.Add("Fr2", PB.DockMat);
            tD.Add("Fc3", PB.DockMat);
            tD.Add("Fc4", PB.CovMat);
            switch (pPos)
            {
                case "至管顶50cm":
                    return tD[pPos];
                case "至管顶标高":
                    tD["Fc3"] = PB.CovMat;
                    return tD[pPos];
                case "至管中心标高":
                    tD["Fr2"] = PB.CovMat;
                    tD["Fc3"] = PB.CovMat;
                    return tD[pPos];
                case "至沟槽顶标高":
                    tD["Fc4"] = PB.DockMat;
                    return tD[pPos];
                default:
                    return tD[pPos];
            }
        }

    }

}

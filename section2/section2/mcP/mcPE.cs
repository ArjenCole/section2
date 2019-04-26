using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPE:mcStruct.macDicDoub<mcPEn>
    {
        #region 下拉框数据源
        public static string[] sExvCat = new[] { "Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石" };
        public static string[] sDockPos = new[] { "至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高" };
        public static string[] sFndMat = new[] { "采用混凝土基础", "不采用混凝土基础" };
        public static string[] sFndAgl = new[] { "90", "120", "150", "180" };
        #endregion
        #region 属性及参数
        public string ExvCat = "Ⅰ、Ⅱ类土";
        public string DockPos = "至管顶50cm";
        public string DockMat = "中粗砂";
        public string CovMat = "中粗砂";

        public string FndMat = "采用混凝土基础";
        public string FndAgl = "120";
        public string CuhMat = "中粗砂";
        public string CuhThk = "200";

        public mcPD PD = new mcPD();
        public List<mcPW> PWs = new List<mcPW>();
        #endregion
        
        public mcPE()
        {
            this.SetName("围护原则");
        }
        public mcPE(string pName)
        {
            this.SetName(pName);
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
            tD.Add("Fc1", CuhMat);
            tD.Add("Fc2", CuhMat);
            tD.Add("Fr1", DockMat);
            tD.Add("Fr2", DockMat);
            tD.Add("Fc3", DockMat);
            tD.Add("Fc4", CovMat);
            switch (pPos)
            {
                case "至管顶50cm":
                    return tD[pPos];
                case "至管顶标高":
                    tD["Fc3"] = CovMat;
                    return tD[pPos];
                case "至管中心标高":
                    tD["Fr2"] = CovMat;
                    tD["Fc3"] = CovMat;
                    return tD[pPos];
                case "至沟槽顶标高":
                    tD["Fc4"] = DockMat;
                    return tD[pPos];
                default:
                    return tD[pPos];
            }
        }

    }

}

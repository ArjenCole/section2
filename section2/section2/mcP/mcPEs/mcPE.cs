using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mac;
using section2.mcData;
using section2.mcStruct;

namespace section2.mcP
{
    public class mcPE:mcRangeList<mcPEn>,Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        #endregion

        public mcPB PB = new mcPB();
        public mcRangeList<mcPD> PDs = new mcRangeList<mcPD>();
        public mcDic<mcPW> PWs = new mcDic<mcPW>();

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
            this.orderAdd(new mcPEn());
        }

        public mcExp Fc1() { return new mcExp("垫层", choseMat("Fc1")); }
        public mcExp Fc2() { return new mcExp("垫层", choseMat("Fc2")); }
        public mcExp Fr1() { return new mcExp("回填", choseMat("Fr1")); }
        public mcExp Fr2() { return new mcExp("回填", choseMat("Fr2")); }
        public mcExp Fc3() { return new mcExp("回填", choseMat("Fr3")); }
        public mcExp Fc4() { return new mcExp("回填", choseMat("Fc4")); }
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

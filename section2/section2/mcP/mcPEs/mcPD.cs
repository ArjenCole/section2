using section2.mcData;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    public class mcPD:Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        public string[] GetDgvTxt()
        {
            string[] rtStrs = new string[3];
            rtStrs[0] = DepthDoub().ToString();
            rtStrs[1] = "+∞";
            rtStrs[2] = Cat();
            return rtStrs;
        }
        #endregion

        public mcCpt Cpt;

        public mcPD()
        {
            SetName("0");
            Cpt = mscInventory.PD.First().Value;
        }

    }
}

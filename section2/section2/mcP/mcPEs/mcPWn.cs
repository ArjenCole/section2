using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    public class mcPWn:Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        #endregion
        public string Width = "1000";//单位mm

    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcP;
using section2.mac;

namespace section2.mcP
{
    /// <summary>
    /// 工作面宽度原则
    /// </summary>
    public class mcPW : mcRangeList<mcPWn>,Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        #endregion

        public mcPW()
        {
            this.SetName("混凝土管道工作面宽度");
        }
        public mcPW(string pName)
        {
            this.SetName(pName);
        }
        
    }
}

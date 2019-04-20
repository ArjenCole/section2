using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    /// <summary>
    /// 工作面宽度原则
    /// </summary>
    public class mcPW : mcStruct.macDicDoub<mcData.mcCpt>
    {
        public mcPW()
        {
            this.SetName("工作面宽原则");
        }
        public mcPW(string pName)
        {
            this.SetName(pName);
        }
    }
}

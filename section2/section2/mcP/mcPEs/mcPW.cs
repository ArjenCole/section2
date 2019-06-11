using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcP;

namespace section2.mcP
{
    /// <summary>
    /// 工作面宽度原则
    /// </summary>
    public class mcPW : macDicRange<mcPWn>
    {
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

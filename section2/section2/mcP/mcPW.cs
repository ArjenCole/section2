using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    /// <summary>
    /// 工作面宽度原则
    /// </summary>
    public class mcPW : mcStruct.Iname
    {
        public string Name() { return name; }
        public void SetName(string pName) { name = pName; }
        private string name;

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

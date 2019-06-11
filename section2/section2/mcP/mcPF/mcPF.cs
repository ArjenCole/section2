using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPF:Iname
    {
        public string GetName() { return name; }
        public void SetName(string pName) { name = pName; }
        private string name;

        public List<mcCpt> CptList = new List<mcCpt>();

        public mcPF()
        {
            this.SetName("地基处理原则");
        }
        public mcPF(string pName)
        {
            this.SetName(pName);
        }
    }
}

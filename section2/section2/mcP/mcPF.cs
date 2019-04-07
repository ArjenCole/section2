using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPF:mcStruct.macDic<>
    {
        public List<mcCpt> CptList;

        public mcPF()
        {

        }
        public mcPF(string pName)
        {
            this.SetName(pName);
        }
    }
}

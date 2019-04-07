using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPE:mcStruct.macDic<mcPEn>
    {
        public mcQ Fc1;
        public mcQ Fc2;
        public mcQ Fr1;
        public mcQ Fr2;
        public mcQ Fc3;
        public mcQ Fc4;

        public mcPE()
        {

        }
        public mcPE(string pName)
        {
            this.SetName(pName);
        }

    }
}

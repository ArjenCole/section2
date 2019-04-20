using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPE:mcStruct.macDicDoub<mcPEn>
    {
        public mcQ Fc1 = new mcQ();
        public mcQ Fc2 = new mcQ();
        public mcQ Fr1 = new mcQ();
        public mcQ Fr2 = new mcQ();
        public mcQ Fc3 = new mcQ();
        public mcQ Fc4 = new mcQ();

        public mcPE()
        {
            this.SetName("围护原则");
        }
        public mcPE(string pName)
        {
            this.SetName(pName);
        }

    }
}

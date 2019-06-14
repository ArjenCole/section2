using section2.mac;
using section2.mcData;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    public class mcPD:mcRange
    {
        public mcCpt Cpt;

        public mcPD()
        {
            Cpt = mscInventory.PD.First().Value;
        }
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcData
{
    public class mcQ
    {
        public string Cat = "";
        public string Name = "";
        public string Exp = "";
        public string Unit = "";

        public bool isConFound = true;

        public mcQ()
        {

        }
        public mcQ(string pCat,string pName)
        {
            Cat = pCat;Name = pName;
        }

        public string CNU()
        {
            return Cat + "|" + Name + "|" + Unit;
        }
    }
}

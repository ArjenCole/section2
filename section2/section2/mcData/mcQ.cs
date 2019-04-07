using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcData
{
    public class mcQ
    {
        public string Cat;
        public string Name;
        public string Exp;
        public string Unit;

        public mcQ Fc1;
        public mcQ Fc2;
        public mcQ Fr1;
        public mcQ Fr2;
        public mcQ Fc3;
        public mcQ Fc4;

        public bool isConFound = true;

        public string CNU { get { return Cat + "|" + Name + "|" + Unit; } }
    }
}

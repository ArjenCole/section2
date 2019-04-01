using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcData
{
    public class mcQ
    {
        public string Name;
        public string Exp;
        public string Unit;

        public string NameUnit { get { return Name + "|" + Unit; } }
    }
}

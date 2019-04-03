using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcStruct
{
    public class mcUnit:macList<mcS>
    {
        public mcUnit()
        {

        }
        public mcUnit(string pName)
        {
            SetName(pName);
        }
    }
}

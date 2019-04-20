using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    //降水原则
    public class mcPD : mcStruct.macDicDoub<mcData.mcCpt>
    {
        public mcPD()
        {
            this.SetName("降水原则");
        }
        public mcPD(string pName)
        {
            this.SetName(pName);
        }
    }
}

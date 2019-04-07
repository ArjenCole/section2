using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public class mcDC:macDic<mcSG>
    {
        public mcBI BI;


        public mcDC()
        {
            BI = new mcStruct.mcBI();
            mDic = new Dictionary<string, mcSG>();

        }
    }
}

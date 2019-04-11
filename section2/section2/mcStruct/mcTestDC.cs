using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;
using section2.mcP;

namespace section2.mcStruct
{
    public class mcTestDC:macDic<mcSG>
    {
        public mcBI BI;
        
        public mcDic<mcPE> PEdic = new mcDic<mcPE>();

        public mcTestDC()
        {
            mDic = new Dictionary<string, mcSG>();

            BI = new mcBI();
            
            PEdic.Add(new mcPE());

        }
    }
}

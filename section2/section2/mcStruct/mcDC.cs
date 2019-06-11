using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;
using section2.mcP;

namespace section2.mcStruct
{
    public class mcDC:macDic<mcSG>
    {
        public mcBI BI;

        public mcDic<mcPE> PE = new mcDic<mcPE>();
        public mcDic<mcPF> PF = new mcDic<mcPF>();

        public mcDC()
        {
            mDic = new Dictionary<string, mcSG>();

            BI = new mcBI();
            
            PE.Add(new mcPE());
            PF.Add(new mcPF());
        }
    }
}

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

        public mcDic<mcPE> PEdic = new mcDic<mcPE>();
        public mcDic<mcPF> PFdic = new mcDic<mcPF>();
        public mcDic<mcPD> PDdic = new mcDic<mcPD>();
        public mcDic<mcPW> PWdic = new mcDic<mcPW>();

        public mcDC()
        {
            mDic = new Dictionary<string, mcSG>();

            BI = new mcBI();
            
            PEdic.Add(new mcPE());
            PFdic.Add(new mcPF());
        }
    }
}

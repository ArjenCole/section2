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

        public mcDic<mcPE> PEdic;
        public mcDic<mcPF> PFdic;
        public mcDic<mcPD> PDdic;
        public mcDic<mcPW> PWdic;

        public mcDC()
        {
            mDic = new Dictionary<string, mcSG>();

            BI = new mcBI();

            PEdic = new mcDic<mcP.mcPE>();
            PEdic.Add(new mcPE("围护原则"));


        }
    }
}

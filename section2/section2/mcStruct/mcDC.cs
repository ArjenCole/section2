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

        public mcPEdic PEdic;
        public mcPFdic PFdic;
        public mcPWdic PWdic;

        public mcDC()
        {
            BI = new mcStruct.mcBI();
            mDic = new Dictionary<string, mcSG>();

        }
    }
}

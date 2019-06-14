using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcStruct
{
    public class mcUN:mcDic<mcS>
    {
        public mcUN()
        {
            SetName("单位工程");
        }
        public mcUN(string pName)
        {
            SetName(pName);
        }
    }
}

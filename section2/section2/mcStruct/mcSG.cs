using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public class mcSG:macDic<mcUN>
    {
        public mcSG()
        {
            SetName("标段");
        }
        public mcSG(List<string> pNameList)
        {
            SetName("标段");
            foreach (string feStr in pNameList)
            {
                Add(new mcUN(feStr));
            }
        }
    }
}

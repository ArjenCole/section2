using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcData
{
    public class mcCpt:mcStruct.macDic<mcQ>
    {
        public static List<string> KeepWords = new List<string> { "保留字1", "保留字2" };
        public List<mcQ> Qlist = new List<mcQ>();

    }
}

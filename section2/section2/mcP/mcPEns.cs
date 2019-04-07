using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPEns : mcStruct.macDic<mcData.mcCpt>
    {
        public int Height;//固定高度mm
        public int Width;//工作面宽度mm
        public mcCpt Cpt;
    }
}

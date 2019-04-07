using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPEn : mcStruct.macDic<mcPEns>
    {
        public int Depth;//起始（浅）埋深mm
        public mcCpt cptStopWater;//止水
        public mcCpt cptSupport;//支撑
    }
}

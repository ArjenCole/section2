using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2
{
    public static class mscTools
    {
        public static List<mcQ> sumQ(List<mcQ> pL1, List<mcQ> pL2)
        {
            List<mcQ> rtL = new List<mcQ>();
            rtL.AddRange(pL1);
            rtL.AddRange(pL2);
            return sumQ(rtL);
        }
        public static List<mcQ> sumQ(List<mcQ> pL1)
        {
            Dictionary<string, mcQ> tD = new Dictionary<string, mcQ>();
            foreach (mcQ feQ in pL1)
                if (tD.Keys.Contains(feQ.NameUnit))
                    tD[feQ.NameUnit].Exp += "+" + feQ.Exp;
                else
                    tD.Add(feQ.NameUnit, feQ);
            
            return tD.Values.ToList();
        }
    }
}

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
                if (tD.Keys.Contains(feQ.CNU))
                    tD[feQ.CNU].Exp += "+" + feQ.Exp;
                else
                    tD.Add(feQ.CNU, feQ);
            
            return tD.Values.ToList();
        }

        public static string reName<T>(List<T> pL, string pName)
        {
            string rtName = pName;
            if (pL.Count == 0) return rtName;
            T tT;
            int i = 0;
            while (pL.Find(t => ((mcStruct.Iname)t).Name() == rtName) != null) 
            {
                i++;
                rtName = pName + i.ToString();
            }
            return rtName;
        }
    }
}

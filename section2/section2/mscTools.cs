using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
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

        public static string reName<T>(Dictionary<string, T> pD, string pName)
        {
            string rtName = pName;
            if (pD.Count == 0) return rtName;
            int i = 0;
            while (pD.Keys.Contains(rtName)) 
            {
                i++;
                rtName = pName + i.ToString();
            }
            return rtName;
        }
        
        public static Dictionary<Int64,T> OrderDic<T>(Dictionary<Int64, T> pDic)
        {
            IOrderedEnumerable<KeyValuePair<Int64, T>> dicSort = from objDic in pDic orderby objDic.Key select objDic;
            //return from objDic in pDQ orderby order(objDic.Key) descending select objDic; 降序

            var rtDic = new Dictionary<Int64, T>();
            foreach (KeyValuePair<Int64, T> feKVP in dicSort)
                rtDic.Add(feKVP.Key ,feKVP.Value);
            return rtDic;
        }

        public static string toJson<T>(T pT)
        {
            var serializer = new JavaScriptSerializer();
            return serializer.Serialize(pT);
        }
        public static T anJson<T>(string pJsonStr)
        {
            var serializer = new JavaScriptSerializer();
            return serializer.Deserialize<T>(pJsonStr);
        }

        public static T DeepClone<T>(T pT)
        {
            string tJsonStr = toJson<T>(pT);
            return anJson<T>(tJsonStr);
        }
    }
}

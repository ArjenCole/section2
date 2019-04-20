using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcData
{
    public class mcCpt:mcStruct.macDic<mcQ>
    {
        public static List<string> KeepWords = new List<string>
        {
            "Auto",
            "Autot","t",
            "Autoa","a",
            "AutoC1","C1",
            "AutoC2","C2",
            "DN",
            "slope","WorkWidth","FoundAngle",
            "保留字2"
        };
        public List<mcQ> Qlist = new List<mcQ>();
        /*
        private Dictionary<string, string> keepPara = new Dictionary<string, string>();
        public void SetKeepPara(string pParaName, string pParaValue)
        {
            if (keepPara.Keys.Contains(pParaName))
                keepPara[pParaName] = pParaValue;
            else
                keepPara.Add(pParaName, pParaValue);
        }
        public string GetKeepPara(string pParaName)
        {
            if (keepPara.Keys.Contains(pParaName))
                return keepPara[pParaName];
            else
                return null;

        }
        */
    }
}

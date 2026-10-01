using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcComponent:ItoXML
    {
        public string Name;
        public string DiscribeFmla = string.Empty;
        public Dictionary<string, KeyValuePair<string, string>> param = new Dictionary<string, KeyValuePair<string, string>>();
        public int paramCnt = 0;
        public int fomlaCnt = 0;
        public int zomlaCnt = 0;

        public mcComponent()
        {

        }
        public mcComponent(XElement pXE)
        {
            param.Clear();
            if (pXE == null) { return; }
            foreach (XElement feXE in pXE.Elements())
            {
                if (feXE.Name.ToString() == "Name")
                {
                    KeyValuePair<string, string> tKVP = splitString(feXE.Value.ToString());
                    Name = tKVP.Key;
                    DiscribeFmla = tKVP.Value;
                }
                else
                    param.Add(feXE.Name.ToString(), splitString(feXE.Value));
            }
            getCnt();
        }
        private KeyValuePair<string,string> splitString(string pStr)
        {
            string[] tStr = pStr.Split(new[] { "|" }, StringSplitOptions.None);
            string tKey = tStr.First();
            for (int i = 1; i < tStr.Length - 1; i++) 
            {
                tKey += "|" + tStr[i];
            }

            return new KeyValuePair<string, string>(tKey, tStr.Last());
        }
        public Dictionary<string, mcQ> Q(double pHeight, double pWidth, double pCount, string pCat = "F")
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            foreach(string feKey in param.Keys)
            {
                if (feKey.StartsWith(pCat) && feKey.Length > 1) 
                {
                    string tmpExp = ValueExp(feKey);
                    if(tmpExp == string.Empty) { continue; }
                    double q = preSub(tmpExp, pHeight, pWidth, pCount);
                    if(q !=0)
                    {
                        rtD.Add(KeyExp(feKey), new mcQ(q));
                    }
                }
            }

            return rtD;
        }
        private double preSub(string pExp, double pHeight, double pWidth, double pCount)
        {
            //pExp = pExp.Replace("PI()", "PI");
            pExp = pExp.Replace("height", pHeight.ToString());
            pExp = pExp.Replace("width", pWidth.ToString());
            pExp = pExp.Replace("count", pCount.ToString());
            return mscMslns.ToDouble(mscExp.Eval(pExp));
        }

        public void getCnt()
        {
            paramCnt = 0; fomlaCnt = 0;
            if (param.Count == 0) { return; }
            foreach (char feChar in mscInventory.Alphabet)
            {
                string feStr = feChar.ToString();
                if ((param.Keys.Contains(feStr)) && (param[feStr].Key != string.Empty)) { paramCnt++; }
                if ((param.Keys.Contains("F" + feStr)) && (param["F" + feStr].Key != string.Empty)) { fomlaCnt++; }
                if ((param.Keys.Contains("Z" + feStr)) && (param["Z" + feStr].Key != string.Empty)) { zomlaCnt++; }
            }
        }

        public string ValueExp(string pKey)
        {
            Regex objRegEx = new Regex(@"\b" + "参数循环引用" + @"\b");
            List<string> tmpListStr = new List<string>();
            tmpListStr.Add(pKey);
            string tmpStr = SubstitutingExp(param[pKey].Value, tmpListStr);
            if (objRegEx.IsMatch(tmpStr)) { return "参数循环引用"; }
            return tmpStr;
        }
        private string SubstitutingExp(string pStr, List<string> pKeyList)
        {
            string rtStr = pStr;
            foreach (string feKey in param.Keys)
            {
                Regex objRegEx = new Regex(@"\b" + feKey + @"\b");
                if (objRegEx.IsMatch(rtStr))
                {
                    if (pKeyList.Contains(feKey)) { return "参数循环引用"; }
                    pKeyList.Add(feKey);
                    rtStr = objRegEx.Replace(rtStr, "(" + SubstitutingExp(param[feKey].Value, pKeyList) + ")");
                    pKeyList.Remove(feKey);
                }
            }
            if (rtStr == string.Empty) { rtStr = "0"; }
            return rtStr;
        }

        public string Discribe()
        {
            Regex objRegEx = new Regex(@"\b" + "参数循环引用" + @"\b");
            List<string> tmpListStr = new List<string>();
            string tmpStr = SubstitutingExp(DiscribeFmla, tmpListStr);
            if (objRegEx.IsMatch(tmpStr)) { return "参数循环引用"; }
            tmpStr = tmpStr.Replace("(", ""); tmpStr = tmpStr.Replace(")", "");
            return tmpStr;
        }

        public string KeyExp(string pKey)
        {
            string rtStr = param[pKey].Key;
            foreach (string feKey in param.Keys)
            {
                Regex objRegEx = new Regex(@"\b" + feKey + @"\b");
                var tmp = objRegEx.IsMatch(rtStr);
                rtStr = objRegEx.Replace(rtStr, param[feKey].Value);
            }
            return rtStr.Replace(" ", "");
        }

        public XElement toXML()
        {
            XElement rtXE = new XElement(this.ToString().Replace("section.", ""), null);
            rtXE.Add(new XElement("Name", Name + "|" + DiscribeFmla));
            foreach (string feKey in param.Keys)
            {
                if (param[feKey].Key == string.Empty) { continue; }
                rtXE.Add(new XElement(feKey, param[feKey].Key + "|" + param[feKey].Value));
            }

            return rtXE;
        }
    }
}

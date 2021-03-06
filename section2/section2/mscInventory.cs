﻿using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcP;
using section2.mcData;
using System.Data;

namespace section2
{
    public static class mscInventory
    {
        public static Dictionary<string, mcCpt> DicPEns;
        private static List<string> listPEnsKeys = new List<string>();
        public static List<string> ListPEnsKeysAddMult()
        {
            listPEnsKeys = DicPEns.Keys.ToList();
            listPEnsKeys.Add(mcPEn.StrMultiPEns);
            return listPEnsKeys;
        }
        public static List<string> ListPEnsKeys()
        {
            listPEnsKeys = DicPEns.Keys.ToList();
            return listPEnsKeys;
        }

        public static Dictionary<string, mcCpt> DicStopWater;
        private static List<string> listStopWaterKeys = new List<string>();
        public static List<string> ListStopWaterKeys()
        {
            listPEnsKeys = DicStopWater.Keys.ToList();
            return listPEnsKeys;
        }

        public static Dictionary<string, mcCpt> PD;

        const string Alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

        public static void ini()
        {
            DicPEns = loadCSV("DicPEn");
            DicStopWater = loadCSV("DicStopWater");
            PD = loadCSV("PD");
        }


        private static Dictionary<string, mcCpt> loadCSV(string pFileName)
        {
            DataTable tmpDT = mscTools.OpenCSV(@"Inventory\" + pFileName + ".CSV");
            return getRowsByFilter(tmpDT);
        }
        //TODO:提高此函数复用性
        private static Dictionary<string, mcCpt> getRowsByFilter(DataTable pDT)
        {
            Dictionary<string, mcCpt> rtDic = new Dictionary<string, mcCpt>();
            DataTable table = pDT;
            DataRow[] foundRowsDis;
            DataRow[] foundRowsValue;
            //使用选择方法来找到匹配的所有行。
            foundRowsDis = table.Select("key = 'discribe'");
            foundRowsValue = table.Select("key = 'value'");
            //过滤行,找到所要的行。
            for (int i = 0; i < foundRowsDis.Length; i++)
            {
                mcCpt tmC = new mcCpt();
                tmC.SetName(mscTools.ToString(foundRowsDis[i]["name"]));
                tmC.NameExp = mscTools.ToString(foundRowsValue[i]["name"]);
                foreach (char feChar in Alphabet)
                {
                    string tKey = mscTools.ToString(feChar);
                    string tDis = mscTools.ToString(foundRowsDis[i][tKey]);
                    if (tDis != "")
                    {
                        if (!tDis.Contains("|")) tDis += "|";
                        string[] tDisS = tDis.Split(new[] { "|" }, StringSplitOptions.None);
                        string tCat = tKey;
                        string tName = tDisS[0];
                        string tUnit = tDisS[1];
                        string tExp = mscTools.ToString(foundRowsValue[i][tKey]);
                        tmC.Add(new mcExp(tKey, tName, tExp, tUnit));
                    }
                    else
                    {
                        break;
                    }
                }
                foreach (char feChar in Alphabet)
                {
                    string tKey = "F" + mscTools.ToString(feChar);
                    string tDis = mscTools.ToString(foundRowsDis[i][tKey]);
                    if (tDis != "")
                    {
                        if (!tDis.Contains("|")) tDis += "|";
                        string[] tDisS = tDis.Split(new[] { "|" }, StringSplitOptions.None);
                        string tCat = tDisS[0];
                        string tName = tDisS[1];
                        string tUnit = tDisS[2];
                        string tExp = mscTools.ToString(foundRowsValue[i][tKey]);
                        tmC.Qlist.Add(new mcExp("围护", tName, tExp, tUnit));
                    }
                    else
                    {
                        break;
                    }   
                }
                try
                {
                    foreach (char feChar in Alphabet)
                    {
                        string tKey = "Z" + mscTools.ToString(feChar);
                        string tDis = mscTools.ToString(foundRowsDis[i][tKey]);
                        if (tDis != "")
                        {
                            if (!tDis.Contains("|")) tDis += "|";
                            string[] tDisS = tDis.Split(new[] { "|" }, StringSplitOptions.None);
                            string tCat = tDisS[0];
                            string tName = tDisS[1];
                            string tUnit = tDisS[2];
                            string tExp = mscTools.ToString(foundRowsValue[i][tKey]);
                            tmC.Qlist.Add(new mcExp("支撑", tName, tExp, tUnit));
                        }
                        else
                        {
                            break;
                        }
                    }
                }
                catch { }
                rtDic.Add(mscTools.ToString(foundRowsDis[i]["name"]), tmC);
            }
            return rtDic;
        }

    }
}

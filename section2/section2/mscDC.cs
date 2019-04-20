using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;
using section2.mcStruct;
using section2.mcP;

namespace section2
{
    public static class mscDC
    {        
        private static mcDC dc;

        public static mcDC newDC()
        {
            return newDC("新建项目", "", "", 2, new List<string>() { "雨水工程", "污水工程" });
        }
        public static mcDC newDC(string pPN, string pPI, string pD, int pSC, List<string> pC)
        {
            dc = new mcDC();
            dc.BI.ProjectName = pPN;
            dc.BI.ProjectIndex = pPI;
            dc.BI.Designer = pD;
            for (int i = 0; i < pSC; i++)
                dc.Add(new mcSG(pC));
            return getDC();
        }


        #region 读取
        public static mcDC getDC()
        {
            return mscTools.DeepClone(dc);
        }
        public static mcSG getSG(string pSGname)
        {
            return getDC().Son(pSGname);
        }
        public static mcUN getUN(string pSGname, string pUNname)
        {
            return getSG(pSGname).Son(pUNname);
        }
        public static List<mcS> getSlist(string pSGname, string pUNname)
        {
            return getUN(pSGname, pUNname).Sons();
        }
        public static mcS getS(string pSGname, string pUNname, int pIdx)
        {
            return getUN(pSGname, pUNname).Sons()[pIdx];
        }

        public static mcDic<mcPE> getPEdic()
        {
            return getDC().PEdic;
        }
        public static mcDic<mcPF> getPFdic()
        {
            return getDC().PFdic;
        }
        public static mcDic<mcPD> getPDdic()
        {
            return getDC().PDdic;
        }
        public static mcDic<mcPW> getPWdic()
        {
            return getDC().PWdic;
        }
        #endregion

    }
}

﻿using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2
{
    public static class mscCal
    {
        private static mcS crtS = null;

        private static double depth0 = 0;
        private static double depth1 = 0;
        
        public static List<mcExp> Cal(mcS pmS)
        {
            crtS = pmS;
            analyze();
            List<mcExp> Qs = calS();
            List<mcExp> Qpit = null;
            List<mcExp> Qocp = null;

            List<mcExp> rtQ = null;
            rtQ = mscTools.sumQ(rtQ, Qs);
            rtQ = mscTools.sumQ(rtQ, Qpit);
            rtQ = mscTools.sumQ(rtQ, Qocp);

            return rtQ;
        }

        private static void analyze()
        {
            analyzeDepth();

        }
        private static void analyzeDepth()
        {
            string tDepth = crtS.Depth;
            string[] sDepth;
            tDepth.Replace("~", "~");
            tDepth.Replace("-", "~");
            tDepth.Replace("—", "~");
            if (tDepth.Contains("~"))
            {
                sDepth = tDepth.Split('~');
                depth0 = mscExp.Doub(sDepth[0]);
                depth1 = mscExp.Doub(sDepth[1]);
            }
            else
            {
                depth0 = mscExp.Doub(tDepth);
                depth1 = depth0;
            }

        }

        private static void choicePEn()
        {

        }

        private static List<mcExp> calS()
        {
            switch (crtS.Type)
            {
                case mcStype.Null:
                    return null;
                case mcStype.Pipe:
                    return calSpipe();
                case mcStype.ConBox:
                    return calSconBox();
                case mcStype.Jacking:
                    return calSjacking();
                case mcStype.Custom:
                    return calScustom();
                default:
                    return null;
            }
        }

        private static List<mcExp> calSpipe()
        {
            return null;
        }
        private static List<mcExp> calSconBox()
        {
            return null;
        }
        private static List<mcExp> calSjacking()
        {
            return null;
        }
        private static List<mcExp> calScustom()
        {
            return null;
        }
    }
}

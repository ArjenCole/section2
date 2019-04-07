using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.FmTool;
using section2.mcData;
using section2.mcStruct;
using section2.mcP;

namespace section2
{
    public static class mscCtrl
    {
        public static FmMain fmMain;

        private static mcDC dc;

        public static bool LoadFinished = false;//主程序加载完毕后封面窗体自动消失

        #region 新建
        public static mcDC NewFileFromGuide()
        {
            FmGuide fmGuide = new FmTool.FmGuide();
            if (fmGuide.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                return newFile(fmGuide);
            else
                return newFile();
        }
        private static mcDC newFile()
        {
            dc = new mcDC();
            dc.BI.ProjectName = "新建项目";
            dc.BI.ProjectIndex = "";
            dc.BI.Designer = "";
            mcSG tS = new mcSG();
            mcUN tU = new mcUN();
            tS.Add(tU);
            dc.Add(tS);
            return getDC();
        }
        private static mcDC newFile(FmGuide pFmGuide)
        {
            dc = new mcDC();
            dc.BI.ProjectName = pFmGuide.ProjectName;
            dc.BI.ProjectIndex = pFmGuide.ProjectIndex;
            dc.BI.Designer = pFmGuide.Designer;
            int segmentCNT = pFmGuide.SegmentCount;
            for(int i = 0; i< segmentCNT; i++)
                dc.Add(new mcSG(pFmGuide.Cat));
            return getDC();
        }
        #endregion
        #region 读取
        public static mcDC getDC()
        {
            return dc;
        }
        public static mcSG getSG(string pSGname)
        {
            return getDC().Son(pSGname);
        }
        public static mcUN getUN(string pSGname,string pUNname)
        {
            return getSG(pSGname).Son(pUNname);
        }
        public static mcDic<mcPE> getPEdic()
        {
            return getDC().PEdic;
        }
        public static mcDic<mcPF> getPFdic()
        {
            return getDC().PFdic;
        }

        #endregion
    }
}

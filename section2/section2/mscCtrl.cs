using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.FmTool;
using section2.mcData;
using section2.mcStruct;

namespace section2
{
    public static class mscCtrl
    {
        public static FmMain fmMain;

        private static mcDC dc;

        public static bool LoadFinished = false;//主程序加载完毕后封面窗体自动消失

        public static void NewFileFromGuide()
        {
            FmGuide fmGuide = new FmTool.FmGuide();
            if (fmGuide.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            {
                NewFile(fmGuide);
            }
        }
        public static void NewFile(FmGuide pFmGuide)
        {
            dc = new mcDC();
            dc.BI.ProjectName = pFmGuide.ProjectName;
            dc.BI.ProjectIndex = pFmGuide.ProjectIndex;
            dc.BI.Designer = pFmGuide.Designer;
            int segmentCNT = pFmGuide.SegmentCount;
            for(int i = 0; i< segmentCNT; i++)
            {
                dc.Add(new mcSegment());
            }
        }

    }
}

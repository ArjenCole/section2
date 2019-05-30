using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.FmTool;
using section2.mcData;
using section2.mcStruct;
using section2.mcP;
using System.Windows.Forms;

namespace section2
{
    public static class mscVctrl
    {
        public static FmMain fmMain;
        
        public static bool LoadFinished = false;//主程序加载完毕后封面窗体自动消失

        public static void ini()
        {
            mscInventory.ini();

            LoadFinished = true;
        }

        #region 新建
        public static void NewFileFromGuide()
        {
            FmGuide fmGuide = new FmTool.FmGuide();
            if (fmGuide.ShowDialog() == DialogResult.OK)
                mscDC.newDC(fmGuide.ProjectName, fmGuide.ProjectIndex, fmGuide.Designer, fmGuide.SegmentCount, fmGuide.Cat);
            else
                mscDC.newDC();
        }
        #endregion

        public static void ShowFmPE(string pName)
        {
            FmPE fmPE = new FmPE(mscDC.getPE(pName));
            if (fmPE.ShowDialog() == DialogResult.OK)
            {
                mscDC.Update(pName, fmPE.rtPE);
                fmMain.Fls_scPcp();
            }

        }
        public static void ShowFmPF(string pName)
        {
            /*
            FmPE fmPE = new FmPE(mscDC.getPE(pName));
            if (fmPE.ShowDialog() == DialogResult.OK)
                mscDC.updatePE(pName, fmPE.resultPE);
                */
            FmCptEditor fmCptEditor = new FmCptEditor(mscInventory.DicPEns.Last().Value);
            fmCptEditor.ShowDialog();


        }
        public static mcCpt EditCpt(mcCpt pC)
        {
            FmCptEditor fmCptEditor = new FmCptEditor(pC);
            if (fmCptEditor.ShowDialog() == DialogResult.OK)
                return fmCptEditor.rtmC;
            else
                return fmCptEditor.omC;
        }
    }
}

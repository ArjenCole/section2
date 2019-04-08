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
    public static class mscVctrl
    {
        public static FmMain fmMain;
        
        public static bool LoadFinished = false;//主程序加载完毕后封面窗体自动消失

        #region 新建
        public static mcDC NewFileFromGuide()
        {
            FmGuide fmGuide = new FmTool.FmGuide();
            if (fmGuide.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                return mscMctrl.newDC(fmGuide.ProjectName, fmGuide.ProjectIndex, fmGuide.Designer, fmGuide.SegmentCount, fmGuide.Cat);
            else
                return mscMctrl.newDC();
        }

        #endregion
    }
}

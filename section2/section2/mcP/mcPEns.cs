using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;

namespace section2.mcP
{
    public class mcPEns
    {
        public int Height = -1;//固定高度mm
        public int Width = 1;//工作面宽度mm
        public mcCpt Cpt;

        public mcPEns()
        {
            Cpt = mscTools.DeepClone(mscInventory.DicPEns.First().Value);
        }
        public mcPEns(string pCat)
        {
            if (mscInventory.DicPEns.Keys.Contains(pCat))
                Cpt = mscTools.DeepClone(mscInventory.DicPEns[pCat]);
            else
                Cpt = mscTools.DeepClone(mscInventory.DicPEns.First().Value);
        }
        public mcPEns(mcCpt pC)
        {
            Cpt = mscTools.DeepClone(pC);
        }
    }
}

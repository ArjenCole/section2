using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcData;
using section2.mcStruct;

namespace section2.mcP
{
    public class mcPEn:Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        #endregion
        public const string StrMultiPEns= "多级围护";
        
        public List<mcPEns> ListPEns = null;
        public mcCpt cptStopWater;//止水

        public string Depth()
        {
            return Name;
        }

        public mcPEn()
        {
            SetName("0");
            ListPEns = new List<mcPEns>();
            ListPEns.Add(new mcPEns());
        }

        public mcPEn(string pDepth,string pCat)
        {
            SetName(pDepth);
            if (mscInventory.DicPEns.Keys.Contains(pCat))
            {
                ListPEns = new List<mcPEns>();
                ListPEns.Add(new mcPEns(mscInventory.DicPEns[pCat]));
            }
        }

        public string Cat()
        {
            if (ListPEns.Count == 1)
                return ListPEns[0].Cpt.Name;
            else
                return StrMultiPEns;
        }

        public string Discribe()
        {
            if (ListPEns.Count == 1)
                return ListPEns[0].Cpt.Name;
            else
               return ListPEns.Count.ToString() + "级围护";
        }
    }
}

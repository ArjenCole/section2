using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mac;
using section2.mcData;
using section2.mcStruct;

namespace section2.mcP
{
    public class mcPEn:macRange,Iname,IdgvTxt
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        public string[] GetDgvTxt()
        {
            string[] rtStrs = new string[4];
            rtStrs[0] = DepthDoub().ToString();
            rtStrs[1] = "+∞";
            rtStrs[2] = Cat();
            rtStrs[3] = StopWater.Name;
            return rtStrs;
        }
        #endregion
        public const string StrMultiPEns= "多级围护";
        
        public List<mcPEns> ListPEns = null;
        public mcCpt StopWater;//止水

        public string DepthStr()
        {
            return Name;
        }

        public double DepthDoub()
        {
            return (double)((int.Parse(Name)) / 1000.0);
        }

        public mcPEn()
        {
            SetName("0");
            ListPEns = new List<mcPEns>();
            ListPEns.Add(new mcPEns());
            SetStopWater();
        }
        public mcPEn(int pDepth)
        {
            SetName(pDepth.ToString());
            ListPEns = new List<mcPEns>();
            ListPEns.Add(new mcPEns());
            SetStopWater();
        }
        public mcPEn(string pDepth,string pCat)
        {
            SetName(pDepth);
            if (mscInventory.DicPEns.Keys.Contains(pCat))
            {
                ListPEns = new List<mcPEns>();
                ListPEns.Add(new mcPEns(mscInventory.DicPEns[pCat]));
            }
            SetStopWater();
        }

        public void SetStopWater()
        {
            StopWater = mscInventory.DicStopWater.Values.First();
        }
        public void SetStopWater(string pCat)
        {
            StopWater = mscInventory.DicStopWater[pCat];
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

        public int Count()
        {
            return ListPEns.Count;
        }

    }
}

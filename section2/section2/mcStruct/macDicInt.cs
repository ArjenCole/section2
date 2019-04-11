using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public abstract class macDicInt<T> : Iname
    {
        #region 实现接口
        public string Name() { return name; }
        public void SetName(string pName) { name = pName; }
        private string name = "";

        public string toJson()
        {
            return mscTools.toJson<macDicInt<T>>(this);
        }
        public macDicInt<T> DeepClone()
        {
            return mscTools.anJson<macDicInt<T>>(toJson());
        }
        #endregion

        public Dictionary<Int64, T> mDicInt = new Dictionary<Int64, T>();

        public Int64 Count
        {
            get { return mDicInt.Count; }
        }
        public T Son(Int64 pIdx)
        {
            mDicInt = mscTools.OrderDic(mDicInt);
            var tKeyList = mDicInt.Keys.ToList();
            if (pIdx == 0) return mDicInt[0];
            for (int i = 0; i < mDicInt.Count - 1; i++)
                if (pIdx > tKeyList[i] && pIdx <= tKeyList[i + 1])
                    return mDicInt[tKeyList[i]];

            return mDicInt[tKeyList.Last()];
        }
        public List<T> Sons() { return mDicInt.Values.ToList(); }

        public void Add(string pExp, T pT)
        {
            Int64 tInt = Convert.ToInt64(Math.Round(double.Parse(pExp) * 1000, 0));
            mDicInt.Add(tInt, pT);
            mDicInt = mscTools.OrderDic(mDicInt);
        }
        
    }

}

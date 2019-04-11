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
        private string name;

        public string toJson()
        {
            return mscTools.toJson<macDicInt<T>>(this);
        }
        public macDicInt<T> DeepClone()
        {
            return mscTools.DeepClone<macDicInt<T>>(this);
        }
        #endregion

        public Dictionary<Int64, T> mDic = new Dictionary<Int64, T>();

        public Int64 Count
        {
            get { return mDic.Count; }
        }
        public T Son(Int64 pIdx)
        {
            mDic = mscTools.OrderDic(mDic);
            var tKeyList = mDic.Keys.ToList();
            if (pIdx == 0) return mDic[0];
            for (int i = 0; i < mDic.Count - 1; i++)
                if (pIdx > tKeyList[i] && pIdx <= tKeyList[i + 1])
                    return mDic[tKeyList[i]];

            return mDic[tKeyList.Last()];
        }
        public List<T> Sons() { return mDic.Values.ToList(); }

        public void Add(string pExp, T pT)
        {
            Int64 tInt = Convert.ToInt64(Math.Round(double.Parse(pExp) * 1000, 0));
            mDic.Add(tInt, pT);
            mDic = mscTools.OrderDic(mDic);
        }
        
    }

}

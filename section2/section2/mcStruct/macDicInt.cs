using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public abstract class macDicInt<T> :macDic<T>
    {
        public T Son(long pIdx)
        {
            Dictionary<long, T> mDicInt = new Dictionary<long, T>();
            mDicInt = mscTools.OrderDic(mDicInt);
            var tKeyList = mDicInt.Keys.ToList();
            if (pIdx == 0) return mDicInt[0];
            for (int i = 0; i < mDicInt.Count - 1; i++)
                if (pIdx > tKeyList[i] && pIdx <= tKeyList[i + 1])
                    return mDicInt[tKeyList[i]];

            return mDicInt[tKeyList.Last()];
        }
        public List<T> Sons() { return mDic.Values.ToList(); }

        public override void Add(T pT)
        {
            mDic.Add(((Iname)pT).Name(), pT);
            mDic = mscTools.OrderDic(mDicInt);

            //TODO: 添加项后自动排序
        }

    }

}

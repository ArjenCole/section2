using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public abstract class macDicInt<T> :macDic<T>
    {
        public T Son(string pKey)
        {
            double tDouble = mscExp.Doub(pKey);
            Dictionary<string, T> mDicOrd = new Dictionary<string, T>();
            mDicOrd = mscTools.OrderDic(mDic);
            if (tDouble <= 0) return mDicOrd.First().Value;
            var tKeyList = mDicOrd.Keys.ToList();
            for (int i = 0; i < mDicOrd.Count - 1; i++)
                if (tDouble > mscExp.Doub(tKeyList[i]) && tDouble <= mscExp.Doub(tKeyList[i + 1]))
                    return mDicOrd[tKeyList[i]];

            return mDicOrd[tKeyList.Last()];
        }
        public List<T> Sons() { return mDic.Values.ToList(); }

        public override void Add(T pT)
        {
            mDic.Add(((Iname)pT).Name(), pT);
            mDic = mscTools.OrderDic(mDic);

            //TODO: 添加项后自动排序
        }

    }

}

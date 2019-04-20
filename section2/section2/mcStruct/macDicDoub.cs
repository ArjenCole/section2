using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public abstract class macDicDoub<T> :macDic<T>
    {
        public int SonIdx(string pKey)
        {
            orderDic();
            double tDouble = mscExp.Doub(pKey);
            if (tDouble <= 0) return 0;
            var tKeyList = mDic.Keys.ToList();
            for (int i = 0; i < mDic.Count - 1; i++)
                if (tDouble > mscExp.Doub(tKeyList[i]) && tDouble <= mscExp.Doub(tKeyList[i + 1]))
                    return i;

            return tKeyList.Count;
        }

        public T Son(string pKey)
        {
            return mDic.ElementAt(SonIdx(pKey)).Value;
        }

        public List<KeyValuePair<T, double>> SonsPick(double pKey0, double pKey1)
        {
            double tKey0 = 0;double tKey1 = 0;
            if (pKey0 >= pKey1)
                { tKey0 = pKey1; tKey1 = pKey0; }
            else
                { tKey0 = pKey0; tKey1 = pKey1; }

            int idx0 = SonIdx(tKey0.ToString());
            int idx1 = SonIdx(tKey1.ToString());

            List<double> doubList = new List<double>();
            foreach (var fe in mDic.Keys)
                doubList.Add(mscExp.Doub(fe));

            List<KeyValuePair<T, double>> rtL = new List<KeyValuePair<T, double>>();

            double total = keyDoub(idx1) - keyDoub(idx0);
            double tPercent = (keyDoub(idx0 + 1) - tKey0) / total;
            rtL.Add(new KeyValuePair<T, double>(valueT(idx0), tPercent));
            
            for (int i = idx0 + 1; i < idx1; i++)
            {
                tPercent = (keyDoub(i + 1) - keyDoub(i)) / total;
                rtL.Add(new KeyValuePair<T, double>(valueT(i), tPercent));
            }

            return rtL;
        }

        public List<T> Sons() { return mDic.Values.ToList(); }

        public override void Add(T pT)
        {
            mDic.Add(((Iname)pT).Name(), pT);
            orderDic();

            //TODO: 添加项后自动排序
        }

        private void orderDic()
        {
            mDic = mscTools.OrderDic(mDic);
        }
        private double keyDoub(int pIdx)
        {
            return mscExp.Doub(mDic.ElementAt(pIdx).Key);
        }
        private T valueT(int pIdx)
        {
            return mDic.ElementAt(pIdx).Value;
        }
    }

}

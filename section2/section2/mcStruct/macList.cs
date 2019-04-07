using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public abstract class macList<T>: Iname
    {
        public string Name() { return name; }
        public void SetName(string pName) { name = pName; }
        private string name;
        public List<T> mList = new List<T>();

        public int Count
        {
            get { return mList.Count; }
        }
        public T Son(string pName)
        {
            return mList.Find(t => ((Iname)t).Name() == pName);
        }
        public T Son(int pIdx)
        {
            return mList[pIdx];
        }

        public void Add(T pT)
        {
            string tName = ((Iname)pT).Name();
            tName = mscTools.reName(mList, tName);
            ((Iname)pT).SetName(tName);
            mList.Add(pT);
        }
        public void MoveUp(int pIdx)
        {
            if (pIdx <= 0) return; exchange(pIdx - 1, pIdx);
        }
        public void MoveDown(int pIdx)
        {
            if (pIdx >= mList.Count) return; exchange(pIdx, pIdx + 1);
        }
        private void exchange(int pIdx1, int pIdx2)
        {
            if (pIdx1 > mList.Count || pIdx2 > mList.Count) return;
            if (pIdx1 < 0 || pIdx2 < 0) return;

            T t1 = mList[pIdx1];
            T t2 = mList[pIdx2];

            mList.RemoveAt(pIdx1);
            mList.Insert(pIdx1, t2);
            mList.RemoveAt(pIdx2);
            mList.Insert(pIdx2, t1);
        }
    }


}

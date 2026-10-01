using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcNameList<T>: ItoXML
    {
        public string Name = "";
        public List<T> mList = new List<T>();
        public void Add(T pT)
        {
            mList.Add(pT);
        }
        public int Count
        {
            get { return mList.Count; }
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
            mList.Insert(pIdx1,t2);
            mList.RemoveAt(pIdx2);
            mList.Insert(pIdx2, t1);
        }
        virtual public XElement toXML()
        {
            XElement rtXE = new XElement(this.ToString().Replace("section.", ""),
                       new XElement("Name", Name));
            foreach (T t in mList)
            {
                XElement tXE = ((ItoXML)t).toXML();
                rtXE.Add(tXE);
            }
            return rtXE;
        }
    }

    public interface ItoXML
    {
        XElement toXML();
    }
}

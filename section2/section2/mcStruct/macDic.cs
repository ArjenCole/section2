using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public abstract class macDic<T> : Iname
    {
        #region 实现接口
        public string Name() { return name; }
        public void SetName(string pName) { name = pName; }
        public string name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        #endregion
        public Dictionary<string, T> mDic = new Dictionary<string, T>();

        public int Count
        {
            get { return mDic.Count; }
        }

        public T Son(string pName)
        {
            return mDic[pName];
        }
        public T Son(int pIdx)
        {
            return mDic[mDic.Keys.ToList()[pIdx]];
        }
        public List<T> Sons() { return mDic.Values.ToList(); }

        public virtual void Add(T pT)
        {
            string tName = ((Iname)pT).Name();
            tName = mscTools.reName(mDic, tName);
            ((Iname)pT).SetName(tName);
            mDic.Add(tName, pT);
        }
    }
    public class mcDic<T> :macDic<T>
    {

    }
}

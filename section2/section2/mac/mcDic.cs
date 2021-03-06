﻿using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2
{
    public class mcDic<T> : Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }
        public string Name = "";//应该为私有变量拒绝直接修改，但是为了深拷贝不得不改为公共变量

        #endregion
        public Dictionary<string, T> mDic = new Dictionary<string, T>();

        public int Count()
        {  return mDic.Count; }

        public T Son(string pName) { return mDic[pName]; }
        public T Son(int pIdx) { return mDic[mDic.Keys.ToList()[pIdx]]; }
        public List<string> SonKeys() { return mDic.Keys.ToList(); }
        public List<T> Sons() { return mDic.Values.ToList(); }


        public virtual void Add(T pT)
        {
            string tName = ((Iname)pT).GetName();
            tName = mscTools.reName(mDic, tName);
            ((Iname)pT).SetName(tName);
            mDic.Add(tName, pT);
        }

        public void UpdateSon(int pIdx, T pT)
        {
            mDic[mDic.Keys.ToList()[pIdx]] = pT;                
        }

        public void UpdateSon(string pOname, T pT)
        {
            if (pOname == ((Iname)pT).GetName())
            {
                mDic[pOname] = pT;
            }
            else
            {
                mDic.Remove(pOname);
                Add(pT);
            }
        }
    }
}

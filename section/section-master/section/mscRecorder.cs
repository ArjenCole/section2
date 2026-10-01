using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;


namespace section
{
    
    public static class mscRecorder<T>
    {

        [Serializable]
        private class mcTandInfo
        {
            public Dictionary<string, string> Info = new Dictionary<string, string>();
            public T data;
            public mcTandInfo(T pT, Dictionary<string, string> pInfo)
            {
                Info = mscMslns.DeepClone(pInfo);
                data = mscMslns.DeepClone(pT);
            }
            public string discribe()
            {
                string tStr1 = Info["discribe"];
                string tStr2 = Info["mSname"] == "" ? "" : "-" + Info["mSname"];
                string tStr3 = Info["mUname"] == "" ? "" : "-" + Info["mUname"];
                string tStr4 = Info["mPEname"] == "" ? "" : "-" + Info["mPEname"];
                string tStr5 = Info["mPFname"] == "" ? "" : "-" + Info["mPFname"];
                return tStr1 + tStr2 + tStr3 + tStr4 + tStr5;
            }
        }

        private static Stack<mcTandInfo> history = new Stack<mcTandInfo>();
        private static Stack<mcTandInfo> future = new Stack<mcTandInfo>();

        public static void Ini(T pT = default(T), Dictionary<string, string> pInfo = null)
        {
            history.Clear();
            future.Clear();
            Do(pT, pInfo);
            mscLog.Write("重置操作记录");
        }
        public static void Do(T pT = default(T), Dictionary<string, string> pInfo = null)
        {
            mcTandInfo mTI = new mcTandInfo(pT, pInfo);
            history.Push(mTI);
            future.Clear();
            setFormControl();
            mscLog.Write(mTI.discribe());
        }

        public static T Undo(out Dictionary<string,string> pInfo)
        {
            if (history.Count > 1)
            {
                future.Push(history.Pop());
                pInfo = future.Peek().Info;
                setFormControl();
                mscLog.Write("撤销：" + history.Peek().discribe());
                return mscMslns.DeepClone(history.Peek().data);
            }
            if(history.Count==1)
            {
                pInfo = null;
                setFormControl();
                //mscLog.Write("撤销：" + history.Peek().discribe());
                return mscMslns.DeepClone(history.Peek().data);
            }
            else
            {
                pInfo = null;
                setFormControl();
                return default(T);
            }
            
        }
        public static T Redo(out Dictionary<string, string> pInfo)
        {
            if (future.Count > 0)
            {
                history.Push(future.Pop());
                mcTandInfo mTI = history.Peek();
                pInfo = mTI.Info;
                setFormControl();
                mscLog.Write("重做：" + mTI.discribe());
                return mscMslns.DeepClone(mTI.data);
            }
            pInfo = null;
            setFormControl();
            //mscLog.Write("重做：" + history.Peek().discribe());
            return mscMslns.DeepClone(history.Peek().data);
        }
        private static void setFormControl()
        {
            List<string> hisDiscribe = new List<string>();
            for (int i = 0; i <= 10; i++)
                if (history.Count >= i + 1)
                    hisDiscribe.Add(history.ElementAt(i).discribe());
                    
            List<string> futDiscribe = new List<string>();
            for (int i = 0; i <= 10; i++)
                if (future.Count >= i + 1)
                    futDiscribe.Add(future.ElementAt(i).discribe());

            mscCtrl.formMdi.FlashUndoRedo(hisDiscribe, futDiscribe);
        }
        
    }
}

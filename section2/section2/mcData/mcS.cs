using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcData
{
    public enum mcStype
    {
        Null = 0,
        Pipe = 1,//单管
        ConBox = 2,//箱涵
        Jacking = 3,//顶管
        Custom = 1000//自定义
    }
    public abstract class mcS:mcCpt
    {
        public mcStype Type;
        public string Describe;
        public string Depth;
        public string Unit;
        public string Amount;

        public Dictionary<string,double> PEdic;
        public Dictionary<string,double> PFdic;
        public Dictionary<string, double> PDdic;
        public Dictionary<string, double> PWdic;
        /// <summary>
        /// 获得断面在任意高度(基础底起算)的占土面积
        /// </summary>
        /// <param name="pH">从断面基础底标高(不含地基换填)起算的高度,单位mm</param>
        /// <returns></returns>
        protected virtual string OccupiedS(int pH) { return string.Empty; }
        /// <summary>
        /// 计算基坑挖填、围护、支撑、降水相关数量
        /// </summary>
        /// <param name="pPEname"></param>
        /// <param name="pPFname"></param>
        /// <returns></returns>
        private List<mcQ> pitQ(string pPEname, string pPFname) { return null; }

        protected virtual List<mcQ> eleQ() { return null; }
        public virtual List<mcQ> Q()
        {
            List<mcQ> rtL = new List<mcQ>();
            foreach (string fePE in PEdic.Keys)
                foreach (string fePF in PFdic.Keys)
                    rtL = mscTools.sumQ(rtL, pitQ(fePE, fePF));
            return mscTools.sumQ(rtL, eleQ());
        }
    }
}

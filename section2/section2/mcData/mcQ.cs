using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using section2.mcStruct;

namespace section2.mcData
{
    public class mcQ:Iname
    {
        #region 实现接口
        public string GetName() { return Name; }
        public void SetName(string pName) { Name = pName; }

        #endregion
        public string Cat = "";
        public string Name = "";
        public string Exp = "";
        public string Unit = "";
        
        public mcQ()
        {

        }
        public mcQ(string pCat,string pName)
        {
            Cat = pCat;Name = pName;
        }
        public mcQ(string pCat, string pName,string pExp,string pUnit)
        {
            Cat = pCat; Name = pName;Exp = pExp;Unit = pUnit;
        }

        public string CNU()
        {
            return Cat + "|" + Name + "|" + Unit;
        }
    }
}

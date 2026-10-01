using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcE0 : mcElement
    {
        public mcE0()
        {

        }
        public mcE0(XElement pXE)
        {
            readXE(pXE);
        }
        public mcE0(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            GetData(pData, pDicPE, pDicPF);
        }
        public override string Specification()
        {
            return string.Empty;
        }
        public override Dictionary<string, mcQ> cal_found()
        {
            return new Dictionary<string, mcQ>();
        }
    }

}

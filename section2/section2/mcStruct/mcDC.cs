using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public class mcDC:macList<mcSegment>
    {
        public mcBI BI;


        public mcDC()
        {
            BI = new mcStruct.mcBI();
            mList = new List<mcStruct.mcSegment>();

        }
    }
}

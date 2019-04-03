using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public class mcSegment:macList<mcUnit>
    {
        public mcSegment()
        {
            SetName("标段");
        }
        public mcSegment(List<string> pNameList)
        {
            SetName("标段");
            foreach (string feStr in pNameList)
            {
                Add(new mcUnit(feStr));
            }
        }
    }
}

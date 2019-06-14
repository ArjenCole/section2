using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mac
{
    public class mcRangeList<T>:List<macRange>
    {
        public void Order()
        {
            this.Sort(delegate (macRange x, macRange y)
            {
                return x.StartNum.CompareTo(y.StartNum);
            });
        }
    }

}

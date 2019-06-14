using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mac
{
    public class mcRangeList<T>:List<mcRange>
    {
        public void Order()
        {
            this.Sort(delegate (mcRange x, mcRange y)
            {
                return x.StartNum.CompareTo(y.StartNum);
            });
        }

        public void orderAdd(mcRange pR)
        {
            this.Add(pR);
            Order();
        }
        public void AddAt(int pIdx, mcRange pR)
        {
            this.AddAt(pIdx, pR);
        }
        public void Update(int pIdx, mcRange pR)
        {
            this[pIdx] = pR;
        }

    }

}

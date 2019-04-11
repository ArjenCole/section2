using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcStruct
{
    public interface Ijson<T>
    {
        string toJson();
        T DeepClone();
    }
}

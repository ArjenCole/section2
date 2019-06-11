using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace section2.mcP
{
    public class mcPB
    {
        public string ExvCat = "Ⅰ、Ⅱ类土";
        public string DockPos = "至管顶50cm";
        public string DockMat = "中粗砂";
        public string CovMat = "中粗砂";

        public string FndMat = "采用混凝土基础";
        public string FndAgl = "120";
        public string CuhMat = "中粗砂";
        public string CuhThk = "200";

        #region 下拉框数据源
        public static string[] sExvCat = new[] { "Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石" };
        public static string[] sDockPos = new[] { "至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高" };
        public static string[] sFndMat = new[] { "采用混凝土基础", "不采用混凝土基础" };
        public static string[] sFndAgl = new[] { "90", "120", "150", "180" };
        #endregion

    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using section2.mcData;
using System.Data;
using System.IO;
using System.Windows.Forms;

namespace section2
{
    public static class mscTools
    {
        #region 数据格式转换
        public static string ToString(object pObj)
        {
            try { return pObj.ToString(); }
            catch (Exception) { return string.Empty; }
        }
        #endregion

        #region 自定义数据格式运算
        public static List<mcQ> sumQ(List<mcQ> pL1, List<mcQ> pL2)
        {
            List<mcQ> rtL = new List<mcQ>();
            rtL.AddRange(pL1);
            rtL.AddRange(pL2);
            return sumQ(rtL);
        }
        public static List<mcQ> sumQ(List<mcQ> pL1)
        {
            Dictionary<string, mcQ> tD = new Dictionary<string, mcQ>();
            foreach (mcQ feQ in pL1)
                if (tD.Keys.Contains(feQ.CNU()))
                    tD[feQ.CNU()].Exp += "+" + feQ.Exp;
                else
                    tD.Add(feQ.CNU(), feQ);
            
            return tD.Values.ToList();
        }

        public static string reName<T>(Dictionary<string, T> pD, string pName)
        {
            string rtName = pName;
            if (pD.Count == 0) return rtName;
            int i = 0;
            while (pD.Keys.Contains(rtName)) 
            {
                i++;
                rtName = pName + i.ToString();
            }
            return rtName;
        }
        public static Dictionary<string,T> OrderDic<T>(Dictionary<string, T> pDic)
        {
            IOrderedEnumerable<KeyValuePair<string, T>> dicSort = from objDic in pDic orderby mscExp.Doub(objDic.Key) select objDic;
            //return from objDic in pDQ orderby order(objDic.Key) descending select objDic; 降序

            var rtDic = new Dictionary<string, T>();
            foreach (KeyValuePair<string, T> feKVP in dicSort)
                rtDic.Add(feKVP.Key ,feKVP.Value);
            return rtDic;
        }
        #endregion

        #region 序列化
        public static string toJson<T>(T pT)
        {
            var serializer = new JavaScriptSerializer();
            return serializer.Serialize(pT);
        }
        public static T anJson<T>(string pJsonStr)
        {
            var serializer = new JavaScriptSerializer();
            return serializer.Deserialize<T>(pJsonStr);
        }
        public static T DeepClone<T>(T pT)
        {
            string tJsonStr = toJson<T>(pT);
            return anJson<T>(tJsonStr);
        }
        #endregion

        #region 控件处理
        /// <summary>
        /// 利用反射机制修改TableLayoutPanel的Protected的DoubleBuffered属性 避免闪烁
        /// </summary>
        /// <param name="pO"></param>
        public static void DoubleBuffered(object pO)
        {
            pO.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(pO, true, null);
        }

        public static void DgvAdjRowsCnt(DataGridView pDGV, int pCnt)
        {
            int cnt = pDGV.Rows.Count;
            if (cnt == pCnt) return;
            if (cnt < pCnt) { pDGV.Rows.Add(pCnt - cnt);return; }
            for (int i = cnt; i <= pCnt; i--)
                pDGV.Rows.RemoveAt(i - 1);
        }
        #endregion
        /// <summary>
        /// 读取CSV文件
        /// </summary>
        /// <param name="pFileName">文件路径</param>
        /// <returns>DataTable</returns>
        static public DataTable OpenCSV(string pFileName)
        {
            DataTable rtDT = new DataTable();
            FileStream tFS = new FileStream(Application.StartupPath + @"\" + pFileName, System.IO.FileMode.Open, System.IO.FileAccess.Read);
            StreamReader tSR = new StreamReader(tFS, System.Text.Encoding.Default);
            //记录每次读取的一行记录
            string strLine = "";
            //记录每行记录中的各字段内容
            string[] aryLine;
            //标示列数
            int columnCount = 0;
            //标示是否是读取的第一行
            bool IsFirst = true;

            //逐行读取CSV中的数据
            while ((strLine = tSR.ReadLine()) != null)
            {
                aryLine = strLine.Split(',');
                if (IsFirst == true)
                {
                    IsFirst = false;
                    columnCount = aryLine.Length;
                    //创建列
                    for (int i = 0; i < columnCount; i++)
                    {
                        DataColumn dc = new DataColumn(aryLine[i]);
                        rtDT.Columns.Add(dc);
                    }
                }
                else
                {
                    DataRow dr = rtDT.NewRow();
                    for (int j = 0; j < columnCount; j++)
                    {
                        dr[j] = aryLine[j];
                    }
                    rtDT.Rows.Add(dr);
                }
            }
            tSR.Close();
            tFS.Close();
            return rtDT;
        }

    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization.Formatters.Binary;
using System.Text;

using System.Windows.Forms;
using System.Xml.Linq;

namespace section
{
    /// <summary>
    /// 杂项
    /// </summary>
    static class mscMslns
    {
        public static string EnvironmentAdd()
        {
            return Application.StartupPath + @"\";
        }
        public static string EnvironmentAdd(string pFileName)
        {
            return EnvironmentAdd() + pFileName;
        }

        public static string ShowDouble(double p_double)
        {
            return Math.Round(p_double, 4).ToString();
        }

        public static double ToDouble(object pObj)
        {
            return ((pObj == null) || (pObj is DBNull) || pObj.ToString() == "") ? 0 : Convert.ToDouble(pObj);
        }
        public static double ToDouble(string pStr)
        {
            return pStr == string.Empty ? 0 : Convert.ToDouble(pStr);
        }
        public static string ToString(object p_obj)
        {
            try
            {
                return p_obj.ToString();
            }
            catch (Exception)
            {
                return string.Empty;
            }
        }

        public static void DGV_RcntAdjust(DataGridView p_DGV, int p_RowCnt)
        {
            if (p_RowCnt == 0) { p_DGV.Rows.Clear(); return; }
            if (p_DGV.Rows.Count < p_RowCnt)
            {
                p_DGV.Rows.Add(p_RowCnt - p_DGV.Rows.Count);
            }
            else
            {
                for (int i = p_DGV.Rows.Count - 1; i > p_RowCnt - 1; i--)
                {
                    p_DGV.Rows.RemoveAt(i - 1);
                }
            }
        }
        public static void DGV_ShowDic(DataGridView p_DGV, Dictionary<string, string> p_Dic)
        {
            mscMslns.DGV_RcntAdjust(p_DGV, p_Dic.Count);
            int i = 0;
            foreach (KeyValuePair<string, string> fe_KVP in p_Dic)
            {
                p_DGV.Rows[i].HeaderCell.Value = fe_KVP.Key;
                p_DGV[0, i].Value = fe_KVP.Value;
                i++;
            }
        }
        public static void DGV_DeleteRows(DataGridView p_DGV)
        {
            foreach (DataGridViewCell fe_DGVC in p_DGV.SelectedCells)
            {
                if (fe_DGVC.RowIndex < 0) { continue; }
                if (!fe_DGVC.OwningRow.IsNewRow)
                {
                    p_DGV.Rows.Remove(fe_DGVC.OwningRow);
                }
            }
        }

        public static T DeepClone<T>(T para_obj)
        {
            using (var ms = new MemoryStream())
            {
                var formatter = new BinaryFormatter();
                formatter.Serialize(ms, para_obj);
                ms.Position = 0;

                return (T)formatter.Deserialize(ms);
            }
        }

        public static string ReNameToAdd(List<string> pNameList, string pNameToAdd)
        {
            string rtName = pNameToAdd;
            int i = 0;
            while (pNameList.Contains(rtName))
            {
                i++;
                rtName = pNameToAdd + i.ToString();
            }
            return rtName;
        }

        public static void CheckPath(string pPath)
        {
            if (!File.Exists(pPath))
            {
                FileInfo fi = new FileInfo(pPath);
                var di = fi.Directory;
                di.Create();
            }
        }
    }
}

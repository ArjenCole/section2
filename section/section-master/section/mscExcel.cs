using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Data;
using System.Data.OleDb;

using Excel = Microsoft.Office.Interop.Excel;
using System.Windows.Forms;
using System.IO;

namespace section
{
    static class mscExcel
    {
        #region 读取
        static private DataSet myds = new DataSet();//创建数据集

        static public DataSet getDS(string para_fileName, string para_sheetName)
        {
            string fileadd = Application.StartupPath + @"\" + para_fileName;//获得运行文件的存储路径

            OleDbConnection olecnt = new OleDbConnection("Provider=Microsoft.ACE.OLEDB.12.0;Data Source="
                + fileadd + ";Extended Properties=Excel 8.0");//连接EXCEL数据库
            olecnt.Open();//打开数据库连接
            OleDbDataAdapter oledbda = new OleDbDataAdapter("select * from [" + para_sheetName + "$]", olecnt);
            myds.Clear();
            oledbda.Fill(myds);
            oledbda.Dispose();
            olecnt.Close();
            return myds;
        }
        static public DataTable getDT(string para_fileName, string para_sheetName)
        {

            DataTable mydt = new DataTable();//创建数据表
            string fileadd = Application.StartupPath + @"\" + para_fileName;//获得运行文件的存储路径
            
            OleDbConnection olecnt = new OleDbConnection("Provider=Microsoft.ACE.OLEDB.12.0;Data Source="
                + fileadd + ";Extended Properties=Excel 12.0");//连接EXCEL数据库
            olecnt.Open();//打开数据库连接
            OleDbDataAdapter oledbda = new OleDbDataAdapter("select * from [" + para_sheetName + "$]", olecnt);
            mydt.Clear();
            oledbda.Fill(mydt);
            mydt.TableName = para_sheetName;
            oledbda.Dispose();
            olecnt.Close();


            string tFileName = para_fileName.Replace(".xlsx", "");
            tFileName += "--" + para_sheetName + ".csv";
            SaveCSV(mydt.Copy(), tFileName);
            return mydt.Copy();
        }
        #endregion

        #region 写入
        /// <summary>
        /// 导出到Excel
        /// </summary>
        /// <param name="pSaveFileName">默认文件名</param>
        /// <param name="pDGVQ">数据源，一个页面上的DataGridView控件</param>
        static public bool ExportExcel(string pSaveFileName, DataGridView pDGVQ, DataGridView pDGVL, bool pMessageBox = true)
        {

            Microsoft.Office.Interop.Excel.Application xlApp;
            try
            {
                xlApp = new Microsoft.Office.Interop.Excel.Application();
                //设置禁止弹出保存和覆盖的询问提示框  
                xlApp.DisplayAlerts = false;
                xlApp.AlertBeforeOverwriting = false;
            }
            catch (Exception)
            {
                MessageBox.Show("无法创建Excel对象,请确认已安装Excel。", "对象创建错误", MessageBoxButtons.OK);
                return false; 
            }
            finally
            {
            }

            Microsoft.Office.Interop.Excel.Workbooks workbooks = xlApp.Workbooks;

            Microsoft.Office.Interop.Excel.Workbook workbook = workbooks.Add(Microsoft.Office.Interop.Excel.XlWBATemplate.xlWBATWorksheet);

            workbook.Worksheets.Add();


            Microsoft.Office.Interop.Excel.Worksheet worksheet1 = (Microsoft.Office.Interop.Excel.Worksheet)workbook.Worksheets[1];//取得sheet1
            worksheet1.Name = "定额工程量";
            writeData(worksheet1, pDGVQ);

            Microsoft.Office.Interop.Excel.Worksheet worksheet2 = (Microsoft.Office.Interop.Excel.Worksheet)workbook.Worksheets[2];//取得sheet2
            worksheet2.Name = "清单工程量";
            writeData(worksheet2, pDGVL);
            bool fileSaved = false;
            if (pSaveFileName != "")
            {
                try
                {
                    workbook.SaveAs(pSaveFileName, 56);
                    workbook.Saved = true;
                    fileSaved = true;
                }
                catch (Exception ex)
                {
                    MessageBox.Show(ex.Message  +" 文件可能正在使用。" , "导出错误", MessageBoxButtons.OK);
                    return false;
                }

            }
            xlApp.Quit();
            GC.Collect();//强行销毁 
            if (fileSaved && pMessageBox) 
                MessageBox.Show(pSaveFileName + " 导出成功", "提示", MessageBoxButtons.OK);
            return true;
        }
        static private void writeData(Excel.Worksheet pWorkSheet, DataGridView pDGV)
        {
            //写入列标题
            for (int i = 0; i <= pDGV.Columns.Count - 1; i++)
            {
                pWorkSheet.Cells[1, i + 1] = pDGV.Columns[i].HeaderCell.Value;

            }
            //写入数值
            for (int r = 0; r <= pDGV.Rows.Count - 1; r++)
            {
                if (pDGV.Rows[r].Cells[0].Value != null && pDGV.Rows[r].Cells[0].Value.ToString() == "清单项目")
                {
                    var tCell1 = pWorkSheet.Cells[r + 2, 1];
                    var tCell2 = pWorkSheet.Cells[r + 2, pDGV.Columns.Count];
                    Excel.Range range = pWorkSheet.Range[tCell1, tCell2].Cells;
                    range.Interior.Color = System.Drawing.Color.FromArgb(255, 204, 153).ToArgb();
                    
                }
                for (int i = 0; i <= pDGV.Columns.Count - 1; i++)
                {
                    pWorkSheet.Cells[r + 2, i + 1] = pDGV.Rows[r].Cells[i].Value;
                }
                System.Windows.Forms.Application.DoEvents();
            }

            pWorkSheet.Columns.EntireColumn.AutoFit();//列宽自适应
        }
        #endregion



        /// 将DataTable中数据写入到CSV文件中
        ///
        /// 提供保存数据的DataTable
        /// CSV的文件路径
        static private void SaveCSV(DataTable pDT, string pFileName)
        {

            FileStream fs = new FileStream(pFileName, System.IO.FileMode.Create, System.IO.FileAccess.Write);
            StreamWriter sw = new StreamWriter(fs, System.Text.Encoding.Default);
            string data = "";

            //写出列名称
            for (int i = 0; i < pDT.Columns.Count; i++)
            {
                data += pDT.Columns[i].ColumnName.ToString();
                if (i < pDT.Columns.Count - 1)
                {
                    data += ",";
                }
            }
            sw.WriteLine(data);
            //写出各行数据
            for (int i = 0; i < pDT.Rows.Count; i++)
            {
                data = "";
                for (int j = 0; j < pDT.Columns.Count; j++)
                {
                    data += pDT.Rows[i][j].ToString();
                    if (j < pDT.Columns.Count - 1)
                    {
                        data += ",";
                    }
                }
                sw.WriteLine(data);
            }
            sw.Close();
            fs.Close();
            //MessageBox.Show("CSV文件保存成功！");
        }

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

using System;
using System.Collections.Generic;
using System.Data;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace section
{
    class mscInventory
    {
        public const string Alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        public static Dictionary<string, mcComponent> Ecpnti = new Dictionary<string, mcComponent>();
        public static Dictionary<string, mcComponent> WScpnti = new Dictionary<string, mcComponent>();
        public static Dictionary<string, mcComponent> Fcpnti = new Dictionary<string, mcComponent>();

        public static mcDataCarrier Elei = new mcDataCarrier();

        public static Dictionary<string, Dictionary<int, double>> WorkWidth = new Dictionary<string, Dictionary<int, double>>();
        public static Dictionary<string, Dictionary<int, double>> GrooveB = new Dictionary<string, Dictionary<int, double>>();

        public static Dictionary<string, List<string>> SteelProducts = new Dictionary<string, List<string>>();
        public static Dictionary<string, Dictionary<string, double>> price = new Dictionary<string, Dictionary<string, double>>();

        public static void Init()
        {
            mscLog.Write("载入元素库");//载入元素库
            Elei = mscXML.ReadXml(Application.StartupPath + @"\Inventory\EleInventory.stn");
            mscLog.Write("载入围护库");//载入围护库
            Ecpnti = LoadCpnti("Ei");
            mscLog.Write("载入止水库");//载入止水库
            WScpnti = LoadCpnti("WSi");
            mscLog.Write("载入地基库");//载入地基库
            Fcpnti = LoadCpnti("Fi");
            mscLog.Write("载入默认工作面宽度表");//载入默认工作面宽度表
            WorkWidth = LoadGrooveWidth("WorkWidth");
            mscLog.Write("载入默认沟槽宽度表");//载入默认沟槽宽度表
            GrooveB = LoadGrooveWidth("GrooveB");
            mscLog.Write("载入钢制品参数");//载入钢制品参数
            SteelProducts = LoadSteelProducts("SteelProducts");
            mscLog.Write("载入价格库");//载入价格库
            price = LoadPrice("price");
        }
        private static Dictionary<string, mcComponent> LoadCpnti(string piName)
        {
            DataTable tmpDT = mscExcel.OpenCSV(@"Inventory\ComponentInventory--"+ piName + ".CSV");
            return GetRowsByFilter(tmpDT);
        }
        private static Dictionary<string, mcComponent> GetRowsByFilter(DataTable pDT)
        {
            Dictionary<string, mcComponent> rtDic = new Dictionary<string, mcComponent>();
            DataTable table = pDT;
            DataRow[] foundRowsDis;
            DataRow[] foundRowsValue;
            //使用选择方法来找到匹配的所有行。
            foundRowsDis = table.Select("key = 'discribe'");
            foundRowsValue = table.Select("key = 'value'");
            //过滤行,找到所要的行。
            for (int i = 0; i < foundRowsDis.Length; i++)
            {
                mcComponent tmpmC = new mcComponent();
                tmpmC.Name = mscMslns.ToString(foundRowsDis[i]["name"]);
                tmpmC.DiscribeFmla = mscMslns.ToString(foundRowsValue[i]["name"]);
                foreach (char feChar in Alphabet)
                {
                    string tKey = mscMslns.ToString(feChar);
                    string tVKey = mscMslns.ToString(foundRowsDis[i][tKey]);
                    string tVValue = mscMslns.ToString(foundRowsValue[i][tKey]);
                    AddTotmpmC(tmpmC, tKey, tVKey, tVValue);

                    tKey = "F" + mscMslns.ToString(feChar);
                    tVKey = mscMslns.ToString(foundRowsDis[i][tKey]);
                    tVValue = mscMslns.ToString(foundRowsValue[i][tKey]);
                    AddTotmpmC(tmpmC, tKey, tVKey, tVValue);
                    try
                    {
                        tKey = "Z" + mscMslns.ToString(feChar);
                        tVKey = mscMslns.ToString(foundRowsDis[i][tKey]);
                        tVValue = mscMslns.ToString(foundRowsValue[i][tKey]);
                        AddTotmpmC(tmpmC, tKey, tVKey, tVValue);
                    }catch { }
                }
                tmpmC.getCnt();
                rtDic.Add(mscMslns.ToString(foundRowsDis[i]["name"]), tmpmC);
            }
            return rtDic;
        }
        private static void AddTotmpmC(mcComponent pmC, string pKey, string pVKey, string pVValue)
        {
            if (pVKey == string.Empty) { return; }
            pmC.param[pKey] = new KeyValuePair<string, string>(pVKey, pVValue);
        }

        private static Dictionary<string, Dictionary<int, double>> LoadGrooveWidth(string pSheetName)
        {
            Dictionary<string, Dictionary<int, double>> rtDic = new Dictionary<string, Dictionary<int, double>>();

            DataTable table = mscExcel.OpenCSV(@"Atlas\GB 50268-2008--" + pSheetName + ".CSV");
            foreach (DataRow feDR in table.Rows)
            {
                string tName = mscMslns.ToString(feDR["名称"]);
                Dictionary<int, double> tdic = new Dictionary<int, double>();
                for (int i = 0; i <= 30; i++)
                {
                    string tKey = mscMslns.ToString(i * 100);
                    tdic.Add(i * 100, mscMslns.ToDouble(feDR[tKey]));
                }
                rtDic.Add(tName, tdic);
            }
            return rtDic;

        }

        private static Dictionary<string, List<string>> LoadSteelProducts(string pSheetName)
        {
            DataTable table = mscExcel.OpenCSV(@"Inventory\SteelProducts--" + pSheetName + ".CSV");
            Dictionary<string, List<string>> rtDic = new Dictionary<string, List<string>>();
            for (int row = 1; row < table.Rows.Count; row++)
            {
                string rowName = mscMslns.ToString(table.Rows[row][0]);
                if(!rtDic.Keys.Contains(rowName))
                    rtDic.Add(rowName, new List<string>());
                for (int col = 1; col < table.Columns.Count; col++)
                    rtDic[rowName].Add(mscMslns.ToString(table.Rows[row][col]));
            }
            return rtDic;
        }

        private static Dictionary<string, Dictionary<string, double>> LoadPrice(string pSheetName)
        {
            DataTable table = mscExcel.OpenCSV(@"Inventory\Price--" + pSheetName + ".CSV");
            Dictionary<string, Dictionary<string, double>> rtDic = new Dictionary<string, Dictionary<string, double>>();
            for (int col = 3; col < table.Columns.Count; col++)
            {
                Dictionary<string, double> tDic = new Dictionary<string, double>();
                for (int row = 0; row < table.Rows.Count; row++)
                {
                    string tKey = mscMslns.ToString(table.Rows[row][0]) + "|" + mscMslns.ToString(table.Rows[row][1]) + "|" + mscMslns.ToString(table.Rows[row][2]);
                    tDic.Add(tKey, mscMslns.ToDouble(table.Rows[row][col]));
                }
                rtDic.Add(table.Columns[col].ColumnName, tDic);
            }
            return rtDic;

        }

    }
}

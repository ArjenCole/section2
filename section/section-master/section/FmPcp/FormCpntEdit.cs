using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;

using System.Windows.Forms;

namespace section
{
    public partial class FormCpntEdit : Form
    {
        public mcComponent mCcrt = new mcComponent();
        
        public FormCpntEdit(mcComponent pmC)
        {
            InitializeComponent();
            mCcrt = mscMslns.DeepClone(pmC);
            FlashdGV();
        }
        
        private void BTNyes_Click(object sender, EventArgs e)
        {
            getmCFromdGVs();
            DialogResult = DialogResult.Yes;
            this.Close();
        }
        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }
        private void getmCFromdGVs()
        {
            mCcrt.param.Clear();
            getmCFromdGV(dGVparam, string.Empty);
            getmCFromdGV(dGVfomla, "F");
            getmCFromdGV(dGVzomla, "Z");
        }
        private void getmCFromdGV(DataGridView pDGV, string pKeyHead)
        {
            for (int i = 0; i < pDGV.RowCount; i++)
            {
                string tKey = pKeyHead + mscInventory.Alphabet[i];
                string tVKey = mscMslns.ToString(pDGV[0, i].Value);
                string tVValue = mscMslns.ToString(pDGV[1, i].Value);
                mCcrt.param.Add(tKey, new KeyValuePair<string, string>(tVKey, tVValue));
            }
        }

        private void FlashdGV()
        {
            Dictionary<string, KeyValuePair<string, string>> tD = mCcrt.param;
            foreach (string feKey in tD.Keys)
            {
                if (feKey.StartsWith("F") && (feKey.Length == 2))
                    AddRowTodGV(dGVfomla, feKey, mCcrt.param[feKey]);
                else if (feKey.StartsWith("Z") && (feKey.Length == 2))
                    AddRowTodGV(dGVzomla, feKey, mCcrt.param[feKey]);
                else
                    AddRowTodGV(dGVparam, feKey, mCcrt.param[feKey]);
            }
        }
        private void AddRowTodGV(DataGridView pDGV, string pKey, KeyValuePair<string, string> pValue)
        {
            pDGV.Rows.Add();
            int tRowIdx = pDGV.Rows.Count - 1;
            pDGV.Rows[tRowIdx].HeaderCell.Value = pKey;
            pDGV[0, tRowIdx].Value = pValue.Key;
            pDGV[1, tRowIdx].Value = pValue.Value;
        }

        private void FormCpntEdit_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                    FormCancel();
                    break;
                default:
                    break;
            }
        }
        private void FormCancel()
        {
            DialogResult = DialogResult.Cancel;
            this.Close();
        }

        private void dGVparam_SelectionChanged(object sender, EventArgs e)
        {
            CMS.Items.Clear();
            if (dGVparam.CurrentCell == null) return;
            string tRowName = mscMslns.ToString(dGVparam.CurrentCell.OwningRow.Cells[0].Value);
            var tKeys = mscInventory.SteelProducts.Where(q => q.Value[0] == tRowName).Select(q => q.Key);  //get all keys
            foreach (string feStr in tKeys)
                CMS.Items.Add(feStr);
        }

        private void CMS_ItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
            string tKey = e.ClickedItem.Text;
            Dictionary<string, string> tDic = new Dictionary<string, string>();
            switch (mscInventory.SteelProducts[tKey][0])
            {
                case "钢板桩型号":
                    tDic.Add("钢板桩型号", mscInventory.SteelProducts[tKey][3]);
                    tDic.Add("单桩宽度 mm", mscInventory.SteelProducts[tKey][2]);
                    tDic.Add("桩中心间隔 mm", mscInventory.SteelProducts[tKey][2]);
                    tDic.Add("单桩延米重量 kg/m", mscInventory.SteelProducts[tKey][1]);
                    break;
                case "工法桩轴数 轴":
                    tDic.Add("桩径 mm", mscInventory.SteelProducts[tKey][2]);
                    tDic.Add("工法桩轴数 轴", mscInventory.SteelProducts[tKey][3]);
                    tDic.Add("单套截面积 m2", mscInventory.SteelProducts[tKey][1]);
                    tDic.Add("搭接 mm", mscInventory.SteelProducts[tKey][4]);
                    break;

                default:
                    tDic.Add(mscInventory.SteelProducts[tKey][0], mscInventory.SteelProducts[tKey][1]);
                    break;
            }
            for (int i = 0; i < dGVparam.Rows.Count; i++)
            {
                string tRowName = mscMslns.ToString(dGVparam.Rows[i].Cells[0].Value);
                if (tDic.Keys.Contains(tRowName)) 
                    dGVparam.Rows[i].Cells[1].Value = tDic[tRowName];
            }
        }
    }
}

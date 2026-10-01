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
    public partial class FormEcls : Form
    {
        public mcEnclosure mEclscrt;
        public FormEcls(mcEnclosure pmEcls)
        {
            mEclscrt = mscMslns.DeepClone(pmEcls);
            InitializeComponent();
            ColEclsCat.DataSource = mscInventory.Ecpnti.Keys.ToList();
            FlashdGVCpnt();
        }

        private void TXTStepCnt_KeyUp(object sender, KeyEventArgs e)
        {

            FlashdGVCpnt();
        }

        private void dGVCpnt_CellContentClick(object sender, DataGridViewCellEventArgs e)
        {
            mcEclsCpnt tmEC = mEclscrt.mList[e.RowIndex];
            switch (dGVCpnt.Columns[e.ColumnIndex].Name)
            {
                case "ColHfix":
                    tmEC.H = !Convert.ToBoolean(dGVCpnt.CurrentCell.Value) ? 1 : -1;//因为此时修改尚未被单元格接收，所以要按照原有值推算修改值
                    FlashdGVCpntRow(e.RowIndex);
                    break;
                default:
                    break;
            }
        }
        private void dGVCpnt_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            mcEclsCpnt tmEC = mEclscrt.mList[e.RowIndex];
            switch (dGVCpnt.Columns[e.ColumnIndex].Name)
            {
                case "ColH":
                    tmEC.H = mscMslns.ToDouble(dGVCpnt.CurrentCell.Value);
                    //FlashdGVCpntRow(e.RowIndex);
                    break;
                case "ColStepWidth":
                    tmEC.stepWidth = mscMslns.ToDouble(dGVCpnt.CurrentCell.Value);
                    break;
                case "ColEclsCat":
                    if (tmEC.Cpnt.Name == mscMslns.ToString(dGVCpnt.CurrentCell.Value)) return;
                    tmEC.Cpnt = mscInventory.Ecpnti[mscMslns.ToString(dGVCpnt.CurrentCell.Value)];
                    FlashdGVCpntRow(e.RowIndex);
                    break;
                default:
                    break;
            }
        }
        private void dGVCpnt_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            if (dGVCpnt.Columns[e.ColumnIndex].Name != "ColEclsDis")
            {
                dGVCpnt.BeginEdit(true);
                return;
            }
            FormCpntEdit formCpntEdit = new FormCpntEdit(mEclscrt.mList[e.RowIndex].Cpnt);
            if (formCpntEdit.ShowDialog() == DialogResult.Yes)
            {
                mEclscrt.mList[e.RowIndex].Cpnt = formCpntEdit.mCcrt;
                FlashdGVCpntRow(e.RowIndex);
            }

        }
        private void dGVCpnt_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Insert:
                    InsertCpnt(dGVCpnt.CurrentCell.RowIndex);
                    break;
                case Keys.Delete:
                    List<int> tmpL = new List<int>();
                    foreach (DataGridViewCell feDGVC in dGVCpnt.SelectedCells)
                        if (!tmpL.Contains(feDGVC.RowIndex)) tmpL.Add(feDGVC.RowIndex);
                    if (tmpL.Count == mEclscrt.Count) { MessageBox.Show("至少需要一级围护做法。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk); return; }
                    tmpL.Sort();
                    tmpL.Reverse();
                    foreach (int i in tmpL)
                        mEclscrt.mList.RemoveAt(i);
                    FlashdGVCpnt();
                    break;
                default:
                    break;
            }
        }
        private void BTNadd_Click(object sender, EventArgs e)
        {
            InsertCpnt(-1);
        }
        private void InsertCpnt(int pIdx = -1)
        {
            if (pIdx < 0) pIdx = mEclscrt.Count; //默认加在最后
            mEclscrt.mList.Insert(pIdx, new mcEclsCpnt(mscInventory.Ecpnti.First().Key));

            FlashdGVCpnt();
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            this.DialogResult = DialogResult.Yes;
            this.Close();
        }
        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }


        private void FlashdGVCpnt()
        {
            mscMslns.DGV_RcntAdjust(dGVCpnt, mEclscrt.Count);

            for (int i = 0; i < mEclscrt.Count; i++)
                FlashdGVCpntRow(i);
        }
        private void FlashdGVCpntRow(int pIdx)
        {
            mcEclsCpnt tmEC = mEclscrt.mList[pIdx];
            if (tmEC == null) { tmEC = new mcEclsCpnt(mscInventory.Ecpnti.First().Key); }
            dGVCpnt["ColHfix", pIdx].Value = tmEC.H < 0 ? false : true;
            dGVCpnt["ColH", pIdx].Value = tmEC.H < 0 ? "均分高度" : mscMslns.ToString(tmEC.H);
            dGVCpnt["ColH", pIdx].ReadOnly = tmEC.H < 0 ? true : false;
            dGVCpnt["ColStepWidth", pIdx].Value = mscMslns.ToString(tmEC.stepWidth);
            dGVCpnt["ColEclsCat", pIdx].Value = tmEC.Cpnt.Name;
            dGVCpnt["ColEclsDis", pIdx].Value = tmEC.Cpnt.Discribe();

        }

        private void FormEcls_KeyUp(object sender, KeyEventArgs e)
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

        private void dGVCpnt_CellClick(object sender, DataGridViewCellEventArgs e)
        {
            if (dGVCpnt.Columns[e.ColumnIndex].GetType().ToString() == "System.Windows.Forms.DataGridViewComboBoxColumn")
                dGVCpnt.BeginEdit(true);

        }
    }
}

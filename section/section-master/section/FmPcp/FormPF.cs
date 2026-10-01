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
    public partial class FormPF : Form
    {
        private mcPcpFoundation mPFcrt;
        private string OrigName;

        public FormPF(string pmPFname)
        {
            InitializeComponent();
            CBOcpnt.DataSource = mscInventory.Fcpnti.Keys.ToList();

            mPFcrt = mscMslns.DeepClone(mscCtrl.DC.PF[pmPFname]);
            OrigName = mPFcrt.Name;
            FlashFm();
        }

        private void CBOcpnt_DropDownClosed(object sender, EventArgs e)
        {
            if (!mscInventory.Fcpnti.Keys.Contains(CBOcpnt.Text)) return;
            if (mPFcrt == null) return;
            if (mPFcrt.Foundation.Name == CBOcpnt.Text) return;
            mPFcrt.Foundation = mscInventory.Fcpnti[CBOcpnt.Text];
            FlashCpnt();
        }
        private void LBLcpnt_DoubleClick(object sender, EventArgs e)
        {
            FormCpntEdit formCpntEdit = new FormCpntEdit(mPFcrt.Foundation);
            if (formCpntEdit.ShowDialog() == DialogResult.Yes)
            {
                mPFcrt.Foundation = formCpntEdit.mCcrt;
                FlashCpnt();
            }
        }

        private void dGVR_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            switch (e.ColumnIndex)
            {
                case 0:
                    mPFcrt.mList[e.RowIndex].Name = mscMslns.ToString(dGVR.CurrentCell.Value);
                    break;
                case 1:
                    mPFcrt.mList[e.RowIndex].H = mscMslns.ToDouble(dGVR.CurrentCell.Value);
                    break;
                default:
                    break;
            }
        }
        private void dGVR_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Insert:
                    if (dGVR.CurrentCell == null)
                        InsertEcls(-1);
                    else
                        InsertEcls(dGVR.CurrentCell.RowIndex);
                    break;
                case Keys.Delete:
                    List<int> tmpL = new List<int>();
                    foreach (DataGridViewCell feDGVC in dGVR.SelectedCells)
                    {
                        if (!tmpL.Contains(feDGVC.RowIndex)) { tmpL.Add(feDGVC.RowIndex); }
                    }
                    tmpL.Sort();
                    tmpL.Reverse();
                    foreach (int i in tmpL)
                    {
                        mPFcrt.mList.RemoveAt(i);
                    }
                    FlashdGVR();
                    break;
                default:
                    break;
            }
        }
        private void BTNadd_Click(object sender, EventArgs e)
        {
            InsertEcls(-1);
        }
        private void InsertEcls(int pIdx)
        {
            if (pIdx < 0) { pIdx = mPFcrt.Count; }//默认加在最后
            mPFcrt.mList.Insert(pIdx, new mcReplacement("碎石", 200));
            FlashdGVR();
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            mPFcrt.Name = TXTPFname.Text;
            mscCtrl.Set(OrigName, mPFcrt);
            this.Close();
        }
        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }

        private void FlashFm()
        {
            TXTPFname.Text = mPFcrt.Name;
            FlashdGVR();
            FlashCpnt();
        }
        private void FlashdGVR()
        {
            mscMslns.DGV_RcntAdjust(dGVR, mPFcrt.Count);
            for (int i = 0; i < mPFcrt.Count; i++)
            {
                mcReplacement tmR = mPFcrt.mList[i];
                dGVR[0, i].Value = tmR.Name;
                dGVR[1, i].Value = mscMslns.ToString(tmR.H);
            }
            FlashCpnt();
        }
        private void FlashCpnt()
        {
            CBOcpnt.Text = mPFcrt.Foundation.Name;
            LBLcpnt.Text = mPFcrt.Count > 0 ? "本原则采用" + mPFcrt.Count + "层换填；" : "不采用换填；";
            LBLcpnt.Text += mPFcrt.Foundation.Discribe() + "。";
        }

        private void BTNedit_Click(object sender, EventArgs e)
        {
            FormCpntEdit formCpnt = new FormCpntEdit(mPFcrt.Foundation);
            if (formCpnt.ShowDialog() == DialogResult.Yes)
            {
                mPFcrt.Foundation = formCpnt.mCcrt;
                FlashCpnt();
            }
        }

        private void FormPF_KeyUp(object sender, KeyEventArgs e)
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
    }
}

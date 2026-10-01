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
    public partial class FormPE : Form
    {
        mcPcpEnclosure mPEcrt;
        private string OrigName;

        public FormPE(string pPEname)
        {
            mPEcrt = mscMslns.DeepClone(mscCtrl.DC.PE[pPEname]);
            OrigName = mPEcrt.Name;
            InitializeComponent();
            SetDropItems();
        }
        private void FormPE_Load(object sender, EventArgs e)
        {
            FlashFm();
        }
        private void SetDropItems()
        {
            CBOexcvt.DataSource = new[] { "Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石" };
            CBOdock.DataSource = new[] { "至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高" };
            CBOconfound.DataSource = new[] { "采用混凝土基础", "不采用混凝土基础" };
            CBOconangle.DataSource = new[] { "90", "120", "150", "180" };

            List<string> tL1 = mscInventory.Ecpnti.Keys.ToList();
            tL1.Add(mcEnclosure.MultiScpntTxt);
            ColEclsCat.DataSource = tL1;

            List<string> tL2 = mscInventory.WScpnti.Keys.ToList();
            ColWSCat.DataSource = tL2;

        }

        private void dGVPE_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            mcEnclosure tmEcls = mPEcrt.mList[e.RowIndex];
            switch (dGVPE.Columns[e.ColumnIndex].Name)
            {
                case "Coldepth":
                    tmEcls.MinDepth = mscMslns.ToDouble(dGVPE.CurrentCell.Value);
                    FlashdGVPERow(e.RowIndex - 1);
                    break;
                case "ColEclsCat":
                    if (tmEcls.ECpntCat == mscMslns.ToString(dGVPE.CurrentCell.Value)) return;
                    tmEcls.ECpntCat = mscMslns.ToString(dGVPE.CurrentCell.Value);
                    FlashdGVPERow(e.RowIndex);
                    break;
                case "ColWSCat":
                    if (tmEcls.WSCpnt.Name == mscMslns.ToString(dGVPE.CurrentCell.Value)) return;
                    tmEcls.WSCpnt = mscInventory.WScpnti[mscMslns.ToString(dGVPE.CurrentCell.Value)];
                    FlashdGVPERow(e.RowIndex);
                    break;
                default:
                    break;
            }
        }

        private void dGVPE_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0) { return; }
            switch (dGVPE.Columns[e.ColumnIndex].Name)
            {
                case "ColEclsDis":
                    if (mPEcrt.mList[e.RowIndex].ECpntCat == mcEnclosure.MultiScpntTxt)//多级围护
                    {
                        FormEcls formEcls = new FormEcls(mPEcrt.mList[e.RowIndex]);
                        if (formEcls.ShowDialog() == DialogResult.Yes)
                        {
                            mPEcrt.mList[e.RowIndex] = formEcls.mEclscrt;
                            FlashdGVPERow(e.RowIndex);
                        }   
                    }
                    else//单级围护
                    {
                        FormCpntEdit formCpntEdit1 = new FormCpntEdit(mPEcrt.mList[e.RowIndex].mList[0].Cpnt);
                        if (formCpntEdit1.ShowDialog() == DialogResult.Yes)
                        {
                            mPEcrt.mList[e.RowIndex].mList[0].Cpnt = formCpntEdit1.mCcrt;
                            FlashdGVPERow(e.RowIndex);
                        }   
                    }
                    break;
                case "ColWSDis":
                    FormCpntEdit formCpntEdit2 = new FormCpntEdit(mPEcrt.mList[e.RowIndex].WSCpnt);
                    if (formCpntEdit2.ShowDialog() == DialogResult.Yes)
                    {
                        mPEcrt.mList[e.RowIndex].WSCpnt = formCpntEdit2.mCcrt;
                        FlashdGVPERow(e.RowIndex);
                    }
                    break;
                default:
                    dGVPE.BeginEdit(true);
                    break;
            }
        }
        private void dGVPE_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Insert:
                    InsertEcls(dGVPE.CurrentCell.RowIndex);
                    break;
                case Keys.Delete:
                    List<int> tmpL = new List<int>();
                    foreach (DataGridViewCell feDGVC in dGVPE.SelectedCells)
                    {
                        if (!tmpL.Contains(feDGVC.RowIndex)) { tmpL.Add(feDGVC.RowIndex); }
                    }
                    if (tmpL.Count == mPEcrt.Count) { MessageBox.Show("至少需要一种围护做法。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk); return; }
                    tmpL.Sort();
                    tmpL.Reverse();
                    foreach (int i in tmpL)
                    {
                        mPEcrt.mList.RemoveAt(i);
                    }
                    mPEcrt.mList[0].MinDepth = 0;
                    FlashdGVPE();
                    break;
                default:
                    break;
            }
        }
        private void BTNadd_Click(object sender, EventArgs e)
        {
            InsertEcls();
        }
        private void InsertEcls(int pIdx = -1)
        {
            if (pIdx < 0) { pIdx = mPEcrt.Count; }//默认加在最后
            mPEcrt.mList.Insert(pIdx, new mcEnclosure());
            if (pIdx + 1 == mPEcrt.Count)//如果加在最后一个
            {
                mPEcrt.mList[pIdx].MinDepth = mPEcrt.mList[pIdx - 1].MinDepth + 3.5;
            }
            else if (pIdx == 0) //如果加在第一个
            {
                if (mPEcrt.Count == 2)
                    mPEcrt.mList[1].MinDepth = 3.5;
                else
                    mPEcrt.mList[1].MinDepth = mPEcrt.mList[2].MinDepth / 2.0;
            }
            else //加在中间
            {
                mPEcrt.mList[pIdx].MinDepth = (mPEcrt.mList[pIdx - 1].MinDepth + mPEcrt.mList[pIdx + 1].MinDepth) / 2.0;
            }

            FlashdGVPE();
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            GetDetailFormFm();
            mscCtrl.Set(OrigName, mPEcrt);
            this.Close();
        }
        private void GetDetailFormFm()
        {
            mPEcrt.Name = TXTPEname.Text;
            mPEcrt.Excvt = CBOexcvt.Text;
            mPEcrt.DockL = TXTdock.Text;
            switch (CBOdock.Text)
            {
                case "至管顶50cm":
                    mPEcrt.DockH = TXTdock.Text;
                    mPEcrt.Cover50 = TXTdock.Text;
                    mPEcrt.Cover = TXTcover.Text;
                    break;
                case "至管顶标高":
                    mPEcrt.DockH = TXTdock.Text;
                    mPEcrt.Cover50 = TXTcover.Text;
                    mPEcrt.Cover = TXTcover.Text;
                    break;
                case "至管中心标高":
                    mPEcrt.DockH = TXTcover.Text;
                    mPEcrt.Cover50 = TXTcover.Text;
                    mPEcrt.Cover = TXTcover.Text;
                    break;
                case "至沟槽顶标高":
                    mPEcrt.DockH = TXTdock.Text;
                    mPEcrt.Cover50 = TXTdock.Text;
                    mPEcrt.Cover = TXTdock.Text;
                    break;
                default:
                    break;
            }
            mPEcrt.ConFound = CBOconfound.Text.Contains("不") ? false : true;
            mPEcrt.FoundAngle = Convert.ToInt16(CBOconangle.Text);
            mPEcrt.Cush.Name = TXTcushname.Text;
            mPEcrt.Cush.H = mscMslns.ToDouble(TXTcushH.Text);
        }
        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }
        private void BTNWW_Click(object sender, EventArgs e)
        {
            FormWorkWidth formWW = new FormWorkWidth(mPEcrt.grooveWidth, mPEcrt.WorkWidth, mPEcrt.GrooveB);
            if(formWW.ShowDialog()==DialogResult.Yes)
            {
                mPEcrt.grooveWidth = formWW.GWcrt;
                mPEcrt.WorkWidth = formWW.WWcrt;
                mPEcrt.GrooveB = formWW.GBcrt;
            }
        }
        private void BTNWWpre_Click(object sender, EventArgs e)
        {
            FormPrecipitation formPre = new FormPrecipitation(mPEcrt);
            if (formPre.ShowDialog() == DialogResult.Yes)
            {
                mPEcrt = formPre.mPEcrt;
                LBLpre.Text = mPEcrt.DiscribePreciptitation();
            }
        }

        private void FlashFm()
        {
            FlashDetail();
            FlashdGVPE();
        }
        private void FlashDetail()
        {
            TXTPEname.Text = mPEcrt.Name;
            CBOexcvt.Text = mPEcrt.Excvt;
            TXTdock.Text = mPEcrt.DockL;
            TXTcover.Text = mPEcrt.Cover;
            #region CBOdock.Text = 条件判断
            if (mPEcrt.DockH == mPEcrt.DockL)
                if (mPEcrt.Cover50 == mPEcrt.DockL)
                    if (mPEcrt.Cover == mPEcrt.DockL)
                    {
                        CBOdock.Text = "至沟槽顶标高";
                        TXTcover.Text = "素土";
                    }   
                    else
                        CBOdock.Text = "至管顶50cm";
                else
                    CBOdock.Text = "至管顶标高";
            else
                CBOdock.Text = "至管中心标高";
            #endregion

            CBOconfound.Text = mPEcrt.ConFound == true ? "采用混凝土基础" : "不采用混凝土基础";
            CBOconangle.Text = mPEcrt.FoundAngle.ToString();

            TXTcushname.Text = mPEcrt.Cush.Name;
            TXTcushH.Text = mPEcrt.Cush.H.ToString();

            LBLpre.Text = mPEcrt.DiscribePreciptitation();
        }
        private void FlashdGVPE()
        {
            mscMslns.DGV_RcntAdjust(dGVPE, mPEcrt.Count);
            for (int i = 0; i < mPEcrt.Count; i++)
            {
                FlashdGVPERow(i);
            }
            dGVPE[0, 0].ReadOnly = true;
        }
        private void FlashdGVPERow(int pIdx)
        {
            DataGridViewRow tDGVR = dGVPE.Rows[pIdx];
            mcEnclosure tmEcls = mPEcrt.mList[pIdx];

            tDGVR.Cells["Coldepth"].Value = tmEcls.MinDepth;
            tDGVR.Cells["Colrange"].Value = pIdx + 1 + 1 > mPEcrt.Count ? "+∞" : mPEcrt.mList[pIdx + 1].MinDepth.ToString();
            tDGVR.Cells["ColEclsCat"].Value = tmEcls.ECpntCat;
            tDGVR.Cells["ColEclsDis"].Value = tmEcls.EclsDis();
            tDGVR.Cells["ColWSCat"].Value = tmEcls.WSCpnt.Name;
            tDGVR.Cells["ColWSDis"].Value = tmEcls.WSDis();
        }

        private void FormPE_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                    //FormCancel();
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

        private void dGVPE_CellClick(object sender, DataGridViewCellEventArgs e)
        {
            if (dGVPE.Columns[e.ColumnIndex].GetType().ToString() == "System.Windows.Forms.DataGridViewComboBoxColumn")
                dGVPE.BeginEdit(true);
        }


    }
}

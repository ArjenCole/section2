using section2.mcP;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace section2
{
    public partial class FmPE : Form
    {
        public mcPE oPE = new mcPE();
        public mcPE rtPE = new mcPE();

        public FmPE(mcPE pmPE)
        {
            InitializeComponent();
            iniData(pmPE);
            iniDropItems();
        }
        private void FmPE_Load(object sender, EventArgs e)
        {
            fls_gbPEpara(oPE);
            fls_dgvPE();
        }

        private void dgvPE_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            int rowIdx = e.RowIndex;
            if (e.RowIndex < 0) return;
            string tColName = dgvPE.Columns[e.ColumnIndex].Name;
            var tPEn = rtPE.Son(rowIdx);
            switch (tColName)
            {
                case "eColPEnDis":
                    if (tPEn.Cat() == "多级围护")//mcPEn.StrMultiPEns)//多级围护
                    {/*
                        FormEcls formEcls = new FormEcls(mPEcrt.mList[e.RowIndex]);
                        if (formEcls.ShowDialog() == DialogResult.Yes)
                        {
                            mPEcrt.mList[e.RowIndex] = formEcls.mEclscrt;
                            FlashdGVPERow(e.RowIndex);
                        }*/
                    }
                    else//单级围护
                    {
                        mscVctrl.ShowCpt(tPEn.ListPEns[0].Cpt);
                    }
                    break;
                case "eColSWDis":
                    mscVctrl.ShowCpt(tPEn.StopWater);
                    /*
                    FormCpntEdit formCpntEdit2 = new FormCpntEdit(mPEcrt.mList[e.RowIndex].WSCpnt);
                    if (formCpntEdit2.ShowDialog() == DialogResult.Yes)
                    {
                        mPEcrt.mList[e.RowIndex].WSCpnt = formCpntEdit2.mCcrt;
                        FlashdGVPERow(e.RowIndex);
                    }*/
                    break;
                default:
                    //dGVPE.BeginEdit(true);
                    break;
            }
        }
        private void dgvPE_CellMouseUp(object sender, DataGridViewCellMouseEventArgs e)
        {
            if (e.RowIndex < 0) return;
            if (e.Button == MouseButtons.Right)
            {
                dgvPE.ClearSelection();
                dgvPE[e.ColumnIndex, e.RowIndex].Selected = true;
                cmsDrop.Items.Clear();
                var colIdx = e.ColumnIndex;
                var rowIdx = e.RowIndex;
                string colName = dgvPE.Columns[colIdx].Name;
                cmsDrop.Tag = new Point(rowIdx, colIdx);
                switch (colName)
                {
                    case "eColPEnDis":
                        foreach (string feStr in mscInventory.ListPEnsKeys())
                            cmsDrop.Items.Add(feStr);
                        cmsDrop.Visible = true;
                        break;
                    case "eColSWDis":
                        foreach (string feStr in mscInventory.ListStopWaterKeys())
                            cmsDrop.Items.Add(feStr);
                        cmsDrop.Visible = true;
                        break;
                    default:
                        cmsDrop.Visible = false;
                        break;
                }
            }
        }
        private void cmsDrop_ItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
            var rowIdx = ((Point)cmsDrop.Tag).X;
            var colIdx = ((Point)cmsDrop.Tag).Y;
            string colName = dgvPE.Columns[colIdx].Name;

            string tTxt = e.ClickedItem.Text;
            switch (colName)
            {
                case "eColPEnDis":
                    if (mscInventory.ListPEnsKeys().Contains(tTxt))
                    {
                        mcPEn tmcPEn = new mcPEn(rtPE.Son(rowIdx).DepthStr(), tTxt);
                        dgvPE[colIdx, rowIdx].Value = tmcPEn.Discribe();
                        rtPE.UpdateSon(rowIdx, tmcPEn);
                    }
                    break;
                case "eColSWDis":
                    if (mscInventory.ListStopWaterKeys().Contains(tTxt))
                    {
                        rtPE.Son(rowIdx).SetStopWater(tTxt);
                        dgvPE[colIdx, rowIdx].Value = rtPE.Son(rowIdx).StopWater.Name;
                    }
                    break;
                default:
                    cmsDrop.Visible = false;
                    break;
            }
        }

        private void btnOK_Click(object sender, EventArgs e)
        {
            getPEpara();
            this.DialogResult = DialogResult.OK;
        }
        private void btnCancel_Click(object sender, EventArgs e)
        {
            this.DialogResult = DialogResult.Cancel;
        }
        private void btnAddPEn_Click(object sender, EventArgs e)
        {
            int newDepth = 0;
            int bRowInt = dgvRowIdx(dgvPE);
            int aRowInt = bRowInt - 1;
            if (aRowInt < 0)
            {
                newDepth = rtPE.Sons().Last().DepthInt() + 3000;
            }
            else
            {
                int tDepth = (int)Math.Round((rtPE.Son(bRowInt).DepthInt() + rtPE.Son(aRowInt).DepthInt()) / 2.0, 0);
                if (rtPE.SonKeys().Contains(tDepth.ToString()))
                    newDepth = rtPE.Sons().Last().DepthInt() + 3000;
                else
                    newDepth = tDepth;
            }
            rtPE.Add(new mcPEn(newDepth));
            fls_dgvPE();
        }

        private void iniData(mcPE pmPE)
        {
            oPE = mscTools.DeepClone(pmPE);
            rtPE = mscTools.DeepClone(pmPE);
        }
        private void iniDropItems()
        {
            cboExv.DataSource = mcPE.sExvCat;
            cboDockMat.DataSource = mcPE.sDockPos;
            cboFndMat.DataSource = mcPE.sFndMat;
            cboFndAgl.DataSource = mcPE.sFndAgl;
        }

        private void fls_gbPEpara(mcPE pPE)
        {
            txtPEname.Text = pPE.GetName();
            //gbPEparaDock
            txtCovMat.Text = pPE.CovMat;
            txtCuhMat.Text = pPE.CuhMat;
            txtCuhThk.Text = pPE.CuhThk;
            txtDockMat.Text = pPE.DockMat;
            //gbPEparaFound
            cboDockMat.Text = pPE.DockPos;
            cboExv.Text = pPE.ExvCat;
            cboFndAgl.Text = pPE.FndAgl;
            cboFndMat.Text = pPE.FndMat;
        }
        private void fls_dgvPE()
        {
            int cnt = rtPE.Count();
            mscTools.DgvAdjRowsCnt(dgvPE, cnt);
            for (int i = 0; i < cnt; i++)
                fls_dgvPErow(i);
        }
        private void fls_dgvPErow(int pIdx)
        {
            mcPEn tPEn = rtPE.Son(pIdx);
            DataGridViewRow tDGVR = dgvPE.Rows[pIdx];
            tDGVR.Cells[0].Value = tPEn.DepthDoub().ToString();
            tDGVR.Cells[1].Value = pIdx + 1 == rtPE.Count() ? "+∞" : rtPE.Son(pIdx + 1).DepthDoub().ToString();
            tDGVR.Cells[2].Value = tPEn.Cat();
            tDGVR.Cells[3].Value = tPEn.StopWater.Name;
        }

        private void getPEpara()
        {
            rtPE.SetName(txtPEname.Text);
            //gbPEparaDock
            rtPE.CovMat = txtCovMat.Text;
            rtPE.CuhMat = txtCuhMat.Text;
            rtPE.CuhThk = txtCuhThk.Text;
            rtPE.DockMat = txtDockMat.Text;
            //gbPEparaFound
             rtPE.DockPos = cboDockMat.Text;
             rtPE.ExvCat= cboExv.Text;
             rtPE.FndAgl= cboFndAgl.Text;
             rtPE.FndMat = cboFndMat.Text;
        }

        private int dgvRowIdx(DataGridView pDGV)
        {
            return pDGV.SelectedCells[0].RowIndex;
        }
        
    }
}

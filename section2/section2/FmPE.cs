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

        mcDataGridView dgvPD;
        List<mcDataGridView> dgvPW;

        public FmPE(mcPE pmPE)
        {
            InitializeComponent();
            iniData(pmPE);
            iniDropItems();

            iniDgvPD();
            iniDgvPW();

        }

        private void iniDgvPD()
        {
            Dictionary<string, string> tDic = new Dictionary<string, string>();
            tDic.Add("colDepth", "埋深");
            tDic.Add("colRange", "范围");
            tDic.Add("colPD", "降水方式");
            addmcDgv("dgvPD", tDic, tpPD);
        }
        private void iniDgvPW()
        {
            Dictionary<string, string> tDic = new Dictionary<string, string>();
            tDic.Add("colDepth", "尺寸");
            tDic.Add("colRange", "范围");
            tDic.Add("colWidth", "工作面宽度");
            foreach (TabPage feTP in tcPW.Controls)
                addmcDgv("dgvPW", tDic, feTP);
        }
        private void addmcDgv(string pName, Dictionary<string, string> pDic, Control pC)
        {
            mcDataGridView tDGV = new mcDataGridView(pName, pDic);
            foreach (DataGridViewColumn feDGVC in tDGV.Columns)
            {
                if (feDGVC.HeaderText.Count() > 3)
                    feDGVC.Width = feDGVC.HeaderText.Count() * 40;
                if (feDGVC.Index == 0)
                    feDGVC.ReadOnly = false;
                else
                    feDGVC.ReadOnly = true;
            }
            pC.Controls.Add(tDGV);
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
            mcPEn tPEn = (mcPEn)mscTools.DeepClone(rtPE[rowIdx]);
            switch (tColName)
            {
                case "eColPEnDis":
                    if (tPEn.Cat() == "多级围护")//多级围护
                        tPEn = mscVctrl.EditPEn(tPEn);
                    else//单级围护
                        tPEn.ListPEns[0].Cpt = mscVctrl.EditCpt(tPEn.ListPEns[0].Cpt);
                    break;
                case "eColSWDis":
                    tPEn.StopWater = mscVctrl.EditCpt(tPEn.StopWater);
                    break;
                default:
                    //dGVPE.BeginEdit(true);
                    break;
            }
            rtPE.Update(rowIdx, tPEn);
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
                        foreach (string feStr in mscInventory.ListPEnsKeysAddMult())
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
                    if (tTxt == dgvPE[colIdx, rowIdx].Value.ToString()) break;//如果选中类型与现类型一致，不发生变化
                    mcPEn tPEn = new mcPEn(((mcPEn)rtPE[rowIdx]).DepthStr(), tTxt);
                    if (tTxt.Contains("级围护"))
                        tPEn = mscVctrl.EditPEn(new mcPEn());
                    rtPE.Update(rowIdx, tPEn);
                    fls_dgvPErow(rowIdx, ((mcPEn)rtPE[rowIdx]));
                    break;
                case "eColSWDis":
                    if (tTxt == dgvPE[colIdx, rowIdx].Value.ToString()) break;//如果选中类型与现类型一致，不发生变化
                    if (mscInventory.ListStopWaterKeys().Contains(tTxt))
                    {
                        ((mcPEn)rtPE[rowIdx]).SetStopWater(tTxt);
                        fls_dgvPErow(rowIdx, ((mcPEn)rtPE[rowIdx]));
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
            int tRowIdx = dgvRowIdx(dgvPE);
            rtPE.AddAt(tRowIdx, new mcPEn());
            /*
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
            */
            fls_dgvPE();
        }

        private void iniData(mcPE pmPE)
        {
            oPE = mscTools.DeepClone(pmPE);
            rtPE = mscTools.DeepClone(pmPE);
        }
        private void iniDropItems()
        {
            cboExv.DataSource = mcPB.sExvCat;
            cboDockMat.DataSource = mcPB.sDockPos;
            cboFndMat.DataSource = mcPB.sFndMat;
            cboFndAgl.DataSource = mcPB.sFndAgl;
        }

        private void fls_gbPEpara(mcPE pPE)
        {
            txtPEname.Text = pPE.GetName();
            //gbPEparaDock
            txtCovMat.Text = pPE.PB.CovMat;
            txtCuhMat.Text = pPE.PB.CuhMat;
            txtCuhThk.Text = pPE.PB.CuhThk;
            txtDockMat.Text = pPE.PB.DockMat;
            //gbPEparaFound
            cboDockMat.Text = pPE.PB.DockPos;
            cboExv.Text = pPE.PB.ExvCat;
            cboFndAgl.Text = pPE.PB.FndAgl;
            cboFndMat.Text = pPE.PB.FndMat;
        }
        private void fls_dgvPE()
        {
            int cnt = rtPE.Count();
            mscTools.DgvAdjRowsCnt(dgvPE, cnt);
            for (int i = 0; i < cnt; i++)
                fls_dgvPErow(i, (mcPEn)rtPE[i]);
        }
        private void fls_dgvPErow(int pIdx,IdgvTxt pDgvTxt)
        {
            DataGridViewRow tDGVR = dgvPE.Rows[pIdx];
            string[] tStrs = pDgvTxt.GetDgvTxt();

            for (int i = 0; i < tStrs.Count(); i++)
                tDGVR.Cells[i].Value = tStrs[i];
            if (pIdx > 0) dgvPE.Rows[pIdx - 1].Cells[1].Value = tStrs[0];
        }

        private void getPEpara()
        {
            rtPE.SetName(txtPEname.Text);
            //gbPEparaDock
            rtPE.PB.CovMat = txtCovMat.Text;
            rtPE.PB.CuhMat = txtCuhMat.Text;
            rtPE.PB.CuhThk = txtCuhThk.Text;
            rtPE.PB.DockMat = txtDockMat.Text;
            //gbPEparaFound
            rtPE.PB.DockPos = cboDockMat.Text;
            rtPE.PB.ExvCat = cboExv.Text;
            rtPE.PB.FndAgl = cboFndAgl.Text;
            rtPE.PB.FndMat = cboFndMat.Text;
        }

        private int dgvRowIdx(DataGridView pDGV)
        {
            return pDGV.SelectedCells[0].RowIndex;
        }

        private void dgvPE_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            if (((DataGridView)sender).Columns[e.ColumnIndex].Name.EndsWith("depth"))
            {
                var t = 1;
            }
        }
    }
}

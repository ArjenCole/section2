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
    public partial class FmPEn : Form
    {
        public mcPEn oPEn = new mcPEn();
        public mcPEn rtPEn = new mcPEn();

        public FmPEn(mcPEn pPEn)
        {
            InitializeComponent();
            iniData(pPEn);
        }

        private void FmPEn_Load(object sender, EventArgs e)
        {
            fls_dgvPEn();
        }

        private void fls_dgvPEn()
        {
            int cnt = rtPEn.Count();
            mscTools.DgvAdjRowsCnt(dgvPEn, cnt);
            for (int i = 0; i < cnt; i++)
                fls_dgvPErow(i);
        }
        private void fls_dgvPErow(int pIdx)
        {
            mcPEns tPEns = rtPEn.ListPEns[pIdx];
            DataGridViewRow tDGVR = dgvPEn.Rows[pIdx];
            tDGVR.Cells[0].Value = tPEns.Height < 0 ? false : true;
            tDGVR.Cells[1].Value = tPEns.Height < 0 ? "均分" : tPEns.Height.ToString();
            tDGVR.Cells[1].ReadOnly = tPEns.Height < 0 ? true : false;
            tDGVR.Cells[2].Value = tPEns.Width;
            tDGVR.Cells[3].Value = tPEns.Cpt.GetName();
        }

        private void iniData(mcPEn pPEn)
        {
            oPEn = mscTools.DeepClone(pPEn);
            rtPEn = mscTools.DeepClone(pPEn);
        }

        private void dgvPEn_CellValueChanged(object sender, DataGridViewCellEventArgs e)
        {

        }

        private void dgvPEn_CellContentClick(object sender, DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0) return;
            mcPEns tPEns = rtPEn.ListPEns[e.RowIndex];
            if (e.ColumnIndex == 0)
            {
                var tCellCheck = dgvPEn.Rows[e.RowIndex].Cells[0];
                var tCellH = dgvPEn.Rows[e.RowIndex].Cells[1];
                if (!bool.Parse(tCellCheck.Value.ToString()))//点击时，值尚未改变
                    tPEns.Height = 1;
                else
                    tPEns.Height = -1;
                fls_dgvPErow(e.RowIndex);
            }
        }

        private void btnAddPEn_Click(object sender, EventArgs e)
        {
            rtPEn.ListPEns.Add(new mcPEns());
            fls_dgvPEn();
        }

        private void dgvPEn_CellMouseUp(object sender, DataGridViewCellMouseEventArgs e)
        {
            if (e.RowIndex < 0) return;
            if (e.Button == MouseButtons.Right)
            {
                dgvPEn.ClearSelection();
                dgvPEn[e.ColumnIndex, e.RowIndex].Selected = true;
                cmsDrop.Items.Clear();
                var colIdx = e.ColumnIndex;
                var rowIdx = e.RowIndex;
                string colName = dgvPEn.Columns[colIdx].Name;
                cmsDrop.Tag = new Point(rowIdx, colIdx);
                switch (colName)
                {
                    case "eColPEnDis":
                        foreach (string feStr in mscInventory.ListPEnsKeys())
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
            string colName = dgvPEn.Columns[colIdx].Name;

            string tTxt = e.ClickedItem.Text;
            switch (colName)
            {
                case "eColPEnDis":
                    if (tTxt == dgvPEn[colIdx, rowIdx].Value.ToString()) break;//如果选中类型与现类型一致，不发生变化
                    rtPEn.ListPEns[rowIdx] = new mcP.mcPEns(tTxt);
                    fls_dgvPErow(rowIdx);
                    break;
                default:
                    cmsDrop.Visible = false;
                    break;
            }
        }

        private void dgvPEn_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            int rowIdx = e.RowIndex;
            if (e.RowIndex < 0) return;
            string tColName = dgvPEn.Columns[e.ColumnIndex].Name;
            var tPEns = rtPEn.ListPEns[rowIdx];
            switch (tColName)
            {
                case "eColPEnDis":
                    tPEns.Cpt = mscVctrl.EditCpt(tPEns.Cpt);
                    break;

                default:
                    //dGVPE.BeginEdit(true);
                    break;
            }
        }

        private void getPara()
        {
            for (int i = 0; i < rtPEn.Count(); i++)
            {
                if (bool.Parse(dgvPEn.Rows[i].Cells[0].Value.ToString()))
                    rtPEn.ListPEns[i].Height = int.Parse(dgvPEn.Rows[i].Cells[1].Value.ToString());
                else
                    rtPEn.ListPEns[i].Height = -1;
                rtPEn.ListPEns[i].Width = int.Parse(dgvPEn.Rows[i].Cells[2].Value.ToString());
            }
        }

        private void btnOK_Click(object sender, EventArgs e)
        {
            getPara();
            this.DialogResult = DialogResult.OK;
        }

        private void btnCancel_Click(object sender, EventArgs e)
        {
            this.DialogResult = DialogResult.Cancel;
        }
    }
}

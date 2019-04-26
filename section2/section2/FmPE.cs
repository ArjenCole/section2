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
        public mcPE resultPE = new mcPE();

        public FmPE(mcPE pmPE)
        {
            InitializeComponent();
            oPE = mscTools.DeepClone(pmPE);
            resultPE = mscTools.DeepClone(pmPE);

            initDropItems();
        }

        private void FmPE_Load(object sender, EventArgs e)
        {
            initShowPEpara();
            flashdgvPE();
        }

        private void dgvPE_CellClick(object sender, DataGridViewCellEventArgs e)
        {
            if (dgvPE.Columns[e.ColumnIndex].GetType().ToString() == "System.Windows.Forms.DataGridViewComboBoxColumn")
                dgvPE.BeginEdit(true);
        }

        private void dgvPE_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            int rowIdx = e.RowIndex;
            if (e.RowIndex < 0) return;
            string tColName = dgvPE.Columns[e.ColumnIndex].Name;
            var tPEn = resultPE.Son(rowIdx);
            switch (tColName)
            {
                case "eColPEnCat":
                    if (tPEn.Cat() == mcPEn.StrMultiPEns)//多级围护
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
                case "ColWSDis":/*
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

        private void initDropItems()
        {
            cboExv.DataSource = mcPE.sExvCat;
            cboDockMat.DataSource = mcPE.sDockPos;
            cboFndMat.DataSource = mcPE.sFndMat;
            cboFndAgl.DataSource = mcPE.sFndAgl;

            eColPEnCat.DataSource = mscInventory.ListPEnsKeys();
        }

        private void initShowPEpara()
        {
            txtPEname.Text = oPE.GetName();
            txtCovMat.Text = oPE.CovMat;
            txtCuhMat.Text = oPE.CuhMat;
            txtCuhThk.Text = oPE.CuhThk;
            txtDockMat.Text = oPE.DockMat;
            cboDockMat.Text = oPE.DockPos;
            cboExv.Text = oPE.ExvCat;
            cboFndAgl.Text = oPE.FndAgl;
            cboFndMat.Text = oPE.FndMat;
        }

        private void flashdgvPE()
        {
            dgvPE.Rows.Add(resultPE.Count);
            int i = 0;
            foreach(var fePEn in resultPE.Sons())
            {
                DataGridViewRow tDGVR = dgvPE.Rows[i];
                tDGVR.Cells[0].Value = fePEn.Depth.ToString();
                tDGVR.Cells[1].Value = fePEn.Depth.ToString();
                tDGVR.Cells[2].Value = fePEn.Cat();
                tDGVR.Cells[3].Value = fePEn.Discribe();

            }
        }

    }
}

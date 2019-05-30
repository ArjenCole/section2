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
            if (e.RowIndex < 0) return;
            mcPEns tPEns = rtPEn.ListPEns[e.RowIndex];
            if (e.ColumnIndex == 0)
            {
                var tCellCheck = dgvPEn.Rows[e.RowIndex].Cells[0];
                var tCellH = dgvPEn.Rows[e.RowIndex].Cells[1];
                if (bool.Parse(tCellCheck.Value.ToString()))
                    tPEns.Height = 1;
                else
                    tPEns.Height = -1;
                fls_dgvPErow(e.RowIndex);
            }
        }
    }
}

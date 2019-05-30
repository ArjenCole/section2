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
            tDGVR.Cells[0].Value = tPEns.Height < 0 ? true : false;
            tDGVR.Cells[1].Value = tPEns.Height;
            tDGVR.Cells[2].Value = tPEns.Width;
            tDGVR.Cells[3].Value = tPEns.Cpt.GetName();
        }

        private void iniData(mcPEn pPEn)
        {
            oPEn = mscTools.DeepClone(pPEn);
            rtPEn = mscTools.DeepClone(pPEn);
        }
    }
}

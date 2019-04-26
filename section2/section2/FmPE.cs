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
            resultPE = pmPE;

            initDropItems();
        }

        private void FmPE_Load(object sender, EventArgs e)
        {
            initShowPEpara();

        }

        private void initDropItems()
        {
            cboExv.DataSource = mcPE.sExvCat;
            cboDockMat.DataSource = mcPE.sDockPos;
            cboFndMat.DataSource = mcPE.sFndMat;
            cboFndAgl.DataSource = mcPE.sFndAgl;
        }
        private void initShowPEpara()
        {
            txtPEname.Text = oPE.Name();
            txtCovMat.Text = oPE.CovMat;
            txtCuhMat.Text = oPE.CuhMat;
            txtCuhThk.Text = oPE.CuhThk;
            txtDockMat.Text = oPE.DockMat;
            cboDockMat.Text = oPE.DockPos;
            cboExv.Text = oPE.ExvCat;
            cboFndAgl.Text = oPE.FndAgl;
            cboFndMat.Text = oPE.FndMat;
        }

    }
}

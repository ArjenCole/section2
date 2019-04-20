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

            initShowPEpara();
            initDropItems();
        }
        private void initShowPEpara()
        {

        }
        private void initDropItems()
        {
            cboExv.DataSource = new[] { "Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石" };
            cboDock.DataSource = new[] { "至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高" };
            cboConfound.DataSource = new[] { "采用混凝土基础", "不采用混凝土基础" };
            cboConangle.DataSource = new[] { "90", "120", "150", "180" };
        }
    }
}

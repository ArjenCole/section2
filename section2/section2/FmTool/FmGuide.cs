using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace section2.FmTool
{
    public partial class FmGuide : Form
    {
        public string ProjectName;
        public string ProjectIndex;
        public string Designer;
        public List<string> Cat;
        public int SegmentCount;

        public FmGuide()
        {
            InitializeComponent();
        }

        private void BTNok_Click(object sender, EventArgs e)
        {

        }
    }
}

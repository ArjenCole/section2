﻿using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace section2
{
    public partial class FmMain : Form
    {
        public FmMain()
        {
            InitializeComponent();
            mscCtrl.LoadFinished = true;
        }

        private void 新建ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.NewFileFromGuide();
        }
    }
}

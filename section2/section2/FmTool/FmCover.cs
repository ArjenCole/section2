using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace section2.FmTool
{
    public partial class FmCover : Form
    {
        public FmCover()
        {
            InitializeComponent();
        }

        private void TMdetective_Tick(object sender, EventArgs e)
        {
            this.Text = this.Opacity.ToString();
            if (mscVctrl.LoadFinished)
            {
                this.Opacity -= 0.04;
                if (this.Opacity <= 0)
                {
                    this.Close();
                }
            }
            else
            {
                this.Opacity += 0.10;
                if (this.Opacity >= 1)
                {
                    Thread.Sleep(1000);
                }
            }
        }
    }
}

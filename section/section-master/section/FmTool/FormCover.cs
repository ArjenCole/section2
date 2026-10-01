using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace section
{
    public partial class FormCover : Form
    {
        private bool show100 = false;

        public FormCover()
        {
            InitializeComponent();

            AddLBL();
        }
        private void AddLBL()
        {
            Label LBLemail = NewLBL("jinhesky@hotmail.com", this.Width - 50, this.Height - 20);
            Label LBLauthor = NewLBL("JinHe , 2017.06 ", this.Width - 50, this.Height - 35);
            Label LBLversion = NewLBL(System.Reflection.Assembly.GetExecutingAssembly().GetName().Version.ToString() + "\n",
                                        this.Width - 50, this.Height - 50);
        }

        private Label NewLBL(string pText, int pX, int pY)
        {
            Label rtLBL = new Label();
            rtLBL.Text = pText;
            rtLBL.BackColor = Color.Transparent;
            rtLBL.ForeColor = Color.AliceBlue;
            rtLBL.Font = new Font("微软雅黑", 9);
            rtLBL.Parent = this;
            rtLBL.Left = pX - rtLBL.Width;
            rtLBL.Top = pY - rtLBL.Height;
            rtLBL.AutoSize = true;
            return rtLBL;
        }

        private void timer1_Tick(object sender, EventArgs e)
        {
            if (mscCtrl.Th_CompleteOpen && this.show100)
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
                    this.show100 = true;
                    Thread.Sleep(1000);
                }
            }
                
        }
    }
}

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace section
{
    public partial class FormWait : Form
    {
        public bool Cancel = false;
        private string message;
        private int pointCnt = 0;

        public FormWait(string pMessage)
        {
            InitializeComponent();
            message = pMessage;
            LBLmessage.Text = pMessage;
        }

        private void BTNcancel_Click(object sender, EventArgs e)
        {
            Cancel = true;
            this.Close();
        }

        private void timer1_Tick(object sender, EventArgs e)
        {
            pointCnt = (pointCnt + 1) % 4;
            LBLmessage.Text = message + new string('.', pointCnt);
            //if (mscCtrl.Th_CompleteWait)
            //    this.Close();
        }
    }
}

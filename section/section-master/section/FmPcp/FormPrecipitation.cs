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
    public partial class FormPrecipitation : Form
    {
        public mcPcpEnclosure mPEcrt;
        public FormPrecipitation(mcPcpEnclosure pmPE)
        {
            mPEcrt = mscMslns.DeepClone(pmPE);
            InitializeComponent();
            dGVPre.Rows.Add(5);
            SetdGVPreRow("湿土排水", 0, mPEcrt.wetsoild);
            SetdGVPreRow("轻型井点", 1, mPEcrt.lightwell);
            SetdGVPreRow("喷射井点", 2, mPEcrt.jetwell);
            SetdGVPreRow("大口径井点", 3, mPEcrt.bigwell);
            SetdGVPreRow("深井", 4, mPEcrt.deepwell);
            FlashFm();
        }
        private void dGVPre_CellContentClick(object sender, DataGridViewCellEventArgs e)
        {
            switch (dGVPre.Columns[e.ColumnIndex].Name)
            {
                case "ColCheck":
                    dGVPre.CurrentCell.Value = !Convert.ToBoolean(dGVPre.CurrentCell.Value);
                    FlashFm();
                    break;
                default:
                    break;
            }
        }
        private void dGVPre_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            FlashFm();
        }

        private void SetdGVPreRow(string pName, int pIdx, mcPrecipitation pmPre)
        {
            dGVPre.Rows[pIdx].HeaderCell.Value = pName;
            if (pmPre.elevation >= 0)
            {
                dGVPre[0, pIdx].Value = true;
                dGVPre[1, pIdx].Value = pmPre.elevation;
                dGVPre[1, pIdx].ReadOnly = false;
            }
            else
            {
                dGVPre[0, pIdx].Value = false;
                dGVPre[1, pIdx].ReadOnly = true;
            }
            dGVPre[3, pIdx].Value = pmPre.sides;
            dGVPre[4, pIdx].Value = pmPre.gap;
        }
        private void FlashFm()
        {
            string currentS = "+∞";
            for (int i = 4; i >= 0; i--)
            {
                if (Convert.ToBoolean(dGVPre[0, i].Value))
                {
                    dGVPre[2, i].Value = currentS;
                    dGVPre[1, i].ReadOnly = false;
                    if (mscMslns.ToString(dGVPre[1, i].Value) == "-") { dGVPre[1, i].Value = "0"; }
                    currentS = mscMslns.ToString(dGVPre[1, i].Value);
                }
                else
                {
                    dGVPre[1, i].Value = "-";
                    dGVPre[1, i].ReadOnly = true;
                    dGVPre[2, i].Value = "-";
                }
            }
            GetDataFromFm();
            LBLpre.Text = mPEcrt.DiscribePreciptitation();
        }
        private void GetDataFromFm()
        {
            //double tDouble = mscMslns.ToString(dGVPre[1, 0].Value) != "-" ? mscMslns.ToDouble(dGVPre[1, 0].Value) : -1;
            mPEcrt.wetsoild = new mcPrecipitation("wetsoild", dGVPre[1, 0].Value, dGVPre[4, 0].Value, dGVPre[3, 0].Value);
            //mPEcrt.lightwell.elevation = mscMslns.ToString(dGVPre[1, 1].Value) != "-" ? mscMslns.ToDouble(dGVPre[1, 1].Value) : -1;
            mPEcrt.lightwell = new mcPrecipitation("lightwell", dGVPre[1, 1].Value, dGVPre[4, 1].Value, dGVPre[3, 1].Value);
            //mPEcrt.jetwell.elevation = mscMslns.ToString(dGVPre[1, 2].Value) != "-" ? mscMslns.ToDouble(dGVPre[1, 2].Value) : -1;
            mPEcrt.jetwell = new mcPrecipitation("jetwell", dGVPre[1, 2].Value, dGVPre[4, 2].Value, dGVPre[3, 2].Value);
            //mPEcrt.bigwell.elevation = mscMslns.ToString(dGVPre[1, 3].Value) != "-" ? mscMslns.ToDouble(dGVPre[1, 3].Value) : -1;
            mPEcrt.bigwell = new mcPrecipitation("bigwell", dGVPre[1, 3].Value, dGVPre[4, 3].Value, dGVPre[3, 3].Value);
            //mPEcrt.deepwell.elevation = mscMslns.ToString(dGVPre[1, 4].Value) != "-" ? mscMslns.ToDouble(dGVPre[1, 4].Value) : -1;
            mPEcrt.deepwell = new mcPrecipitation("deepwell", dGVPre[1, 4].Value, dGVPre[4, 4].Value, dGVPre[3, 4].Value);
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            if (!CheckDepth())
            {
                MessageBox.Show("存在逆序埋深序列。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
            }
            else
            {
                DialogResult = DialogResult.Yes;
                this.Close();
            }

        }

        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }

        private bool CheckDepth()
        {
            double tdouble = -1;
            for (int i = 1; i < 5; i++)
            {
                if (mscMslns.ToString(dGVPre[1, i].Value) == "-") { continue; }
                if (mscMslns.ToDouble(dGVPre[1, i].Value) <= tdouble)
                    return false;
                tdouble = mscMslns.ToDouble(dGVPre[1, i].Value);
            }
            return true;
        }

        private void FormPrecipitation_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                    FormCancel();
                    break;
                default:
                    break;
            }
        }
        private void FormCancel()
        {
            DialogResult = DialogResult.Cancel;
            this.Close();
        }
    }
}

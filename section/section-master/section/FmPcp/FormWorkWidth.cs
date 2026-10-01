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
    public partial class FormWorkWidth : Form
    {

        public mcPcpEnclosure.GrooveWidth GWcrt = mcPcpEnclosure.GrooveWidth.WorkWidth;
        public Dictionary<string, Dictionary<int, double>> WWcrt = new Dictionary<string, Dictionary<int, double>>();
        public Dictionary<string, Dictionary<int, double>> GBcrt = new Dictionary<string, Dictionary<int, double>>();
        

        public FormWorkWidth(mcPcpEnclosure.GrooveWidth pGW,Dictionary<string,Dictionary<int,double>> pWorkWidth, Dictionary<string, Dictionary<int, double>> pGrooveB)
        {
            GWcrt = mscMslns.DeepClone(pGW);
            WWcrt = mscMslns.DeepClone(pWorkWidth);
            GBcrt = mscMslns.DeepClone(pGrooveB);

            InitializeComponent();
            #region  利用反射机制修改dGV的Protected的DoubleBuffered属性 避免闪烁
            dGVWW.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(dGVWW, true, null);
            dGVGB.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(dGVGB, true, null);
            #endregion

            dGVWW.Dock = DockStyle.Bottom; dGVGB.Dock = DockStyle.Bottom;
            for (int i = 0; i <= 30; i++)
            {
                dGVWW.Columns.Add("DN" + mscMslns.ToString(i * 100), "DN" + mscMslns.ToString(i * 100));
                dGVWW.Columns[i].Width = 50;
                dGVGB.Columns.Add("DN" + mscMslns.ToString(i * 100), "DN" + mscMslns.ToString(i * 100));
                dGVGB.Columns[i].Width = 50;
            }
            FlashdGV(dGVWW, WWcrt);
            FlashdGV(dGVGB, GBcrt);
            if (pGW == mcPcpEnclosure.GrooveWidth.WorkWidth)
                RBWW.Checked = true;
            else
                RBGB.Checked = true;
        }
        private void FlashdGV(DataGridView pDGV, Dictionary<string, Dictionary<int, double>> pSheet)
        {
            pDGV.Rows.Clear();
            foreach (string feStr in pSheet.Keys)
            {
                pDGV.Rows.Add();
                DataGridViewRow NewRow = pDGV.Rows[pDGV.Rows.Count - 1];
                NewRow.HeaderCell.Value = feStr;
                foreach (int feInt in pSheet[feStr].Keys)
                {
                    NewRow.Cells["DN" + mscMslns.ToString(feInt)].Value = pSheet[feStr][feInt];

                }
            }
        }

        private void BTNreset_Click(object sender, EventArgs e)
        {
            WWcrt = mscMslns.DeepClone(mscInventory.WorkWidth);
            GBcrt = mscMslns.DeepClone(mscInventory.GrooveB);
            RBWW.Checked = true;
            FlashdGV(dGVWW, WWcrt);
            FlashdGV(dGVGB, GBcrt);
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            DialogResult = DialogResult.Yes;
            this.Close();
        }

        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }

        private void dGVWW_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            string RowName = mscMslns.ToString(dGVWW.Rows[e.RowIndex].HeaderCell.Value);
            int Col = e.ColumnIndex * 100;
            WWcrt[RowName][Col] = mscMslns.ToDouble(dGVWW[e.ColumnIndex, e.RowIndex].Value);
        }

        private void dGVGB_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            string RowName = mscMslns.ToString(dGVGB.Rows[e.RowIndex].HeaderCell.Value);
            int Col = e.ColumnIndex * 100;
            GBcrt[RowName][Col] = mscMslns.ToDouble(dGVGB[e.ColumnIndex, e.RowIndex].Value);

        }

        private void RBWW_CheckedChanged(object sender, EventArgs e)
        {
            dGVWW.Visible = RBWW.Checked;
            dGVGB.Visible = !RBWW.Checked;
            checkGWcrt();
        }

        private void RBGB_CheckedChanged(object sender, EventArgs e)
        {
            dGVGB.Visible = RBGB.Checked;
            dGVWW.Visible = !RBGB.Checked;
            checkGWcrt();
        }
        private void checkGWcrt()
        {
            if (RBWW.Checked)
                GWcrt = mcPcpEnclosure.GrooveWidth.WorkWidth;
            else
                GWcrt = mcPcpEnclosure.GrooveWidth.B;
        }

        private void FormWorkWidth_KeyUp(object sender, KeyEventArgs e)
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

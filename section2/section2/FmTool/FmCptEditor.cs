using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using section2.mcData;

namespace section2.FmTool
{
    public partial class FmCptEditor : Form
    {
        public mcCpt omC;
        public mcCpt rtmC;
        public FmCptEditor(mcCpt pmC)
        {
            InitializeComponent();
            omC = mscTools.DeepClone(pmC);
            rtmC = mscTools.DeepClone(pmC);
            showCpt();
        }

        private void showCpt()
        {
            showQs(dgvPara, omC.mDic.Values);
            showQs(dgvExp, omC.Qlist);
        }
        private void showQs(DataGridView pDGV, IEnumerable<mcExp> pmcQs)
        {
            int cnt = pmcQs.Count();
            if (cnt == 0) return;
            pDGV.Rows.Add(cnt);
            int i = 0;
            foreach (var fe in pmcQs)
            {
                DataGridViewRow tRow = pDGV.Rows[i];
                tRow.Cells[0].Value = fe.Cat;
                tRow.Cells[1].Value = fe.Name;
                tRow.Cells[2].Value = fe.Unit;
                tRow.Cells[3].Value = fe.Exp;
                i++;
            }
        }

        private List<mcExp> getQs(DataGridView pDGV)
        {
            List<mcExp> rtList = new List<mcData.mcExp>();
            foreach (DataGridViewRow feRow in pDGV.Rows)
            {
                mcExp tmQ = new mcData.mcExp();
                tmQ.Cat = feRow.Cells[0].Value.ToString();
                tmQ.Name = feRow.Cells[1].Value.ToString();
                tmQ.Unit = feRow.Cells[2].Value.ToString();
                tmQ.Exp = feRow.Cells[3].Value.ToString();
                rtList.Add(tmQ);
            }
            return rtList;
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            List<mcExp> tListQ = getQs(dgvPara);
            rtmC.mDic.Clear();
            foreach (mcExp femQ in tListQ)
                rtmC.Add(femQ);
            rtmC.Qlist = getQs(dgvExp);
            this.DialogResult = DialogResult.OK;
        }

        private void BTNcancel_Click(object sender, EventArgs e)
        {
            this.DialogResult = DialogResult.Cancel;
        }
    }
}

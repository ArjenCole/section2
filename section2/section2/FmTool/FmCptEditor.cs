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
        private mcCpt omC;
        public mcCpt rtmC;
        public FmCptEditor(mcCpt pmC)
        {
            InitializeComponent();
            omC = mscTools.DeepClone(pmC);
            showCpt();
        }

        private void showCpt()
        {
            showQs(dgvPara, omC.mDic.Values);
            showQs(dgvExp, omC.Qlist);
        }
        private void showQs(DataGridView pDGV, IEnumerable<mcQ> pmcQs)
        {
            pDGV.Rows.Add(pmcQs.Count());
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
    }
}

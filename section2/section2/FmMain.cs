using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using section2.mcStruct;
using section2.mcData;

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
            mcDC tDC = mscCtrl.NewFileFromGuide();
            flashTVdc(tDC);
            flashPcpTab();
        }
        private void TVdc_NodeMouseClick(object sender, TreeNodeMouseClickEventArgs e)
        {

        }


        private void flashTVdc(mcDC pDC)
        {
            TreeNode ActiveNode = null;
            TVdc.Nodes.Clear();
            if (pDC == null) { return; }
            TreeNode NodeProject = new TreeNode(pDC.BI.ProjectName, 1, 2);//一级节点
            foreach (mcSG feSG in pDC.Sons()) 
            {
                TreeNode NodeSegment = new TreeNode(feSG.Name());
                foreach (mcUN feUN in feSG.Sons())
                {
                    TreeNode NodeUnit = new TreeNode(feUN.Name());
                    NodeSegment.Nodes.Add(NodeUnit);
                    /*if ((ActiveFormUnit != null) && (ActiveFormUnit.OwnerName == feSG.Name) && (ActiveFormUnit.mUName == feUN.Name))
                        ActiveNode = NodeUnit;*/
                }
                NodeProject.Nodes.Add(NodeSegment);
            }
            TVdc.Nodes.Add(NodeProject);
            TVdc.ExpandAll();
            if (ActiveNode != null)
                TVdc.SelectedNode = ActiveNode;
        }
        private void flashPcpTab()
        {
            TLPmPE.Controls.Clear();
            TLPmPF.Controls.Clear();
            if (mscCtrl.getDC() == null) { RBmPE.Checked = true; RBmPD.Checked = true; SCpcpHigh.Enabled = false; SCpcpLow.Visible = false; return; }
            SCpcpHigh.Enabled = true; SCpcpHigh.Visible = true;
            SCpcpLow.Enabled = true; SCpcpLow.Visible = true;

            foreach (string feKey in mscCtrl.getPEdic().mDic.Keys)
                TLPmPE.Controls.Add(NewPrincpleLab("围护", feKey));
            foreach (string feKey in mscCtrl.getPFdic().mDic.Keys)
                TLPmPF.Controls.Add(NewPrincpleLab("地基", feKey));
            //TODO：此处需要添加字典匹配类型和颜色，并且添加降水、工作面对应内容
        }
        private Label NewPrincpleLab(string para_str_cat, string para_str_name)
        {

            Label lab = new Label();
            lab.Text = para_str_name;
            lab.Width = 200; lab.Height = 40;
            //通过Anchor 设置Label 列中居中
            lab.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom)));
            lab.ForeColor = ColorTranslator.FromHtml("#FFFFFF");
            if (para_str_cat == "围护")
                lab.BackColor = ColorTranslator.FromHtml("#448AFF");
            else
                lab.BackColor = ColorTranslator.FromHtml("#455A64");
            lab.Font = new System.Drawing.Font("微软雅黑", 14.25F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            lab.TextAlign = ContentAlignment.MiddleCenter;
            lab.DoubleClick += new EventHandler(PrincpleLab_DoubleClick);
            lab.MouseUp += new MouseEventHandler(PrincpleLab_MouseUp);
            return lab;
        }
        private void PrincpleLab_DoubleClick(object sender, EventArgs e)
        {
            //ShowPEPF(((Label)sender).Text);
        }
        private void PrincpleLab_MouseUp(object sender, MouseEventArgs e)
        {
            /*
            if (e.Button == MouseButtons.Right)
            {
                Point ClickPoint = new Point(e.X, e.Y);
                CMSpcp.Text = ((Label)sender).Text;
                CMSpcp.Show((Control)sender, ClickPoint);
            }
            FormUnitEndEdit();*/
        }

        private void flashDGVunit(string pSGname,string pUNname)
        {
            mcUN tUN = mscCtrl.getUN(pSGname, pUNname);

        }

        private void FmMain_Load(object sender, EventArgs e)
        {

        }

        private void BTNpcpAddHigh_Click(object sender, EventArgs e)
        {

        }

        private void RBmP_CheckedChanged(object sender, EventArgs e)
        {
            TLPmPE.Visible = false;
            TLPmPF.Visible = false;
            TLPmPD.Visible = false;
            TLPmPW.Visible = false;
            switch (((RadioButton)sender).Name)
            {
                case "RBmPE":
                    TLPmPE.Visible = true;
                    break;
                case "RBmPF":
                    TLPmPF.Visible = true;
                    break;
                case "RBmPD":
                    TLPmPD.Visible = true;
                    break;
                case "RBmPW":
                    TLPmPW.Visible = true;
                    break;
            }
        }
    }
}

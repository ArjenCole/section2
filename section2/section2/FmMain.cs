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
            mscVctrl.LoadFinished = true;
        }
        private void FmMain_Load(object sender, EventArgs e)
        {

        }

        private void BTNpcpAddHigh_Click(object sender, EventArgs e)
        {

        }

        private void RBmP_CheckedChanged(object sender, EventArgs e)
        {
            TLPmPE.Visible = RBmPE.Checked;
            TLPmPF.Visible = RBmPF.Checked;
            TLPmPD.Visible = RBmPD.Checked;
            TLPmPW.Visible = RBmPW.Checked;
        }

        private void 新建ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscVctrl.NewFileFromGuide();
            flashTVdc();
            flashPcpTab();
        }

        private void TVdc_NodeMouseClick(object sender, TreeNodeMouseClickEventArgs e)
        {
            switch (nodeType(e.Node))
            {
                case eNodeType.Null:
                    break;
                case eNodeType.DC:
                    break;
                case eNodeType.SG:
                    break;
                case eNodeType.UN:
                    break;
                case eNodeType.Other:
                    break;
                default:
                    break;
            }
        }

        private void initFlashPcpTab()
        {

        }

        private void flashTVdc()
        {
            TreeNode ActiveNode = null;
            TVdc.Nodes.Clear();
            mcDC tDC = mscDC.getDC();
            if (tDC == null) { return; }
            TreeNode NodeDC = new TreeNode(tDC.BI.ProjectName, 1, 2);//一级节点
            foreach (mcSG feSG in tDC.Sons()) 
            {
                TreeNode NodeSG = new TreeNode(feSG.Name());
                foreach (mcUN feUN in feSG.Sons())
                {
                    TreeNode NodeUN = new TreeNode(feUN.Name());
                    NodeSG.Nodes.Add(NodeUN);
                    /*if ((ActiveFormUnit != null) && (ActiveFormUnit.OwnerName == feSG.Name) && (ActiveFormUnit.mUName == feUN.Name))
                        ActiveNode = NodeUnit;*/
                }
                NodeDC.Nodes.Add(NodeSG);
            }
            TVdc.Nodes.Add(NodeDC);
            TVdc.ExpandAll();
            if (ActiveNode != null)
                TVdc.SelectedNode = ActiveNode;
        }

        private void flashPcpTab()
        {
            TLPmPE.Controls.Clear();
            TLPmPF.Controls.Clear();
            if (mscDC.getDC() == null) { RBmPE.Checked = true; RBmPD.Checked = true; SCpcpHigh.Enabled = false; SCpcpLow.Visible = false; return; }
            SCpcpHigh.Enabled = true; SCpcpHigh.Visible = true;
            SCpcpLow.Enabled = true; SCpcpLow.Visible = true;

            foreach (string feKey in mscDC.getPEdic().mDic.Keys)
                TLPmPE.Controls.Add(newPcpLab("围护", feKey));
            foreach (string feKey in mscDC.getPFdic().mDic.Keys)
                TLPmPF.Controls.Add(newPcpLab("地基", feKey));
            foreach (string feKey in mscDC.getPDdic().mDic.Keys)
                TLPmPD.Controls.Add(newPcpLab("降水", feKey));
            foreach (string feKey in mscDC.getPWdic().mDic.Keys)
                TLPmPW.Controls.Add(newPcpLab("工作面", feKey));
        }
        #region 原则标签框生成
        private Label newPcpLab(string pCat, string pName)
        {
            Dictionary<string, Color> pcpColor = new Dictionary<string, Color>
            {
                { "围护",ColorTranslator.FromHtml("#448AFF") },
                { "地基",ColorTranslator.FromHtml("#455A64") },
                { "降水",ColorTranslator.FromHtml("#448AFF") },
                { "工作面",ColorTranslator.FromHtml("#455A64") },
            };
            Label lab = new Label();
            lab.Text = pName;
            lab.Width = 200; lab.Height = 40;
            //通过Anchor 设置Label 列中居中
            lab.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom)));
            lab.ForeColor = ColorTranslator.FromHtml("#FFFFFF");
            lab.BackColor = pcpColor[pCat];
            
            lab.Font = new System.Drawing.Font("微软雅黑", 14.25F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            lab.TextAlign = ContentAlignment.MiddleCenter;
            lab.DoubleClick += new EventHandler(PcpLab_DoubleClick);
            lab.MouseUp += new MouseEventHandler(PcpLab_MouseUp);
            return lab;
        }
        private void PcpLab_DoubleClick(object sender, EventArgs e)
        {
            //ShowPEPF(((Label)sender).Text);
        }
        private void PcpLab_MouseUp(object sender, MouseEventArgs e)
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
        #endregion

        private void flashDGVunit(string pSGname,string pUNname)
        {
            mcUN tUN = mscDC.getUN(pSGname, pUNname);

        }

        private enum eNodeType
        {
            Null = 0,
            DC = 1,
            SG = 2,
            UN = 3,
            Other = 4
        }
        private eNodeType nodeType(TreeNode pTN)
        {
            if (pTN == null) return eNodeType.Null;
            if (pTN.Parent == null) return eNodeType.DC;
            if (pTN.Parent.Parent == null) return eNodeType.SG;
            if (pTN.Parent.Parent.Parent == null) return eNodeType.UN;
            return eNodeType.Other;
        }

    }
}

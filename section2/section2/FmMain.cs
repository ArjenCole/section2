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
        private void flashDGVunit(string pSGname,string pUNname)
        {
            mcUN tUN = mscCtrl.getUN(pSGname, pUNname);

        }

        private void FmMain_Load(object sender, EventArgs e)
        {

        }
    }
}

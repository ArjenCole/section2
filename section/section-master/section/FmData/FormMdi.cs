using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Configuration;
using System.Data;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using System.Xml.Linq;

namespace section
{
    public partial class FormMdi : Form
    {
        List<mcDataCarrier> dataCarrierList = new List<mcDataCarrier>();

        private bool treeView1_Editing = false;//检测是否在编辑节点名称中，以便控制意外中断编辑情况下菜单栏有效性

        public FormMdi(string[] args)
        {
            InitializeComponent();
            mscCtrl.Th_CompleteOpen = true;

            try
            {
                mscLog.Write("FormMdi-FormMdi-ControlsIni()");
                ControlsIni();
                try
                {
                    mscLog.Write("FormMdi-FormMdi-mcAtlas.Init()");
                    mcAtlas.Init();
                    mscLog.Write("mscInventory.Init()");
                    mscInventory.Init();
                }
                catch
                {
                    mscLog.Write("mscCtrl.InportDataFromExcel()");
                    mscCtrl.InportDataFromExcel();
                    mscLog.Write("mcAtlas.Init()");
                    mcAtlas.Init();
                    mscLog.Write("mscInventory.Init()");
                    mscInventory.Init();
                }

                mscCtrl.formMdi = this;
                if (args.Length > 0)//带文件打开程序
                {
                    mscCtrl.Open(args[0]);
                }
                else//不文件打开程序
                {
                    string tBackupPath = mscDirtyShutDown.CheckDirty("");
                    if (tBackupPath != "")
                        mscCtrl.Open(tBackupPath);
                }
                mscLog.Write("FlashUI()");
                FlashUI();
                mscLog.Write("FlashEleInventory()");
                FlashEleInventory();

            }
            catch (Exception ex)
            {
                mscCtrl.Th_CompleteOpen = true;
                MessageBox.Show(ex.Message);
            }
            //mscCtrl.Th_CompleteOpen = true;
            //this.TopMost = true;
            //this.TopMost = false;
            this.Activate();
        }
        private void ControlsIni()
        {
            TLPmPE.Dock = DockStyle.Left;
            TLPmPF.Dock = DockStyle.Left;
            TLPmPE.Visible = true;
            TLPmPF.Visible = false;
            #region  利用反射机制修改TableLayoutPanel的Protected的DoubleBuffered属性 避免闪烁
            TLPmPE.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(TLPmPE, true, null);
            TLPmPF.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(TLPmPF, true, null);
            #endregion
            BTNaddPCP.Dock = DockStyle.Left;
        }
        #region 原则栏
        /// <summary>
        /// 单选框选择显示规则栏：围护/地基
        /// </summary>
        /// <param name="sender"></param>
        /// <param name="e"></param>
        private void radioButton_Click(object sender, EventArgs e)
        {
            switch (((RadioButton)sender).Name)
            {
                case "RBmPE":
                    TLPmPE.Visible = true;
                    TLPmPF.Visible = false;
                    break;
                case "RBmPF":
                    TLPmPE.Visible = false;
                    TLPmPF.Visible = true;
                    break;
            }
        }

        private Label NewPrincpleLab(string para_str_cat,string para_str_name)
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
        private void PrincpleLab_MouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                Point ClickPoint = new Point(e.X, e.Y);
                CMSpcp.Text = ((Label)sender).Text;
                CMSpcp.Show((Control)sender, ClickPoint);
            }
            FormUnitEndEdit();
        }

        private void FormUnitEndEdit()
        {
            foreach (Form feFm in mscCtrl.formMdi.MdiChildren)
            {
                if (!(feFm is FormUnit)) continue;
                FormUnit feFU = (FormUnit)feFm;
                feFU.dGVmain.EndEdit();
            }
        }

        private void PrincpleLab_DoubleClick(object sender, EventArgs e)
        {
            ShowPEPF(((Label)sender).Text);
        }
        private void ShowPEPF(string pName)
        {
            if (RBmPE.Checked)
            {
                FormPE formPE = new FormPE(pName);
                formPE.ShowDialog();
            }
            else
            {
                FormPF formPF = new FormPF(pName);
                formPF.ShowDialog();
            }

        }
        #endregion

        #region treeView1 事件
        private void treeView1_BeforeLabelEdit(object sender, NodeLabelEditEventArgs e)
        {
            treeView1_Editing = true;
            FlashEditMenu(false);
        }
        private void treeView1_AfterLabelEdit(object sender, NodeLabelEditEventArgs e)
        {
            if (e.Node == null) { return; }
            if (e.Label == null) { return; }//未做修改
            if (e.Node.Text == e.Label) { return; }
            if (e.Label == "")
            {
                MessageBox.Show("节点名称不得为空。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                e.CancelEdit = true;
                return;
            }
            if (e.Node.Parent == null)//根节点
            {
                mcBasicInfo tmB = mscMslns.DeepClone(mscCtrl.DC.BI);
                tmB.ProjectName = e.Label;
                mscCtrl.Set(tmB, "修改项目名称");
            }
            else if (e.Node.Parent.Parent == null)//标段节点
            {
                mcSegment tmS = mscCtrl.DC.Segment(e.Label);
                if (tmS != null)
                {
                    MessageBox.Show("与现有标段重名。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                    e.CancelEdit = true;
                    return;
                }//新名字与原有节点重名
                tmS = mscMslns.DeepClone(mscCtrl.DC.Segment(e.Node.Text));
                if (tmS == null) { return; }
                tmS.Name = e.Label;
                foreach (mcUnit femU in tmS.mList) 
                {
                    femU.OwnerName = tmS.Name;
                }
                mscCtrl.Set(e.Node.Text, tmS);
            }
            else if (e.Node.Parent.Parent.Parent == null)//单位工程节点
            {
                mcUnit tmU = mscCtrl.DC.Segment(e.Node.Parent.Text).Unit(e.Label);
                if (tmU != null)
                {
                    MessageBox.Show("与现有单位工程重名。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                    e.CancelEdit = true;
                    return;
                }//新名字与原有节点重名
                tmU = mscMslns.DeepClone(mscCtrl.DC.Segment(e.Node.Parent.Text).Unit(e.Node.Text));
                if (tmU == null) { return; }
                tmU.Name = e.Label;
                mscCtrl.Set(e.Node.Text, tmU, "重命名单位工程");
            }
            treeView1_Editing = false;
            FlashEditMenu(true);
        }
        private void treeView1_NodeMouseDoubleClick(object sender, TreeNodeMouseClickEventArgs e)
        {
            if (e.Node.Parent == null)//根节点
            {
                return;
            }
            else if (e.Node.Parent.Parent == null)//标段节点
            {

            }
            else//单位工程节点
            {

                for (int i = 0; i <= this.MdiChildren.Length - 1; i++)
                {
                    if (this.MdiChildren[i].Text == e.Node.Parent.Text + "-" + e.Node.Text)
                    {
                        this.MdiChildren[i].Activate();
                        ((FormUnit)this.MdiChildren[i]).FlashSectionPic();
                        return;
                    }
                }
                FormUnit formUnit = new FormUnit(e.Node.Parent.Text, e.Node.Text);
                formUnit.Show();
            }
        }
        private void treeView1_MouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)//判断你点的是不是右键
            {
                Point ClickPoint = new Point(e.X, e.Y);
                TreeNode CurrentNode = treeView1.GetNodeAt(ClickPoint);
                ContextMenuStrip tmp_CMS = new ContextMenuStrip();
                if (CurrentNode != null)//判断你点的是不是一个节点
                {
                    if (CurrentNode.Parent == null) //根节点
                    {
                        tmp_CMS = CMStvDC;
                    }
                    else if (CurrentNode.Parent.Parent == null) //标段节点
                    {
                        tmp_CMS = CMStvSegment;
                    }
                    else if (CurrentNode.Parent.Parent.Parent == null) //单位工程节点
                    {
                        tmp_CMS = CMStvUnit;
                    }
                    treeView1.SelectedNode = CurrentNode;//选中这个节点
                    //CurrentNode.ContextMenuStrip = tmp_CMS;
                    tmp_CMS.Show(treeView1, ClickPoint);
                }
            }
        }
        #endregion

        #region 元素库 事件
        private void CBOEleIvt_SelectedIndexChanged(object sender, EventArgs e)
        {
            FlashTVEleIvt();
        }
        private void TVEleIvt_NodeMouseDoubleClick(object sender, TreeNodeMouseClickEventArgs e)
        {
            if (treeView1.SelectedNode == null) { return; }//无选中
            if (treeView1.SelectedNode.Parent == null) { return; }//选中项目节点
            if (treeView1.SelectedNode.Parent.Parent == null) { return; }//选中标段节点
            if (e.Node.Text != TVEleIvt.SelectedNode.Text) { return; }
            if (e.Node.Parent == null)//根节点
            {
                return;
            }
            else if (e.Node.Parent.Parent == null)//元素节点
            {
                mcSegment tmS = mscInventory.Elei.Segment(CBOEleIvt.Text);
                mcUnit tmU = tmS.Unit(e.Node.Parent.Text);
                mcElement tmE = mscMslns.DeepClone(tmU.mList[e.Node.Index]);
                tmE.PEname.Clear();
                tmE.PEname.Add(mscCtrl.DC.PE.First().Key, 1);
                tmE.showPEname = tmE.PEname.First().Key;
                tmE.mainPEname = tmE.showPEname;
                tmE.PFname.Clear();
                tmE.PFname.Add(mscCtrl.DC.PF.First().Key, 1);
                tmE.showPFname = tmE.PFname.First().Key;

                tmS = mscCtrl.DC.Segment(treeView1.SelectedNode.Parent.Text);
                tmU = tmS.Unit(treeView1.SelectedNode.Text);

                foreach (Form feFm in mscCtrl.formMdi.MdiChildren)
                {
                    if (!(feFm is FormUnit)) continue;
                    FormUnit feFU = (FormUnit)feFm;
                    if ((feFU.OwnerName == tmS.Name) && (feFU.mUName == tmU.Name))
                    {
                        //int tIdx = feFm.dGVmain.SelectedCells[0].RowIndex;
                        //tmU.mList.Insert(tIdx, tmE);

                        //feFm.GetmU(tmS.Name, tmU.Name);
                        //feFm.UpdateUnit();
                        //feFm.FlashFm();
                        feFU.Insert(tmE);
                        return;
                    }

                }
            }
        }
        #endregion

        #region 刷新界面
        public void FlashUI()
        {
            FlashFormMdiTxt();
            FlashtreeView1();
            FlashPrincpleTab();
            FlashControlsEnable();
        }

        public void FlashFormMdiTxt()
        {
            if (mscCtrl.DC == null)
            {
                this.Text= "section"; 
                return;
            }
            string tFileName = Path.GetFileName(mscCtrl.DC.BI.FilePath);
            this.Text = tFileName == "" ? mscCtrl.DC.BI.ProjectName + " - section" : tFileName + " - section";
        }
        public void FlashEditMenu(bool pEnable)
        {
            FlashSubMenu(编辑ToolStripMenuItem, pEnable);
        }
        public void FlashtreeView1()
        {
            FormUnit ActiveFormUnit = this.ActiveMdiChild as FormUnit;
            TreeNode ActiveNode = null;
            treeView1.Nodes.Clear();
            if (mscCtrl.DC == null) { return; }
            TreeNode NodeProject = new TreeNode(mscCtrl.DC.BI.ProjectName, 1, 2);//一级节点
            foreach (mcSegment femS in mscCtrl.DC.mList)
            {
                TreeNode NodeSegment = new TreeNode(femS.Name);
                foreach (mcUnit femU in femS.mList)
                {
                    TreeNode NodeUnit = new TreeNode(femU.Name);
                    NodeSegment.Nodes.Add(NodeUnit);
                    if ((ActiveFormUnit != null) && (ActiveFormUnit.OwnerName == femS.Name) && (ActiveFormUnit.mUName == femU.Name))
                        ActiveNode = NodeUnit;
                }
                NodeProject.Nodes.Add(NodeSegment);
            }
            treeView1.Nodes.Add(NodeProject);
            treeView1.ExpandAll();
            if (ActiveNode != null)
                treeView1.SelectedNode = ActiveNode;
        }

        public void FlashPrincpleTab()
        {
            TLPmPE.Controls.Clear();
            TLPmPF.Controls.Clear();
            if (mscCtrl.DC == null) { RBmPE.Checked = true; panelPrincple.Enabled = false; panelPrincple.Visible = false; return; }
            panelPrincple.Enabled = true; panelPrincple.Visible = true;
            foreach (string feKey in mscCtrl.DC.PE.Keys)
            {
                TLPmPE.Controls.Add(NewPrincpleLab("围护", feKey));
                //this.SuspendLayout();
            }
            foreach (string feKey in mscCtrl.DC.PF.Keys)
            {
                TLPmPF.Controls.Add(NewPrincpleLab("地基", feKey));
                //this.SuspendLayout();
            }
        }
        private void FlashSubMenu(ToolStripMenuItem pTSMI, bool pEnable)
        {
            pTSMI.Enabled = pEnable;
            foreach (ToolStripItem feTSI in pTSMI.DropDownItems)
            {
                if (feTSI is ToolStripMenuItem)
                {
                    ((ToolStripMenuItem)feTSI).Enabled = pEnable;
                }
            }
        }
        private void FlashControlsEnable()
        {
            bool tbool = mscCtrl.DC == null ? false : true;
            保存ToolStripMenuItem.Enabled = tbool;
            另存为ToolStripMenuItem.Enabled = tbool;
            关闭当前项目ToolStripMenuItem.Enabled = tbool;
            //编辑ToolStripMenuItem.Enabled = tbool;
            FlashSubMenu(编辑ToolStripMenuItem, tbool);
            FlashSubMenu(项目ToolStripMenuItem, tbool);
            FlashSubMenu(视图ToolStripMenuItem, tbool);

            TSBsave.Enabled = tbool;
            TSBundo.Enabled = tbool;
            TSBredo.Enabled = tbool;
            TSBcopy.Enabled = tbool;
            TSBcut.Enabled = tbool;
            TSBpaste.Enabled = tbool;
            TSBbi.Enabled = tbool;
            TSBsum.Enabled = tbool;

            TVEleIvt.Enabled = tbool;
            CBOEleIvt.Enabled = tbool;
        }

        private void FlashEleInventory()
        {
            List<string> tL = new List<string>();
            foreach (mcSegment femS in mscInventory.Elei.mList)
                tL.Add(femS.Name);
            CBOEleIvt.DataSource = tL;
        }
        private void FlashTVEleIvt()
        {
            TVEleIvt.Nodes.Clear();
            mcSegment tmS = mscInventory.Elei.Segment(CBOEleIvt.Text);
            foreach(mcUnit femU in tmS.mList)
            {
                TreeNode NodeUnit = new TreeNode(femU.Name);
                foreach(mcElement femE in femU.mList)
                {
                    string tName = femE.Name == string.Empty ? femE.Specification() : femE.Name;
                    TreeNode NodeEle = new TreeNode(tName);
                    NodeUnit.Nodes.Add(NodeEle);
                }
                TVEleIvt.Nodes.Add(NodeUnit);
            }
            //TVEleIvt.ExpandAll();
        }

        public void FlashUndoRedo(List<string> pHisDis, List<string> pFutDis)
        {
            FlashDropDownItems(TSBundo, pHisDis, HisDropDownItems_Click);
            FlashDropDownItems(TSBredo, pFutDis, FutDropDownItems_Click);
        }
        private void FlashDropDownItems(ToolStripSplitButton pTSSB, List<string> pDis, EventHandler pEH)
        {
            pTSSB.DropDownItems.Clear();
            ToolStripMenuItem[] tTSMI = new ToolStripMenuItem[pDis.Count];
            for (int i = 0; i < pDis.Count; i++)
            {
                tTSMI[i] = new ToolStripMenuItem();
                tTSMI[i].Text = pDis[i];
                tTSMI[i].Tag = i;
                tTSMI[i].Click += new EventHandler(pEH);
            }
            pTSSB.DropDownItems.AddRange(tTSMI);
        }
        private void HisDropDownItems_Click(object sender, EventArgs e)
        {
            int index = Convert.ToInt16(((ToolStripMenuItem)sender).Tag);
            mscCtrl.MultUndo(index);
        }
        private void FutDropDownItems_Click(object sender, EventArgs e)
        {
            int index = Convert.ToInt16(((ToolStripMenuItem)sender).Tag);
            mscCtrl.MultRedo(index);
            
        }
        #endregion

        #region 与子窗体交互刷新
        public void CloseAllSubWindows()
        {
            while (this.MdiChildren.Length > 0) MdiChildren[0].Close();
        }
        public void FlashSubfmUnit()
        {
            foreach (Form feFm in this.MdiChildren)
                if (feFm is FormUnit)
                {
                    FormUnit tFU= feFm as FormUnit;
                    if (!mscCtrl.DC.SegmentNames.Contains(tFU.OwnerName)) { tFU.Close();continue; }
                    if (!mscCtrl.DC.Segment(tFU.OwnerName).UnitNames.Contains(tFU.mUName)) { tFU.Close(); continue; }
                    tFU.GetmU(tFU.OwnerName, tFU.mUName);
                    tFU.SetPEPFDropItems();
                    tFU.FlashFm();
                }
        }
        public void FlashSubfmUnitTxt(string pOrigmSname, string pNewmSname, string pOrigmUname, string pNewmUname)
        {
            foreach (Form feFm in this.MdiChildren)
            {
                if (feFm is FormUnit)
                {
                    FormUnit tFU = (FormUnit)feFm;
                    if (tFU.OwnerName == pOrigmSname) tFU.SetOwnerName(pNewmSname);
                    if (tFU.mUName == pOrigmUname) tFU.SetmUname(pNewmUname);
                    tFU.SetFmTxt();
                }
            }
        }
        public void FlashSubfmSumDGV()
        {
            foreach (Form feFm in this.MdiChildren)
                if (feFm is FormSum)
                {
                    FormSum tFS = feFm as FormSum;
                    tFS.Summary();
                }
        }
        public void FlashSubfmSumTV()
        {
            foreach (Form feFm in this.MdiChildren)
                if (feFm is FormSum)
                {
                    FormSum tFS = feFm as FormSum;
                    tFS.FlashtreeView1();
                }
        }
        public void SettreeView1ActiveNode(string p_mSname, string p_mUname)
        {
            if(p_mSname==string.Empty)
            {
                treeView1.SelectedNode = null; return;
            }
            TreeNode tmp_TN = treeView1.Nodes[0];
            foreach (TreeNode fe_TN in tmp_TN.Nodes)
            {
                if (fe_TN.Text == p_mSname)
                {
                    bool tmp_bool = false;
                    foreach(TreeNode fe_TN1 in fe_TN.Nodes)
                    {
                        if (fe_TN1.Text == p_mUname)
                        {
                            treeView1.SelectedNode = fe_TN1;
                            tmp_bool = true;
                            break;
                        }
                    }
                    if (tmp_bool) { break; }
                }
            }
        }
        public void CanceltreeView1ActiveNode(string pNameOfClosedFmUnit)
        {
            if(treeView1.SelectedNode == null) { return; }
            if (treeView1.SelectedNode.Text == pNameOfClosedFmUnit) 
            {
                treeView1.SelectedNode = null;
            }
        }

        #endregion

        #region MDI菜单栏
        #region 文件
        private void 新建ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if(mscCtrl.New())
            {
                CloseAllSubWindows();
                FlashUI();
            }
        }
        private void 打开ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if(mscCtrl.Open())
            {
                CloseAllSubWindows();
            }
            FlashUI();
        }
        private void 保存ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Save();
            FlashFormMdiTxt();
        }
        private void 另存为ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.SaveAs();
            FlashFormMdiTxt();
        }
        private void 关闭当前项目ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Close();
            FlashFormMdiTxt();
        }
        private void 关于SetionToolStripMenuItem_Click(object sender, EventArgs e)
        {
            FormAbout formAbout = new section.FormAbout();
            formAbout.ShowDialog();
        }
        #endregion

        #region 编辑
        private void 撤销ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Undo();
            //string tmp_str_discribe = string.Empty;
            //dataCarrierCurrent = msc_URD<mc_DataCarrier>.Undo(out tmp_str_discribe);
            //FlashUI();
        }
        private void 重做ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Redo();
            //string tmp_str_discribe = string.Empty;
            //dataCarrierCurrent = msc_URD<mc_DataCarrier>.Redo(out tmp_str_discribe);
            //FlashUI();
        }

        private void 复制ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            FormUnit formUnit = this.ActiveMdiChild as FormUnit;
            if (formUnit == null) return;
            formUnit.Copy();
        }
        private void 剪切ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            FormUnit formUnit = this.ActiveMdiChild as FormUnit;
            if (formUnit == null) return;
            formUnit.Copy();
            formUnit.Delete("剪切元素");
        }
        private void 粘贴ToolStripMenuItem_Click(object sender, EventArgs e)
        {

            FormUnit formUnit = this.ActiveMdiChild as FormUnit;
            if (formUnit == null) return;
            formUnit.Paste();
        }

        #endregion

        #region 项目
        #region 添加
        private void 添加标段ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Add(new mcSegment());
        }
        private void 添加单位工程ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if ((treeView1.SelectedNode == null)|| (treeView1.SelectedNode.Parent == null))
            {
                MessageBox.Show("请于项目树状结构中选中标段以添加单位工程。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                return;
            }
            if (treeView1.SelectedNode.Parent.Parent == null)//当前选中了标段节点
            {
                mscCtrl.Add(new mcUnit(treeView1.SelectedNode.Text));
            }
            else if (treeView1.SelectedNode.Parent.Parent.Parent == null)//当前选中了单位工程节点
            {
                mscCtrl.Add(new mcUnit(treeView1.SelectedNode.Parent.Text));
            }
            //FlashUI();
        }

        private void 添加沟槽围护原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Add(new mcPcpEnclosure());
            RBmPE.Checked = true;
        }
        private void 添加地基处理原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.Add(new mcPcpFoundation());
            RBmPF.Checked = true;
        }
        #endregion
        #region 汇总
        private void TSBsum_ButtonClick(object sender, EventArgs e)
        {
            if (treeView1.SelectedNode == null) return;

            if (treeView1.SelectedNode.Parent == null)
            {
                项目汇总ToolStripMenuItem_Click(null, null);return;
            }
            if (treeView1.SelectedNode.Parent.Parent == null)
            {
                标段汇总ToolStripMenuItem_Click(null, null);return;
            }
            if (treeView1.SelectedNode.Parent.Parent.Parent == null)
            {
                单位工程汇总ToolStripMenuItem_Click(null, null); return;
            }
        }
        private void 单位工程汇总ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if ((treeView1.SelectedNode == null) || (treeView1.SelectedNode.Parent == null)) { return; }
            if (treeView1.SelectedNode.Parent.Parent == null) { return; }

            string tmSname = treeView1.SelectedNode.Parent.Text;
            string tmUname = treeView1.SelectedNode.Text;
            List<mcUnit> tmUList = new List<mcUnit>();

            tmUList.Add(mscCtrl.DC.Segment(tmSname).Unit(tmUname));
            //FormSum formSum = new FormSum(tmUList);
            //formSum.ShowDialog();
            ShowFormSum(tmUList);
        }
        private void 标段汇总ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            string tmSname = string.Empty;
            string tmUname = string.Empty;

            if ((treeView1.SelectedNode == null) || (treeView1.SelectedNode.Parent == null)) { return; }
            if (treeView1.SelectedNode.Parent.Parent == null)
                tmSname = treeView1.SelectedNode.Text;
            else if (treeView1.SelectedNode.Parent.Parent.Parent == null)
                tmSname = treeView1.SelectedNode.Parent.Text;
            if (tmSname == string.Empty) { return; }
            List<mcUnit> tmUList = new List<mcUnit>();
            mcSegment tmS = mscCtrl.DC.Segment(tmSname);

            tmUList.AddRange(tmS.mList);
            //FormSum formSum = new FormSum(tmUList);
            //formSum.ShowDialog();
            ShowFormSum(tmUList);
        }
        private void 项目汇总ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            List<mcUnit> tmUList = new List<mcUnit>();
            foreach (mcSegment femS in mscCtrl.DC.mList)
            {
                tmUList.AddRange(femS.mList);
            }
            //FormSum formSum = new FormSum(tmUList);
            //formSum.ShowDialog();
            ShowFormSum(tmUList);
        }
        private void ShowFormSum(List<mcUnit> pmUList)
        {
            if (mscCtrl.formSum != null)
                if (!mscCtrl.formSum.IsDisposed)
                    mscCtrl.formSum.Dispose();
            FormSum formSum = new FormSum(pmUList);
            if (formSum.IsDisposed == false) formSum.Show();
        }

        #endregion
        #endregion

        #region 视图
        private void 水平平铺ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            LayoutMdi(MdiLayout.TileHorizontal);
        }
        private void 垂直平铺ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            LayoutMdi(MdiLayout.TileVertical);
        }
        private void 层叠排列ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            LayoutMdi(MdiLayout.Cascade);
        }
        private void 关闭所有窗体ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            CloseAllSubWindows();
        }
        #endregion

        #region 右键菜单
        private void 删除标段ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            string tmp_mSname = treeView1.SelectedNode.Text;
            mscCtrl.Delete(mscCtrl.DC.Segment(tmp_mSname));
        }
        private void 删除单位工程ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            string tmSname = treeView1.SelectedNode.Parent.Text;
            string tmUname = treeView1.SelectedNode.Text;
            mscCtrl.Delete(mscCtrl.DC.Segment(tmSname).Unit(tmUname));
        }

        private void 编辑原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (RBmPE.Checked)
                foreach (Control fe_col in TLPmPE.Controls)
                    if ((fe_col is Label) && (CMSpcp.Text == ((Label)fe_col).Text))
                        ShowPEPF(CMSpcp.Text);
            if (RBmPF.Checked)
                foreach (Control fe_col in TLPmPF.Controls)
                    if ((fe_col is Label) && (CMSpcp.Text == ((Label)fe_col).Text))
                        ShowPEPF(CMSpcp.Text);
        }
        private void 导入原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            string tEnvironment = System.Windows.Forms.Application.StartupPath + @"\Inventory\spcp\";
            string tOpenPath = mscCtrl.getOpenPath("*.spcp|*.spcp", tEnvironment);
            if (tOpenPath != string.Empty)
            {
                XElement tXE = XElement.Load(tOpenPath);
                string tXEname = tXE.FirstNode.Parent.Name.ToString();
                switch (tXEname)
                {
                    case "mcPcpEnclosure":
                        mcPcpEnclosure tPE = new mcPcpEnclosure(tXE);
                        mscCtrl.Add(tPE);
                        RBmPE.Checked = true;
                        break;
                    case "mcPcpFoundation":
                        mcPcpFoundation tPF = new mcPcpFoundation(tXE);
                        mscCtrl.Add(tPF);
                        RBmPF.Checked = true;
                        break;
                    default:
                        break;
                }
            }
        }
        private void 导出原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            try
            {
                if (RBmPE.Checked)
                    mscXML.SaveXml(mscCtrl.DC.PE[CMSpcp.Text].toXML(), mscCtrl.getSavePath(CMSpcp.Text, "*.spcp|*.spcp"));
                else if (RBmPF.Checked)
                    mscXML.SaveXml(mscCtrl.DC.PF[CMSpcp.Text].toXML(), mscCtrl.getSavePath(CMSpcp.Text, "*.spcp|*.spcp"));
            }
            catch
            {
                //MessageBox.Show("", "提示");
            }

        }
        private void 删除原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (RBmPE.Checked)
                mscCtrl.Delete(mscCtrl.DC.PE[CMSpcp.Text]);
            else if (RBmPF.Checked)
                mscCtrl.Delete(mscCtrl.DC.PF[CMSpcp.Text]);
        }
        #endregion

        #endregion

        private void 项目基本信息ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            FormBscIfo formBscIfo = new FormBscIfo();
            if (formBscIfo.ShowDialog() == DialogResult.Yes) FlashtreeView1();
        }

        private void FormMdi_FormClosing(object sender, FormClosingEventArgs e)
        {
            //if (!mscCtrl.DealWithCurrentFile()) e.Cancel = true;
            if (!mscCtrl.Close()) e.Cancel = true;
        }

        private void BTNaddPCP_Click(object sender, EventArgs e)
        {
            if (RBmPE.Checked)
                添加沟槽围护原则ToolStripMenuItem_Click(null, null);
            else
                添加地基处理原则ToolStripMenuItem_Click(null, null);
        }

        #region 测试输出板
        public void test_print(string p_str)
        {
            testlabel.Text += "\r\n" + p_str;
        }
        public void test_clear()
        {
            testlabel.Text = string.Empty;
        }



        #endregion

        private void btnMoveUp_Click(object sender, EventArgs e)
        {
            TreeNode currentNode = treeView1.SelectedNode;
            if (currentNode == null) return;
            string currentNodeTxt = currentNode.Text;
            if (currentNode.Parent == null)//根节点
            {
                return;
            }
            else if (currentNode.Parent.Parent == null)//标段节点
            {
                if (currentNode.PrevNode != null) mscCtrl.MoveUp(currentNode.Text);
                foreach(TreeNode feTN in treeView1.Nodes[0].Nodes)//移动后选中被移动的节点
                    if(feTN.Text==currentNodeTxt)
                    {
                        treeView1.SelectedNode = feTN;
                        return;
                    }
            }
            else//单位工程节点
            {
                if (currentNode.PrevNode != null) mscCtrl.MoveUp(currentNode.Parent.Text, currentNode.Text);
            }
        }

        private void btnMoveDown_Click(object sender, EventArgs e)
        {
            TreeNode currentNode = treeView1.SelectedNode;
            if (currentNode == null) return;
            string currentNodeTxt = currentNode.Text;
            if (currentNode.Parent == null)//根节点
            {
                return;
            }
            else if (currentNode.Parent.Parent == null)//标段节点
            {
                if (currentNode.NextNode != null) mscCtrl.MoveDown(currentNode.Text);
                foreach (TreeNode feTN in treeView1.Nodes[0].Nodes)//移动后选中被移动的节点
                    if (feTN.Text == currentNodeTxt)
                    {
                        treeView1.SelectedNode = feTN;
                        return;
                    }
            }
            else//单位工程节点
            {
                if (currentNode.NextNode != null) mscCtrl.MoveDown(currentNode.Parent.Text, currentNode.Text);
            }
        }

        private void 查看帮助ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            System.Diagnostics.Process.Start(Application.StartupPath + @"\Res\section软件使用说明书.pdf");
        }

        private void 退出ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            this.Close();
        }

        private void 导入检查井元素库ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mcSegment tmS = mscCtrl.DC.Segment(treeView1.SelectedNode.Parent.Text);
            mcUnit tmU = tmS.Unit(treeView1.SelectedNode.Text);


            DataSet pvDS = new DataSet();
            pvDS.Tables.Add(mscExcel.getDT(@"Atlas\【井】排水井工程量计算书.xlsx", "整理格式").Copy());//0
            foreach (DataRow feDR in pvDS.Tables[0].Rows)
            {
                mcE7 tmE7 = new mcE7();
                tmE7.Name = feDR["-名称"].ToString();
                tmE7.Category = "构筑物";
                tmE7.Depth = "";
                tmE7.Amount = "";
                tmE7.Source = "";

                tmE7.Param = new Dictionary<string, string>();
                foreach (DataColumn feDC in pvDS.Tables[0].Columns)
                    tmE7.Param.Add(feDC.ColumnName, feDR[feDC.ColumnName].ToString());

                tmE7.PEname.Clear();
                tmE7.PEname.Add(mscCtrl.DC.PE.First().Key, 1);
                tmE7.showPEname = tmE7.PEname.First().Key;
                tmE7.mainPEname = tmE7.showPEname;
                tmE7.PFname.Clear();
                tmE7.PFname.Add(mscCtrl.DC.PF.First().Key, 1);
                tmE7.showPFname = tmE7.PFname.First().Key;


                foreach (FormUnit feFm in mscCtrl.formMdi.MdiChildren)
                    if ((feFm.OwnerName == tmS.Name) && (feFm.mUName == tmU.Name))
                        feFm.Insert(tmE7);
            }

        }

        private void 从EXCEL中导入基础数据ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.InportDataFromExcel();
            mcAtlas.Init();
        }

        private void FormMdi_Deactivate(object sender, EventArgs e)
        {
            if (treeView1_Editing)
            {
                treeView1_Editing = false;
                FlashEditMenu(true);
            }
            
        }
    }
}

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace section
{
    public partial class FormSum : Form
    {
        #region mcQL用于线程间传递结果的类
        private class mcQL
        {
            public FormWait formWait;

            public Dictionary<string, mcQ> QsumDic = new Dictionary<string, mcQ>();

            public List<Dictionary<string, mcQ>> LsumDic = new List<Dictionary<string, mcQ>>();
            public List<mcElement> LmE = new List<mcElement>();
            public int LsumDicCnt = 0;
        }
        #endregion
        private List<mcUnit> mUSumList;

        public FormSum(List<mcUnit> pmUList)
        {
            mUSumList = pmUList;
            this.MdiParent = mscCtrl.formMdi;
            mscCtrl.formSum = this;
            InitializeComponent();
            #region  利用反射机制修改dGV的Protected的DoubleBuffered属性 避免闪烁
            dGVQ.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(dGVQ, true, null);
            dGVL.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(dGVL, true, null);
            #endregion

            SetPriceDropItems();
            FlashtreeView1();
            Summary();
        }
        private void SetPriceDropItems()
        {
            List<string> tl = mscInventory.price.Keys.ToList();
            批量载价ToolStripMenuItem.DropDown.Items.Clear();
            foreach (string feStr in tl)
                批量载价ToolStripMenuItem.DropDown.Items.Add(feStr);
        }
        private void FormSum_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                    this.Close();
                    break;
                default:
                    break;
            }
        }

        #region treeView1
        #region treeView1刷新
        public void FlashtreeView1()
        {
            treeView1.Nodes.Clear();
            if (mscCtrl.DC == null) { return; }
            TreeNode NodeProject = new TreeNode(mscCtrl.DC.BI.ProjectName, 1, 2);//一级节点
            if (mscCtrl.DC.Count > 0)
            {
                foreach (mcSegment femS in mscCtrl.DC.mList)
                {
                    TreeNode NodeSegment = new TreeNode(femS.Name);
                    if (femS.Count > 0)
                    {
                        foreach (mcUnit femU in femS.mList)
                        {
                            TreeNode NodeUnit = new TreeNode(femU.Name);
                            NodeSegment.Nodes.Add(NodeUnit);
                        }
                    }
                    NodeProject.Nodes.Add(NodeSegment);
                }
            }
            treeView1.Nodes.Add(NodeProject);
            treeView1.ExpandAll();
            foreach (mcUnit femU in mUSumList)
            {
                checktVnodes(treeView1.Nodes[0], femU.OwnerName, femU.Name);
            }
        }
        /// <summary>
        /// 勾选单位工程列表
        /// </summary>
        /// <param name="pTN">根节点</param>
        /// <param name="pmSname">标段名称</param>
        /// <param name="pmUname">单位工程名称</param>
        private void checktVnodes(TreeNode pTN, string pmSname, string pmUname)
        {
            if ((pTN.Parent != null) && (pTN.Parent.Parent != null))
            {
                if ((pmSname == pTN.Parent.Text) && (pmUname == pTN.Text))
                {
                    pTN.Checked = true;
                    return;
                }
            }
            TreeNodeCollection tmp_nodes = pTN.Nodes;
            if (tmp_nodes.Count > 0)
            {
                int tmp_int_cnt = 0;
                foreach (TreeNode fe_tn in tmp_nodes)
                {
                    checktVnodes(fe_tn, pmSname, pmUname);
                    if (fe_tn.Checked == true) { tmp_int_cnt++; }
                }
                if (tmp_int_cnt == tmp_nodes.Count) { pTN.Checked = true; }
            }
        }
        #endregion
        #region treeView1自动选中子节点 事件
        private void treeView1_AfterCheck(object sender, TreeViewEventArgs e)
        {
            if (e.Action == TreeViewAction.ByMouse)
            {
                if (e.Node.Checked == true)
                {
                    //选中节点之后，选中该节点所有的子节点
                    setChildNodeCheckedState(e.Node, true);
                    setParentNodeCheckedStateTrue(e.Node);
                }
                else if (e.Node.Checked == false)
                {
                    //取消节点选中状态之后，取消该节点所有子节点选中状态
                    setChildNodeCheckedState(e.Node, false);
                    //如果节点存在父节点，取消父节点的选中状态
                    if (e.Node.Parent != null)
                        setParentNodeCheckedStateFalse(e.Node);
                }
            }
        }
        //取消节点选中状态之后，取消所有父节点的选中状态
        private void setParentNodeCheckedStateFalse(TreeNode currNode)
        {
            TreeNode parentNode = currNode.Parent;
            parentNode.Checked = false;
            if (currNode.Parent.Parent != null)
                setParentNodeCheckedStateFalse(currNode.Parent);
        }
        //选中节点之后，选中节点的所有子节点
        private void setChildNodeCheckedState(TreeNode currNode, bool state)
        {
            TreeNodeCollection nodes = currNode.Nodes;
            if (nodes.Count > 0)
            {
                foreach (TreeNode tn in nodes)
                {
                    tn.Checked = state;
                    setChildNodeCheckedState(tn, state);
                }
            }
        }
        //选中节点后，选中节点的所有父节点检查是否满选
        private void setParentNodeCheckedStateTrue(TreeNode currNode)
        {
            if (currNode.Parent == null) { return; }
            int tmp_int_cnt = 0;
            foreach (TreeNode fe_TN in currNode.Parent.Nodes)
            {
                if (fe_TN.Checked == true) { tmp_int_cnt++; }
            }
            if (tmp_int_cnt == currNode.Parent.Nodes.Count)
            {
                currNode.Parent.Checked = true;
                setParentNodeCheckedStateTrue(currNode.Parent);
            }
        }
        #endregion
        private void treeView1_NodeMouseClick(object sender, TreeNodeMouseClickEventArgs e)
        {
            var tList = new List<mcUnit>();
            foreach (TreeNode feTN in treeView1.Nodes[0].Nodes)
                foreach (TreeNode feTN1 in feTN.Nodes)
                    if (feTN1.Checked)
                        tList.Add(mscCtrl.DC.Segment(feTN.Text).Unit(feTN1.Text));
            if (mUSumList.Count != tList.Count)
            {
                mUSumList = tList;
                Summary();
            }   
        }
        #endregion

        #region 计算及等待窗体_多线程
        public void Summary()
        {
            FormWait formWait = new FormWait("工程量计算中,请稍后");
            #region 后台
            using (BackgroundWorker bw = new BackgroundWorker())
            {
                bw.RunWorkerCompleted += new RunWorkerCompletedEventHandler(bw_RunWorkerCompleted);
                bw.DoWork += new DoWorkEventHandler(bw_DoWork);
                bw.RunWorkerAsync(formWait);
            }
            #endregion
            #region 前台
            if (!formWait.IsDisposed)
            {
                formWait.ShowDialog();
                if (formWait.Cancel) this.Dispose();
            }
            #endregion
        }
        void bw_DoWork(object sender, DoWorkEventArgs e)
        {
            // 这里是后台线程， 是在另一个线程上完成的 
            // 这里是真正做事的工作线程 
            // 可以在这里做一些费时的，复杂的操作 
            mcQL mQL = new mcQL();
            mQL.formWait = e.Argument as FormWait;
            foreach (mcUnit femU in mUSumList)
            {
                if (mscCtrl.DC.Segment(femU.OwnerName).Unit(femU.Name) == null) continue;
                foreach (mcElement femE in femU.mList)
                {
                    Dictionary<string, mcQ> tmDQ = femE.DQ;
                    if (tmDQ == null) { continue; }
                    //定额汇总
                    mQL.QsumDic = mscGroove.PlusDic_StrmcQ(mQL.QsumDic, tmDQ);
                    //清单汇总
                    mQL.LsumDic.Add(tmDQ);
                    mQL.LmE.Add(femE);
                    mQL.LsumDicCnt += tmDQ.Count + 1;
                    //Thread.Sleep(10);
                }
            }
            e.Result = mQL;
        }
        void bw_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            //这时后台线程已经完成，并返回了主线程，所以可以直接使用UI控件了 
            mcQL mQL = e.Result as mcQL;
            try
            {
                FlashdGVQ(mQL.QsumDic);
                FlashdGVL(mQL.LsumDic, mQL.LmE, mQL.LsumDicCnt);
                mQL.formWait.Dispose();
            }
            catch
            {
                //执行过程中可能主程序已经关闭了formSum，此时此处控件调用丢失对象
            }
                
        }
        #endregion

        #region dGV
        #region dGV刷新
        private void FlashdGVQ(Dictionary<string, mcQ> pDQ)
        {
            mscMslns.DGV_RcntAdjust(dGVQ, pDQ.Count);
            ShowSummary(dGVQ, FlashItem(pDQ, dGVQ, 0));
        }
        private void FlashdGVL(List<Dictionary<string, mcQ>> pLDQ,List<mcElement> pLmE, int pRowCnt)
        {
            mscMslns.DGV_RcntAdjust(dGVL, pRowCnt);
            int tRowIdx = 0;
            double tPriceSum = 0;//总价
            for (int i = 0; i < pLDQ.Count; i++) 
            {
                Dictionary<string, mcQ> feDQ = pLDQ[i];
                mcElement femE = pLmE[i];
                dGVL.Rows[tRowIdx].DefaultCellStyle.BackColor = Color.LightBlue;
                dGVL[0, tRowIdx].Value = "清单项目";
                dGVL[1, tRowIdx].Value = femE.Category;
                dGVL[2, tRowIdx].Value = femE.Specification() + " 埋深 " + femE.DepthD.ToString() + "m";
                dGVL[3, tRowIdx].Value = femE.Unit;
                dGVL[4, tRowIdx].Value = femE.AmountD;

                dGVL[5, tRowIdx].Value = mscMslns.ShowDouble(femE.AmountD == 0 ? 0 : femE.TotalPrice / femE.AmountD);
                dGVL[6, tRowIdx].Value = mscMslns.ShowDouble(femE.TotalPrice);
                tRowIdx++;

                tPriceSum += FlashItem(feDQ, dGVL, tRowIdx)["合计"];

                tRowIdx += feDQ.Count;
            }

            ShowSummary(dGVL, tPriceSum);
        }
        private Dictionary<string, double> FlashItem(Dictionary<string, mcQ> pDQ, DataGridView pDGV, int pStartRowIdx)
        {
            int i = pStartRowIdx;
            //double rtDb = 0;
            Dictionary<string, double> rtDb = new Dictionary<string, double>();
            rtDb.Add("合计", 0.0);
            foreach (KeyValuePair<string, mcQ> pKVP in mscGroove.OrderDQ(pDQ)) 
            {
                string tKey = pKVP.Key;


                var tStr = tKey.Split(new[] { "|" }, StringSplitOptions.None);

                if (tStr.Length == 3) 
                {
                    pDGV[0, i].Value = string.Empty;
                    pDGV[1, i].Value = tStr[0];
                    pDGV[2, i].Value = tStr[1];
                    pDGV[3, i].Value = tStr[2];
                }
                if (tStr.Length == 2)
                {
                    pDGV[0, i].Value = string.Empty;
                    pDGV[1, i].Value = "";
                    pDGV[2, i].Value = tStr[0];
                    pDGV[3, i].Value = tStr[1];
                }
                if (tStr.Length == 1)
                {
                    pDGV[0, i].Value = string.Empty;
                    pDGV[1, i].Value = "";
                    pDGV[2, i].Value = tStr[0];
                    pDGV[3, i].Value = "";
                }
                pDGV[4, i].Value = mscMslns.ShowDouble(pKVP.Value.Q);

                double tPrice = mscCtrl.getPrice(pKVP.Key);
                pDGV[5, i].Value = mscMslns.ShowDouble(tPrice);
                pDGV[6, i].Value = mscMslns.ShowDouble(tPrice * pKVP.Value.Q);

                pDGV.Rows[i].DefaultCellStyle.BackColor = treeView1.BackColor;
                i++;

                if (rtDb.Keys.Contains(tStr[0]))
                    rtDb[tStr[0]] += tPrice * pKVP.Value.Q;
                else
                    rtDb.Add(tStr[0], tPrice * pKVP.Value.Q);
                rtDb["合计"] += tPrice * pKVP.Value.Q;
            }
            return rtDb;//返回总价
        }
        private void ShowSummary(DataGridView pDGV, double pSum)
        {
            pDGV.Rows.Add(2);
            int idx = pDGV.Rows.GetLastRow(DataGridViewElementStates.None);
            showMoney(pDGV, idx, "合计：", pSum);
        }
        private void ShowSummary(DataGridView pDGV, Dictionary<string, double> pSum)
        {
            int idx = pDGV.Rows.GetLastRow(DataGridViewElementStates.None) + 2;
            
            pDGV.Rows.Add(pSum.Count + 1);
            showMoney(pDGV, idx, "合计：", pSum["合计"]);
            foreach (string feS in pSum.Keys)
            {
                if (feS == "合计") continue;
                idx += 1;
                showMoney(pDGV, idx, feS, pSum[feS]);
            }
        }
        private void showMoney(DataGridView pDGV, int pIdx, string pKey, double pValue)
        {
            if(pKey.Contains("合计"))
                pDGV[0, pIdx].Value = pKey;
            else
                pDGV[1, pIdx].Value = pKey;

            pDGV[3, pIdx].Value = "元";
            pDGV[6, pIdx].Value = mscMslns.ShowDouble(pValue);
        }
        #endregion
        #region dGV事件脚本
        private void dGVQ_CellClick(object sender, DataGridViewCellEventArgs e)
        {
            var t = dGVQ.CurrentCell.Value;
            if (t != null) { CopyToClipBoard(mscMslns.ToString(t)); }
        }
        private void dGVL_CellClick(object sender, DataGridViewCellEventArgs e)
        {
            var t = dGVL.CurrentCell.Value;
            if (t != null) { CopyToClipBoard(mscMslns.ToString(t)); }
        }
        #endregion
        #endregion

        private void CopyToClipBoard(string pCopyStr)
        {
            Clipboard.SetDataObject(pCopyStr);
        }

        private void dGV_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            int RowIdx = e.RowIndex;
            DataGridView tDGV = sender as DataGridView;
            DataGridViewRow tDGVR = tDGV.CurrentRow;
            mscCtrl.setPrice( mscMslns.ToString(tDGVR.Cells[1].Value), mscMslns.ToString(tDGVR.Cells[2].Value), mscMslns.ToString(tDGVR.Cells[3].Value)
                                , mscMslns.ToDouble(tDGV.Rows[RowIdx].Cells[5].Value));
            Summary();
        }

        #region 右键菜单
        private void 批量载价ToolStripMenuItem_DropDownItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
            ToolStripItem tTSI = e.ClickedItem;
            string tName = tTSI.Text;
            DialogResult tMB = MessageBox.Show("是否覆盖当前已填写的价格信息？", "提示",
                                        MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question);
            switch (tMB)
            {
                case DialogResult.None:
                case DialogResult.Cancel:
                    return;
                case DialogResult.Yes:
                    mscCtrl.setPrice(mscInventory.price[tName], true);
                    break;
                case DialogResult.No:
                    mscCtrl.setPrice(mscInventory.price[tName], false);
                    break;
            }
            Summary();
        }
        private void 清空所有价格ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            mscCtrl.clearPrice();
            Summary();
        }
        #endregion

        private void btnCurrentToExcel_Click(object sender, EventArgs e)
        {
            string fileName = mscCtrl.getSavePath("工程数量表", "*.xls|*.xls");
            mscExcel.ExportExcel(fileName, dGVQ, dGVL);

        }
        private void btnAllToExcel_Click(object sender, EventArgs e)
        {
            FolderBrowserDialog FBD = new FolderBrowserDialog();
            string sPath;
            if (FBD.ShowDialog() == DialogResult.OK)
                sPath = FBD.SelectedPath + @"\" + mscCtrl.DC.BI.ProjectName + @"\";
            else
                return;

            if (!Directory.Exists(sPath))
                Directory.CreateDirectory(sPath);

            var tList = mscMslns.DeepClone(mUSumList);
            foreach (mcSegment femS in mscCtrl.DC.mList)
                foreach (mcUnit femU in femS.mList)
                {
                    mUSumList.Clear();
                    mUSumList.Add(femU);
                    Summary();

                    if(!mscExcel.ExportExcel(sPath + femS.Name + "-" + femU.Name + ".xls", dGVQ, dGVL, false))
                    {
                        goto gtSetUI;
                    }
                }
gtSetUI:
            mUSumList = tList;
            Summary();
            MessageBox.Show(sPath + " 导出成功", "提示", MessageBoxButtons.OK);

        }
    }
}

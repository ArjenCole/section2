using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using System.Xml.Linq;
namespace section
{
    public partial class FormUnit : Form
    {
        //private mcSegment mScrt;
        private mcUnit mUcrt;
        public string OwnerName;
        public string mUName;
        private bool cmbBoxMainPE_ChangeByMan = true;//<主要原则>comboBox数据源修改前标记false 修改后标记true，避免cmbBoxMainPE的事件重复触发UpdateUnit();
        private mcPictureBox PBsection = new mcPictureBox();
        #region 公共函数
        #region 数据名称
        public void GetmU(string pOwnerName, string pName)
        {
            mUcrt = mscMslns.DeepClone(mscCtrl.DC.Segment(pOwnerName).Unit(pName));
        }
        public void SetOwnerName(string pOwnerName)
        {
            OwnerName = pOwnerName;
            mUcrt.OwnerName = OwnerName;
        }
        public void SetmUname(string pmUName)
        {
            mUName = pmUName;
            mUcrt.Name = mUName;
        }
        public void SetFmTxt()
        {
            this.Text = OwnerName + "-" + mUName;
        }
        #endregion

        #region 复制粘贴字符串
        public void Copy()
        {
            XElement tXE = new XElement("COPYmcE");
            List<XElement> tList = new List<XElement>();
            foreach (DataGridViewCell feDGVC in dGVmain.SelectedCells)
            {
                if (feDGVC.RowIndex == dGVmain.Rows.Count - 1) { continue; }
                tList.Add(mUcrt.mList[feDGVC.RowIndex].toXML());
            }
            tList.Reverse();
            tXE.Add(tList);
            mscXML.SaveXml(tXE, Application.StartupPath + @"\mClipboard.xml");
            Clipboard.SetDataObject(string.Empty);
        }
        public void Paste()
        {
            IDataObject iData = Clipboard.GetDataObject();// Declares an IDataObject to hold the data returned from the clipboard.
            if (iData.GetDataPresent(DataFormats.Text))// Determines whether the data is in a format you can use.
            {
                string DataString = (String)iData.GetData(DataFormats.Text);
                if (DataString != string.Empty)
                {
                    Paste(DataString);
                    return;
                }
            }
            Paste(XElement.Load(Application.StartupPath + @"\mClipboard.xml"));
        }
        private void Paste(XElement pXE)
        {
            IEnumerable<XElement> elements = from ele in pXE.Elements("mcElement")
                                             select ele;
            List<mcElement> tList = new List<mcElement>();
            foreach (XElement feXE in elements)
            {
                tList.Add(mcElement.NewElement(feXE));
            }
            mUcrt.mList.InsertRange(dGVmain.CurrentCell.RowIndex, tList);
            FlashFm();
            UpdateUnit("粘贴元素");
        }
        private void Paste(string pPasteStr)
        {
            int RowIdx = dGVmain.CurrentCell.RowIndex;
            int ColIdx = dGVmain.CurrentCell.ColumnIndex;
            if (pPasteStr.EndsWith("\r\n")) pPasteStr = pPasteStr.Remove(pPasteStr.Length - 2, 2);//最后一行若为空行则删除
            string[] tStrRow = pPasteStr.Split(new[] { "\r\n" }, StringSplitOptions.None);
            if (ColIdx == 8)
            {
                #region 字符串识别
                string tDN = "";
                mcPipe tDefaultPipe = new mcPipe();//合并单元格管道延续
                Dictionary<string, string> tDefaultParam = null; //= (new mcE3()).Param;tDefaultParam["净宽 m(含内壁厚度)"] = "0";

                for (int i = 0; i < tStrRow.Count(); i++)
                {
                    string[] tStrCell = tStrRow[i].Split(new[] { "\t" }, StringSplitOptions.None);
                    int oRowIdx = RowIdx + i;

                    string SourceStr = tStrRow[i];
                    string feDN = getDN(SourceStr);
                    tDN = feDN == "" ? "" : feDN;
                    var tDouble = getDouble(SourceStr);


                    mcElement tmE;
                    if (tDouble.Count <= 1)  //(tAmount == 0 && tDeep == 10000000000000000)
                        tmE = new mcE0();
                    else
                        tmE = getmcElement(SourceStr, tDN, tDefaultPipe, tDefaultParam);

                    #region 埋深/数量自动摘取
                    double tDeep = 10000000000000000;
                    double tAmount = 0;

                    List<double> tDoubleList = new List<double>();
                    foreach(var feCN in tDouble)
                    {
                        double tmpD = mscMslns.ToDouble(feCN.ToString());
                        tDoubleList.Add(tmpD);
                    }
                    if (tmE is mcE1)
                    {
                        tDoubleList.Remove(mscMslns.ToDouble(tDN));
                    }
                    else if(tmE is mcE3)
                    {
                        tDoubleList.Remove(mscMslns.ToDouble(tmE.Param["净宽 m(含内壁厚度)"]) * 1000);
                        tDoubleList.Remove(mscMslns.ToDouble(tmE.Param["净高 m"]) * 1000);
                    }                                            
                    foreach (double feDouble in tDoubleList)
                    {
                        if (feDouble == mscMslns.ToDouble(tDN)) continue;
                        if (Math.Abs(feDouble) > Math.Abs(tAmount)) tAmount = feDouble;
                        if (Math.Abs(feDouble) < Math.Abs(tDeep)) tDeep = feDouble;
                    }

                    tmE.Amount = tAmount == 0 ? "" : tAmount.ToString();
                    tmE.Depth = tDeep == 10000000000000000 ? "" : tDeep.ToString();
                    #endregion

                    if (tmE!=null)
                    {
                        initPCP(tmE);
                        tmE.Source = SourceStr;
                        mUcrt.SetmEx(oRowIdx, tmE);
                        if (tmE.Count > 0) tDefaultPipe = mscMslns.DeepClone(tmE.Pipe(0));
                        if (tmE is mcE3) tDefaultParam = mscMslns.DeepClone(tmE.Param);
                    }                    
                }
                FlashFm();
                UpdateUnit("粘贴文本");
                #endregion
            }
            else
            {
                #region 普通粘贴
                bool flag = false;
                for (int i = 0; i < tStrRow.Count(); i++)
                {
                    string[] tStrCell = tStrRow[i].Split(new[] { "\t" }, StringSplitOptions.None);
                    int oRowIdx = RowIdx + i;
                    if (mUcrt.Element(oRowIdx) == null) { break; }
                    for (int j = 0; j < tStrCell.Count(); j++)
                    {
                        //mcElement tmE = mscMslns.DeepClone(mUcrt.Element(oRowIdx));
                        mcElement tmE = mUcrt.Element(oRowIdx);
                        int oColIdx = ColIdx + j;
                        switch (dGVmain.Columns[oColIdx].Name)
                        {
                            case "mainColName":
                                tmE.Name = tStrCell[j];
                                flag = true;
                                break;
                            case "mainColDepth":
                                tmE.Depth = tStrCell[j];
                                flag = true;
                                break;
                            case "mainColAmount":
                                tmE.Amount = tStrCell[j];
                                flag = true;
                                break;
                            default:
                                break;
                        }
                        if (flag)
                        {
                            mUcrt.SetmEx(oRowIdx, tmE);
                            FlashdGVmainRow(oRowIdx);
                        }
                    }
                }
                if (flag)
                {
                    FlashPanel2dGVs();
                    FlashdGVQ();
                    FlashSectionPic();
                    UpdateUnit("粘贴文本");
                }
                #endregion
            }

        }
        #region 识别元素
        private string getDN(string pStr)
        {
            string tStr = pStr.Replace("φ", "DN");
            tStr = tStr.Replace("Φ", "DN");
            string rtStr = "";

            string re1 = "(D)"; // Any Single Word Character (Not Whitespace) 1
            string re2 = ".*?"; // Non-greedy match on filler
            string re3 = "(\\d+)";  // Integer Number 1

            Regex r = new Regex(re1 + re2 + re3, RegexOptions.IgnoreCase | RegexOptions.Singleline);
            Match m = r.Match(tStr);
            if (m.Success)
            {
                String w1 = m.Groups[1].ToString();
                rtStr = m.Groups[2].ToString();
            }
            return rtStr;
        }
        private MatchCollection getDouble(string str)
        {
            /**  \\d+\\.?\\d*
            * \d 表示数字
            * + 表示前面的数字有一个或多个（至少出现一次）
            * \. 此处需要注意，. 表示任何原子，此处进行转义，表示单纯的 小数点
            * ? 表示0个或1个
            * * 表示0次或者多次
            */
            Regex r = new Regex("\\d+\\.?\\d*");
            bool ismatch = r.IsMatch(str);
            MatchCollection mc = r.Matches(str);

            return mc;
        }

        private mcElement getmcElement(string SourceStr, string pDN, mcPipe pDefaultPipe, Dictionary<string, string> pDefaultParam)
        {
            mcElement rtmE;
            if (SourceStr.Contains("座") || SourceStr.Contains("只") || SourceStr.Contains("个") || SourceStr.Contains("套"))
            {
                rtmE = new mcE7();
            }
            else if (pDN == "" && (SourceStr.Contains("×") || SourceStr.Contains("*") || SourceStr.Contains("x") || SourceStr.Contains("X") || pDefaultParam != null)) 
            {
                rtmE = getmcE3(SourceStr, pDefaultParam);
            }
            else if (SourceStr.Contains("顶管") || SourceStr.Contains("顶推") || SourceStr.Contains("顶进")) 
            {
                rtmE = getmcE4(SourceStr, pDN, pDefaultPipe);
            }
            else if (SourceStr.Contains("牵引") || SourceStr.Contains("拖拉") || SourceStr.Contains("定向钻"))
            {
                rtmE = getmcE5(SourceStr, pDN, pDefaultPipe);
            }
            else
            {
                rtmE = getmcE1(SourceStr, pDN, pDefaultPipe);
            }

            rtmE.Amount = "";//tAmount.ToString();
            rtmE.Depth = "";// tDeep == 10000000000000000 ? "0" : tDeep.ToString();

            return rtmE;
        }
        private mcE1 getmcE1(string SourceStr, string pDN, mcPipe pDefaultPipe)
        {
            mcE1 rtmE = new mcE1();
            rtmE.Category = "直埋管道";

            mcPipe tmP = getmcPipe(SourceStr, pDN, pDefaultPipe);

            rtmE.Add(tmP);
            return rtmE;
        }
        private mcE3 getmcE3(string SourceStr, Dictionary<string, string> pDefaultParam)
        {
            mcE3 rtmE = new mcE3();
            rtmE.Category = "箱涵";
            if (pDefaultParam != null) rtmE.Param = pDefaultParam;
            string tB = "", tH = "";
            SourceStr = SourceStr.Replace("*", "×");
            SourceStr = SourceStr.Replace("x", "×");
            SourceStr = SourceStr.Replace("X", "×");
            string[] tSP = SourceStr.Split(new[] { "\t" }, StringSplitOptions.None);
            foreach (string feS in tSP)
            {
                if (feS.Contains("×"))
                {
                    var tMC = getDouble(feS);
                    double tD = mscMslns.ToDouble(tMC[0].ToString());
                    rtmE.Param["净宽 m(含内壁厚度)"] = tD < 20 ? tD.ToString() : (tD / 1000.0).ToString();
                    tD = mscMslns.ToDouble(tMC[1].ToString());
                    rtmE.Param["净高 m"] = tD < 20 ? tD.ToString() : (tD / 1000.0).ToString();
                    break;
                }
            }
            return rtmE;
        }
        private mcE4 getmcE4(string SourceStr, string pDN, mcPipe pDefaultPipe)
        {
            mcE4 rtmE = new mcE4();
            rtmE.Category = "顶管";

            mcPipe tmP = getmcPipe(SourceStr, pDN, pDefaultPipe);

            rtmE.Add(tmP);
            return rtmE;
        }
        private mcE5 getmcE5(string SourceStr, string pDN, mcPipe pDefaultPipe)
        {
            mcE5 rtmE = new mcE5();
            rtmE.Category = "牵引管";

            mcPipe tmP = getmcPipe(SourceStr, pDN, pDefaultPipe);

            rtmE.Add(tmP);
            return rtmE;
        }

        private mcPipe getmcPipe(string SourceStr, string pDN, mcPipe pDefultPipe)
        {
            mcPipe rtmP = pDefultPipe;
            if (pDN != "") rtmP.Dn = mscMslns.ToDouble(pDN);
            if (SourceStr.Contains("混凝土") || SourceStr.Contains("砼"))
            {
                rtmP.Mat = "钢筋混凝土Ⅱ级管";
                if (SourceStr.Contains("一级") || SourceStr.Contains("Ⅰ")) rtmP.Mat = "钢筋混凝土Ⅰ级管";                
                if (SourceStr.Contains("三级") || SourceStr.Contains("Ⅲ")) rtmP.Mat = "钢筋混凝土Ⅲ级管";
            }
            if (SourceStr.Contains("PE") || SourceStr.Contains("pe"))
            {
                rtmP.Mat = "聚氯乙烯(PE)双壁波纹管";
                if (SourceStr.Contains("缠绕"))
                {
                    rtmP.Mat = "聚氯乙烯(PE)缠绕结构壁管 A型";
                    if (SourceStr.Contains("B")) rtmP.Mat = "聚氯乙烯(PE)缠绕结构壁管 B型";
                }
                if (SourceStr.Contains("波纹")) rtmP.Mat = "聚氯乙烯(PE)双壁波纹管";
            }
            if (SourceStr.Contains("HDPE") || SourceStr.Contains("hdpe"))
            {
                rtmP.Mat = "HDPE承插式双壁缠绕管";
                if (SourceStr.Contains("缠绕")) rtmP.Mat = "HDPE承插式双壁缠绕管";
                if (SourceStr.Contains("波纹")) rtmP.Mat = "HDPE双壁波纹管";
            }

            if (SourceStr.Contains("球墨") || SourceStr.Contains("球铁") || SourceStr.Contains("铸铁"))
            {
                string tmpLevel = " K9";
                if (SourceStr.Contains("K8") || SourceStr.Contains("k8")) tmpLevel = " K8";
                if (SourceStr.Contains("K10") || SourceStr.Contains("k10")) tmpLevel = " K10";
                rtmP.Mat = "球墨铸铁管" + tmpLevel;
            }
            else if (SourceStr.Contains("钢管"))
            {
                if (SourceStr.Contains("焊接"))
                {
                    rtmP.Mat = "焊接钢管1.0Mpa";
                    if (SourceStr.Contains("1.6Mpa") || SourceStr.Contains("1.6mpa")) rtmP.Mat = "焊接钢管1.6Mpa";
                }
                else if (SourceStr.Contains("无缝"))
                {
                    rtmP.Mat = "无缝钢管";
                }
                else
                {
                    rtmP.Mat = "给水钢管";
                }
            }

            return rtmP;
        }
        #endregion
        private void initPCP(mcElement pmE)
        {
            pmE.PEname.Clear();
            pmE.PEname.Add(mscCtrl.DC.PE.First().Key, 1);
            pmE.showPEname = pmE.PEname.First().Key;
            pmE.mainPEname = pmE.showPEname;
            pmE.PFname.Clear();
            pmE.PFname.Add(mscCtrl.DC.PF.First().Key, 1);
            pmE.showPFname = pmE.PFname.First().Key;
        }
        #endregion

        #region 复制粘贴原则
        private enum ePastePCP
        {
            PE, PF, PE_PF
        }
        public void CopyPCP()
        {
            if (dGVmain.CurrentCell == null) return;
            mcElement tmE = mUcrt.mList[dGVmain.CurrentCell.RowIndex];
            mscXML.SaveXml(tmE.toXML(), Application.StartupPath + @"\mClipboard_PCP.xml");
        }
        private void PastePCP(ePastePCP pPastePCP)
        {
            XElement tXE = XElement.Load(Application.StartupPath + @"\mClipboard_PCP.xml");
            mcElement tmE = mcElement.NewElement(tXE);
            foreach (DataGridViewCell feDGVC in dGVmain.SelectedCells)
            {
                if (feDGVC.RowIndex >= mUcrt.Count) continue;
                mcElement femE = mUcrt.mList[feDGVC.RowIndex];
                if (pPastePCP == ePastePCP.PE || pPastePCP == ePastePCP.PE_PF)
                    femE.SetPE(tmE.PEname, tmE.showPEname, tmE.mainPEname);
                if (pPastePCP == ePastePCP.PF || pPastePCP == ePastePCP.PE_PF)
                    femE.SetPF(tmE.PFname, tmE.showPFname);
                FlashdGVmainRow(feDGVC.RowIndex);
            }
            if (dGVmain.SelectedCells.Count > 0)
            {
                FlashdGVQ();
                FlashPanel2dGVs();
                FlashSectionPic();
                UpdateUnit("应用原则");
            }
        }
        #endregion

        #region 增删元素
        public void Insert(mcElement pmE)
        {
            int tIdx = dGVmain.SelectedCells[0].RowIndex;
            mUcrt.mList.Insert(tIdx, pmE);
            FlashFm();
            UpdateUnit("插入元素");
        }
        public void Delete(string pDiscribe = "删除元素")
        {
            List<int> tmpL = new List<int>();
            foreach (DataGridViewCell feDGVC in dGVmain.SelectedCells)
            {
                if (feDGVC.RowIndex == dGVmain.Rows.Count - 1) { continue; }
                if (!tmpL.Contains(feDGVC.RowIndex)) { tmpL.Add(feDGVC.RowIndex); }
            }
            tmpL.Sort();
            tmpL.Reverse();
            foreach (int i in tmpL)
            {
                mUcrt.mList.RemoveAt(i);
            }
            UpdateUnit(pDiscribe);
            FlashdGVmain();
            FlashPanel2dGVs();
        }
        #endregion
        #endregion
        public FormUnit(string pOwnerName, string pName)
        {
            this.MdiParent = mscCtrl.formMdi;
            OwnerName = pOwnerName; mUName = pName;
            GetmU(OwnerName, pName);
            InitializeComponent();
            #region  利用反射机制修改dGV的Protected的DoubleBuffered属性 避免闪烁
            dGVmain.GetType().GetProperty
                ("DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .SetValue(dGVmain, true, null);
            #endregion
            #region 添加画板
            spltCtnerR.Panel2.Controls.Add(PBsection);
            PBsection.Left = 0;
            PBsection.Height = 200;
            //PBsection.Dock = DockStyle.Bottom;
            PBsection.Dock = DockStyle.Fill;
            #endregion
            SetFmTxt();
            SetCatDropItems();
            SetPipeDropItems();
            SetPEPFDropItems();
            FlashFm();
        }
        private void FormUnit_Activated(object sender, EventArgs e)
        {
            mscCtrl.formMdi.SettreeView1ActiveNode(mUcrt.OwnerName, mUcrt.Name);
        }
        private void FormUnit_FormClosed(object sender, FormClosedEventArgs e)
        {
            mscCtrl.formMdi.CanceltreeView1ActiveNode(mUcrt.Name);
        }
        #region 设置下拉框内容
        private void SetCatDropItems()
        {
            mainColCat.DataSource = mcElement.typeDic.Keys.ToList();
        }
        private void SetPipeDropItems()
        {
            List<string> NList = new List<string>() { "包封埋管", "箱涵", "管廊" };//负面清单
            foreach(mcSegment femS in mscInventory.Elei.mList)
            {
                if (NList.Contains(femS.Name)) continue;
                ToolStripMenuItem tTSMI = new ToolStripMenuItem(femS.Name);
                tTSMI.DropDownItemClicked += new ToolStripItemClickedEventHandler(选择管道类型ToolStripMenuItem_DropDownItemClicked);
                foreach (string feS in femS.UnitNames)
                    tTSMI.DropDown.Items.Add(feS.Replace(" 顶管", string.Empty).Replace("水平定向钻", string.Empty));
                CMSpipe.Items.Add(tTSMI);
            }
        }

        public void SetPEPFDropItems()
        {
            List<string> tl = mscCtrl.DC.PE.Keys.ToList();
            PEColKey.DataSource = mscMslns.DeepClone(tl);

            选择沟槽围护原则ToolStripMenuItem.DropDown.Items.Clear();
            foreach (string feStr in tl)
                选择沟槽围护原则ToolStripMenuItem.DropDown.Items.Add(feStr);
            tl.Add("多围护原则");
            mainColPE.DataSource = mscMslns.DeepClone(tl);

            tl = mscCtrl.DC.PF.Keys.ToList();
            PFColKey.DataSource = mscMslns.DeepClone(tl);

            选择地基处理原则ToolStripMenuItem.DropDown.Items.Clear();
            foreach (string feStr in tl)
                选择地基处理原则ToolStripMenuItem.DropDown.Items.Add(feStr);
            tl.Add("多地基原则");
            mainColPF.DataSource = mscMslns.DeepClone(tl);
        }
        #endregion

        #region 刷新整个窗体UI
        public void FlashFm()
        {
            FlashdGVmain();
            FlashPanel2dGVs();
            FlashdGVQ();
            FlashSectionPic();
        }
        private void FlashdGVmain()
        {
            mscMslns.DGV_RcntAdjust(dGVmain, mUcrt.Count + 1);
            for (int i = 0; i < mUcrt.Count; i++)
            {
                FlashdGVmainRow(i);
            }
        }
        private void FlashdGVmainRow(int pIdx)
        {
            
            DataGridViewRow tRow = dGVmain.Rows[pIdx];
            if (pIdx + 1 == dGVmain.Rows.Count) 
            {
                tRow = new DataGridViewRow();
                return;
            }
            mcElement tmE = mUcrt.Element(pIdx);
            tRow.Cells["mainColName"].Value = tmE.Name;
            tRow.Cells["mainColCat"].Value = tmE.Category;
            tRow.Cells["mainColSpec"].Value = tmE.Specification();
            tRow.Cells["mainColDepth"].Value = tmE.Depth;
            tRow.Cells["mainColUnit"].Value = tmE.Unit;
            tRow.Cells["mainColAmount"].Value = tmE.Amount;
            tRow.Cells["mainColPE"].Value = tmE.showPEname;
            tRow.Cells["mainColPF"].Value = tmE.showPFname;
            tRow.Cells["mainColSource"].Value = tmE.Source;
        }
        private void FlashPanel2dGVs()
        {
            DataGridViewRow dGVRowcrt = dGVmain.CurrentRow;
            mcElement mEcrt;
            if ((dGVRowcrt == null) || dGVmain.SelectedCells.Count > 1)
                mEcrt = null;
            else
                mEcrt = mUcrt.Element(dGVmain.CurrentRow.Index);

            FlashdGVpipe(mEcrt);
            FlashdGVdetail(mEcrt);
            FlashdGVPE(mEcrt);
            FlashdGVPF(mEcrt);
            SetPosition();
        }
        private void SetPosition()
        {
            Dictionary<bool, int> tDic = new Dictionary<bool, int>();
            tDic.Add(true, 1); tDic.Add(false, 0);
            PNLpipe.Left = 0;
            PNLdetail.Left = PNLpipe.Left + PNLpipe.Width * tDic[PNLpipe.Visible];
            PNLPE.Left = PNLdetail.Left + PNLdetail.Width * tDic[PNLdetail.Visible];
            PNLPF.Left = PNLPE.Left + PNLPE.Width * tDic[PNLPE.Visible];
        }
        private void FlashdGVQ()
        {
            var tSumDic = new Dictionary<string, mcQ>();
            List<int> tLRow = new List<int>();
            foreach (DataGridViewCell feDGVC in dGVmain.SelectedCells)
            {
                if (tLRow.Contains(feDGVC.RowIndex)) continue;
                tLRow.Add(feDGVC.RowIndex);
                mcElement tmE = mUcrt.Element(feDGVC.RowIndex);
                if (tmE == null) { continue; }
                tSumDic = mscGroove.PlusDic_StrmcQ(tSumDic, tmE.DQ);
            }
            mscMslns.DGV_RcntAdjust(dGVQ, tSumDic.Keys.Count);
            int i = 0;
            foreach (KeyValuePair<string, mcQ> feKVP in mscGroove.OrderDQ(tSumDic))
            {
                dGVQ[0, i].Value = feKVP.Key;
                dGVQ[1, i].Value = mscMslns.ShowDouble(feKVP.Value.Q);
                i++;
            }
            if (tSumDic.Count == 0)
                LBLQnull.Visible = true;
            else
                LBLQnull.Visible = false;
        }
        public void FlashSectionPic()
        {
            DataGridViewRow dGVRowcrt = dGVmain.CurrentRow;
            mcElement mEcrt;
            PNLpicCtrler.Visible = false;

            if (dGVRowcrt == null || dGVmain.SelectedCells.Count > 1)
                return;
            else
                mEcrt = mUcrt.Element(dGVmain.CurrentRow.Index);
            if (mEcrt == null)
                PBsection.PaintSection();
            else
            {
                if (mEcrt.showPEname != mcPcpEnclosure.Multi_PETxt && mEcrt.showPFname != mcPcpFoundation.Multi_PFTxt)
                {
                    PBsection.PaintSection(mEcrt, mEcrt.PEname.First().Key, mEcrt.PEname.First().Key, mEcrt.PFname.First().Key);
                }
                else
                {
                    PNLpicCtrler.Visible = true;
                    CMBpicCtrlerLPE.DataSource = mEcrt.PEname.Keys.ToList();
                    CMBpicCtrlerRPE.DataSource = mEcrt.PEname.Keys.ToList();
                    CMBpicCtrlerPF.DataSource = mEcrt.PFname.Keys.ToList();
                    CMBpicCtrlerLPE.SelectedIndex = 0;
                    CMBpicCtrlerRPE.SelectedIndex = mEcrt.PEname.Count > 1 ? 1 : 0;
                    CMBpicCtrlerPF.SelectedIndex = 0;
                    PBsection.PaintSection(mEcrt, CMBpicCtrlerLPE.Text, CMBpicCtrlerRPE.Text, CMBpicCtrlerPF.Text);
                }
            }
            //if (tmA != null)
            //    LBL_At.Text = "t=" + tmA.t.ToString() + " a=" + tmA.a.ToString() + " C1=" + tmA.C1 + " C2=" + tmA.C2.ToString();
        }
        #region FlashPanel2dGVs
        private void FlashdGVpipe(mcElement pmE)
        {
            if (pmE == null) { dGVpipe.Rows.Clear(); PNLpipe.Visible = false; return; }
            switch (pmE.Type)
            {
                case "mcE1":
                case "mcE4":
                case "mcE5":
                    PNLpipe.Visible = true;
                    dGVpipe.AllowUserToAddRows = false;
                    break;
                case "mcE2":
                    PNLpipe.Visible = true;
                    dGVpipe.AllowUserToAddRows = true;
                    break;
                default:
                    PNLpipe.Visible = false;
                    dGVpipe.Rows.Clear();
                    break;
            }
            int ExtrRow = dGVpipe.AllowUserToAddRows == true ? 1 : 0;
            mscMslns.DGV_RcntAdjust(dGVpipe, pmE.Count + ExtrRow);
            for (int i = 0; i < pmE.Count; i++)
            {
                FlashdGVpipeRow(i, pmE.Pipe(i));
            }
        }
        private void FlashdGVpipeRow(int pIdx, mcPipe pmP)
        {
            dGVpipe["pipeColMat", pIdx].Value = pmP.Mat;
            dGVpipe["pipeColDn", pIdx].Value = pmP.Dn;
            dGVpipe["pipeColCont", pIdx].Value = pmP.Content;
        }
        private void FlashdGVdetail(mcElement pmE)
        {
            if (pmE == null) { dGVdetail.Rows.Clear(); PNLdetail.Visible = false; return; }
            switch (pmE.Type)
            {
                case "mcE2":
                case "mcE3":
                case "mcE6":
                    PNLdetail.Visible = true;
                    dGVdetail.AllowUserToAddRows = false;
                    mscMslns.DGV_RcntAdjust(dGVdetail, pmE.Param.Count);
                    dGVdetail.Columns[0].ReadOnly = true;
                    int i = 0;
                    foreach (KeyValuePair<string, string> feKVP in pmE.Param)
                    {
                        dGVdetail.Rows[i].Cells[0].Value = feKVP.Key;
                        dGVdetail.Rows[i].Cells[1].Value = mscMslns.ToString(feKVP.Value);
                        i++;
                    }
                    dGVdetail.AllowUserToDeleteRows = false;
                    break;
                case "mcE7":
                    PNLdetail.Visible = true;
                    dGVdetail.AllowUserToAddRows = true;
                    mscMslns.DGV_RcntAdjust(dGVdetail, pmE.Param.Count + 1);
                    dGVdetail.Columns[0].ReadOnly = false;
                    dGVdetail.Rows[0].Cells[0].ReadOnly = true;
                    dGVdetail.Rows[1].Cells[0].ReadOnly = true;

                    i = 0;
                    foreach (KeyValuePair<string, string> feKVP in pmE.Param)
                    {
                        dGVdetail.Rows[i].Cells[0].Value = feKVP.Key;
                        dGVdetail.Rows[i].Cells[1].Value = mscMslns.ToString(feKVP.Value);
                        i++;
                    }
                    dGVdetail.AllowUserToDeleteRows = true;
                    break;
                default:
                    PNLdetail.Visible = false;
                    dGVdetail.Rows.Clear();
                    break;
            }
        }
        private void FlashdGVPE(mcElement pmE)
        {
            if (pmE == null) { dGVPE.Rows.Clear(); PNLPE.Visible = false; return; }
            cmbBoxMainPE_ChangeByMan = false;
            switch (pmE.showPEname)
            {
                case mcPcpEnclosure.Multi_PETxt:
                    PNLPE.Visible = true;
                    mscMslns.DGV_RcntAdjust(dGVPE, pmE.PEname.Count + 1);
                    int i = 0;
                    foreach (string feKey in pmE.PEname.Keys)
                    {
                        dGVPE["PEColKey", i].Value = feKey;
                        dGVPE["PEColValue", i].Value = pmE.PEname[feKey];
                        i++;
                    }
                    cmbBoxMainPE.DataSource = pmE.PEname.Keys.ToList();
                    cmbBoxMainPE.Text = pmE.mainPEname;
                    break;
                default:
                    PNLPE.Visible = false;
                    dGVPE.Rows.Clear();
                    cmbBoxMainPE.Text = string.Empty;
                    break;
            }
            cmbBoxMainPE_ChangeByMan = true;
        }
        private void FlashdGVPF(mcElement pmE)
        {
            if (pmE == null) { dGVPF.Rows.Clear(); PNLPF.Visible = false; return; }
            switch (pmE.showPFname)
            {
                case mcPcpFoundation.Multi_PFTxt:
                    PNLPF.Visible = true;
                    mscMslns.DGV_RcntAdjust(dGVPF, pmE.PFname.Count + 1);
                    int i = 0;
                    foreach (string feKey in pmE.PFname.Keys)
                    {
                        dGVPF["PFColKey", i].Value = feKey;
                        dGVPF["PFColValue", i].Value = pmE.PFname[feKey];
                        i++;
                    }
                    break;
                default:
                    PNLPF.Visible = false;
                    dGVPF.Rows.Clear();
                    break;
            }
        }
        #endregion
        #endregion
        #region dGV事件脚本
        #region dGVmain
        private void dGVmain_SelectionChanged(object sender, EventArgs e)
        {
            FlashPanel2dGVs();
            FlashdGVQ();
            FlashSectionPic();
        }
        private void dGVmain_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            dGVmain.BeginEdit(true);
        }
        private void dGVmain_CellClick(object sender, DataGridViewCellEventArgs e)
        {
            if (dGVmain.Columns[e.ColumnIndex].GetType().ToString() == "System.Windows.Forms.DataGridViewComboBoxColumn")
                dGVmain.BeginEdit(true);
        }
        private void dGVmain_CellBeginEdit(object sender, DataGridViewCellCancelEventArgs e)
        {
            mscCtrl.formMdi.FlashEditMenu(false);
        }
        private void dGVmain_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            //mcElement tmE = mscMslns.DeepClone(mUcrt.Element(e.RowIndex));
            mcElement tmE = mUcrt.Element(e.RowIndex);
            if (tmE == null)
            {
                tmE = getmEformdGVmainRow(e.RowIndex);
                mUcrt.SetmEx(e.RowIndex, tmE);
            }
            else
            {
                DataGridViewRow tRow = dGVmain.Rows[e.RowIndex];
                switch (dGVmain.Columns[e.ColumnIndex].Name)
                {
                    case "mainColName":
                        tmE.Name = mscMslns.ToString(tRow.Cells["mainColName"].Value);
                        break;
                    case "mainColCat":
                        string tStr = mscMslns.ToString(tRow.Cells["mainColCat"].Value);
                        if (tmE.Category != tStr)
                            tmE = getmEformdGVmainRow(e.RowIndex);
                        else
                            return;
                        break;
                    case "mainColDepth":
                        tmE.Depth = mscMslns.ToString(tRow.Cells["mainColDepth"].Value);
                        break;
                    case "mainColAmount":
                        tmE.Amount = mscMslns.ToString(tRow.Cells["mainColAmount"].Value);
                        break;
                    case "mainColPE":
                        tmE.showPEname = mscMslns.ToString(tRow.Cells["mainColPE"].Value);
                        tmE.mainPEname = tmE.showPEname;
                        break;
                    case "mainColPF":
                        tmE.showPFname = mscMslns.ToString(tRow.Cells["mainColPF"].Value);
                        break;
                    case "mainColSource":
                        tmE.Source = mscMslns.ToString(tRow.Cells["mainColSource"].Value);
                        break;
                    default:
                        break;
                }
                mUcrt.SetmEx(e.RowIndex, tmE);
            }
            UpdateUnit("编辑元素");
            FlashdGVmainRow(e.RowIndex);
            FlashdGVQ();
            mscCtrl.formMdi.FlashEditMenu(true);
        }
        private mcElement getmEformdGVmainRow(int pIdx)
        {
            if (pIdx < 0) { return null; }
            DataGridViewRow tRow = dGVmain.Rows[pIdx];
            object[] tmpObj = new object[7];
            tmpObj[0] = tRow.Cells["mainColName"].Value;
            tmpObj[1] = tRow.Cells["mainColCat"].Value;
            tmpObj[2] = tRow.Cells["mainColDepth"].Value;
            tmpObj[3] = tRow.Cells["mainColAmount"].Value;
            tmpObj[4] = tRow.Cells["mainColPE"].Value;
            tmpObj[5] = tRow.Cells["mainColPF"].Value;
            tmpObj[6] = tRow.Cells["mainColSource"].Value;
            mcElement tmE = mUcrt.Element(pIdx);
            Dictionary<string, double> tDicPE = null;
            Dictionary<string, double> tDicPF = null;
            if (tmE != null)
            {
                tDicPE = mUcrt.Element(pIdx).PEname;
                tDicPF = mUcrt.Element(pIdx).PFname;
            }
            return mcElement.NewElement(mscMslns.ToString(tRow.Cells["mainColCat"].Value), tmpObj, tDicPE, tDicPF);
        }
        private void dGVmain_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Delete:
                    Delete();
                    break;
                case Keys.Insert:
                    mcElement tmE = getmEformdGVmainRow(dGVmain.Rows.Count - 1);
                    Insert(tmE);
                    break;
                default:
                    break;
            }
        }
        #endregion
        #region dGVpipe
        private void dGVpipe_CellBeginEdit(object sender, DataGridViewCellCancelEventArgs e)
        {
            mscCtrl.formMdi.FlashEditMenu(false);
        }
        private void dGVpipe_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
            if (e.RowIndex + 1 > tmE.Count)
                tmE.Add(getmPformdGVpipeRow(e.RowIndex));
            else
                tmE.mList[e.RowIndex] = getmPformdGVpipeRow(e.RowIndex);
            UpdateUnit("编辑管材");
            mscCtrl.formMdi.FlashEditMenu(true);
            FlashdGVmainRow(dGVmain.CurrentRow.Index);
            FlashdGVQ();
            FlashSectionPic();
        }
        private mcPipe getmPformdGVpipeRow(int pIdx)
        {
            if (pIdx < 0) { return null; }
            DataGridViewRow tRow = dGVpipe.Rows[pIdx];
            mcPipe rtP = new mcPipe();
            rtP.Mat = mscMslns.ToString(tRow.Cells["pipeColMat"].Value);
            rtP.Dn = mscMslns.ToDouble(tRow.Cells["pipeColDn"].Value);
            rtP.Content = mscMslns.ToDouble(tRow.Cells["pipeColCont"].Value);
            return rtP;
        }
        private void dGVpipe_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Delete:
                    List<int> tmpL = new List<int>();
                    foreach (DataGridViewCell feDGVC in dGVpipe.SelectedCells)
                    {
                        if (feDGVC.RowIndex == dGVpipe.Rows.Count - 1) { continue; }
                        if (!tmpL.Contains(feDGVC.RowIndex)) { tmpL.Add(feDGVC.RowIndex); }
                    }
                    tmpL.Sort();
                    tmpL.Reverse();
                    mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
                    foreach (int i in tmpL)
                        tmE.mList.RemoveAt(i);
                    UpdateUnit("删除管材");
                    FlashdGVmainRow(dGVmain.CurrentRow.Index);
                    FlashdGVpipe(tmE);
                    FlashdGVQ();
                    FlashSectionPic();
                    break;
                default:
                    break;
            }
        }
        #endregion
        #region dGVdetail
        private void dGVdetail_CellBeginEdit(object sender, DataGridViewCellCancelEventArgs e)
        {
            mscCtrl.formMdi.FlashEditMenu(false);
        }
        private void dGVdetail_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            dGVdetail_endEdit();
        }


        private static int tDeleteRowsCount = 0;
        private static bool flag = false;
        private void dGVdetail_UserDeletingRow(object sender, DataGridViewRowCancelEventArgs e)
        {
            if (e.Row.Index <= 1)
            {
                e.Cancel = true;
                tDeleteRowsCount--;
            }
        }
        private void dGVdetail_UserDeletedRow(object sender, DataGridViewRowEventArgs e)
        {
            var  i=e.Row.Cells[0].Value;
            if (flag == false)
            {
                tDeleteRowsCount = this.dGVdetail.SelectedRows.Count + tDeleteRowsCount + 1;
                flag = true;
            }
            if (tDeleteRowsCount > 1)
            {
                tDeleteRowsCount--;
            }
            else
            {
                flag = false;
                tDeleteRowsCount = 0;
                dGVdetail_endEdit();
            }
        }

        private void dGVdetail_endEdit()
        {
            mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
            tmE.Param.Clear();
            bool tFlag = false;
            foreach (DataGridViewRow feDGVR in dGVdetail.Rows)
            {
                string tKey = mscMslns.ToString(feDGVR.Cells[0].Value);
                if (tKey == "") break;
                string tValue = mscMslns.ToString(feDGVR.Cells[1].Value);
                while (tmE.Param.Keys.Contains(tKey))
                {
                    tKey += " 副本"; tFlag = true;
                }
                tmE.Param.Add(tKey, tValue);
            }
            if (tFlag) FlashPanel2dGVs();

            UpdateUnit("编辑详细参数");
            mscCtrl.formMdi.FlashEditMenu(true);
            FlashdGVmainRow(dGVmain.CurrentRow.Index);
            FlashdGVQ();
            FlashSectionPic();
        }
        #endregion
        #region dGVPE
        private void dGVPE_CellBeginEdit(object sender, DataGridViewCellCancelEventArgs e)
        {
            mscCtrl.formMdi.FlashEditMenu(false);
        }
        private void dGVPE_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
            DataGridViewRow tRow = dGVPE.Rows[e.RowIndex];
            string tKey = mscMslns.ToString(tRow.Cells["PEColKey"].Value);
            double tValue = mscMslns.ToDouble(tRow.Cells["PEColValue"].Value);
            if (tKey == string.Empty) { return; }
            if (tmE.PEname.Keys.Contains(tKey))
                tmE.PEname[tKey] = tValue;
            else
                tmE.PEname.Add(tKey, tValue);
            if (!tmE.PEname.Keys.Contains(tmE.mainPEname))
            {
                tmE.mainPEname = tmE.PEname.First().Key;
                cmbBoxMainPE.Text = tmE.mainPEname;
            }
            UpdateUnit("编辑元素围护原则");
            mscCtrl.formMdi.FlashEditMenu(true);
            cmbBoxMainPE_ChangeByMan = false;
            cmbBoxMainPE.DataSource = tmE.PEname.Keys.ToList();
            cmbBoxMainPE_ChangeByMan = true;
            FlashdGVQ();
            FlashSectionPic();
        }
        private void dGVPE_CellValidating(object sender, DataGridViewCellValidatingEventArgs e)
        {
            List<string> tmpL = new List<string>();
            foreach (DataGridViewRow feDGVR in dGVPE.Rows)
            {
                if (feDGVR.Index != e.RowIndex)
                {
                    string tKey = mscMslns.ToString(feDGVR.Cells["PEColKey"].Value);
                    if (tKey != string.Empty) { tmpL.Add(tKey); }
                }
            }
            if (tmpL.Contains(e.FormattedValue.ToString()))
            {
                MessageBox.Show("原则已存在于列表中。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                e.Cancel = true;
            }
        }
        private void cmbBoxMainPE_DropDownClosed(object sender, EventArgs e)
        {
            if (dGVmain.CurrentCell == null) { return; }
            mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
            tmE.mainPEname = cmbBoxMainPE.Text;
            if (cmbBoxMainPE_ChangeByMan)  UpdateUnit("选择元素主要原则"); 
            FlashdGVQ();
            FlashSectionPic();
        }
        private void dGVPE_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Delete:
                    mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
                    #region 判断是否删除了全部内容
                    if (tmE.PEname.Count < dGVPE.SelectedCells.Count)
                    { MessageBox.Show("至少需要一种围护原则。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk); return; }
                    if (tmE.PEname.Count == dGVPE.SelectedCells.Count)
                    {
                        bool tBool = true;
                        foreach (DataGridViewCell feDGVC in dGVPE.SelectedCells)
                            if (feDGVC.RowIndex == dGVPE.RowCount - 1) tBool = false;
                        if (tBool) { MessageBox.Show("至少需要一种围护原则。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk); return; }
                    }
                    #endregion
                    foreach (DataGridViewCell feDGVC in dGVPE.SelectedCells)
                    {
                        int tIdx = feDGVC.RowIndex;
                        string tKey = mscMslns.ToString(dGVPE["PEColKey", tIdx].Value);
                        if (tmE.PEname.Keys.Contains(tKey))
                        {
                            tmE.PEname.Remove(tKey);
                            if (tmE.mainPEname == tKey)  tmE.mainPEname = tmE.PEname.First().Key; 
                        }
                    }
                    UpdateUnit("删除元素围护原则");
                    FlashdGVPE(tmE);
                    FlashdGVQ();
                    FlashSectionPic();
                    break;
                default:
                    break;
            }
        }
        #endregion
        #region dGVPF
        private void dGVPF_CellBeginEdit(object sender, DataGridViewCellCancelEventArgs e)
        {
            mscCtrl.formMdi.FlashEditMenu(false);
        }
        private void dGVPF_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
            DataGridViewRow tRow = dGVPF.Rows[e.RowIndex];
            string tKey = mscMslns.ToString(tRow.Cells["PFColKey"].Value);
            double tValue = mscMslns.ToDouble(tRow.Cells["PFColValue"].Value);
            if (tKey == string.Empty) { return; }
            if (tmE.PFname.Keys.Contains(tKey))
                tmE.PFname[tKey] = tValue;
            else
                tmE.PFname.Add(tKey, tValue);
            UpdateUnit("编辑元素地基原则");
            mscCtrl.formMdi.FlashEditMenu(true);
            FlashdGVQ();
            FlashSectionPic();
        }
        private void dGVPF_CellValidating(object sender, DataGridViewCellValidatingEventArgs e)
        {
            List<string> tmpL = new List<string>();
            foreach (DataGridViewRow feDGVR in dGVPF.Rows)
            {
                if (feDGVR.Index != e.RowIndex)
                {
                    string tKey = mscMslns.ToString(feDGVR.Cells["PFColKey"].Value);
                    if (tKey != string.Empty) { tmpL.Add(tKey); }
                }
            }
            if (tmpL.Contains(e.FormattedValue.ToString()))
            {
                MessageBox.Show("原则已存在于列表中。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                e.Cancel = true;
            }
        }
        private void dGVPF_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Delete:
                    mcElement tmE = mUcrt.Element(dGVmain.CurrentRow.Index);
                    #region 判断是否删除了全部内容
                    if (tmE.PFname.Count < dGVPF.SelectedCells.Count)
                    { MessageBox.Show("至少需要一种地基原则。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk); return; }
                    if (tmE.PFname.Count == dGVPF.SelectedCells.Count)
                    {
                        bool tBool = true;
                        foreach (DataGridViewCell feDGVC in dGVPF.SelectedCells)
                        {
                            if (feDGVC.RowIndex == dGVPF.RowCount - 1)
                            { tBool = false; }
                        }
                        if (tBool) { MessageBox.Show("至少需要一种地基原则。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk); return; }
                    }
                    #endregion
                    foreach (DataGridViewCell feDGVC in dGVPF.SelectedCells)
                    {
                        int tIdx = feDGVC.RowIndex;
                        string tKey = mscMslns.ToString(dGVPF["PFColKey", tIdx].Value);
                        if (tmE.PFname.Keys.Contains(tKey))
                        {
                            tmE.PFname.Remove(tKey);
                            if (tmE.mainPEname == tKey) { tmE.mainPEname = tmE.PFname.First().Key; }
                        }
                    }
                    UpdateUnit("删除元素地基原则");
                    FlashdGVPF(tmE);
                    FlashdGVQ();
                    FlashSectionPic();
                    break;
                default:
                    break;
            }
        }
        #endregion
        #endregion
        public void UpdateUnit(string pDiscribe = "编辑单位工程")
        {
            mscCtrl.Set(mUcrt.Name, mUcrt, pDiscribe);
        }
        private void CMBpicCtrler_DropDownClosed(object sender, EventArgs e)
        {
            DataGridViewRow dGVRowcrt = dGVmain.CurrentRow;
            mcElement mEcrt;
            if (dGVRowcrt == null || dGVmain.SelectedCells.Count > 1)
                return;
            else
                mEcrt = mUcrt.Element(dGVmain.CurrentRow.Index);
            if (mEcrt == null)
                PBsection.PaintSection();
            else
                PBsection.PaintSection(mEcrt, CMBpicCtrlerLPE.Text, CMBpicCtrlerRPE.Text, CMBpicCtrlerPF.Text);
        }
        #region 右键菜单
        #region 选择原则
        private void 选择沟槽围护原则ToolStripMenuItem_DropDownItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
            ToolStripItem tTSI = e.ClickedItem;
            string tPEname = tTSI.Text;
            bool flag = false;
            foreach (DataGridViewCell feDGVC in dGVmain.SelectedCells)
            {
                mcElement tmE = mUcrt.Element(feDGVC.RowIndex);
                if (tmE == null) continue;
                if (tmE.showPEname == tPEname) continue;
                flag = true;
                tmE.showPEname = tPEname;
                tmE.mainPEname = tPEname;
                tmE.PEname.Clear();
                tmE.PEname.Add(tPEname, 1);
                mUcrt.SetmEx(feDGVC.RowIndex, tmE);
                FlashdGVmainRow(feDGVC.RowIndex);
            }
            if (flag)
            {
                FlashdGVQ();
                UpdateUnit("批量修改围护原则");
            }
        }
        private void 选择地基处理原则ToolStripMenuItem_DropDownItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
            ToolStripItem tTSI = e.ClickedItem;
            string tPFname = tTSI.Text;
            bool flag = false;
            foreach (DataGridViewCell feDGVC in dGVmain.SelectedCells)
            {
                mcElement tmE = mUcrt.Element(feDGVC.RowIndex);
                if (tmE == null) continue;
                if (tmE.showPFname == tPFname) continue;
                flag = true;
                tmE.showPFname = tPFname;
                tmE.PFname.Clear();
                tmE.PFname.Add(tPFname, 1);
                mUcrt.SetmEx(feDGVC.RowIndex, tmE);
                FlashdGVmainRow(feDGVC.RowIndex);
            }
            if (flag)
            {
                FlashdGVQ();
                UpdateUnit("批量修改地基原则");
            }
        }
        #endregion

        #region 原则格式刷
        private void 应用沟槽围护原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            PastePCP(ePastePCP.PE);
        }
        private void 应用地基处理原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            PastePCP(ePastePCP.PF);
        }
        private void 应用沟槽及地基原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            PastePCP(ePastePCP.PE);
            PastePCP(ePastePCP.PF);
        }
        private void 复制原则ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            CopyPCP();
        }

        #endregion

        #region 复制粘贴
        private void 复制ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Copy();
        }
        private void 剪切ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Copy();
            Delete("剪切元素");
        }
        private void 粘贴ToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Paste();
        }
        #endregion
        private void 选择管道类型ToolStripMenuItem_DropDownItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
            var crtCell = dGVmain.CurrentCell;
            if (crtCell == null) return;
            mcElement tmE = mUcrt.Element(crtCell.RowIndex);
            if (tmE == null) return;
            crtCell = dGVpipe.CurrentCell;
            if (crtCell == null) return;
            
            ToolStripItem tTSI = e.ClickedItem;
            string tPipeName = tTSI.Text;
            tmE.Pipe(crtCell.RowIndex).Mat = tPipeName;
            UpdateUnit("选择管道材质");
            FlashdGVmainRow(dGVmain.CurrentRow.Index);
            FlashdGVQ();
            FlashdGVpipeRow(crtCell.RowIndex, tmE.Pipe(crtCell.RowIndex));
            FlashSectionPic();
        }


        #endregion


    }
}
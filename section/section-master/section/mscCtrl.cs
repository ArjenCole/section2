using section.mcEmail;
using System;
using System.Collections.Generic;
using System.Configuration;
using System.IO;
using System.Linq;
using System.Text;

using System.Windows.Forms;

namespace section
{
    public static class mscCtrl
    {
        private static mcDataCarrier dc;
        public static mcDataCarrier DC { get { return dc; } }

        private static bool filechanged = false;
        public static bool fileChanged { get { return filechanged; } }

        public static bool Th_CompleteOpen = false;//用于确认数据载入，确认后关闭formCover

        public static FormMdi formMdi;
        public static FormSum formSum;


        #region 文件操作

        public static bool New()
        {
            if (!DealWithCurrentFile()) return false;
            dc = new mcDataCarrier();
            mscLog.OpenFile("New");
            FormNewGuide formNewGuide = new FormNewGuide();
            formNewGuide.ShowDialog();
            Add(new mcPcpEnclosure());
            Add(new mcPcpFoundation());

            FileChange();
            mscDirtyShutDown.AddRecord("", dc.BackupFile);
            mscRecorder<mcDataCarrier>.Ini(dc, RecorderInfo("新建文件:" + dc.BI.ProjectName, string.Empty, string.Empty, string.Empty, string.Empty));
            return true;
        }
        public static bool Open()
        {
            if (!DealWithCurrentFile())  return false;
            string tOpenPath = getOpenPath();
            if (tOpenPath != string.Empty) 
            {
                Open(tOpenPath);
                //filechanged = false;
                //mscRecorder<mcDataCarrier>.Ini(dc, RecorderInfo("打开文件", string.Empty, string.Empty, string.Empty, string.Empty));
                //mscLog.Start();
                return true;
            }
            return false;
        }
        public static string getOpenPath(string pFilter = "*.stn|*.stn", string pPath = "")
        {
            using (OpenFileDialog OFD = new OpenFileDialog())
            {
                OFD.Filter = pFilter;
                //OFD.InitialDirectory = pPath == "" ? Environment.GetFolderPath(Environment.SpecialFolder.Desktop) : pPath;
                if (pPath != "") OFD.InitialDirectory = pPath;
                if (OFD.ShowDialog() == DialogResult.OK)
                    return OFD.FileName;
                else
                    return string.Empty;
            }   
        }
        public static void Open(string pFilePath)
        {
            string tFilePath = pFilePath;
            string tBackupPath = mscDirtyShutDown.CheckDirty(pFilePath);
            if (tBackupPath != "") tFilePath = tBackupPath;

            dc = mscXML.ReadXml(tFilePath);
            dc.BI.FilePath = tFilePath;
            filechanged = false;
            mscLog.OpenFile(tFilePath);
            mscDirtyShutDown.AddRecord(tFilePath, dc.BackupFile);
            mscRecorder<mcDataCarrier>.Ini(dc, RecorderInfo("打开文件:" + dc.BI.ProjectName, string.Empty, string.Empty, string.Empty, string.Empty));
            versionCtrl();
        }
        public static void Save()
        {
            if (dc.BI.FilePath == string.Empty)
                dc.BI.FilePath = getSavePath(dc.BI.ProjectName);
            if (dc.BI.FilePath != string.Empty)
            {
                mscXML.SaveXml(dc.toXML(), dc.BI.FilePath);
                filechanged = false;
            }
        }
        public static void SaveAs()
        {
            string tPath = getSavePath(dc.BI.ProjectName);
            if (tPath != string.Empty)
            {
                dc.BI.FilePath = tPath;
                mscXML.SaveXml(dc.toXML(), dc.BI.FilePath);
                filechanged = false;
            }
        }
        public static string getSavePath(string pFileName = "", string pFilter = "*.stn|*.stn")
        {
            //保存对话框获取保存地址
            using (SaveFileDialog SFD = new SaveFileDialog())
            {
                SFD.Filter = pFilter;
                SFD.FileName = pFileName;
                if (SFD.ShowDialog() == DialogResult.OK)
                    return SFD.FileName;
                else
                    return string.Empty;
            }   
        }
        public static bool Close()
        {
            if (!DealWithCurrentFile()) return false;
            close();
            return true;
        }
        private static void close()
        {
            if (dc == null) return;
            if (fileChanged) File.Delete(dc.BackupFile);

            //SetDirtyShutDown(false);
            mscDirtyShutDown.Close(dc.BI.FilePath);
            
            dc = null; filechanged = false;
            formMdi.CloseAllSubWindows();
            formMdi.FlashUI();
            
            //mscLog.End();

            
        }
        private static bool DealWithCurrentFile()
        {
            if(filechanged)
            {
                DialogResult tMB = MessageBox.Show("当前文档的编辑尚未被保存,是否保存后执行剩余操作?", "提示",
                                                        MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question);
                switch (tMB)
                {
                    case DialogResult.None:
                        return false;
                    case DialogResult.Cancel:
                        return false;
                    case DialogResult.Yes:
                        Save();
                        close();
                        return true;
                    case DialogResult.No:
                        close();
                        return true;
                }
            }
            close();
            return true;
        }
        #endregion

        public static void Regedit()
        {
            string tAppPath = formMdi.GetType().Assembly.Location;
            if (!mscRegistry.SearchValueRegEdit(".stn\\shell\\open\\command", tAppPath)) 
            {
                if (MessageBox.Show("检测到本程序未关联stn文件，是否注册关联?", "提示"
                    , MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                {
                    string tExtName = ".stn";
                    string tType = "section 项目文件";
                    string tContent = "section/project";
                    string tIcoPath = System.Windows.Forms.Application.StartupPath + @"\Res\sFile.ico";
                    mscRegistry.FileAssociation(tAppPath, tExtName, tType, tContent, tIcoPath);
                }
            }
        }
        #region 增加节点
        public static void Add(mcUnit pmU)
        {
            mcSegment tmS = dc.Segment(pmU.OwnerName);
            if (tmS == null) { return; }
            pmU.Name = mscMslns.ReNameToAdd(tmS.UnitNames, pmU.Name);
            tmS.Add(pmU);
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("增加单位工程", pmU.OwnerName, pmU.Name, string.Empty, string.Empty));
            FileChange();
        }
        public static void Add(mcSegment pmS)
        {
            pmS.Name = mscMslns.ReNameToAdd(dc.SegmentNames, pmS.Name);
            dc.Add(pmS);
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("增加标段", pmS.Name, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void Add(mcPcpEnclosure pmPE)
        {
            pmPE.Name = mscMslns.ReNameToAdd(dc.PE.Keys.ToList(), pmPE.Name);
            dc.PE.Add(pmPE.Name, pmPE);
            formMdi.FlashPrincpleTab();
            formMdi.FlashSubfmUnit();
            formMdi.FlashSubfmSumTV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("增加沟槽围护原则", string.Empty, string.Empty, pmPE.Name, string.Empty));
            FileChange();
        }
        public static void Add(mcPcpFoundation pmPF)
        {
            pmPF.Name = mscMslns.ReNameToAdd(dc.PF.Keys.ToList(), pmPF.Name);
            dc.PF.Add(pmPF.Name, pmPF);
            formMdi.FlashPrincpleTab();
            formMdi.FlashSubfmUnit();
            formMdi.FlashSubfmSumTV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("增加地基处理原则", string.Empty, string.Empty, string.Empty, pmPF.Name));
            FileChange();
        }

        #endregion
        #region 删除节点
        public static void Delete(mcUnit pmU)
        {
            dc.Segment(pmU.OwnerName).mList.Remove(pmU);
            formMdi.FlashSubfmUnit();
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("删除单位工程", pmU.OwnerName, pmU.Name, string.Empty, string.Empty));
            FileChange();
        }
        public static void Delete(mcSegment pmS)
        {
            dc.mList.Remove(pmS);
            formMdi.FlashSubfmUnit();
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("删除标段", pmS.Name, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void Delete(mcPcpEnclosure pmPE)
        {
            if (dc.PE.Count == 1)
            {
                MessageBox.Show("至少需要一种沟槽围护原则。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
            }
            else
            {
                string firstPEname = string.Empty;
                foreach (mcPcpEnclosure femPE in dc.PE.Values) 
                {
                    if (femPE.Name != pmPE.Name)
                        firstPEname = femPE.Name;
                }
                if (MessageBox.Show("删除后该原则的引用将被<" + firstPEname + ">替代,确认删除?", "提示", MessageBoxButtons.YesNo, MessageBoxIcon.Question)==DialogResult.Yes)
                {
                    string tName = pmPE.Name;
                    dc.PE.Remove(tName);
                    foreach (mcSegment femS in dc.mList)
                    {
                        foreach (mcUnit femU in femS.mList)
                        {
                            foreach (mcElement femE in femU.mList)
                            {
                                if (femE.PEname.Keys.Contains(tName))
                                {
                                    double tValue = femE.PEname[tName];
                                    femE.PEname.Remove(tName);
                                    if (femE.PEname.Keys.Contains(firstPEname))
                                        femE.PEname[firstPEname] += tValue;
                                    else
                                        femE.PEname.Add(firstPEname, tValue);
                                    if (femE.showPEname == tName) { femE.showPEname = firstPEname; }
                                    if (femE.mainPEname == tName) { femE.mainPEname = firstPEname; }
                                }
                            }
                        }
                    }
                    formMdi.FlashPrincpleTab();
                    formMdi.FlashSubfmUnit();
                    formMdi.FlashSubfmSumDGV();
                    mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("删除沟槽围护原则", string.Empty, string.Empty, pmPE.Name, string.Empty));
                    FileChange();
                }
            }
        }
        public static void Delete(mcPcpFoundation pmPF)
        {
            if (dc.PF.Count == 1)
            {
                MessageBox.Show("至少需要一种地基处理原则。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
            }
            else
            {
                string firstPFname = string.Empty;
                foreach (mcPcpFoundation femPF in dc.PF.Values)
                {
                    if (femPF.Name != pmPF.Name)
                        firstPFname = femPF.Name;
                }

                if (MessageBox.Show("删除后该原则的引用将被<" + firstPFname + ">替代,确认删除?", "提示", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                {
                    string tName = pmPF.Name;
                    dc.PF.Remove(tName);
                    foreach (mcSegment femS in dc.mList)
                    {
                        foreach (mcUnit femU in femS.mList)
                        {
                            foreach (mcElement femE in femU.mList)
                            {
                                if (femE.PFname.Keys.Contains(tName))
                                {
                                    double tValue = femE.PFname[tName];
                                    femE.PFname.Remove(tName);
                                    if (femE.PFname.Keys.Contains(firstPFname))
                                        femE.PFname[firstPFname] += tValue;
                                    else
                                        femE.PFname.Add(firstPFname, tValue);
                                    if (femE.showPFname == tName) { femE.showPFname = firstPFname; }
                                }
                            }
                        }
                    }
                    formMdi.FlashPrincpleTab();
                    formMdi.FlashSubfmUnit();
                    formMdi.FlashSubfmSumDGV();
                    mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("删除地基处理原则", string.Empty, string.Empty, string.Empty, pmPF.Name));
                    FileChange();
                }
            }
        }
        #endregion
        #region 替换节点
        public static void Set(mcBasicInfo pmB, string pDiscribe)
        {
            pmB.FilePath = dc.BI.FilePath;
            dc.BI = pmB;
            formMdi.FlashFormMdiTxt();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo(pDiscribe, string.Empty, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void Set(string pOrigName, mcUnit pmU, string pDisribe)
        {
            mcSegment tmS = dc.Segment(pmU.OwnerName);
            int tIdx= tmS.mList.FindIndex(t => t.Name == pOrigName);
            tmS.mList[tIdx] = pmU;
            formMdi.FlashSubfmUnitTxt(pmU.OwnerName, pmU.OwnerName, pOrigName, pmU.Name);
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo(pDisribe, pmU.OwnerName, pmU.Name, string.Empty, string.Empty));
            FileChange();
        }
        public static void Set(string pOrigName, mcSegment pmS)
        {
            int tIdx = dc.mList.FindIndex(t => t.Name == pOrigName);
            dc.mList[tIdx] = pmS;
            formMdi.FlashSubfmUnitTxt(pOrigName, pmS.Name, string.Empty, string.Empty);
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("编辑标段", pmS.Name, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void Set(string pOrigName, mcPcpEnclosure pmPE)
        {
            if(pOrigName==pmPE.Name)
            {
                dc.PE[pOrigName] = pmPE;
                formMdi.FlashSubfmUnit();
            }   
            else
            {
                foreach (mcSegment femS in dc.mList)
                {
                    foreach (mcUnit femU in femS.mList)
                    {
                        foreach (mcElement femE in femU.mList)
                        {
                            if (femE.PEname.Keys.Contains(pOrigName))
                            {
                                double tValue = femE.PEname[pOrigName];
                                femE.PEname.Remove(pOrigName);
                                femE.PEname.Add(pmPE.Name, tValue);
                                if (femE.showPEname == pOrigName) { femE.showPEname = pmPE.Name; }
                                if (femE.mainPEname == pOrigName) { femE.mainPEname = pmPE.Name; }
                            }
                        }
                    }
                }
                dc.PE.Remove(pOrigName);
                Add(pmPE);
            }
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("编辑沟槽围护原则", string.Empty, string.Empty, pmPE.Name, string.Empty));
            FileChange();
        }
        public static void Set(string pOrigName, mcPcpFoundation pmPF)
        {
            if (pOrigName == pmPF.Name)
            {
                dc.PF[pOrigName] = pmPF;
                formMdi.FlashSubfmUnit();
            }
            else
            {
                foreach (mcSegment femS in dc.mList)
                {
                    foreach (mcUnit femU in femS.mList)
                    {
                        foreach (mcElement femE in femU.mList)
                        {
                            if (femE.PFname.Keys.Contains(pOrigName))
                            {
                                double tValue = femE.PFname[pOrigName];
                                femE.PFname.Remove(pOrigName);
                                femE.PFname.Add(pmPF.Name, tValue);
                                if (femE.showPFname == pOrigName) { femE.showPFname = pmPF.Name; }
                            }
                        }
                    }
                }
                dc.PF.Remove(pOrigName);
                Add(pmPF);
            }
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("编辑地基处理原则", string.Empty, string.Empty, string.Empty, pmPF.Name));
            FileChange();
        }
        #endregion
        #region 移动节点
        public static void MoveUp(string pSname, string pUname)
        {
            mcSegment tmS = dc.Segment(pSname);
            int tIdx = tmS.mList.FindIndex(t => t.Name == pUname);
            tmS.MoveUp(tIdx);
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("上移单位工程", pSname, pUname, string.Empty, string.Empty));
            FileChange();
        }
        public static void MoveUp(string pSname)
        {
            int tIdx = dc.mList.FindIndex(t => t.Name == pSname);
            dc.MoveUp(tIdx);
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("上移标段", pSname, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void MoveDown(string pSname, string pUname)
        {
            mcSegment tmS = dc.Segment(pSname);
            int tIdx = tmS.mList.FindIndex(t => t.Name == pUname);
            tmS.MoveDown(tIdx);
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("下移单位工程", pSname, pUname, string.Empty, string.Empty));
            FileChange();
        }
        public static void MoveDown(string pSname)
        {
            int tIdx = dc.mList.FindIndex(t => t.Name == pSname);
            dc.MoveDown(tIdx);
            formMdi.FlashtreeView1();
            formMdi.FlashSubfmSumTV();
            formMdi.FlashSubfmSumDGV();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("下移标段", pSname, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        #endregion
        #region 操作综合单价
        public static double getPrice(string pName)
        {
            if (dc.price.Keys.Contains(pName))
                return dc.price[pName];
            else
                return 0;
        }
        public static void setPrice(string pCat, string pName, string pUnit, double pPrice)
        {
            string tKey = pCat + "|" + pName + "|" + pUnit;
            if (dc.price.Keys.Contains(tKey))
                dc.price[tKey] = pPrice;
            else
                dc.price.Add(tKey, pPrice);
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("修改综合单价", string.Empty, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void setPrice(Dictionary<string, double> pPrice, bool pCover = false)
        {
            foreach (string feKey in pPrice.Keys)
            {
                if (!dc.price.Keys.Contains(feKey))
                {
                    dc.price.Add(feKey, pPrice[feKey]);
                    continue;
                }
                if (pCover) dc.price[feKey] = pPrice[feKey];
            }
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("载入综合单价", string.Empty, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        public static void clearPrice()
        {
            dc.price.Clear();
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("清空综合单价", string.Empty, string.Empty, string.Empty, string.Empty));
            FileChange();
        }
        #endregion
        #region 撤销/重做
        public static void Undo()
        {
            Dictionary<string, string> tDic = new Dictionary<string, string>();
            dc = mscRecorder<mcDataCarrier>.Undo(out tDic);
            flashUI(tDic);
        }
        public static void Redo()
        {
            Dictionary<string, string> tDic = new Dictionary<string, string>();
            dc = mscRecorder<mcDataCarrier>.Redo(out tDic);
            flashUI(tDic);
        }
        private static void flashUI(Dictionary<string, string> pDic)
        {
            if ((dc == null) || (pDic == null))
            {
                return;
            }
            if (pDic["mSname"] + pDic["mUname"] != string.Empty)
            {
                if (pDic["discribe"].Contains("增加") || pDic["discribe"].Contains("删除"))
                    formMdi.FlashtreeView1();
                formMdi.FlashSubfmUnit();
                formMdi.FlashSubfmSumTV();
                formMdi.FlashSubfmSumDGV();
            }
            if (pDic["mPEname"] + pDic["mPFname"] != string.Empty)
            {
                formMdi.FlashPrincpleTab();
                formMdi.FlashSubfmUnit();
                formMdi.FlashSubfmSumDGV();
            }
            if (pDic["discribe"].Contains("综合单价")) 
            {
                formMdi.FlashSubfmSumDGV();
            }
            formMdi.test_print("重做:" + pDic["discribe"]);
            FileChange();
        }
        public static void MultUndo(int pIdx)
        {
            for (int i = 0; i <= pIdx; i++)
                Undo();
        }
        public static void MultRedo(int pIdx)
        {
            for (int i = 0; i <= pIdx; i++)
                Redo();
        }
        private static Dictionary<string, string> RecorderInfo(string pDiscribe, string pmSname, string pmUname, string pmPEname, string pmPFname)
        {
            Dictionary<string, string> info = new Dictionary<string, string>();
            info.Add("discribe", pDiscribe);
            info.Add("mSname", pmSname);
            info.Add("mUname", pmUname);
            info.Add("mPEname", pmPEname);
            info.Add("mPFname", pmPFname);
            return info;
        }
        #endregion
        private static void FileChange()
        {
            filechanged = true;
            mscXML.SaveXml(dc.toXML(), dc.BackupFile);
        }
        #region 更新文件版本
        private static void versionCtrl()
        {
            string currentVersion = dc.fileVersion;
            if (string.Compare(dc.fileVersion, System.Reflection.Assembly.GetExecutingAssembly().GetName().Version.ToString()) > 0)
            {
                Th_CompleteOpen = true;//关闭封面窗体
                MessageBox.Show("正在打开的是高版本文件,可能会造成部分功能无法正常使用。" + Environment.NewLine + "[文件版本号:" + dc.fileVersion + "]", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                return;
            }

            if (string.Compare(dc.fileVersion, "1.2.1.1") < 0)//箱涵增加含钢量参数
            {
                version1_2_1_1();
                currentVersion = commitUpdate("1.2.1.1");
            }
            if (string.Compare(dc.fileVersion, "1.2.2.1") < 0)//沟槽工作面描述中，“箱涵”改为“箱涵-管廊”
            {
                version1_2_2_1();
                currentVersion = commitUpdate("1.2.2.1");
            }
            if (string.Compare(dc.fileVersion, "1.4.0.0") < 0)//增加未知构件的工作面宽度
            {
                version1_4_0_0();
                currentVersion = commitUpdate("1.4.0.0");
            }

            if (currentVersion != dc.fileVersion)
            {
                dc.fileVersion = currentVersion;
                Th_CompleteOpen = true;//关闭封面窗体
                MessageBox.Show("打开的是低版本文件,已更新至" + currentVersion + "版本,如需完成更新请保存文件。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
            }
            
        }
        private static void version1_2_1_1()
        {
            foreach (mcSegment femS in dc.mList)
                foreach (mcUnit femU in femS.mList)
                    foreach (mcElement femE in femU.mList)
                        if (femE is mcE3)
                            femE.Param.Add("含钢量 kg/m3", "150");
        }
        private static void version1_2_2_1()
        {
            foreach (mcPcpEnclosure fePE in dc.PE.Values)
                if (fePE.WorkWidth.Keys.Contains("箱涵"))
                {
                    var t = fePE.WorkWidth["箱涵"];
                    fePE.WorkWidth.Remove("箱涵");
                    fePE.WorkWidth.Add("箱涵-管廊", t);
                }
        }
        private static void version1_4_0_0()
        {
            foreach (mcPcpEnclosure fePE in dc.PE.Values)
                if (!fePE.WorkWidth.Keys.Contains("未知构件"))
                {
                    var t = fePE.WorkWidth["混凝土管-刚性接口"];
                    Dictionary<int, double> tmpDic = new Dictionary<int, double>();
                    foreach (KeyValuePair<int, double> feKVP in t)
                        tmpDic.Add(feKVP.Key, feKVP.Value);
                    fePE.WorkWidth.Add("未知构件", tmpDic);
                }
        }
        private static string commitUpdate(string pVersion)
        {
            mscRecorder<mcDataCarrier>.Do(dc, RecorderInfo("更新文件版本至" + pVersion, string.Empty, string.Empty, string.Empty, string.Empty));
            FileChange();
            return pVersion;
        }
        #endregion

        public static void InportDataFromExcel()
        {
            mscExcel.getDT(@"Atlas\06MS201-1.xlsx", "砼管砼基础").Copy();//0
            mscExcel.getDT(@"Atlas\06MS201-1.xlsx", "砼管砂基础").Copy();//1

            mscExcel.getDT(@"Atlas\JC-T 640-1996.xlsx", "砼顶管").Copy();//2

            mscExcel.getDT(@"Atlas\HDPE-PE.xlsx", "HDPE承插式双壁缠绕管").Copy();//3
            mscExcel.getDT(@"Atlas\HDPE-PE.xlsx", "PE管").Copy();//4

            mscExcel.getDT(@"Atlas\06MS201-2.xlsx", "硬聚氯乙烯(PVC-U)管").Copy();//5
            mscExcel.getDT(@"Atlas\06MS201-2.xlsx", "聚氯乙烯(PE)管").Copy();//6
            mscExcel.getDT(@"Atlas\06MS201-2.xlsx", "钢带增强聚乙烯(PE)管").Copy();//7

            mscExcel.getDT(@"Atlas\金属管道.xlsx", "球墨铸铁管").Copy();//8
            mscExcel.getDT(@"Atlas\金属管道.xlsx", "钢管").Copy();//9
            
            mscExcel.getDT(@"Inventory\ComponentInventory.xlsx", "Ei");
            mscExcel.getDT(@"Inventory\ComponentInventory.xlsx", "WSi");
            mscExcel.getDT(@"Inventory\ComponentInventory.xlsx", "Fi");

            mscExcel.getDT(@"Atlas\GB 50268-2008.xlsx", "WorkWidth");
            mscExcel.getDT(@"Atlas\GB 50268-2008.xlsx", "GrooveB");

            mscExcel.getDT(@"Inventory\SteelProducts.xlsx", "SteelProducts");

            mscExcel.getDT(@"Inventory\Price.xlsx", "price");
        }
    }
}

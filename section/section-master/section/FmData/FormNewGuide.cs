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
    public partial class FormNewGuide : Form
    {
        public FormNewGuide()
        {
            InitializeComponent();
            TXTprojectName.Text = mscCtrl.DC.BI.ProjectName;
            TXTprojectIndex.Text = mscCtrl.DC.BI.ProjectIndex;
            TXTauthor.Text = mscCtrl.DC.BI.Author;
            CBatlas.DataSource = mcAtlas.Atlas;
            CBatlas.Text = mscCtrl.DC.BI.AtlasName;
        }

        private void FormNewGuide_KeyUp(object sender, KeyEventArgs e)
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

        private void BTNok_Click(object sender, EventArgs e)
        {
            #region 输入有效性检查
            if (TXTprojectName.Text == string.Empty)
            {
                MessageBox.Show("项目名称不可为空。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                return;
            }
            int segmentCnt = 0;
            try
            {
                segmentCnt = Convert.ToInt32(TXTsegmentCount.Text);
            }
            catch
            {
                MessageBox.Show("标段数量输入有误。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                return;
            }
            if (segmentCnt <= 0)
            {
                MessageBox.Show("标段数量输入有误。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Asterisk);
                return;
            }
            #endregion
            mcBasicInfo tmB = new mcBasicInfo();
            tmB.ProjectName = TXTprojectName.Text;
            tmB.ProjectIndex = TXTprojectIndex.Text;
            tmB.Author = TXTauthor.Text;
            mscCtrl.Set(tmB, "创建项目基本信息");
            for (int i = 1; i <= segmentCnt; i++)
            {
                mcSegment tmS = new mcSegment();
                //tmS = mscCtrl.DC.mList[i - 1];
                foreach (Control col in groupBox2.Controls)
                {
                    if (col is CheckBox)
                    {
                        if (((CheckBox)col).Checked)
                        {
                            mcUnit tmU = new mcUnit(tmS.Name);
                            tmU.Name = col.Text;
                            tmU.OwnerName = tmS.Name;
                            //mscCtrl.Add(tmU);
                            tmS.Add(tmU);
                        }
                    }
                }

                mscCtrl.Add(tmS);
            }
            this.DialogResult = DialogResult.Yes;
            this.Close();

        }
    }
}

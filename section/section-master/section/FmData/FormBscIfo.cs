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
    public partial class FormBscIfo : Form
    {
        public FormBscIfo()
        {
            InitializeComponent();
            TXTprojectName.Text = mscCtrl.DC.BI.ProjectName;
            TXTprojectIndex.Text = mscCtrl.DC.BI.ProjectIndex;
            TXTauthor.Text = mscCtrl.DC.BI.Author;
            CBatlas.DataSource = mcAtlas.Atlas;
            CBatlas.Text = mscCtrl.DC.BI.AtlasName;

            foreach (Control feTB in this.Controls)
                if (feTB is TextBox)
                    feTB.Tag = ((TextBox)feTB).Text;
            CBatlas.Tag = CBatlas.Text;
        }

        private void BTNyes_Click(object sender, EventArgs e)
        {
            bool dataChanged = false;
            DialogResult = DialogResult.Cancel;

            foreach (Control feTB in this.Controls)
                if (feTB is TextBox)
                    if (feTB.Tag.ToString() != ((TextBox)feTB).Text)
                        dataChanged = true;
            if (CBatlas.Tag.ToString() != CBatlas.Text)
                dataChanged = true;

            if (dataChanged)
            {
                mcBasicInfo tmB = new mcBasicInfo();
                tmB.ProjectName = TXTprojectName.Text;
                tmB.ProjectIndex = TXTprojectIndex.Text;
                tmB.Author = TXTauthor.Text;
                tmB.AtlasName = CBatlas.Text;
                mscCtrl.Set(tmB, "编辑项目基本信息");
                DialogResult = DialogResult.Yes;
            }
            this.Close();
        }

        private void BTNcancel_Click(object sender, EventArgs e)
        {
            FormCancel();
        }
        private void TXT_KeyUp(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                    FormCancel();
                    break;
                default:
                    break;
            }
        }
        private void FormCancel()
        {
            DialogResult = DialogResult.Cancel;
            this.Close();
        }
    }
}

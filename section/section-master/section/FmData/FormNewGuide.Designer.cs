namespace section
{
    partial class FormNewGuide
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.label3 = new System.Windows.Forms.Label();
            this.TXTsegmentCount = new System.Windows.Forms.TextBox();
            this.BTNok = new System.Windows.Forms.Button();
            this.groupBox2 = new System.Windows.Forms.GroupBox();
            this.checkBox4 = new System.Windows.Forms.CheckBox();
            this.checkBox3 = new System.Windows.Forms.CheckBox();
            this.checkBox2 = new System.Windows.Forms.CheckBox();
            this.checkBox1 = new System.Windows.Forms.CheckBox();
            this.groupBox1 = new System.Windows.Forms.GroupBox();
            this.LBLauthor = new System.Windows.Forms.Label();
            this.TXTauthor = new System.Windows.Forms.TextBox();
            this.label2 = new System.Windows.Forms.Label();
            this.label1 = new System.Windows.Forms.Label();
            this.TXTprojectIndex = new System.Windows.Forms.TextBox();
            this.TXTprojectName = new System.Windows.Forms.TextBox();
            this.CBatlas = new System.Windows.Forms.ComboBox();
            this.label4 = new System.Windows.Forms.Label();
            this.groupBox2.SuspendLayout();
            this.groupBox1.SuspendLayout();
            this.SuspendLayout();
            // 
            // label3
            // 
            this.label3.AutoSize = true;
            this.label3.Location = new System.Drawing.Point(153, 206);
            this.label3.Name = "label3";
            this.label3.Size = new System.Drawing.Size(53, 12);
            this.label3.TabIndex = 13;
            this.label3.Text = "标段数量";
            // 
            // TXTsegmentCount
            // 
            this.TXTsegmentCount.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTsegmentCount.Location = new System.Drawing.Point(248, 204);
            this.TXTsegmentCount.Name = "TXTsegmentCount";
            this.TXTsegmentCount.Size = new System.Drawing.Size(101, 21);
            this.TXTsegmentCount.TabIndex = 12;
            this.TXTsegmentCount.Text = "1";
            this.TXTsegmentCount.TextAlign = System.Windows.Forms.HorizontalAlignment.Center;
            // 
            // BTNok
            // 
            this.BTNok.Location = new System.Drawing.Point(248, 271);
            this.BTNok.Name = "BTNok";
            this.BTNok.Size = new System.Drawing.Size(101, 32);
            this.BTNok.TabIndex = 11;
            this.BTNok.Text = "完成";
            this.BTNok.UseVisualStyleBackColor = true;
            this.BTNok.Click += new System.EventHandler(this.BTNok_Click);
            // 
            // groupBox2
            // 
            this.groupBox2.Controls.Add(this.checkBox4);
            this.groupBox2.Controls.Add(this.checkBox3);
            this.groupBox2.Controls.Add(this.checkBox2);
            this.groupBox2.Controls.Add(this.checkBox1);
            this.groupBox2.Location = new System.Drawing.Point(14, 185);
            this.groupBox2.Name = "groupBox2";
            this.groupBox2.Size = new System.Drawing.Size(106, 122);
            this.groupBox2.TabIndex = 10;
            this.groupBox2.TabStop = false;
            this.groupBox2.Text = "涵盖专业";
            // 
            // checkBox4
            // 
            this.checkBox4.AutoSize = true;
            this.checkBox4.Checked = true;
            this.checkBox4.CheckState = System.Windows.Forms.CheckState.Checked;
            this.checkBox4.Location = new System.Drawing.Point(25, 20);
            this.checkBox4.Name = "checkBox4";
            this.checkBox4.Size = new System.Drawing.Size(72, 16);
            this.checkBox4.TabIndex = 14;
            this.checkBox4.Text = "雨水工程";
            this.checkBox4.UseVisualStyleBackColor = true;
            // 
            // checkBox3
            // 
            this.checkBox3.AutoSize = true;
            this.checkBox3.Checked = true;
            this.checkBox3.CheckState = System.Windows.Forms.CheckState.Checked;
            this.checkBox3.Location = new System.Drawing.Point(25, 42);
            this.checkBox3.Name = "checkBox3";
            this.checkBox3.Size = new System.Drawing.Size(72, 16);
            this.checkBox3.TabIndex = 13;
            this.checkBox3.Text = "污水工程";
            this.checkBox3.UseVisualStyleBackColor = true;
            // 
            // checkBox2
            // 
            this.checkBox2.AutoSize = true;
            this.checkBox2.Location = new System.Drawing.Point(25, 64);
            this.checkBox2.Name = "checkBox2";
            this.checkBox2.Size = new System.Drawing.Size(72, 16);
            this.checkBox2.TabIndex = 12;
            this.checkBox2.Text = "给水工程";
            this.checkBox2.UseVisualStyleBackColor = true;
            // 
            // checkBox1
            // 
            this.checkBox1.AutoSize = true;
            this.checkBox1.Location = new System.Drawing.Point(25, 86);
            this.checkBox1.Name = "checkBox1";
            this.checkBox1.Size = new System.Drawing.Size(72, 16);
            this.checkBox1.TabIndex = 11;
            this.checkBox1.Text = "中水工程";
            this.checkBox1.UseVisualStyleBackColor = true;
            // 
            // groupBox1
            // 
            this.groupBox1.Controls.Add(this.LBLauthor);
            this.groupBox1.Controls.Add(this.TXTauthor);
            this.groupBox1.Controls.Add(this.label2);
            this.groupBox1.Controls.Add(this.label1);
            this.groupBox1.Controls.Add(this.TXTprojectIndex);
            this.groupBox1.Controls.Add(this.TXTprojectName);
            this.groupBox1.Location = new System.Drawing.Point(14, 17);
            this.groupBox1.Name = "groupBox1";
            this.groupBox1.Size = new System.Drawing.Size(350, 156);
            this.groupBox1.TabIndex = 9;
            this.groupBox1.TabStop = false;
            this.groupBox1.Text = "项目基本信息";
            // 
            // LBLauthor
            // 
            this.LBLauthor.AutoSize = true;
            this.LBLauthor.Location = new System.Drawing.Point(21, 120);
            this.LBLauthor.Name = "LBLauthor";
            this.LBLauthor.Size = new System.Drawing.Size(41, 12);
            this.LBLauthor.TabIndex = 5;
            this.LBLauthor.Text = "编制人";
            // 
            // TXTauthor
            // 
            this.TXTauthor.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTauthor.Location = new System.Drawing.Point(92, 116);
            this.TXTauthor.Name = "TXTauthor";
            this.TXTauthor.Size = new System.Drawing.Size(91, 21);
            this.TXTauthor.TabIndex = 4;
            // 
            // label2
            // 
            this.label2.AutoSize = true;
            this.label2.Location = new System.Drawing.Point(21, 82);
            this.label2.Name = "label2";
            this.label2.Size = new System.Drawing.Size(53, 12);
            this.label2.TabIndex = 3;
            this.label2.Text = "项目编号";
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Location = new System.Drawing.Point(21, 34);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(53, 12);
            this.label1.TabIndex = 2;
            this.label1.Text = "项目名称";
            // 
            // TXTprojectIndex
            // 
            this.TXTprojectIndex.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTprojectIndex.Location = new System.Drawing.Point(92, 74);
            this.TXTprojectIndex.Name = "TXTprojectIndex";
            this.TXTprojectIndex.Size = new System.Drawing.Size(91, 21);
            this.TXTprojectIndex.TabIndex = 1;
            // 
            // TXTprojectName
            // 
            this.TXTprojectName.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTprojectName.Location = new System.Drawing.Point(92, 32);
            this.TXTprojectName.Name = "TXTprojectName";
            this.TXTprojectName.Size = new System.Drawing.Size(231, 21);
            this.TXTprojectName.TabIndex = 0;
            this.TXTprojectName.Text = "新建项目";
            // 
            // CBatlas
            // 
            this.CBatlas.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBatlas.FormattingEnabled = true;
            this.CBatlas.Location = new System.Drawing.Point(248, 236);
            this.CBatlas.Name = "CBatlas";
            this.CBatlas.Size = new System.Drawing.Size(101, 20);
            this.CBatlas.TabIndex = 15;
            this.CBatlas.Visible = false;
            // 
            // label4
            // 
            this.label4.AutoSize = true;
            this.label4.Location = new System.Drawing.Point(153, 239);
            this.label4.Name = "label4";
            this.label4.Size = new System.Drawing.Size(53, 12);
            this.label4.TabIndex = 14;
            this.label4.Text = "通用图集";
            this.label4.Visible = false;
            // 
            // FormNewGuide
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(383, 332);
            this.Controls.Add(this.CBatlas);
            this.Controls.Add(this.label3);
            this.Controls.Add(this.label4);
            this.Controls.Add(this.TXTsegmentCount);
            this.Controls.Add(this.BTNok);
            this.Controls.Add(this.groupBox2);
            this.Controls.Add(this.groupBox1);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormNewGuide";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "新建向导";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormNewGuide_KeyUp);
            this.groupBox2.ResumeLayout(false);
            this.groupBox2.PerformLayout();
            this.groupBox1.ResumeLayout(false);
            this.groupBox1.PerformLayout();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Label label3;
        private System.Windows.Forms.TextBox TXTsegmentCount;
        private System.Windows.Forms.Button BTNok;
        private System.Windows.Forms.GroupBox groupBox2;
        private System.Windows.Forms.CheckBox checkBox4;
        private System.Windows.Forms.CheckBox checkBox3;
        private System.Windows.Forms.CheckBox checkBox2;
        private System.Windows.Forms.CheckBox checkBox1;
        private System.Windows.Forms.GroupBox groupBox1;
        private System.Windows.Forms.Label label2;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.TextBox TXTprojectIndex;
        private System.Windows.Forms.TextBox TXTprojectName;
        private System.Windows.Forms.Label LBLauthor;
        private System.Windows.Forms.TextBox TXTauthor;
        private System.Windows.Forms.ComboBox CBatlas;
        private System.Windows.Forms.Label label4;
    }
}
namespace section2.FmTool
{
    partial class FmGuide
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
            this.CBatlas = new System.Windows.Forms.ComboBox();
            this.label3 = new System.Windows.Forms.Label();
            this.label4 = new System.Windows.Forms.Label();
            this.TXTsegmentCount = new System.Windows.Forms.TextBox();
            this.BTNok = new System.Windows.Forms.Button();
            this.GBcat = new System.Windows.Forms.GroupBox();
            this.CBrain = new System.Windows.Forms.CheckBox();
            this.CBsewageWork = new System.Windows.Forms.CheckBox();
            this.CBwaterSupply = new System.Windows.Forms.CheckBox();
            this.checkBox1 = new System.Windows.Forms.CheckBox();
            this.groupBox1 = new System.Windows.Forms.GroupBox();
            this.LBLauthor = new System.Windows.Forms.Label();
            this.TXTdesigner = new System.Windows.Forms.TextBox();
            this.label2 = new System.Windows.Forms.Label();
            this.label1 = new System.Windows.Forms.Label();
            this.TXTprojectIndex = new System.Windows.Forms.TextBox();
            this.TXTprojectName = new System.Windows.Forms.TextBox();
            this.GBcat.SuspendLayout();
            this.groupBox1.SuspendLayout();
            this.SuspendLayout();
            // 
            // CBatlas
            // 
            this.CBatlas.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBatlas.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.CBatlas.FormattingEnabled = true;
            this.CBatlas.Location = new System.Drawing.Point(246, 231);
            this.CBatlas.Name = "CBatlas";
            this.CBatlas.Size = new System.Drawing.Size(101, 20);
            this.CBatlas.TabIndex = 22;
            this.CBatlas.Visible = false;
            // 
            // label3
            // 
            this.label3.AutoSize = true;
            this.label3.Location = new System.Drawing.Point(151, 201);
            this.label3.Name = "label3";
            this.label3.Size = new System.Drawing.Size(53, 12);
            this.label3.TabIndex = 20;
            this.label3.Text = "标段数量";
            // 
            // label4
            // 
            this.label4.AutoSize = true;
            this.label4.Location = new System.Drawing.Point(151, 234);
            this.label4.Name = "label4";
            this.label4.Size = new System.Drawing.Size(53, 12);
            this.label4.TabIndex = 21;
            this.label4.Text = "通用图集";
            this.label4.Visible = false;
            // 
            // TXTsegmentCount
            // 
            this.TXTsegmentCount.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTsegmentCount.Location = new System.Drawing.Point(246, 199);
            this.TXTsegmentCount.Name = "TXTsegmentCount";
            this.TXTsegmentCount.Size = new System.Drawing.Size(101, 21);
            this.TXTsegmentCount.TabIndex = 19;
            this.TXTsegmentCount.Text = "1";
            this.TXTsegmentCount.TextAlign = System.Windows.Forms.HorizontalAlignment.Center;
            // 
            // BTNok
            // 
            this.BTNok.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNok.Location = new System.Drawing.Point(246, 266);
            this.BTNok.Name = "BTNok";
            this.BTNok.Size = new System.Drawing.Size(101, 32);
            this.BTNok.TabIndex = 18;
            this.BTNok.Text = "完成";
            this.BTNok.UseVisualStyleBackColor = true;
            this.BTNok.Click += new System.EventHandler(this.BTNok_Click);
            // 
            // GBcat
            // 
            this.GBcat.Controls.Add(this.CBrain);
            this.GBcat.Controls.Add(this.CBsewageWork);
            this.GBcat.Controls.Add(this.CBwaterSupply);
            this.GBcat.Controls.Add(this.checkBox1);
            this.GBcat.Location = new System.Drawing.Point(12, 180);
            this.GBcat.Name = "GBcat";
            this.GBcat.Size = new System.Drawing.Size(106, 122);
            this.GBcat.TabIndex = 17;
            this.GBcat.TabStop = false;
            this.GBcat.Text = "涵盖专业";
            // 
            // CBrain
            // 
            this.CBrain.AutoSize = true;
            this.CBrain.Checked = true;
            this.CBrain.CheckState = System.Windows.Forms.CheckState.Checked;
            this.CBrain.Location = new System.Drawing.Point(25, 20);
            this.CBrain.Name = "CBrain";
            this.CBrain.Size = new System.Drawing.Size(72, 16);
            this.CBrain.TabIndex = 14;
            this.CBrain.Text = "雨水工程";
            this.CBrain.UseVisualStyleBackColor = true;
            // 
            // CBsewageWork
            // 
            this.CBsewageWork.AutoSize = true;
            this.CBsewageWork.Checked = true;
            this.CBsewageWork.CheckState = System.Windows.Forms.CheckState.Checked;
            this.CBsewageWork.Location = new System.Drawing.Point(25, 42);
            this.CBsewageWork.Name = "CBsewageWork";
            this.CBsewageWork.Size = new System.Drawing.Size(72, 16);
            this.CBsewageWork.TabIndex = 13;
            this.CBsewageWork.Text = "污水工程";
            this.CBsewageWork.UseVisualStyleBackColor = true;
            // 
            // CBwaterSupply
            // 
            this.CBwaterSupply.AutoSize = true;
            this.CBwaterSupply.Location = new System.Drawing.Point(25, 64);
            this.CBwaterSupply.Name = "CBwaterSupply";
            this.CBwaterSupply.Size = new System.Drawing.Size(72, 16);
            this.CBwaterSupply.TabIndex = 12;
            this.CBwaterSupply.Text = "给水工程";
            this.CBwaterSupply.UseVisualStyleBackColor = true;
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
            this.groupBox1.Controls.Add(this.TXTdesigner);
            this.groupBox1.Controls.Add(this.label2);
            this.groupBox1.Controls.Add(this.label1);
            this.groupBox1.Controls.Add(this.TXTprojectIndex);
            this.groupBox1.Controls.Add(this.TXTprojectName);
            this.groupBox1.Location = new System.Drawing.Point(12, 12);
            this.groupBox1.Name = "groupBox1";
            this.groupBox1.Size = new System.Drawing.Size(350, 156);
            this.groupBox1.TabIndex = 16;
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
            // TXTdesigner
            // 
            this.TXTdesigner.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTdesigner.Location = new System.Drawing.Point(92, 116);
            this.TXTdesigner.Name = "TXTdesigner";
            this.TXTdesigner.Size = new System.Drawing.Size(91, 21);
            this.TXTdesigner.TabIndex = 4;
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
            // FmGuide
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(376, 316);
            this.Controls.Add(this.CBatlas);
            this.Controls.Add(this.label3);
            this.Controls.Add(this.label4);
            this.Controls.Add(this.TXTsegmentCount);
            this.Controls.Add(this.BTNok);
            this.Controls.Add(this.GBcat);
            this.Controls.Add(this.groupBox1);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.Name = "FmGuide";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "FmGuide";
            this.GBcat.ResumeLayout(false);
            this.GBcat.PerformLayout();
            this.groupBox1.ResumeLayout(false);
            this.groupBox1.PerformLayout();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.ComboBox CBatlas;
        private System.Windows.Forms.Label label3;
        private System.Windows.Forms.Label label4;
        private System.Windows.Forms.TextBox TXTsegmentCount;
        private System.Windows.Forms.Button BTNok;
        private System.Windows.Forms.GroupBox GBcat;
        private System.Windows.Forms.CheckBox CBrain;
        private System.Windows.Forms.CheckBox CBsewageWork;
        private System.Windows.Forms.CheckBox CBwaterSupply;
        private System.Windows.Forms.CheckBox checkBox1;
        private System.Windows.Forms.GroupBox groupBox1;
        private System.Windows.Forms.Label LBLauthor;
        private System.Windows.Forms.TextBox TXTdesigner;
        private System.Windows.Forms.Label label2;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.TextBox TXTprojectIndex;
        private System.Windows.Forms.TextBox TXTprojectName;
    }
}
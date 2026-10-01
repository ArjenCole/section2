namespace section
{
    partial class FormBscIfo
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
            this.BTNyes = new System.Windows.Forms.Button();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.label2 = new System.Windows.Forms.Label();
            this.label1 = new System.Windows.Forms.Label();
            this.TXTprojectIndex = new System.Windows.Forms.TextBox();
            this.TXTprojectName = new System.Windows.Forms.TextBox();
            this.CBatlas = new System.Windows.Forms.ComboBox();
            this.label3 = new System.Windows.Forms.Label();
            this.LBLauthor = new System.Windows.Forms.Label();
            this.TXTauthor = new System.Windows.Forms.TextBox();
            this.SuspendLayout();
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(156, 189);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(75, 23);
            this.BTNyes.TabIndex = 4;
            this.BTNyes.Text = "确定";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(237, 190);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(75, 23);
            this.BTNcancel.TabIndex = 5;
            this.BTNcancel.Text = "取消";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // label2
            // 
            this.label2.AutoSize = true;
            this.label2.Location = new System.Drawing.Point(12, 57);
            this.label2.Name = "label2";
            this.label2.Size = new System.Drawing.Size(53, 12);
            this.label2.TabIndex = 9;
            this.label2.Text = "项目编号";
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Location = new System.Drawing.Point(12, 23);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(53, 12);
            this.label1.TabIndex = 8;
            this.label1.Text = "项目名称";
            // 
            // TXTprojectIndex
            // 
            this.TXTprojectIndex.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTprojectIndex.Location = new System.Drawing.Point(81, 55);
            this.TXTprojectIndex.Name = "TXTprojectIndex";
            this.TXTprojectIndex.Size = new System.Drawing.Size(231, 21);
            this.TXTprojectIndex.TabIndex = 7;
            // 
            // TXTprojectName
            // 
            this.TXTprojectName.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTprojectName.Location = new System.Drawing.Point(81, 21);
            this.TXTprojectName.Name = "TXTprojectName";
            this.TXTprojectName.Size = new System.Drawing.Size(231, 21);
            this.TXTprojectName.TabIndex = 6;
            this.TXTprojectName.Text = "新建项目";
            // 
            // CBatlas
            // 
            this.CBatlas.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBatlas.FormattingEnabled = true;
            this.CBatlas.Location = new System.Drawing.Point(107, 135);
            this.CBatlas.Name = "CBatlas";
            this.CBatlas.Size = new System.Drawing.Size(205, 20);
            this.CBatlas.TabIndex = 13;
            // 
            // label3
            // 
            this.label3.AutoSize = true;
            this.label3.Location = new System.Drawing.Point(12, 138);
            this.label3.Name = "label3";
            this.label3.Size = new System.Drawing.Size(77, 12);
            this.label3.TabIndex = 12;
            this.label3.Text = "通用图集编号";
            // 
            // LBLauthor
            // 
            this.LBLauthor.AutoSize = true;
            this.LBLauthor.Location = new System.Drawing.Point(12, 96);
            this.LBLauthor.Name = "LBLauthor";
            this.LBLauthor.Size = new System.Drawing.Size(41, 12);
            this.LBLauthor.TabIndex = 15;
            this.LBLauthor.Text = "编制人";
            // 
            // TXTauthor
            // 
            this.TXTauthor.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.TXTauthor.Location = new System.Drawing.Point(81, 94);
            this.TXTauthor.Name = "TXTauthor";
            this.TXTauthor.Size = new System.Drawing.Size(231, 21);
            this.TXTauthor.TabIndex = 14;
            // 
            // FormBscIfo
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(340, 259);
            this.Controls.Add(this.LBLauthor);
            this.Controls.Add(this.TXTauthor);
            this.Controls.Add(this.CBatlas);
            this.Controls.Add(this.label3);
            this.Controls.Add(this.label2);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.TXTprojectIndex);
            this.Controls.Add(this.TXTprojectName);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.BTNcancel);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormBscIfo";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "项目基本信息";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.TXT_KeyUp);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Label label2;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.TextBox TXTprojectIndex;
        private System.Windows.Forms.TextBox TXTprojectName;
        private System.Windows.Forms.ComboBox CBatlas;
        private System.Windows.Forms.Label label3;
        private System.Windows.Forms.Label LBLauthor;
        private System.Windows.Forms.TextBox TXTauthor;
    }
}
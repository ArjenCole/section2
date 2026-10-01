namespace section
{
    partial class FormPF
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle1 = new System.Windows.Forms.DataGridViewCellStyle();
            this.dGVR = new System.Windows.Forms.DataGridView();
            this.Column1 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Column2 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.CBOcpnt = new System.Windows.Forms.ComboBox();
            this.LBLcpnt = new System.Windows.Forms.Label();
            this.BTNadd = new System.Windows.Forms.Button();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.BTNyes = new System.Windows.Forms.Button();
            this.TXTPFname = new System.Windows.Forms.TextBox();
            this.LBLPEname = new System.Windows.Forms.Label();
            this.label1 = new System.Windows.Forms.Label();
            this.BTNedit = new System.Windows.Forms.Button();
            ((System.ComponentModel.ISupportInitialize)(this.dGVR)).BeginInit();
            this.SuspendLayout();
            // 
            // dGVR
            // 
            this.dGVR.AllowUserToAddRows = false;
            this.dGVR.AllowUserToDeleteRows = false;
            this.dGVR.AllowUserToResizeColumns = false;
            this.dGVR.AllowUserToResizeRows = false;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle1.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dGVR.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dGVR.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVR.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Column1,
            this.Column2});
            this.dGVR.Location = new System.Drawing.Point(3, 48);
            this.dGVR.Name = "dGVR";
            this.dGVR.RowHeadersVisible = false;
            this.dGVR.RowTemplate.Height = 23;
            this.dGVR.Size = new System.Drawing.Size(293, 226);
            this.dGVR.TabIndex = 1;
            this.dGVR.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVR_CellEndEdit);
            this.dGVR.KeyUp += new System.Windows.Forms.KeyEventHandler(this.dGVR_KeyUp);
            // 
            // Column1
            // 
            this.Column1.HeaderText = "换填材质";
            this.Column1.Name = "Column1";
            this.Column1.Width = 130;
            // 
            // Column2
            // 
            this.Column2.HeaderText = "厚度mm";
            this.Column2.Name = "Column2";
            this.Column2.Width = 120;
            // 
            // CBOcpnt
            // 
            this.CBOcpnt.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBOcpnt.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.CBOcpnt.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.CBOcpnt.FormattingEnabled = true;
            this.CBOcpnt.Location = new System.Drawing.Point(76, 279);
            this.CBOcpnt.Name = "CBOcpnt";
            this.CBOcpnt.Size = new System.Drawing.Size(123, 25);
            this.CBOcpnt.TabIndex = 54;
            this.CBOcpnt.SelectedIndexChanged += new System.EventHandler(this.CBOcpnt_DropDownClosed);
            // 
            // LBLcpnt
            // 
            this.LBLcpnt.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLcpnt.Location = new System.Drawing.Point(3, 328);
            this.LBLcpnt.Name = "LBLcpnt";
            this.LBLcpnt.Size = new System.Drawing.Size(293, 26);
            this.LBLcpnt.TabIndex = 52;
            this.LBLcpnt.Text = "基础角度                 °";
            this.LBLcpnt.DoubleClick += new System.EventHandler(this.LBLcpnt_DoubleClick);
            // 
            // BTNadd
            // 
            this.BTNadd.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNadd.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.BTNadd.Location = new System.Drawing.Point(255, 48);
            this.BTNadd.Name = "BTNadd";
            this.BTNadd.Size = new System.Drawing.Size(41, 30);
            this.BTNadd.TabIndex = 65;
            this.BTNadd.Text = "+";
            this.BTNadd.UseVisualStyleBackColor = true;
            this.BTNadd.Click += new System.EventHandler(this.BTNadd_Click);
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(221, 365);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(75, 23);
            this.BTNcancel.TabIndex = 69;
            this.BTNcancel.Text = "取消修改";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(140, 365);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(75, 23);
            this.BTNyes.TabIndex = 68;
            this.BTNyes.Text = "确认修改";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // TXTPFname
            // 
            this.TXTPFname.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTPFname.Location = new System.Drawing.Point(79, 6);
            this.TXTPFname.Name = "TXTPFname";
            this.TXTPFname.Size = new System.Drawing.Size(121, 26);
            this.TXTPFname.TabIndex = 71;
            // 
            // LBLPEname
            // 
            this.LBLPEname.AutoSize = true;
            this.LBLPEname.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLPEname.Location = new System.Drawing.Point(-1, 10);
            this.LBLPEname.Name = "LBLPEname";
            this.LBLPEname.Size = new System.Drawing.Size(69, 19);
            this.LBLPEname.TabIndex = 70;
            this.LBLPEname.Text = "原则名称:";
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.label1.Location = new System.Drawing.Point(-1, 281);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(65, 20);
            this.label1.TabIndex = 72;
            this.label1.Text = "特殊地基";
            // 
            // BTNedit
            // 
            this.BTNedit.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNedit.Location = new System.Drawing.Point(221, 280);
            this.BTNedit.Name = "BTNedit";
            this.BTNedit.Size = new System.Drawing.Size(75, 23);
            this.BTNedit.TabIndex = 73;
            this.BTNedit.Text = "编辑";
            this.BTNedit.UseVisualStyleBackColor = true;
            this.BTNedit.Click += new System.EventHandler(this.BTNedit_Click);
            // 
            // FormPF
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(301, 400);
            this.Controls.Add(this.BTNedit);
            this.Controls.Add(this.LBLcpnt);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.CBOcpnt);
            this.Controls.Add(this.TXTPFname);
            this.Controls.Add(this.LBLPEname);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.BTNadd);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.dGVR);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormPF";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "地基处理原则编辑";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormPF_KeyUp);
            ((System.ComponentModel.ISupportInitialize)(this.dGVR)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.DataGridView dGVR;
        private System.Windows.Forms.ComboBox CBOcpnt;
        private System.Windows.Forms.Label LBLcpnt;
        private System.Windows.Forms.Button BTNadd;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.TextBox TXTPFname;
        private System.Windows.Forms.Label LBLPEname;
        private System.Windows.Forms.DataGridViewTextBoxColumn Column1;
        private System.Windows.Forms.DataGridViewTextBoxColumn Column2;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.Button BTNedit;
    }
}
namespace section
{
    partial class FormEcls
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle5 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle3 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle4 = new System.Windows.Forms.DataGridViewCellStyle();
            this.dGVCpnt = new System.Windows.Forms.DataGridView();
            this.ColHfix = new System.Windows.Forms.DataGridViewCheckBoxColumn();
            this.ColH = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColStepWidth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColEclsCat = new System.Windows.Forms.DataGridViewComboBoxColumn();
            this.ColEclsDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.BTNadd = new System.Windows.Forms.Button();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.BTNyes = new System.Windows.Forms.Button();
            ((System.ComponentModel.ISupportInitialize)(this.dGVCpnt)).BeginInit();
            this.SuspendLayout();
            // 
            // dGVCpnt
            // 
            this.dGVCpnt.AllowUserToAddRows = false;
            this.dGVCpnt.AllowUserToDeleteRows = false;
            this.dGVCpnt.AllowUserToResizeColumns = false;
            this.dGVCpnt.AllowUserToResizeRows = false;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle1.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dGVCpnt.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dGVCpnt.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVCpnt.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.ColHfix,
            this.ColH,
            this.ColStepWidth,
            this.ColEclsCat,
            this.ColEclsDis});
            dataGridViewCellStyle5.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle5.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle5.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle5.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle5.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle5.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle5.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dGVCpnt.DefaultCellStyle = dataGridViewCellStyle5;
            this.dGVCpnt.Location = new System.Drawing.Point(12, 12);
            this.dGVCpnt.Name = "dGVCpnt";
            this.dGVCpnt.RowHeadersVisible = false;
            this.dGVCpnt.RowTemplate.Height = 23;
            this.dGVCpnt.Size = new System.Drawing.Size(573, 379);
            this.dGVCpnt.TabIndex = 60;
            this.dGVCpnt.CellClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVCpnt_CellClick);
            this.dGVCpnt.CellContentClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVCpnt_CellContentClick);
            this.dGVCpnt.CellDoubleClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVCpnt_CellDoubleClick);
            this.dGVCpnt.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVCpnt_CellEndEdit);
            this.dGVCpnt.KeyUp += new System.Windows.Forms.KeyEventHandler(this.dGVCpnt_KeyUp);
            // 
            // ColHfix
            // 
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            dataGridViewCellStyle2.NullValue = false;
            this.ColHfix.DefaultCellStyle = dataGridViewCellStyle2;
            this.ColHfix.HeaderText = "固定";
            this.ColHfix.Name = "ColHfix";
            this.ColHfix.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.ColHfix.Width = 60;
            // 
            // ColH
            // 
            dataGridViewCellStyle3.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.ColH.DefaultCellStyle = dataGridViewCellStyle3;
            this.ColH.HeaderText = "高度m";
            this.ColH.Name = "ColH";
            this.ColH.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColH.Width = 70;
            // 
            // ColStepWidth
            // 
            dataGridViewCellStyle4.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.ColStepWidth.DefaultCellStyle = dataGridViewCellStyle4;
            this.ColStepWidth.HeaderText = "平台单侧宽";
            this.ColStepWidth.Name = "ColStepWidth";
            this.ColStepWidth.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            // 
            // ColEclsCat
            // 
            this.ColEclsCat.DisplayStyle = System.Windows.Forms.DataGridViewComboBoxDisplayStyle.ComboBox;
            this.ColEclsCat.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.ColEclsCat.HeaderText = "围护类型";
            this.ColEclsCat.Name = "ColEclsCat";
            // 
            // ColEclsDis
            // 
            this.ColEclsDis.HeaderText = "围护形式描述";
            this.ColEclsDis.Name = "ColEclsDis";
            this.ColEclsDis.ReadOnly = true;
            this.ColEclsDis.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColEclsDis.ToolTipText = "双击编辑围护形式";
            this.ColEclsDis.Width = 200;
            // 
            // BTNadd
            // 
            this.BTNadd.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNadd.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.BTNadd.Location = new System.Drawing.Point(544, 12);
            this.BTNadd.Name = "BTNadd";
            this.BTNadd.Size = new System.Drawing.Size(41, 30);
            this.BTNadd.TabIndex = 61;
            this.BTNadd.Text = "+";
            this.BTNadd.UseVisualStyleBackColor = true;
            this.BTNadd.Click += new System.EventHandler(this.BTNadd_Click);
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(591, 90);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(65, 69);
            this.BTNcancel.TabIndex = 69;
            this.BTNcancel.Text = "取消修改";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(591, 12);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(65, 69);
            this.BTNyes.TabIndex = 68;
            this.BTNyes.Text = "确认修改";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // FormEcls
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(665, 405);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.BTNadd);
            this.Controls.Add(this.dGVCpnt);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormEcls";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "分级围护编辑";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormEcls_KeyUp);
            ((System.ComponentModel.ISupportInitialize)(this.dGVCpnt)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.DataGridView dGVCpnt;
        private System.Windows.Forms.Button BTNadd;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.DataGridViewCheckBoxColumn ColHfix;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColH;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColStepWidth;
        private System.Windows.Forms.DataGridViewComboBoxColumn ColEclsCat;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColEclsDis;
    }
}
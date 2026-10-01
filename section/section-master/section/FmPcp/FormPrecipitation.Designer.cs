namespace section
{
    partial class FormPrecipitation
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle7 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle3 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle4 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle5 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle6 = new System.Windows.Forms.DataGridViewCellStyle();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.BTNyes = new System.Windows.Forms.Button();
            this.dGVPre = new System.Windows.Forms.DataGridView();
            this.LBLpre = new System.Windows.Forms.Label();
            this.ColCheck = new System.Windows.Forms.DataGridViewCheckBoxColumn();
            this.ColMindepth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColRange = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColSides = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColGap = new System.Windows.Forms.DataGridViewTextBoxColumn();
            ((System.ComponentModel.ISupportInitialize)(this.dGVPre)).BeginInit();
            this.SuspendLayout();
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(365, 229);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(65, 27);
            this.BTNcancel.TabIndex = 73;
            this.BTNcancel.Text = "取消修改";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(365, 196);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(65, 27);
            this.BTNyes.TabIndex = 72;
            this.BTNyes.Text = "确认修改";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // dGVPre
            // 
            this.dGVPre.AllowUserToAddRows = false;
            this.dGVPre.AllowUserToDeleteRows = false;
            this.dGVPre.AllowUserToResizeColumns = false;
            this.dGVPre.AllowUserToResizeRows = false;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle1.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dGVPre.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dGVPre.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVPre.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.ColCheck,
            this.ColMindepth,
            this.ColRange,
            this.ColSides,
            this.ColGap});
            dataGridViewCellStyle7.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle7.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle7.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle7.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle7.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle7.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle7.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dGVPre.DefaultCellStyle = dataGridViewCellStyle7;
            this.dGVPre.Dock = System.Windows.Forms.DockStyle.Top;
            this.dGVPre.Location = new System.Drawing.Point(0, 0);
            this.dGVPre.Name = "dGVPre";
            this.dGVPre.RowHeadersWidth = 140;
            this.dGVPre.RowTemplate.Height = 23;
            this.dGVPre.Size = new System.Drawing.Size(442, 147);
            this.dGVPre.TabIndex = 71;
            this.dGVPre.CellContentClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVPre_CellContentClick);
            this.dGVPre.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVPre_CellEndEdit);
            // 
            // LBLpre
            // 
            this.LBLpre.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLpre.Location = new System.Drawing.Point(12, 155);
            this.LBLpre.Name = "LBLpre";
            this.LBLpre.Size = new System.Drawing.Size(347, 110);
            this.LBLpre.TabIndex = 74;
            this.LBLpre.Tag = "";
            this.LBLpre.Text = "降水措施描述";
            // 
            // ColCheck
            // 
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            dataGridViewCellStyle2.NullValue = false;
            this.ColCheck.DefaultCellStyle = dataGridViewCellStyle2;
            this.ColCheck.HeaderText = "选用";
            this.ColCheck.Name = "ColCheck";
            this.ColCheck.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.ColCheck.Width = 60;
            // 
            // ColMindepth
            // 
            dataGridViewCellStyle3.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.ColMindepth.DefaultCellStyle = dataGridViewCellStyle3;
            this.ColMindepth.HeaderText = "埋深";
            this.ColMindepth.Name = "ColMindepth";
            this.ColMindepth.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColMindepth.Width = 60;
            // 
            // ColRange
            // 
            dataGridViewCellStyle4.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.ColRange.DefaultCellStyle = dataGridViewCellStyle4;
            this.ColRange.HeaderText = "范围";
            this.ColRange.Name = "ColRange";
            this.ColRange.ReadOnly = true;
            this.ColRange.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColRange.Width = 60;
            // 
            // ColSides
            // 
            dataGridViewCellStyle5.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.ColSides.DefaultCellStyle = dataGridViewCellStyle5;
            this.ColSides.HeaderText = "道数";
            this.ColSides.Name = "ColSides";
            this.ColSides.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColSides.Width = 60;
            // 
            // ColGap
            // 
            dataGridViewCellStyle6.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.ColGap.DefaultCellStyle = dataGridViewCellStyle6;
            this.ColGap.HeaderText = "间隔";
            this.ColGap.Name = "ColGap";
            this.ColGap.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColGap.Width = 60;
            // 
            // FormPrecipitation
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(442, 268);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.dGVPre);
            this.Controls.Add(this.LBLpre);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormPrecipitation";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "降水编辑";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormPrecipitation_KeyUp);
            ((System.ComponentModel.ISupportInitialize)(this.dGVPre)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.DataGridView dGVPre;
        private System.Windows.Forms.Label LBLpre;
        private System.Windows.Forms.DataGridViewCheckBoxColumn ColCheck;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColMindepth;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColRange;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColSides;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColGap;
    }
}
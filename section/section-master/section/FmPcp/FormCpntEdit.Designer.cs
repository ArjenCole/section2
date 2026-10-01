namespace section
{
    partial class FormCpntEdit
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
            this.components = new System.ComponentModel.Container();
            this.dGVparam = new System.Windows.Forms.DataGridView();
            this.pColKey = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.pColValue = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dGVfomla = new System.Windows.Forms.DataGridView();
            this.fColKey = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.fColValue = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dGVzomla = new System.Windows.Forms.DataGridView();
            this.dataGridViewTextBoxColumn3 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.zColKey = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.BTNyes = new System.Windows.Forms.Button();
            this.CMS = new System.Windows.Forms.ContextMenuStrip(this.components);
            ((System.ComponentModel.ISupportInitialize)(this.dGVparam)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.dGVfomla)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.dGVzomla)).BeginInit();
            this.SuspendLayout();
            // 
            // dGVparam
            // 
            this.dGVparam.AllowUserToAddRows = false;
            this.dGVparam.AllowUserToDeleteRows = false;
            this.dGVparam.AllowUserToResizeColumns = false;
            this.dGVparam.AllowUserToResizeRows = false;
            this.dGVparam.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVparam.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.pColKey,
            this.pColValue});
            this.dGVparam.ContextMenuStrip = this.CMS;
            this.dGVparam.Location = new System.Drawing.Point(12, 22);
            this.dGVparam.Name = "dGVparam";
            this.dGVparam.RowTemplate.Height = 23;
            this.dGVparam.Size = new System.Drawing.Size(343, 369);
            this.dGVparam.TabIndex = 0;
            this.dGVparam.SelectionChanged += new System.EventHandler(this.dGVparam_SelectionChanged);
            // 
            // pColKey
            // 
            this.pColKey.HeaderText = "参数名称";
            this.pColKey.Name = "pColKey";
            this.pColKey.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.pColKey.Width = 150;
            // 
            // pColValue
            // 
            this.pColValue.HeaderText = "参数值";
            this.pColValue.Name = "pColValue";
            this.pColValue.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.pColValue.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.pColValue.Width = 150;
            // 
            // dGVfomla
            // 
            this.dGVfomla.AllowUserToAddRows = false;
            this.dGVfomla.AllowUserToDeleteRows = false;
            this.dGVfomla.AllowUserToResizeColumns = false;
            this.dGVfomla.AllowUserToResizeRows = false;
            this.dGVfomla.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVfomla.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.fColKey,
            this.fColValue});
            this.dGVfomla.Location = new System.Drawing.Point(365, 22);
            this.dGVfomla.Name = "dGVfomla";
            this.dGVfomla.RowHeadersWidth = 50;
            this.dGVfomla.RowTemplate.Height = 23;
            this.dGVfomla.Size = new System.Drawing.Size(552, 187);
            this.dGVfomla.TabIndex = 1;
            // 
            // fColKey
            // 
            this.fColKey.HeaderText = "围护工程量";
            this.fColKey.Name = "fColKey";
            this.fColKey.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.fColKey.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.fColKey.Width = 150;
            // 
            // fColValue
            // 
            this.fColValue.HeaderText = "计算公式";
            this.fColValue.Name = "fColValue";
            this.fColValue.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.fColValue.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.fColValue.Width = 350;
            // 
            // dGVzomla
            // 
            this.dGVzomla.AllowUserToAddRows = false;
            this.dGVzomla.AllowUserToDeleteRows = false;
            this.dGVzomla.AllowUserToResizeColumns = false;
            this.dGVzomla.AllowUserToResizeRows = false;
            this.dGVzomla.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVzomla.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.dataGridViewTextBoxColumn3,
            this.zColKey});
            this.dGVzomla.Location = new System.Drawing.Point(365, 215);
            this.dGVzomla.Name = "dGVzomla";
            this.dGVzomla.RowHeadersWidth = 50;
            this.dGVzomla.RowTemplate.Height = 23;
            this.dGVzomla.Size = new System.Drawing.Size(552, 176);
            this.dGVzomla.TabIndex = 2;
            // 
            // dataGridViewTextBoxColumn3
            // 
            this.dataGridViewTextBoxColumn3.HeaderText = "支撑工程量";
            this.dataGridViewTextBoxColumn3.Name = "dataGridViewTextBoxColumn3";
            this.dataGridViewTextBoxColumn3.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.dataGridViewTextBoxColumn3.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.dataGridViewTextBoxColumn3.Width = 150;
            // 
            // zColKey
            // 
            this.zColKey.HeaderText = "计算公式";
            this.zColKey.Name = "zColKey";
            this.zColKey.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.zColKey.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.zColKey.Width = 350;
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(247, 397);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(65, 30);
            this.BTNcancel.TabIndex = 71;
            this.BTNcancel.Text = "取消修改";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(176, 397);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(65, 30);
            this.BTNyes.TabIndex = 70;
            this.BTNyes.Text = "确认修改";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // CMS
            // 
            this.CMS.Name = "CMS";
            this.CMS.Size = new System.Drawing.Size(153, 26);
            this.CMS.ItemClicked += new System.Windows.Forms.ToolStripItemClickedEventHandler(this.CMS_ItemClicked);
            // 
            // FormCpntEdit
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(921, 430);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.dGVzomla);
            this.Controls.Add(this.dGVfomla);
            this.Controls.Add(this.dGVparam);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormCpntEdit";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "构件编辑器";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormCpntEdit_KeyUp);
            ((System.ComponentModel.ISupportInitialize)(this.dGVparam)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.dGVfomla)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.dGVzomla)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.DataGridView dGVparam;
        private System.Windows.Forms.DataGridView dGVfomla;
        private System.Windows.Forms.DataGridView dGVzomla;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.DataGridViewTextBoxColumn pColKey;
        private System.Windows.Forms.DataGridViewTextBoxColumn pColValue;
        private System.Windows.Forms.DataGridViewTextBoxColumn fColKey;
        private System.Windows.Forms.DataGridViewTextBoxColumn fColValue;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn3;
        private System.Windows.Forms.DataGridViewTextBoxColumn zColKey;
        private System.Windows.Forms.ContextMenuStrip CMS;
    }
}
namespace section2.FmTool
{
    partial class FmCptEditor
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.BTNyes = new System.Windows.Forms.Button();
            this.dgvExp = new System.Windows.Forms.DataGridView();
            this.qColCat = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.qColName = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.qColUnit = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.qColExp = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dgvPara = new System.Windows.Forms.DataGridView();
            this.dataGridViewTextBoxColumn1 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dataGridViewTextBoxColumn2 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dataGridViewTextBoxColumn3 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dataGridViewTextBoxColumn4 = new System.Windows.Forms.DataGridViewTextBoxColumn();
            ((System.ComponentModel.ISupportInitialize)(this.dgvExp)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPara)).BeginInit();
            this.SuspendLayout();
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(843, 342);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(65, 30);
            this.BTNcancel.TabIndex = 76;
            this.BTNcancel.Text = "取消修改";
            this.BTNcancel.UseVisualStyleBackColor = true;
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(772, 342);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(65, 30);
            this.BTNyes.TabIndex = 75;
            this.BTNyes.Text = "确认修改";
            this.BTNyes.UseVisualStyleBackColor = true;
            // 
            // dgvExp
            // 
            this.dgvExp.AllowUserToAddRows = false;
            this.dgvExp.AllowUserToDeleteRows = false;
            this.dgvExp.AllowUserToResizeColumns = false;
            this.dgvExp.AllowUserToResizeRows = false;
            this.dgvExp.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvExp.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.qColCat,
            this.qColName,
            this.qColUnit,
            this.qColExp});
            this.dgvExp.Location = new System.Drawing.Point(310, 3);
            this.dgvExp.Name = "dgvExp";
            this.dgvExp.RowHeadersWidth = 50;
            this.dgvExp.RowTemplate.Height = 23;
            this.dgvExp.Size = new System.Drawing.Size(598, 333);
            this.dgvExp.TabIndex = 73;
            // 
            // qColCat
            // 
            this.qColCat.HeaderText = "类型";
            this.qColCat.Name = "qColCat";
            this.qColCat.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.qColCat.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.qColCat.Width = 65;
            // 
            // qColName
            // 
            this.qColName.HeaderText = "数量名称";
            this.qColName.Name = "qColName";
            this.qColName.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.qColName.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.qColName.Width = 120;
            // 
            // qColUnit
            // 
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.qColUnit.DefaultCellStyle = dataGridViewCellStyle1;
            this.qColUnit.HeaderText = "单位";
            this.qColUnit.Name = "qColUnit";
            this.qColUnit.Width = 55;
            // 
            // qColExp
            // 
            this.qColExp.HeaderText = "表达式";
            this.qColExp.Name = "qColExp";
            this.qColExp.Width = 300;
            // 
            // dgvPara
            // 
            this.dgvPara.AllowUserToAddRows = false;
            this.dgvPara.AllowUserToDeleteRows = false;
            this.dgvPara.AllowUserToResizeColumns = false;
            this.dgvPara.AllowUserToResizeRows = false;
            this.dgvPara.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvPara.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.dataGridViewTextBoxColumn1,
            this.dataGridViewTextBoxColumn2,
            this.dataGridViewTextBoxColumn3,
            this.dataGridViewTextBoxColumn4});
            this.dgvPara.Location = new System.Drawing.Point(2, 3);
            this.dgvPara.Name = "dgvPara";
            this.dgvPara.RowHeadersVisible = false;
            this.dgvPara.RowHeadersWidth = 50;
            this.dgvPara.RowTemplate.Height = 23;
            this.dgvPara.Size = new System.Drawing.Size(302, 362);
            this.dgvPara.TabIndex = 77;
            // 
            // dataGridViewTextBoxColumn1
            // 
            this.dataGridViewTextBoxColumn1.HeaderText = "参数";
            this.dataGridViewTextBoxColumn1.Name = "dataGridViewTextBoxColumn1";
            this.dataGridViewTextBoxColumn1.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.dataGridViewTextBoxColumn1.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.dataGridViewTextBoxColumn1.Width = 55;
            // 
            // dataGridViewTextBoxColumn2
            // 
            this.dataGridViewTextBoxColumn2.HeaderText = "参数名称";
            this.dataGridViewTextBoxColumn2.Name = "dataGridViewTextBoxColumn2";
            this.dataGridViewTextBoxColumn2.Resizable = System.Windows.Forms.DataGridViewTriState.False;
            this.dataGridViewTextBoxColumn2.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.dataGridViewTextBoxColumn2.Width = 80;
            // 
            // dataGridViewTextBoxColumn3
            // 
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            this.dataGridViewTextBoxColumn3.DefaultCellStyle = dataGridViewCellStyle2;
            this.dataGridViewTextBoxColumn3.HeaderText = "单位";
            this.dataGridViewTextBoxColumn3.Name = "dataGridViewTextBoxColumn3";
            this.dataGridViewTextBoxColumn3.Width = 55;
            // 
            // dataGridViewTextBoxColumn4
            // 
            this.dataGridViewTextBoxColumn4.HeaderText = "表达式";
            this.dataGridViewTextBoxColumn4.Name = "dataGridViewTextBoxColumn4";
            // 
            // FmCptEditor
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(917, 377);
            this.Controls.Add(this.dgvPara);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.dgvExp);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.Name = "FmCptEditor";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "FmCptEditor";
            ((System.ComponentModel.ISupportInitialize)(this.dgvExp)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPara)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.DataGridView dgvExp;
        private System.Windows.Forms.DataGridViewTextBoxColumn qColCat;
        private System.Windows.Forms.DataGridViewTextBoxColumn qColName;
        private System.Windows.Forms.DataGridViewTextBoxColumn qColUnit;
        private System.Windows.Forms.DataGridViewTextBoxColumn qColExp;
        private System.Windows.Forms.DataGridView dgvPara;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn1;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn2;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn3;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn4;
    }
}
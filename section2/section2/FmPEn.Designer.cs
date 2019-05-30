namespace section2
{
    partial class FmPEn
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle3 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            this.btnAddPEn = new System.Windows.Forms.Button();
            this.dgvPE = new System.Windows.Forms.DataGridView();
            this.eColdepth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.eColPEnDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPE)).BeginInit();
            this.SuspendLayout();
            // 
            // btnAddPEn
            // 
            this.btnAddPEn.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnAddPEn.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnAddPEn.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnAddPEn.Location = new System.Drawing.Point(276, 0);
            this.btnAddPEn.Name = "btnAddPEn";
            this.btnAddPEn.Size = new System.Drawing.Size(41, 30);
            this.btnAddPEn.TabIndex = 64;
            this.btnAddPEn.Text = "+";
            this.btnAddPEn.UseVisualStyleBackColor = true;
            // 
            // dgvPE
            // 
            this.dgvPE.AllowUserToAddRows = false;
            this.dgvPE.AllowUserToResizeColumns = false;
            this.dgvPE.AllowUserToResizeRows = false;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle1.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dgvPE.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dgvPE.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvPE.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.eColdepth,
            this.eColPEnDis});
            dataGridViewCellStyle3.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle3.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle3.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle3.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle3.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle3.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle3.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dgvPE.DefaultCellStyle = dataGridViewCellStyle3;
            this.dgvPE.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvPE.Location = new System.Drawing.Point(0, 0);
            this.dgvPE.Name = "dgvPE";
            this.dgvPE.RowHeadersVisible = false;
            this.dgvPE.RowTemplate.Height = 23;
            this.dgvPE.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.CellSelect;
            this.dgvPE.Size = new System.Drawing.Size(602, 328);
            this.dgvPE.TabIndex = 63;
            // 
            // eColdepth
            // 
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            this.eColdepth.DefaultCellStyle = dataGridViewCellStyle2;
            this.eColdepth.HeaderText = "埋深";
            this.eColdepth.Name = "eColdepth";
            this.eColdepth.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.eColdepth.Width = 70;
            // 
            // eColPEnDis
            // 
            this.eColPEnDis.HeaderText = "围护(右键选择,双击编辑)";
            this.eColPEnDis.Name = "eColPEnDis";
            this.eColPEnDis.ReadOnly = true;
            this.eColPEnDis.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.eColPEnDis.ToolTipText = "双击编辑围护形式";
            this.eColPEnDis.Width = 200;
            // 
            // FmPEn
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(602, 328);
            this.Controls.Add(this.btnAddPEn);
            this.Controls.Add(this.dgvPE);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.Name = "FmPEn";
            this.Text = "FmPEn";
            ((System.ComponentModel.ISupportInitialize)(this.dgvPE)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.Button btnAddPEn;
        private System.Windows.Forms.DataGridView dgvPE;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColdepth;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColPEnDis;
    }
}
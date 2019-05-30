﻿namespace section2
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle4 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle3 = new System.Windows.Forms.DataGridViewCellStyle();
            this.btnAddPEn = new System.Windows.Forms.Button();
            this.dgvPEn = new System.Windows.Forms.DataGridView();
            this.eColFix = new System.Windows.Forms.DataGridViewCheckBoxColumn();
            this.eColHeight = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.eColWidth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.eColPEnDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPEn)).BeginInit();
            this.SuspendLayout();
            // 
            // btnAddPEn
            // 
            this.btnAddPEn.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnAddPEn.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnAddPEn.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnAddPEn.Location = new System.Drawing.Point(443, 0);
            this.btnAddPEn.Name = "btnAddPEn";
            this.btnAddPEn.Size = new System.Drawing.Size(41, 30);
            this.btnAddPEn.TabIndex = 64;
            this.btnAddPEn.Text = "+";
            this.btnAddPEn.UseVisualStyleBackColor = true;
            // 
            // dgvPEn
            // 
            this.dgvPEn.AllowUserToAddRows = false;
            this.dgvPEn.AllowUserToResizeColumns = false;
            this.dgvPEn.AllowUserToResizeRows = false;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle1.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dgvPEn.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dgvPEn.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvPEn.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.eColFix,
            this.eColHeight,
            this.eColWidth,
            this.eColPEnDis});
            dataGridViewCellStyle4.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle4.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle4.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle4.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle4.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle4.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle4.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dgvPEn.DefaultCellStyle = dataGridViewCellStyle4;
            this.dgvPEn.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvPEn.Location = new System.Drawing.Point(0, 0);
            this.dgvPEn.Name = "dgvPEn";
            this.dgvPEn.RowHeadersVisible = false;
            this.dgvPEn.RowTemplate.Height = 23;
            this.dgvPEn.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.CellSelect;
            this.dgvPEn.Size = new System.Drawing.Size(602, 328);
            this.dgvPEn.TabIndex = 63;
            // 
            // eColFix
            // 
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle2.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle2.NullValue = false;
            this.eColFix.DefaultCellStyle = dataGridViewCellStyle2;
            this.eColFix.FillWeight = 70F;
            this.eColFix.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.eColFix.HeaderText = "固定高度";
            this.eColFix.Name = "eColFix";
            this.eColFix.Width = 70;
            // 
            // eColHeight
            // 
            dataGridViewCellStyle3.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            this.eColHeight.DefaultCellStyle = dataGridViewCellStyle3;
            this.eColHeight.HeaderText = "埋深";
            this.eColHeight.Name = "eColHeight";
            this.eColHeight.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.eColHeight.Width = 70;
            // 
            // eColWidth
            // 
            this.eColWidth.HeaderText = "平台宽度";
            this.eColWidth.Name = "eColWidth";
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
            this.Controls.Add(this.dgvPEn);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.Name = "FmPEn";
            this.Text = "FmPEn";
            this.Load += new System.EventHandler(this.FmPEn_Load);
            ((System.ComponentModel.ISupportInitialize)(this.dgvPEn)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.Button btnAddPEn;
        private System.Windows.Forms.DataGridView dgvPEn;
        private System.Windows.Forms.DataGridViewCheckBoxColumn eColFix;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColHeight;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColWidth;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColPEnDis;
    }
}
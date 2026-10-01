namespace section
{
    partial class FormAbout
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
            this.LBLversion = new System.Windows.Forms.Label();
            this.TXTdn = new System.Windows.Forms.TextBox();
            this.BTNok = new System.Windows.Forms.Button();
            this.SuspendLayout();
            // 
            // LBLversion
            // 
            this.LBLversion.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Left)));
            this.LBLversion.AutoSize = true;
            this.LBLversion.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.LBLversion.Font = new System.Drawing.Font("宋体", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLversion.ForeColor = System.Drawing.SystemColors.Menu;
            this.LBLversion.Location = new System.Drawing.Point(14, 442);
            this.LBLversion.Name = "LBLversion";
            this.LBLversion.Size = new System.Drawing.Size(41, 12);
            this.LBLversion.TabIndex = 0;
            this.LBLversion.Text = "label1";
            // 
            // TXTdn
            // 
            this.TXTdn.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.TXTdn.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(69)))), ((int)(((byte)(90)))), ((int)(((byte)(100)))));
            this.TXTdn.BorderStyle = System.Windows.Forms.BorderStyle.None;
            this.TXTdn.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTdn.ForeColor = System.Drawing.SystemColors.Menu;
            this.TXTdn.Location = new System.Drawing.Point(16, 0);
            this.TXTdn.Multiline = true;
            this.TXTdn.Name = "TXTdn";
            this.TXTdn.ReadOnly = true;
            this.TXTdn.ScrollBars = System.Windows.Forms.ScrollBars.Vertical;
            this.TXTdn.Size = new System.Drawing.Size(636, 436);
            this.TXTdn.TabIndex = 1;
            // 
            // BTNok
            // 
            this.BTNok.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Right)));
            this.BTNok.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.BTNok.ForeColor = System.Drawing.SystemColors.Menu;
            this.BTNok.Location = new System.Drawing.Point(577, 436);
            this.BTNok.Name = "BTNok";
            this.BTNok.Size = new System.Drawing.Size(75, 23);
            this.BTNok.TabIndex = 2;
            this.BTNok.Text = "确定";
            this.BTNok.UseVisualStyleBackColor = true;
            this.BTNok.Click += new System.EventHandler(this.BTNok_Click);
            // 
            // FormAbout
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(69)))), ((int)(((byte)(90)))), ((int)(((byte)(100)))));
            this.ClientSize = new System.Drawing.Size(652, 459);
            this.Controls.Add(this.BTNok);
            this.Controls.Add(this.TXTdn);
            this.Controls.Add(this.LBLversion);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormAbout";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "关于 section";
            this.Load += new System.EventHandler(this.FormAbout_Load);
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormAbout_KeyUp);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Label LBLversion;
        private System.Windows.Forms.TextBox TXTdn;
        private System.Windows.Forms.Button BTNok;
    }
}
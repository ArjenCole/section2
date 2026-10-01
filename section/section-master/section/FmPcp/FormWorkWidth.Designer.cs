namespace section
{
    partial class FormWorkWidth
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
            this.dGVWW = new System.Windows.Forms.DataGridView();
            this.BTNreset = new System.Windows.Forms.Button();
            this.BTNyes = new System.Windows.Forms.Button();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.RBWW = new System.Windows.Forms.RadioButton();
            this.RBGB = new System.Windows.Forms.RadioButton();
            this.dGVGB = new System.Windows.Forms.DataGridView();
            ((System.ComponentModel.ISupportInitialize)(this.dGVWW)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.dGVGB)).BeginInit();
            this.SuspendLayout();
            // 
            // dGVWW
            // 
            this.dGVWW.AllowUserToAddRows = false;
            this.dGVWW.AllowUserToDeleteRows = false;
            this.dGVWW.AllowUserToResizeColumns = false;
            this.dGVWW.AllowUserToResizeRows = false;
            this.dGVWW.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVWW.Location = new System.Drawing.Point(12, 55);
            this.dGVWW.Name = "dGVWW";
            this.dGVWW.RowHeadersWidth = 150;
            this.dGVWW.RowTemplate.Height = 23;
            this.dGVWW.Size = new System.Drawing.Size(523, 381);
            this.dGVWW.TabIndex = 0;
            this.dGVWW.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVWW_CellEndEdit);
            // 
            // BTNreset
            // 
            this.BTNreset.Location = new System.Drawing.Point(713, 12);
            this.BTNreset.Name = "BTNreset";
            this.BTNreset.Size = new System.Drawing.Size(168, 23);
            this.BTNreset.TabIndex = 1;
            this.BTNreset.Text = "重置为《GB 50268-2008》";
            this.BTNreset.UseVisualStyleBackColor = true;
            this.BTNreset.Click += new System.EventHandler(this.BTNreset_Click);
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(969, 12);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(75, 23);
            this.BTNyes.TabIndex = 2;
            this.BTNyes.Text = "确认";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(1067, 12);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(75, 23);
            this.BTNcancel.TabIndex = 3;
            this.BTNcancel.Text = "取消";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // RBWW
            // 
            this.RBWW.AutoSize = true;
            this.RBWW.Location = new System.Drawing.Point(21, 19);
            this.RBWW.Name = "RBWW";
            this.RBWW.Size = new System.Drawing.Size(107, 16);
            this.RBWW.TabIndex = 4;
            this.RBWW.Text = "设置工作面宽度";
            this.RBWW.UseVisualStyleBackColor = true;
            this.RBWW.CheckedChanged += new System.EventHandler(this.RBWW_CheckedChanged);
            // 
            // RBGB
            // 
            this.RBGB.AutoSize = true;
            this.RBGB.Location = new System.Drawing.Point(131, 19);
            this.RBGB.Name = "RBGB";
            this.RBGB.Size = new System.Drawing.Size(95, 16);
            this.RBGB.TabIndex = 5;
            this.RBGB.Text = "设置沟槽宽度";
            this.RBGB.UseVisualStyleBackColor = true;
            this.RBGB.CheckedChanged += new System.EventHandler(this.RBGB_CheckedChanged);
            // 
            // dGVGB
            // 
            this.dGVGB.AllowUserToAddRows = false;
            this.dGVGB.AllowUserToDeleteRows = false;
            this.dGVGB.AllowUserToResizeColumns = false;
            this.dGVGB.AllowUserToResizeRows = false;
            this.dGVGB.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVGB.Location = new System.Drawing.Point(566, 55);
            this.dGVGB.Name = "dGVGB";
            this.dGVGB.RowHeadersWidth = 150;
            this.dGVGB.RowTemplate.Height = 23;
            this.dGVGB.Size = new System.Drawing.Size(529, 381);
            this.dGVGB.TabIndex = 6;
            this.dGVGB.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVGB_CellEndEdit);
            // 
            // FormWorkWidth
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(1154, 436);
            this.Controls.Add(this.dGVGB);
            this.Controls.Add(this.RBGB);
            this.Controls.Add(this.RBWW);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.BTNreset);
            this.Controls.Add(this.dGVWW);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormWorkWidth";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "沟槽宽度设置 mm";
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormWorkWidth_KeyUp);
            ((System.ComponentModel.ISupportInitialize)(this.dGVWW)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.dGVGB)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.DataGridView dGVWW;
        private System.Windows.Forms.Button BTNreset;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.RadioButton RBWW;
        private System.Windows.Forms.RadioButton RBGB;
        private System.Windows.Forms.DataGridView dGVGB;
    }
}
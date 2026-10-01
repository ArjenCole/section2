namespace section
{
    partial class FormWait
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
            this.LBLmessage = new System.Windows.Forms.Label();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.timer1 = new System.Windows.Forms.Timer(this.components);
            this.SuspendLayout();
            // 
            // LBLmessage
            // 
            this.LBLmessage.AutoSize = true;
            this.LBLmessage.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLmessage.Location = new System.Drawing.Point(27, 23);
            this.LBLmessage.Name = "LBLmessage";
            this.LBLmessage.Size = new System.Drawing.Size(50, 20);
            this.LBLmessage.TabIndex = 0;
            this.LBLmessage.Text = "label1";
            // 
            // BTNcancel
            // 
            this.BTNcancel.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNcancel.Location = new System.Drawing.Point(76, 63);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(75, 23);
            this.BTNcancel.TabIndex = 1;
            this.BTNcancel.Text = "取消";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // timer1
            // 
            this.timer1.Enabled = true;
            this.timer1.Interval = 300;
            this.timer1.Tick += new System.EventHandler(this.timer1_Tick);
            // 
            // FormWait
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(223, 105);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.LBLmessage);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.Name = "FormWait";
            this.ShowIcon = false;
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "请等待";
            this.TopMost = true;
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Label LBLmessage;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.Timer timer1;
    }
}
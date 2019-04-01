namespace section2
{
    partial class FmMain
    {
        /// <summary>
        /// 必需的设计器变量。
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// 清理所有正在使用的资源。
        /// </summary>
        /// <param name="disposing">如果应释放托管资源，为 true；否则为 false。</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows 窗体设计器生成的代码

        /// <summary>
        /// 设计器支持所需的方法 - 不要修改
        /// 使用代码编辑器修改此方法的内容。
        /// </summary>
        private void InitializeComponent()
        {
            this.SCmain = new System.Windows.Forms.SplitContainer();
            this.SCleft = new System.Windows.Forms.SplitContainer();
            this.SCright = new System.Windows.Forms.SplitContainer();
            this.SCmain.Panel1.SuspendLayout();
            this.SCmain.Panel2.SuspendLayout();
            this.SCmain.SuspendLayout();
            this.SCleft.SuspendLayout();
            this.SCright.SuspendLayout();
            this.SuspendLayout();
            // 
            // SCmain
            // 
            this.SCmain.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCmain.Location = new System.Drawing.Point(0, 0);
            this.SCmain.Name = "SCmain";
            // 
            // SCmain.Panel1
            // 
            this.SCmain.Panel1.Controls.Add(this.SCleft);
            // 
            // SCmain.Panel2
            // 
            this.SCmain.Panel2.Controls.Add(this.SCright);
            this.SCmain.Size = new System.Drawing.Size(783, 348);
            this.SCmain.SplitterDistance = 261;
            this.SCmain.TabIndex = 1;
            // 
            // SCleft
            // 
            this.SCleft.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCleft.Location = new System.Drawing.Point(0, 0);
            this.SCleft.Name = "SCleft";
            this.SCleft.Orientation = System.Windows.Forms.Orientation.Horizontal;
            this.SCleft.Size = new System.Drawing.Size(261, 348);
            this.SCleft.SplitterDistance = 206;
            this.SCleft.TabIndex = 0;
            // 
            // SCright
            // 
            this.SCright.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCright.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCright.Location = new System.Drawing.Point(0, 0);
            this.SCright.Name = "SCright";
            this.SCright.Orientation = System.Windows.Forms.Orientation.Horizontal;
            this.SCright.Size = new System.Drawing.Size(518, 348);
            this.SCright.SplitterDistance = 113;
            this.SCright.TabIndex = 0;
            // 
            // FmMain
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(783, 348);
            this.Controls.Add(this.SCmain);
            this.Name = "FmMain";
            this.Text = "Form1";
            this.SCmain.Panel1.ResumeLayout(false);
            this.SCmain.Panel2.ResumeLayout(false);
            this.SCmain.ResumeLayout(false);
            this.SCleft.ResumeLayout(false);
            this.SCright.ResumeLayout(false);
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.SplitContainer SCmain;
        private System.Windows.Forms.SplitContainer SCleft;
        private System.Windows.Forms.SplitContainer SCright;
    }
}


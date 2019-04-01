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
            this.MSmain = new System.Windows.Forms.MenuStrip();
            this.TSmain = new System.Windows.Forms.ToolStrip();
            this.SCmain = new System.Windows.Forms.SplitContainer();
            this.SCleft = new System.Windows.Forms.SplitContainer();
            this.TVproject = new System.Windows.Forms.TreeView();
            this.TVinventory = new System.Windows.Forms.TreeView();
            this.SCright = new System.Windows.Forms.SplitContainer();
            this.SCmain.Panel1.SuspendLayout();
            this.SCmain.Panel2.SuspendLayout();
            this.SCmain.SuspendLayout();
            this.SCleft.Panel1.SuspendLayout();
            this.SCleft.Panel2.SuspendLayout();
            this.SCleft.SuspendLayout();
            this.SCright.SuspendLayout();
            this.SuspendLayout();
            // 
            // MSmain
            // 
            this.MSmain.Location = new System.Drawing.Point(0, 0);
            this.MSmain.Name = "MSmain";
            this.MSmain.Size = new System.Drawing.Size(783, 24);
            this.MSmain.TabIndex = 2;
            this.MSmain.Text = "menuStrip1";
            // 
            // TSmain
            // 
            this.TSmain.Location = new System.Drawing.Point(0, 24);
            this.TSmain.Name = "TSmain";
            this.TSmain.Size = new System.Drawing.Size(783, 25);
            this.TSmain.TabIndex = 3;
            this.TSmain.Text = "toolStrip1";
            // 
            // SCmain
            // 
            this.SCmain.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCmain.Location = new System.Drawing.Point(0, 49);
            this.SCmain.Name = "SCmain";
            // 
            // SCmain.Panel1
            // 
            this.SCmain.Panel1.Controls.Add(this.SCleft);
            // 
            // SCmain.Panel2
            // 
            this.SCmain.Panel2.Controls.Add(this.SCright);
            this.SCmain.Size = new System.Drawing.Size(783, 299);
            this.SCmain.SplitterDistance = 261;
            this.SCmain.TabIndex = 4;
            // 
            // SCleft
            // 
            this.SCleft.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCleft.Location = new System.Drawing.Point(0, 0);
            this.SCleft.Name = "SCleft";
            this.SCleft.Orientation = System.Windows.Forms.Orientation.Horizontal;
            // 
            // SCleft.Panel1
            // 
            this.SCleft.Panel1.Controls.Add(this.TVproject);
            // 
            // SCleft.Panel2
            // 
            this.SCleft.Panel2.Controls.Add(this.TVinventory);
            this.SCleft.Size = new System.Drawing.Size(261, 299);
            this.SCleft.SplitterDistance = 175;
            this.SCleft.TabIndex = 0;
            // 
            // TVproject
            // 
            this.TVproject.Dock = System.Windows.Forms.DockStyle.Fill;
            this.TVproject.Location = new System.Drawing.Point(0, 0);
            this.TVproject.Name = "TVproject";
            this.TVproject.Size = new System.Drawing.Size(261, 175);
            this.TVproject.TabIndex = 0;
            // 
            // TVinventory
            // 
            this.TVinventory.Dock = System.Windows.Forms.DockStyle.Fill;
            this.TVinventory.Location = new System.Drawing.Point(0, 0);
            this.TVinventory.Name = "TVinventory";
            this.TVinventory.Size = new System.Drawing.Size(261, 120);
            this.TVinventory.TabIndex = 1;
            // 
            // SCright
            // 
            this.SCright.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCright.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCright.Location = new System.Drawing.Point(0, 0);
            this.SCright.Name = "SCright";
            this.SCright.Orientation = System.Windows.Forms.Orientation.Horizontal;
            this.SCright.Size = new System.Drawing.Size(518, 299);
            this.SCright.SplitterDistance = 113;
            this.SCright.TabIndex = 0;
            // 
            // FmMain
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(783, 348);
            this.Controls.Add(this.SCmain);
            this.Controls.Add(this.TSmain);
            this.Controls.Add(this.MSmain);
            this.Name = "FmMain";
            this.Text = "Form1";
            this.WindowState = System.Windows.Forms.FormWindowState.Maximized;
            this.SCmain.Panel1.ResumeLayout(false);
            this.SCmain.Panel2.ResumeLayout(false);
            this.SCmain.ResumeLayout(false);
            this.SCleft.Panel1.ResumeLayout(false);
            this.SCleft.Panel2.ResumeLayout(false);
            this.SCleft.ResumeLayout(false);
            this.SCright.ResumeLayout(false);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion
        private System.Windows.Forms.MenuStrip MSmain;
        private System.Windows.Forms.ToolStrip TSmain;
        private System.Windows.Forms.SplitContainer SCmain;
        private System.Windows.Forms.SplitContainer SCleft;
        private System.Windows.Forms.TreeView TVproject;
        private System.Windows.Forms.SplitContainer SCright;
        private System.Windows.Forms.TreeView TVinventory;
    }
}


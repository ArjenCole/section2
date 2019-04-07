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
            this.文件ToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.新建ToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.打开ToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.TSmain = new System.Windows.Forms.ToolStrip();
            this.SCmain = new System.Windows.Forms.SplitContainer();
            this.SCleft = new System.Windows.Forms.SplitContainer();
            this.TVdc = new System.Windows.Forms.TreeView();
            this.TVinventory = new System.Windows.Forms.TreeView();
            this.SCright = new System.Windows.Forms.SplitContainer();
            this.SCpcp = new System.Windows.Forms.SplitContainer();
            this.RBmPW = new System.Windows.Forms.RadioButton();
            this.RBmPD = new System.Windows.Forms.RadioButton();
            this.RBmPF = new System.Windows.Forms.RadioButton();
            this.RBmPE = new System.Windows.Forms.RadioButton();
            this.MSmain.SuspendLayout();
            this.SCmain.Panel1.SuspendLayout();
            this.SCmain.Panel2.SuspendLayout();
            this.SCmain.SuspendLayout();
            this.SCleft.Panel1.SuspendLayout();
            this.SCleft.Panel2.SuspendLayout();
            this.SCleft.SuspendLayout();
            this.SCright.Panel1.SuspendLayout();
            this.SCright.Panel2.SuspendLayout();
            this.SCright.SuspendLayout();
            this.SCpcp.SuspendLayout();
            this.SuspendLayout();
            // 
            // MSmain
            // 
            this.MSmain.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.文件ToolStripMenuItem});
            this.MSmain.Location = new System.Drawing.Point(0, 0);
            this.MSmain.Name = "MSmain";
            this.MSmain.Size = new System.Drawing.Size(783, 25);
            this.MSmain.TabIndex = 2;
            this.MSmain.Text = "menuStrip1";
            // 
            // 文件ToolStripMenuItem
            // 
            this.文件ToolStripMenuItem.DropDownItems.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.新建ToolStripMenuItem,
            this.打开ToolStripMenuItem});
            this.文件ToolStripMenuItem.Name = "文件ToolStripMenuItem";
            this.文件ToolStripMenuItem.Size = new System.Drawing.Size(44, 21);
            this.文件ToolStripMenuItem.Text = "文件";
            // 
            // 新建ToolStripMenuItem
            // 
            this.新建ToolStripMenuItem.Name = "新建ToolStripMenuItem";
            this.新建ToolStripMenuItem.Size = new System.Drawing.Size(100, 22);
            this.新建ToolStripMenuItem.Text = "新建";
            this.新建ToolStripMenuItem.Click += new System.EventHandler(this.新建ToolStripMenuItem_Click);
            // 
            // 打开ToolStripMenuItem
            // 
            this.打开ToolStripMenuItem.Name = "打开ToolStripMenuItem";
            this.打开ToolStripMenuItem.Size = new System.Drawing.Size(100, 22);
            this.打开ToolStripMenuItem.Text = "打开";
            // 
            // TSmain
            // 
            this.TSmain.Location = new System.Drawing.Point(0, 25);
            this.TSmain.Name = "TSmain";
            this.TSmain.Size = new System.Drawing.Size(783, 25);
            this.TSmain.TabIndex = 3;
            this.TSmain.Text = "toolStrip1";
            // 
            // SCmain
            // 
            this.SCmain.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCmain.Location = new System.Drawing.Point(0, 50);
            this.SCmain.Name = "SCmain";
            // 
            // SCmain.Panel1
            // 
            this.SCmain.Panel1.Controls.Add(this.SCleft);
            // 
            // SCmain.Panel2
            // 
            this.SCmain.Panel2.Controls.Add(this.SCright);
            this.SCmain.Size = new System.Drawing.Size(783, 298);
            this.SCmain.SplitterDistance = 116;
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
            this.SCleft.Panel1.Controls.Add(this.TVdc);
            // 
            // SCleft.Panel2
            // 
            this.SCleft.Panel2.Controls.Add(this.TVinventory);
            this.SCleft.Size = new System.Drawing.Size(116, 298);
            this.SCleft.SplitterDistance = 174;
            this.SCleft.TabIndex = 0;
            // 
            // TVdc
            // 
            this.TVdc.Dock = System.Windows.Forms.DockStyle.Fill;
            this.TVdc.Location = new System.Drawing.Point(0, 0);
            this.TVdc.Name = "TVdc";
            this.TVdc.Size = new System.Drawing.Size(116, 174);
            this.TVdc.TabIndex = 0;
            // 
            // TVinventory
            // 
            this.TVinventory.Dock = System.Windows.Forms.DockStyle.Fill;
            this.TVinventory.Location = new System.Drawing.Point(0, 0);
            this.TVinventory.Name = "TVinventory";
            this.TVinventory.Size = new System.Drawing.Size(116, 120);
            this.TVinventory.TabIndex = 1;
            // 
            // SCright
            // 
            this.SCright.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCright.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCright.IsSplitterFixed = true;
            this.SCright.Location = new System.Drawing.Point(0, 0);
            this.SCright.Name = "SCright";
            this.SCright.Orientation = System.Windows.Forms.Orientation.Horizontal;
            // 
            // SCright.Panel1
            // 
            this.SCright.Panel1.Controls.Add(this.SCpcp);
            // 
            // SCright.Panel2
            // 
            this.SCright.Panel2.Controls.Add(this.RBmPW);
            this.SCright.Panel2.Controls.Add(this.RBmPD);
            this.SCright.Panel2.Controls.Add(this.RBmPF);
            this.SCright.Panel2.Controls.Add(this.RBmPE);
            this.SCright.Size = new System.Drawing.Size(663, 298);
            this.SCright.SplitterDistance = 113;
            this.SCright.TabIndex = 0;
            // 
            // SCpcp
            // 
            this.SCpcp.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCpcp.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCpcp.IsSplitterFixed = true;
            this.SCpcp.Location = new System.Drawing.Point(0, 0);
            this.SCpcp.Name = "SCpcp";
            this.SCpcp.Size = new System.Drawing.Size(663, 113);
            this.SCpcp.SplitterDistance = 91;
            this.SCpcp.TabIndex = 0;
            // 
            // RBmPW
            // 
            this.RBmPW.AutoSize = true;
            this.RBmPW.Checked = true;
            this.RBmPW.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPW.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPW.Location = new System.Drawing.Point(282, 116);
            this.RBmPW.Name = "RBmPW";
            this.RBmPW.Size = new System.Drawing.Size(98, 26);
            this.RBmPW.TabIndex = 12;
            this.RBmPW.TabStop = true;
            this.RBmPW.Text = "工作面宽";
            this.RBmPW.UseVisualStyleBackColor = true;
            // 
            // RBmPD
            // 
            this.RBmPD.AutoSize = true;
            this.RBmPD.Checked = true;
            this.RBmPD.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPD.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPD.Location = new System.Drawing.Point(282, 90);
            this.RBmPD.Name = "RBmPD";
            this.RBmPD.Size = new System.Drawing.Size(98, 26);
            this.RBmPD.TabIndex = 11;
            this.RBmPD.TabStop = true;
            this.RBmPD.Text = "降水原则";
            this.RBmPD.UseVisualStyleBackColor = true;
            // 
            // RBmPF
            // 
            this.RBmPF.AutoSize = true;
            this.RBmPF.Checked = true;
            this.RBmPF.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPF.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPF.Location = new System.Drawing.Point(282, 64);
            this.RBmPF.Name = "RBmPF";
            this.RBmPF.Size = new System.Drawing.Size(98, 26);
            this.RBmPF.TabIndex = 10;
            this.RBmPF.TabStop = true;
            this.RBmPF.Text = "地基处理";
            this.RBmPF.UseVisualStyleBackColor = true;
            // 
            // RBmPE
            // 
            this.RBmPE.AutoSize = true;
            this.RBmPE.Checked = true;
            this.RBmPE.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPE.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPE.Location = new System.Drawing.Point(282, 38);
            this.RBmPE.Name = "RBmPE";
            this.RBmPE.Size = new System.Drawing.Size(98, 26);
            this.RBmPE.TabIndex = 9;
            this.RBmPE.TabStop = true;
            this.RBmPE.Text = "围护原则";
            this.RBmPE.UseVisualStyleBackColor = true;
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
            this.MSmain.ResumeLayout(false);
            this.MSmain.PerformLayout();
            this.SCmain.Panel1.ResumeLayout(false);
            this.SCmain.Panel2.ResumeLayout(false);
            this.SCmain.ResumeLayout(false);
            this.SCleft.Panel1.ResumeLayout(false);
            this.SCleft.Panel2.ResumeLayout(false);
            this.SCleft.ResumeLayout(false);
            this.SCright.Panel1.ResumeLayout(false);
            this.SCright.Panel2.ResumeLayout(false);
            this.SCright.Panel2.PerformLayout();
            this.SCright.ResumeLayout(false);
            this.SCpcp.ResumeLayout(false);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion
        private System.Windows.Forms.MenuStrip MSmain;
        private System.Windows.Forms.ToolStrip TSmain;
        private System.Windows.Forms.SplitContainer SCmain;
        private System.Windows.Forms.SplitContainer SCleft;
        private System.Windows.Forms.TreeView TVdc;
        private System.Windows.Forms.SplitContainer SCright;
        private System.Windows.Forms.TreeView TVinventory;
        private System.Windows.Forms.ToolStripMenuItem 文件ToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem 新建ToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem 打开ToolStripMenuItem;
        private System.Windows.Forms.SplitContainer SCpcp;
        private System.Windows.Forms.RadioButton RBmPW;
        private System.Windows.Forms.RadioButton RBmPD;
        private System.Windows.Forms.RadioButton RBmPF;
        private System.Windows.Forms.RadioButton RBmPE;
    }
}


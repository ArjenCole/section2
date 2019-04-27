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
            this.scPcp = new System.Windows.Forms.SplitContainer();
            this.RBmPF = new System.Windows.Forms.RadioButton();
            this.RBmPE = new System.Windows.Forms.RadioButton();
            this.BTNpcpAddHigh = new System.Windows.Forms.Button();
            this.TLPmPF = new System.Windows.Forms.TableLayoutPanel();
            this.TLPmPE = new System.Windows.Forms.TableLayoutPanel();
            this.Pun = new System.Windows.Forms.Panel();
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
            this.scPcp.Panel1.SuspendLayout();
            this.scPcp.Panel2.SuspendLayout();
            this.scPcp.SuspendLayout();
            this.SuspendLayout();
            // 
            // MSmain
            // 
            this.MSmain.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.文件ToolStripMenuItem});
            this.MSmain.Location = new System.Drawing.Point(0, 0);
            this.MSmain.Name = "MSmain";
            this.MSmain.Size = new System.Drawing.Size(1084, 25);
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
            this.TSmain.Size = new System.Drawing.Size(1084, 25);
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
            this.SCmain.Size = new System.Drawing.Size(1084, 451);
            this.SCmain.SplitterDistance = 160;
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
            this.SCleft.Size = new System.Drawing.Size(160, 451);
            this.SCleft.SplitterDistance = 263;
            this.SCleft.TabIndex = 0;
            // 
            // TVdc
            // 
            this.TVdc.Dock = System.Windows.Forms.DockStyle.Fill;
            this.TVdc.Font = new System.Drawing.Font("等线", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TVdc.Location = new System.Drawing.Point(0, 0);
            this.TVdc.Name = "TVdc";
            this.TVdc.Size = new System.Drawing.Size(160, 263);
            this.TVdc.TabIndex = 0;
            this.TVdc.NodeMouseClick += new System.Windows.Forms.TreeNodeMouseClickEventHandler(this.TVdc_NodeMouseClick);
            // 
            // TVinventory
            // 
            this.TVinventory.Dock = System.Windows.Forms.DockStyle.Fill;
            this.TVinventory.Location = new System.Drawing.Point(0, 0);
            this.TVinventory.Name = "TVinventory";
            this.TVinventory.Size = new System.Drawing.Size(160, 184);
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
            this.SCright.Panel1.Controls.Add(this.scPcp);
            // 
            // SCright.Panel2
            // 
            this.SCright.Panel2.Controls.Add(this.Pun);
            this.SCright.Size = new System.Drawing.Size(920, 451);
            this.SCright.SplitterDistance = 52;
            this.SCright.TabIndex = 0;
            // 
            // scPcp
            // 
            this.scPcp.Dock = System.Windows.Forms.DockStyle.Fill;
            this.scPcp.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.scPcp.IsSplitterFixed = true;
            this.scPcp.Location = new System.Drawing.Point(0, 0);
            this.scPcp.Name = "scPcp";
            // 
            // scPcp.Panel1
            // 
            this.scPcp.Panel1.Controls.Add(this.RBmPF);
            this.scPcp.Panel1.Controls.Add(this.RBmPE);
            // 
            // scPcp.Panel2
            // 
            this.scPcp.Panel2.Controls.Add(this.BTNpcpAddHigh);
            this.scPcp.Panel2.Controls.Add(this.TLPmPF);
            this.scPcp.Panel2.Controls.Add(this.TLPmPE);
            this.scPcp.Size = new System.Drawing.Size(920, 52);
            this.scPcp.SplitterDistance = 105;
            this.scPcp.TabIndex = 2;
            // 
            // RBmPF
            // 
            this.RBmPF.AutoSize = true;
            this.RBmPF.Checked = true;
            this.RBmPF.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPF.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPF.Location = new System.Drawing.Point(14, 27);
            this.RBmPF.Name = "RBmPF";
            this.RBmPF.Size = new System.Drawing.Size(98, 26);
            this.RBmPF.TabIndex = 12;
            this.RBmPF.TabStop = true;
            this.RBmPF.Text = "地基处理";
            this.RBmPF.UseVisualStyleBackColor = true;
            this.RBmPF.CheckedChanged += new System.EventHandler(this.RBmP_CheckedChanged);
            // 
            // RBmPE
            // 
            this.RBmPE.AutoSize = true;
            this.RBmPE.Checked = true;
            this.RBmPE.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPE.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPE.Location = new System.Drawing.Point(14, 1);
            this.RBmPE.Name = "RBmPE";
            this.RBmPE.Size = new System.Drawing.Size(98, 26);
            this.RBmPE.TabIndex = 11;
            this.RBmPE.TabStop = true;
            this.RBmPE.Text = "围护原则";
            this.RBmPE.UseVisualStyleBackColor = true;
            this.RBmPE.CheckedChanged += new System.EventHandler(this.RBmP_CheckedChanged);
            // 
            // BTNpcpAddHigh
            // 
            this.BTNpcpAddHigh.Dock = System.Windows.Forms.DockStyle.Left;
            this.BTNpcpAddHigh.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNpcpAddHigh.Font = new System.Drawing.Font("幼圆", 15.75F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.BTNpcpAddHigh.Location = new System.Drawing.Point(8, 0);
            this.BTNpcpAddHigh.Name = "BTNpcpAddHigh";
            this.BTNpcpAddHigh.Size = new System.Drawing.Size(24, 52);
            this.BTNpcpAddHigh.TabIndex = 5;
            this.BTNpcpAddHigh.TabStop = false;
            this.BTNpcpAddHigh.Text = "+";
            this.BTNpcpAddHigh.UseVisualStyleBackColor = true;
            // 
            // TLPmPF
            // 
            this.TLPmPF.AutoSize = true;
            this.TLPmPF.CellBorderStyle = System.Windows.Forms.TableLayoutPanelCellBorderStyle.Inset;
            this.TLPmPF.ColumnCount = 1;
            this.TLPmPF.ColumnStyles.Add(new System.Windows.Forms.ColumnStyle());
            this.TLPmPF.Dock = System.Windows.Forms.DockStyle.Left;
            this.TLPmPF.GrowStyle = System.Windows.Forms.TableLayoutPanelGrowStyle.AddColumns;
            this.TLPmPF.Location = new System.Drawing.Point(4, 0);
            this.TLPmPF.Name = "TLPmPF";
            this.TLPmPF.RowCount = 1;
            this.TLPmPF.RowStyles.Add(new System.Windows.Forms.RowStyle(System.Windows.Forms.SizeType.Percent, 100F));
            this.TLPmPF.Size = new System.Drawing.Size(4, 52);
            this.TLPmPF.TabIndex = 4;
            // 
            // TLPmPE
            // 
            this.TLPmPE.AutoSize = true;
            this.TLPmPE.CellBorderStyle = System.Windows.Forms.TableLayoutPanelCellBorderStyle.Inset;
            this.TLPmPE.ColumnCount = 1;
            this.TLPmPE.ColumnStyles.Add(new System.Windows.Forms.ColumnStyle());
            this.TLPmPE.Dock = System.Windows.Forms.DockStyle.Left;
            this.TLPmPE.GrowStyle = System.Windows.Forms.TableLayoutPanelGrowStyle.AddColumns;
            this.TLPmPE.Location = new System.Drawing.Point(0, 0);
            this.TLPmPE.Name = "TLPmPE";
            this.TLPmPE.RowCount = 1;
            this.TLPmPE.RowStyles.Add(new System.Windows.Forms.RowStyle(System.Windows.Forms.SizeType.Percent, 100F));
            this.TLPmPE.Size = new System.Drawing.Size(4, 52);
            this.TLPmPE.TabIndex = 3;
            // 
            // Pun
            // 
            this.Pun.Location = new System.Drawing.Point(88, 46);
            this.Pun.Name = "Pun";
            this.Pun.Size = new System.Drawing.Size(629, 245);
            this.Pun.TabIndex = 0;
            // 
            // FmMain
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(1084, 501);
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
            this.SCright.ResumeLayout(false);
            this.scPcp.Panel1.ResumeLayout(false);
            this.scPcp.Panel1.PerformLayout();
            this.scPcp.Panel2.ResumeLayout(false);
            this.scPcp.Panel2.PerformLayout();
            this.scPcp.ResumeLayout(false);
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
        private System.Windows.Forms.Panel Pun;
        private System.Windows.Forms.SplitContainer scPcp;
        private System.Windows.Forms.RadioButton RBmPF;
        private System.Windows.Forms.RadioButton RBmPE;
        private System.Windows.Forms.Button BTNpcpAddHigh;
        private System.Windows.Forms.TableLayoutPanel TLPmPF;
        private System.Windows.Forms.TableLayoutPanel TLPmPE;
    }
}


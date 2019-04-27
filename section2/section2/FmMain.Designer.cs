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
            this.msMain = new System.Windows.Forms.MenuStrip();
            this.文件ToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.新建ToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.打开ToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.tsMain = new System.Windows.Forms.ToolStrip();
            this.scMain = new System.Windows.Forms.SplitContainer();
            this.scLeft = new System.Windows.Forms.SplitContainer();
            this.tvDC = new System.Windows.Forms.TreeView();
            this.tvInventory = new System.Windows.Forms.TreeView();
            this.scRight = new System.Windows.Forms.SplitContainer();
            this.scPcp = new System.Windows.Forms.SplitContainer();
            this.RBmPF = new System.Windows.Forms.RadioButton();
            this.RBmPE = new System.Windows.Forms.RadioButton();
            this.btnPcpAdd = new System.Windows.Forms.Button();
            this.TLPmPF = new System.Windows.Forms.TableLayoutPanel();
            this.TLPmPE = new System.Windows.Forms.TableLayoutPanel();
            this.pUN = new System.Windows.Forms.Panel();
            this.msMain.SuspendLayout();
            this.scMain.Panel1.SuspendLayout();
            this.scMain.Panel2.SuspendLayout();
            this.scMain.SuspendLayout();
            this.scLeft.Panel1.SuspendLayout();
            this.scLeft.Panel2.SuspendLayout();
            this.scLeft.SuspendLayout();
            this.scRight.Panel1.SuspendLayout();
            this.scRight.Panel2.SuspendLayout();
            this.scRight.SuspendLayout();
            this.scPcp.Panel1.SuspendLayout();
            this.scPcp.Panel2.SuspendLayout();
            this.scPcp.SuspendLayout();
            this.SuspendLayout();
            // 
            // msMain
            // 
            this.msMain.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.文件ToolStripMenuItem});
            this.msMain.Location = new System.Drawing.Point(0, 0);
            this.msMain.Name = "msMain";
            this.msMain.Size = new System.Drawing.Size(1084, 25);
            this.msMain.TabIndex = 2;
            this.msMain.Text = "menuStrip1";
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
            // tsMain
            // 
            this.tsMain.Location = new System.Drawing.Point(0, 25);
            this.tsMain.Name = "tsMain";
            this.tsMain.Size = new System.Drawing.Size(1084, 25);
            this.tsMain.TabIndex = 3;
            this.tsMain.Text = "toolStrip1";
            // 
            // scMain
            // 
            this.scMain.Dock = System.Windows.Forms.DockStyle.Fill;
            this.scMain.Location = new System.Drawing.Point(0, 50);
            this.scMain.Name = "scMain";
            // 
            // scMain.Panel1
            // 
            this.scMain.Panel1.Controls.Add(this.scLeft);
            // 
            // scMain.Panel2
            // 
            this.scMain.Panel2.Controls.Add(this.scRight);
            this.scMain.Size = new System.Drawing.Size(1084, 451);
            this.scMain.SplitterDistance = 160;
            this.scMain.TabIndex = 4;
            // 
            // scLeft
            // 
            this.scLeft.Dock = System.Windows.Forms.DockStyle.Fill;
            this.scLeft.Location = new System.Drawing.Point(0, 0);
            this.scLeft.Name = "scLeft";
            this.scLeft.Orientation = System.Windows.Forms.Orientation.Horizontal;
            // 
            // scLeft.Panel1
            // 
            this.scLeft.Panel1.Controls.Add(this.tvDC);
            // 
            // scLeft.Panel2
            // 
            this.scLeft.Panel2.Controls.Add(this.tvInventory);
            this.scLeft.Size = new System.Drawing.Size(160, 451);
            this.scLeft.SplitterDistance = 263;
            this.scLeft.TabIndex = 0;
            // 
            // tvDC
            // 
            this.tvDC.Dock = System.Windows.Forms.DockStyle.Fill;
            this.tvDC.Font = new System.Drawing.Font("等线", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.tvDC.Location = new System.Drawing.Point(0, 0);
            this.tvDC.Name = "tvDC";
            this.tvDC.Size = new System.Drawing.Size(160, 263);
            this.tvDC.TabIndex = 0;
            this.tvDC.NodeMouseClick += new System.Windows.Forms.TreeNodeMouseClickEventHandler(this.tvDC_NodeMouseClick);
            // 
            // tvInventory
            // 
            this.tvInventory.Dock = System.Windows.Forms.DockStyle.Fill;
            this.tvInventory.Location = new System.Drawing.Point(0, 0);
            this.tvInventory.Name = "tvInventory";
            this.tvInventory.Size = new System.Drawing.Size(160, 184);
            this.tvInventory.TabIndex = 1;
            // 
            // scRight
            // 
            this.scRight.Dock = System.Windows.Forms.DockStyle.Fill;
            this.scRight.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.scRight.IsSplitterFixed = true;
            this.scRight.Location = new System.Drawing.Point(0, 0);
            this.scRight.Name = "scRight";
            this.scRight.Orientation = System.Windows.Forms.Orientation.Horizontal;
            // 
            // scRight.Panel1
            // 
            this.scRight.Panel1.Controls.Add(this.scPcp);
            // 
            // scRight.Panel2
            // 
            this.scRight.Panel2.Controls.Add(this.pUN);
            this.scRight.Size = new System.Drawing.Size(920, 451);
            this.scRight.SplitterDistance = 52;
            this.scRight.TabIndex = 0;
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
            this.scPcp.Panel2.Controls.Add(this.btnPcpAdd);
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
            // btnPcpAdd
            // 
            this.btnPcpAdd.Dock = System.Windows.Forms.DockStyle.Left;
            this.btnPcpAdd.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnPcpAdd.Font = new System.Drawing.Font("幼圆", 15.75F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnPcpAdd.Location = new System.Drawing.Point(8, 0);
            this.btnPcpAdd.Name = "btnPcpAdd";
            this.btnPcpAdd.Size = new System.Drawing.Size(24, 52);
            this.btnPcpAdd.TabIndex = 5;
            this.btnPcpAdd.TabStop = false;
            this.btnPcpAdd.Text = "+";
            this.btnPcpAdd.UseVisualStyleBackColor = true;
            this.btnPcpAdd.Click += new System.EventHandler(this.btnPcpAdd_Click);
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
            // pUN
            // 
            this.pUN.Location = new System.Drawing.Point(88, 46);
            this.pUN.Name = "pUN";
            this.pUN.Size = new System.Drawing.Size(629, 245);
            this.pUN.TabIndex = 0;
            // 
            // FmMain
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(1084, 501);
            this.Controls.Add(this.scMain);
            this.Controls.Add(this.tsMain);
            this.Controls.Add(this.msMain);
            this.Name = "FmMain";
            this.Text = "Form1";
            this.WindowState = System.Windows.Forms.FormWindowState.Maximized;
            this.msMain.ResumeLayout(false);
            this.msMain.PerformLayout();
            this.scMain.Panel1.ResumeLayout(false);
            this.scMain.Panel2.ResumeLayout(false);
            this.scMain.ResumeLayout(false);
            this.scLeft.Panel1.ResumeLayout(false);
            this.scLeft.Panel2.ResumeLayout(false);
            this.scLeft.ResumeLayout(false);
            this.scRight.Panel1.ResumeLayout(false);
            this.scRight.Panel2.ResumeLayout(false);
            this.scRight.ResumeLayout(false);
            this.scPcp.Panel1.ResumeLayout(false);
            this.scPcp.Panel1.PerformLayout();
            this.scPcp.Panel2.ResumeLayout(false);
            this.scPcp.Panel2.PerformLayout();
            this.scPcp.ResumeLayout(false);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion
        private System.Windows.Forms.MenuStrip msMain;
        private System.Windows.Forms.ToolStrip tsMain;
        private System.Windows.Forms.SplitContainer scMain;
        private System.Windows.Forms.SplitContainer scLeft;
        private System.Windows.Forms.TreeView tvDC;
        private System.Windows.Forms.SplitContainer scRight;
        private System.Windows.Forms.TreeView tvInventory;
        private System.Windows.Forms.ToolStripMenuItem 文件ToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem 新建ToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem 打开ToolStripMenuItem;
        private System.Windows.Forms.Panel pUN;
        private System.Windows.Forms.SplitContainer scPcp;
        private System.Windows.Forms.RadioButton RBmPF;
        private System.Windows.Forms.RadioButton RBmPE;
        private System.Windows.Forms.Button btnPcpAdd;
        private System.Windows.Forms.TableLayoutPanel TLPmPF;
        private System.Windows.Forms.TableLayoutPanel TLPmPE;
    }
}


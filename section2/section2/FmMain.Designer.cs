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
            this.SCpcpHigh = new System.Windows.Forms.SplitContainer();
            this.RBmPF = new System.Windows.Forms.RadioButton();
            this.RBmPE = new System.Windows.Forms.RadioButton();
            this.BTNpcpAddHigh = new System.Windows.Forms.Button();
            this.TLPmPF = new System.Windows.Forms.TableLayoutPanel();
            this.TLPmPE = new System.Windows.Forms.TableLayoutPanel();
            this.SCpcpLow = new System.Windows.Forms.SplitContainer();
            this.RBmPW = new System.Windows.Forms.RadioButton();
            this.RBmPD = new System.Windows.Forms.RadioButton();
            this.BTNpcpAddLow = new System.Windows.Forms.Button();
            this.TLPmPD = new System.Windows.Forms.TableLayoutPanel();
            this.TLPmPW = new System.Windows.Forms.TableLayoutPanel();
            this.MSmain.SuspendLayout();
            this.SCmain.Panel1.SuspendLayout();
            this.SCmain.Panel2.SuspendLayout();
            this.SCmain.SuspendLayout();
            this.SCleft.Panel1.SuspendLayout();
            this.SCleft.Panel2.SuspendLayout();
            this.SCleft.SuspendLayout();
            this.SCright.Panel1.SuspendLayout();
            this.SCright.SuspendLayout();
            this.SCpcp.Panel1.SuspendLayout();
            this.SCpcp.Panel2.SuspendLayout();
            this.SCpcp.SuspendLayout();
            this.SCpcpHigh.Panel1.SuspendLayout();
            this.SCpcpHigh.Panel2.SuspendLayout();
            this.SCpcpHigh.SuspendLayout();
            this.SCpcpLow.Panel1.SuspendLayout();
            this.SCpcpLow.Panel2.SuspendLayout();
            this.SCpcpLow.SuspendLayout();
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
            this.TVdc.Location = new System.Drawing.Point(0, 0);
            this.TVdc.Name = "TVdc";
            this.TVdc.Size = new System.Drawing.Size(160, 263);
            this.TVdc.TabIndex = 0;
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
            this.SCright.Panel1.Controls.Add(this.SCpcp);
            this.SCright.Size = new System.Drawing.Size(920, 451);
            this.SCright.SplitterDistance = 113;
            this.SCright.TabIndex = 0;
            // 
            // SCpcp
            // 
            this.SCpcp.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.SCpcp.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCpcp.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCpcp.IsSplitterFixed = true;
            this.SCpcp.Location = new System.Drawing.Point(0, 0);
            this.SCpcp.Name = "SCpcp";
            this.SCpcp.Orientation = System.Windows.Forms.Orientation.Horizontal;
            // 
            // SCpcp.Panel1
            // 
            this.SCpcp.Panel1.Controls.Add(this.SCpcpHigh);
            // 
            // SCpcp.Panel2
            // 
            this.SCpcp.Panel2.Controls.Add(this.SCpcpLow);
            this.SCpcp.Size = new System.Drawing.Size(920, 113);
            this.SCpcp.SplitterDistance = 55;
            this.SCpcp.TabIndex = 0;
            // 
            // SCpcpHigh
            // 
            this.SCpcpHigh.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCpcpHigh.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCpcpHigh.IsSplitterFixed = true;
            this.SCpcpHigh.Location = new System.Drawing.Point(0, 0);
            this.SCpcpHigh.Name = "SCpcpHigh";
            // 
            // SCpcpHigh.Panel1
            // 
            this.SCpcpHigh.Panel1.Controls.Add(this.RBmPF);
            this.SCpcpHigh.Panel1.Controls.Add(this.RBmPE);
            // 
            // SCpcpHigh.Panel2
            // 
            this.SCpcpHigh.Panel2.Controls.Add(this.BTNpcpAddHigh);
            this.SCpcpHigh.Panel2.Controls.Add(this.TLPmPF);
            this.SCpcpHigh.Panel2.Controls.Add(this.TLPmPE);
            this.SCpcpHigh.Size = new System.Drawing.Size(918, 53);
            this.SCpcpHigh.SplitterDistance = 126;
            this.SCpcpHigh.TabIndex = 0;
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
            // 
            // BTNpcpAddHigh
            // 
            this.BTNpcpAddHigh.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNpcpAddHigh.Font = new System.Drawing.Font("幼圆", 15.75F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.BTNpcpAddHigh.Location = new System.Drawing.Point(589, 8);
            this.BTNpcpAddHigh.Name = "BTNpcpAddHigh";
            this.BTNpcpAddHigh.Size = new System.Drawing.Size(32, 41);
            this.BTNpcpAddHigh.TabIndex = 5;
            this.BTNpcpAddHigh.TabStop = false;
            this.BTNpcpAddHigh.Text = "+";
            this.BTNpcpAddHigh.UseVisualStyleBackColor = true;
            this.BTNpcpAddHigh.Click += new System.EventHandler(this.BTNpcpAddHigh_Click);
            // 
            // TLPmPF
            // 
            this.TLPmPF.AutoSize = true;
            this.TLPmPF.CellBorderStyle = System.Windows.Forms.TableLayoutPanelCellBorderStyle.Inset;
            this.TLPmPF.ColumnCount = 1;
            this.TLPmPF.ColumnStyles.Add(new System.Windows.Forms.ColumnStyle());
            this.TLPmPF.GrowStyle = System.Windows.Forms.TableLayoutPanelGrowStyle.AddColumns;
            this.TLPmPF.Location = new System.Drawing.Point(392, 5);
            this.TLPmPF.Name = "TLPmPF";
            this.TLPmPF.RowCount = 1;
            this.TLPmPF.RowStyles.Add(new System.Windows.Forms.RowStyle(System.Windows.Forms.SizeType.Percent, 100F));
            this.TLPmPF.Size = new System.Drawing.Size(166, 44);
            this.TLPmPF.TabIndex = 4;
            // 
            // TLPmPE
            // 
            this.TLPmPE.AutoSize = true;
            this.TLPmPE.CellBorderStyle = System.Windows.Forms.TableLayoutPanelCellBorderStyle.Inset;
            this.TLPmPE.ColumnCount = 1;
            this.TLPmPE.ColumnStyles.Add(new System.Windows.Forms.ColumnStyle());
            this.TLPmPE.GrowStyle = System.Windows.Forms.TableLayoutPanelGrowStyle.AddColumns;
            this.TLPmPE.Location = new System.Drawing.Point(202, 5);
            this.TLPmPE.Name = "TLPmPE";
            this.TLPmPE.RowCount = 1;
            this.TLPmPE.RowStyles.Add(new System.Windows.Forms.RowStyle(System.Windows.Forms.SizeType.Percent, 100F));
            this.TLPmPE.Size = new System.Drawing.Size(166, 44);
            this.TLPmPE.TabIndex = 3;
            // 
            // SCpcpLow
            // 
            this.SCpcpLow.Dock = System.Windows.Forms.DockStyle.Fill;
            this.SCpcpLow.FixedPanel = System.Windows.Forms.FixedPanel.Panel1;
            this.SCpcpLow.IsSplitterFixed = true;
            this.SCpcpLow.Location = new System.Drawing.Point(0, 0);
            this.SCpcpLow.Name = "SCpcpLow";
            // 
            // SCpcpLow.Panel1
            // 
            this.SCpcpLow.Panel1.Controls.Add(this.RBmPW);
            this.SCpcpLow.Panel1.Controls.Add(this.RBmPD);
            // 
            // SCpcpLow.Panel2
            // 
            this.SCpcpLow.Panel2.Controls.Add(this.BTNpcpAddLow);
            this.SCpcpLow.Panel2.Controls.Add(this.TLPmPD);
            this.SCpcpLow.Panel2.Controls.Add(this.TLPmPW);
            this.SCpcpLow.Size = new System.Drawing.Size(918, 52);
            this.SCpcpLow.SplitterDistance = 126;
            this.SCpcpLow.TabIndex = 1;
            // 
            // RBmPW
            // 
            this.RBmPW.AutoSize = true;
            this.RBmPW.Checked = true;
            this.RBmPW.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.RBmPW.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.RBmPW.Location = new System.Drawing.Point(14, 27);
            this.RBmPW.Name = "RBmPW";
            this.RBmPW.Size = new System.Drawing.Size(98, 26);
            this.RBmPW.TabIndex = 14;
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
            this.RBmPD.Location = new System.Drawing.Point(14, 1);
            this.RBmPD.Name = "RBmPD";
            this.RBmPD.Size = new System.Drawing.Size(98, 26);
            this.RBmPD.TabIndex = 13;
            this.RBmPD.TabStop = true;
            this.RBmPD.Text = "降水原则";
            this.RBmPD.UseVisualStyleBackColor = true;
            // 
            // BTNpcpAddLow
            // 
            this.BTNpcpAddLow.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNpcpAddLow.Font = new System.Drawing.Font("幼圆", 15.75F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.BTNpcpAddLow.Location = new System.Drawing.Point(573, 8);
            this.BTNpcpAddLow.Name = "BTNpcpAddLow";
            this.BTNpcpAddLow.Size = new System.Drawing.Size(32, 41);
            this.BTNpcpAddLow.TabIndex = 8;
            this.BTNpcpAddLow.TabStop = false;
            this.BTNpcpAddLow.Text = "+";
            this.BTNpcpAddLow.UseVisualStyleBackColor = true;
            // 
            // TLPmPD
            // 
            this.TLPmPD.AutoSize = true;
            this.TLPmPD.CellBorderStyle = System.Windows.Forms.TableLayoutPanelCellBorderStyle.Inset;
            this.TLPmPD.ColumnCount = 1;
            this.TLPmPD.ColumnStyles.Add(new System.Windows.Forms.ColumnStyle());
            this.TLPmPD.GrowStyle = System.Windows.Forms.TableLayoutPanelGrowStyle.AddColumns;
            this.TLPmPD.Location = new System.Drawing.Point(376, 5);
            this.TLPmPD.Name = "TLPmPD";
            this.TLPmPD.RowCount = 1;
            this.TLPmPD.RowStyles.Add(new System.Windows.Forms.RowStyle(System.Windows.Forms.SizeType.Percent, 100F));
            this.TLPmPD.Size = new System.Drawing.Size(166, 44);
            this.TLPmPD.TabIndex = 7;
            // 
            // TLPmPW
            // 
            this.TLPmPW.AutoSize = true;
            this.TLPmPW.CellBorderStyle = System.Windows.Forms.TableLayoutPanelCellBorderStyle.Inset;
            this.TLPmPW.ColumnCount = 1;
            this.TLPmPW.ColumnStyles.Add(new System.Windows.Forms.ColumnStyle());
            this.TLPmPW.GrowStyle = System.Windows.Forms.TableLayoutPanelGrowStyle.AddColumns;
            this.TLPmPW.Location = new System.Drawing.Point(186, 5);
            this.TLPmPW.Name = "TLPmPW";
            this.TLPmPW.RowCount = 1;
            this.TLPmPW.RowStyles.Add(new System.Windows.Forms.RowStyle(System.Windows.Forms.SizeType.Percent, 100F));
            this.TLPmPW.Size = new System.Drawing.Size(166, 44);
            this.TLPmPW.TabIndex = 6;
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
            this.SCright.ResumeLayout(false);
            this.SCpcp.Panel1.ResumeLayout(false);
            this.SCpcp.Panel2.ResumeLayout(false);
            this.SCpcp.ResumeLayout(false);
            this.SCpcpHigh.Panel1.ResumeLayout(false);
            this.SCpcpHigh.Panel1.PerformLayout();
            this.SCpcpHigh.Panel2.ResumeLayout(false);
            this.SCpcpHigh.Panel2.PerformLayout();
            this.SCpcpHigh.ResumeLayout(false);
            this.SCpcpLow.Panel1.ResumeLayout(false);
            this.SCpcpLow.Panel1.PerformLayout();
            this.SCpcpLow.Panel2.ResumeLayout(false);
            this.SCpcpLow.Panel2.PerformLayout();
            this.SCpcpLow.ResumeLayout(false);
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
        private System.Windows.Forms.SplitContainer SCpcpHigh;
        private System.Windows.Forms.RadioButton RBmPF;
        private System.Windows.Forms.RadioButton RBmPE;
        private System.Windows.Forms.SplitContainer SCpcpLow;
        private System.Windows.Forms.RadioButton RBmPW;
        private System.Windows.Forms.RadioButton RBmPD;
        private System.Windows.Forms.Button BTNpcpAddHigh;
        private System.Windows.Forms.TableLayoutPanel TLPmPF;
        private System.Windows.Forms.TableLayoutPanel TLPmPE;
        private System.Windows.Forms.Button BTNpcpAddLow;
        private System.Windows.Forms.TableLayoutPanel TLPmPD;
        private System.Windows.Forms.TableLayoutPanel TLPmPW;
    }
}


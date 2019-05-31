namespace section2
{
    partial class FmPE
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle1 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle4 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle3 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle5 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle8 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle6 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle7 = new System.Windows.Forms.DataGridViewCellStyle();
            this.tcMain = new System.Windows.Forms.TabControl();
            this.tpPE = new System.Windows.Forms.TabPage();
            this.btnAddPEn = new System.Windows.Forms.Button();
            this.dgvPE = new System.Windows.Forms.DataGridView();
            this.eColdepth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.eColrange = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.eColPEnDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.eColSWDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.cmsDrop = new System.Windows.Forms.ContextMenuStrip(this.components);
            this.tpPD = new System.Windows.Forms.TabPage();
            this.tpPW = new System.Windows.Forms.TabPage();
            this.tcPW = new System.Windows.Forms.TabControl();
            this.tabPage4 = new System.Windows.Forms.TabPage();
            this.tabPage5 = new System.Windows.Forms.TabPage();
            this.tabPage6 = new System.Windows.Forms.TabPage();
            this.tabPage7 = new System.Windows.Forms.TabPage();
            this.tabPage8 = new System.Windows.Forms.TabPage();
            this.tabPage9 = new System.Windows.Forms.TabPage();
            this.gbPEparaDock = new System.Windows.Forms.GroupBox();
            this.lblBackFill = new System.Windows.Forms.Label();
            this.cboDockMat = new System.Windows.Forms.ComboBox();
            this.cboExv = new System.Windows.Forms.ComboBox();
            this.lblExv = new System.Windows.Forms.Label();
            this.txtCovMat = new System.Windows.Forms.TextBox();
            this.lblCover = new System.Windows.Forms.Label();
            this.txtDockMat = new System.Windows.Forms.TextBox();
            this.lblDock = new System.Windows.Forms.Label();
            this.gbPEparaFound = new System.Windows.Forms.GroupBox();
            this.label1 = new System.Windows.Forms.Label();
            this.cboFndMat = new System.Windows.Forms.ComboBox();
            this.cboFndAgl = new System.Windows.Forms.ComboBox();
            this.txtCuhThk = new System.Windows.Forms.TextBox();
            this.LBLconangle = new System.Windows.Forms.Label();
            this.LBLcushH = new System.Windows.Forms.Label();
            this.txtCuhMat = new System.Windows.Forms.TextBox();
            this.LBLcushname = new System.Windows.Forms.Label();
            this.txtPEname = new System.Windows.Forms.TextBox();
            this.LBLPEname = new System.Windows.Forms.Label();
            this.btnOK = new System.Windows.Forms.Button();
            this.btnCancel = new System.Windows.Forms.Button();
            this.btnAddPD = new System.Windows.Forms.Button();
            this.dgvPD = new System.Windows.Forms.DataGridView();
            this.dColDepth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dColRange = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.dCol = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.tcMain.SuspendLayout();
            this.tpPE.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPE)).BeginInit();
            this.tpPD.SuspendLayout();
            this.tpPW.SuspendLayout();
            this.tcPW.SuspendLayout();
            this.gbPEparaDock.SuspendLayout();
            this.gbPEparaFound.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPD)).BeginInit();
            this.SuspendLayout();
            // 
            // tcMain
            // 
            this.tcMain.Controls.Add(this.tpPE);
            this.tcMain.Controls.Add(this.tpPD);
            this.tcMain.Controls.Add(this.tpPW);
            this.tcMain.Location = new System.Drawing.Point(7, 195);
            this.tcMain.Name = "tcMain";
            this.tcMain.SelectedIndex = 0;
            this.tcMain.Size = new System.Drawing.Size(598, 342);
            this.tcMain.TabIndex = 1;
            // 
            // tpPE
            // 
            this.tpPE.Controls.Add(this.btnAddPEn);
            this.tpPE.Controls.Add(this.dgvPE);
            this.tpPE.Location = new System.Drawing.Point(4, 22);
            this.tpPE.Name = "tpPE";
            this.tpPE.Padding = new System.Windows.Forms.Padding(3);
            this.tpPE.Size = new System.Drawing.Size(590, 316);
            this.tpPE.TabIndex = 0;
            this.tpPE.Text = "围护原则";
            this.tpPE.UseVisualStyleBackColor = true;
            // 
            // btnAddPEn
            // 
            this.btnAddPEn.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnAddPEn.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnAddPEn.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnAddPEn.Location = new System.Drawing.Point(545, 3);
            this.btnAddPEn.Name = "btnAddPEn";
            this.btnAddPEn.Size = new System.Drawing.Size(41, 30);
            this.btnAddPEn.TabIndex = 62;
            this.btnAddPEn.Text = "+";
            this.btnAddPEn.UseVisualStyleBackColor = true;
            this.btnAddPEn.Click += new System.EventHandler(this.btnAddPEn_Click);
            // 
            // dgvPE
            // 
            this.dgvPE.AllowUserToAddRows = false;
            this.dgvPE.AllowUserToResizeColumns = false;
            this.dgvPE.AllowUserToResizeRows = false;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle1.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dgvPE.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dgvPE.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvPE.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.eColdepth,
            this.eColrange,
            this.eColPEnDis,
            this.eColSWDis});
            this.dgvPE.ContextMenuStrip = this.cmsDrop;
            dataGridViewCellStyle4.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle4.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle4.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle4.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle4.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle4.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle4.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dgvPE.DefaultCellStyle = dataGridViewCellStyle4;
            this.dgvPE.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvPE.Location = new System.Drawing.Point(3, 3);
            this.dgvPE.Name = "dgvPE";
            this.dgvPE.RowHeadersVisible = false;
            this.dgvPE.RowTemplate.Height = 23;
            this.dgvPE.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.CellSelect;
            this.dgvPE.Size = new System.Drawing.Size(584, 310);
            this.dgvPE.TabIndex = 61;
            this.dgvPE.CellDoubleClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dgvPE_CellDoubleClick);
            this.dgvPE.CellMouseUp += new System.Windows.Forms.DataGridViewCellMouseEventHandler(this.dgvPE_CellMouseUp);
            // 
            // eColdepth
            // 
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            this.eColdepth.DefaultCellStyle = dataGridViewCellStyle2;
            this.eColdepth.HeaderText = "埋深";
            this.eColdepth.Name = "eColdepth";
            this.eColdepth.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.eColdepth.Width = 70;
            // 
            // eColrange
            // 
            dataGridViewCellStyle3.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            this.eColrange.DefaultCellStyle = dataGridViewCellStyle3;
            this.eColrange.HeaderText = "范围";
            this.eColrange.Name = "eColrange";
            this.eColrange.ReadOnly = true;
            this.eColrange.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.eColrange.Width = 70;
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
            // eColSWDis
            // 
            this.eColSWDis.HeaderText = "止水(右键选择,双击编辑)";
            this.eColSWDis.Name = "eColSWDis";
            this.eColSWDis.ReadOnly = true;
            this.eColSWDis.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.eColSWDis.Width = 200;
            // 
            // cmsDrop
            // 
            this.cmsDrop.Name = "cmsDrop";
            this.cmsDrop.Size = new System.Drawing.Size(61, 4);
            this.cmsDrop.ItemClicked += new System.Windows.Forms.ToolStripItemClickedEventHandler(this.cmsDrop_ItemClicked);
            // 
            // tpPD
            // 
            this.tpPD.Controls.Add(this.btnAddPD);
            this.tpPD.Controls.Add(this.dgvPD);
            this.tpPD.Location = new System.Drawing.Point(4, 22);
            this.tpPD.Name = "tpPD";
            this.tpPD.Padding = new System.Windows.Forms.Padding(3);
            this.tpPD.Size = new System.Drawing.Size(590, 316);
            this.tpPD.TabIndex = 1;
            this.tpPD.Text = "降水原则";
            this.tpPD.UseVisualStyleBackColor = true;
            // 
            // tpPW
            // 
            this.tpPW.Controls.Add(this.tcPW);
            this.tpPW.Location = new System.Drawing.Point(4, 22);
            this.tpPW.Name = "tpPW";
            this.tpPW.Size = new System.Drawing.Size(590, 316);
            this.tpPW.TabIndex = 2;
            this.tpPW.Text = "工作面宽度";
            this.tpPW.UseVisualStyleBackColor = true;
            // 
            // tcPW
            // 
            this.tcPW.Controls.Add(this.tabPage4);
            this.tcPW.Controls.Add(this.tabPage5);
            this.tcPW.Controls.Add(this.tabPage6);
            this.tcPW.Controls.Add(this.tabPage7);
            this.tcPW.Controls.Add(this.tabPage8);
            this.tcPW.Controls.Add(this.tabPage9);
            this.tcPW.Dock = System.Windows.Forms.DockStyle.Fill;
            this.tcPW.Location = new System.Drawing.Point(0, 0);
            this.tcPW.Name = "tcPW";
            this.tcPW.SelectedIndex = 0;
            this.tcPW.Size = new System.Drawing.Size(590, 316);
            this.tcPW.TabIndex = 0;
            // 
            // tabPage4
            // 
            this.tabPage4.Location = new System.Drawing.Point(4, 22);
            this.tabPage4.Name = "tabPage4";
            this.tabPage4.Padding = new System.Windows.Forms.Padding(3);
            this.tabPage4.Size = new System.Drawing.Size(582, 290);
            this.tabPage4.TabIndex = 0;
            this.tabPage4.Text = "tabPage4";
            this.tabPage4.UseVisualStyleBackColor = true;
            // 
            // tabPage5
            // 
            this.tabPage5.Location = new System.Drawing.Point(4, 22);
            this.tabPage5.Name = "tabPage5";
            this.tabPage5.Padding = new System.Windows.Forms.Padding(3);
            this.tabPage5.Size = new System.Drawing.Size(582, 290);
            this.tabPage5.TabIndex = 1;
            this.tabPage5.Text = "tabPage5";
            this.tabPage5.UseVisualStyleBackColor = true;
            // 
            // tabPage6
            // 
            this.tabPage6.Location = new System.Drawing.Point(4, 22);
            this.tabPage6.Name = "tabPage6";
            this.tabPage6.Size = new System.Drawing.Size(582, 290);
            this.tabPage6.TabIndex = 2;
            this.tabPage6.Text = "tabPage6";
            this.tabPage6.UseVisualStyleBackColor = true;
            // 
            // tabPage7
            // 
            this.tabPage7.Location = new System.Drawing.Point(4, 22);
            this.tabPage7.Name = "tabPage7";
            this.tabPage7.Size = new System.Drawing.Size(582, 290);
            this.tabPage7.TabIndex = 3;
            this.tabPage7.Text = "tabPage7";
            this.tabPage7.UseVisualStyleBackColor = true;
            // 
            // tabPage8
            // 
            this.tabPage8.Location = new System.Drawing.Point(4, 22);
            this.tabPage8.Name = "tabPage8";
            this.tabPage8.Size = new System.Drawing.Size(582, 290);
            this.tabPage8.TabIndex = 4;
            this.tabPage8.Text = "tabPage8";
            this.tabPage8.UseVisualStyleBackColor = true;
            // 
            // tabPage9
            // 
            this.tabPage9.Location = new System.Drawing.Point(4, 22);
            this.tabPage9.Name = "tabPage9";
            this.tabPage9.Size = new System.Drawing.Size(582, 290);
            this.tabPage9.TabIndex = 5;
            this.tabPage9.Text = "tabPage9";
            this.tabPage9.UseVisualStyleBackColor = true;
            // 
            // gbPEparaDock
            // 
            this.gbPEparaDock.Controls.Add(this.lblBackFill);
            this.gbPEparaDock.Controls.Add(this.cboDockMat);
            this.gbPEparaDock.Controls.Add(this.cboExv);
            this.gbPEparaDock.Controls.Add(this.lblExv);
            this.gbPEparaDock.Controls.Add(this.txtCovMat);
            this.gbPEparaDock.Controls.Add(this.lblCover);
            this.gbPEparaDock.Controls.Add(this.txtDockMat);
            this.gbPEparaDock.Controls.Add(this.lblDock);
            this.gbPEparaDock.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.gbPEparaDock.Location = new System.Drawing.Point(7, 47);
            this.gbPEparaDock.Name = "gbPEparaDock";
            this.gbPEparaDock.Size = new System.Drawing.Size(214, 142);
            this.gbPEparaDock.TabIndex = 66;
            this.gbPEparaDock.TabStop = false;
            this.gbPEparaDock.Text = "挖填类型";
            // 
            // lblBackFill
            // 
            this.lblBackFill.AutoSize = true;
            this.lblBackFill.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.lblBackFill.Location = new System.Drawing.Point(6, 51);
            this.lblBackFill.Name = "lblBackFill";
            this.lblBackFill.Size = new System.Drawing.Size(59, 17);
            this.lblBackFill.TabIndex = 70;
            this.lblBackFill.Text = "坞塝回填:";
            // 
            // cboDockMat
            // 
            this.cboDockMat.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cboDockMat.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.cboDockMat.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.cboDockMat.FormattingEnabled = true;
            this.cboDockMat.Location = new System.Drawing.Point(80, 48);
            this.cboDockMat.Name = "cboDockMat";
            this.cboDockMat.Size = new System.Drawing.Size(121, 25);
            this.cboDockMat.TabIndex = 69;
            // 
            // cboExv
            // 
            this.cboExv.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.cboExv.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.cboExv.FormattingEnabled = true;
            this.cboExv.Location = new System.Drawing.Point(80, 18);
            this.cboExv.Name = "cboExv";
            this.cboExv.Size = new System.Drawing.Size(121, 25);
            this.cboExv.TabIndex = 68;
            // 
            // lblExv
            // 
            this.lblExv.AutoSize = true;
            this.lblExv.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.lblExv.Location = new System.Drawing.Point(6, 23);
            this.lblExv.Name = "lblExv";
            this.lblExv.Size = new System.Drawing.Size(59, 17);
            this.lblExv.TabIndex = 67;
            this.lblExv.Text = "开挖类型:";
            // 
            // txtCovMat
            // 
            this.txtCovMat.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.txtCovMat.Location = new System.Drawing.Point(80, 102);
            this.txtCovMat.Name = "txtCovMat";
            this.txtCovMat.Size = new System.Drawing.Size(121, 23);
            this.txtCovMat.TabIndex = 66;
            // 
            // lblCover
            // 
            this.lblCover.AutoSize = true;
            this.lblCover.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.lblCover.Location = new System.Drawing.Point(6, 108);
            this.lblCover.Name = "lblCover";
            this.lblCover.Size = new System.Drawing.Size(59, 17);
            this.lblCover.TabIndex = 65;
            this.lblCover.Text = "顶部回填:";
            // 
            // txtDockMat
            // 
            this.txtDockMat.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.txtDockMat.Location = new System.Drawing.Point(80, 76);
            this.txtDockMat.Name = "txtDockMat";
            this.txtDockMat.Size = new System.Drawing.Size(121, 23);
            this.txtDockMat.TabIndex = 64;
            // 
            // lblDock
            // 
            this.lblDock.AutoSize = true;
            this.lblDock.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.lblDock.Location = new System.Drawing.Point(6, 79);
            this.lblDock.Name = "lblDock";
            this.lblDock.Size = new System.Drawing.Size(59, 17);
            this.lblDock.TabIndex = 63;
            this.lblDock.Text = "坞塝材质:";
            // 
            // gbPEparaFound
            // 
            this.gbPEparaFound.Controls.Add(this.label1);
            this.gbPEparaFound.Controls.Add(this.cboFndMat);
            this.gbPEparaFound.Controls.Add(this.cboFndAgl);
            this.gbPEparaFound.Controls.Add(this.txtCuhThk);
            this.gbPEparaFound.Controls.Add(this.LBLconangle);
            this.gbPEparaFound.Controls.Add(this.LBLcushH);
            this.gbPEparaFound.Controls.Add(this.txtCuhMat);
            this.gbPEparaFound.Controls.Add(this.LBLcushname);
            this.gbPEparaFound.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.gbPEparaFound.Location = new System.Drawing.Point(244, 47);
            this.gbPEparaFound.Name = "gbPEparaFound";
            this.gbPEparaFound.Size = new System.Drawing.Size(214, 142);
            this.gbPEparaFound.TabIndex = 67;
            this.gbPEparaFound.TabStop = false;
            this.gbPEparaFound.Text = "管道基础";
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.label1.Location = new System.Drawing.Point(9, 23);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(59, 17);
            this.label1.TabIndex = 57;
            this.label1.Text = "基础材质:";
            // 
            // cboFndMat
            // 
            this.cboFndMat.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cboFndMat.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.cboFndMat.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.cboFndMat.FormattingEnabled = true;
            this.cboFndMat.Location = new System.Drawing.Point(85, 18);
            this.cboFndMat.Name = "cboFndMat";
            this.cboFndMat.Size = new System.Drawing.Size(123, 25);
            this.cboFndMat.TabIndex = 54;
            // 
            // cboFndAgl
            // 
            this.cboFndAgl.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cboFndAgl.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.cboFndAgl.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.cboFndAgl.FormattingEnabled = true;
            this.cboFndAgl.Location = new System.Drawing.Point(85, 48);
            this.cboFndAgl.Name = "cboFndAgl";
            this.cboFndAgl.Size = new System.Drawing.Size(123, 25);
            this.cboFndAgl.TabIndex = 53;
            // 
            // txtCuhThk
            // 
            this.txtCuhThk.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.txtCuhThk.Location = new System.Drawing.Point(85, 105);
            this.txtCuhThk.Name = "txtCuhThk";
            this.txtCuhThk.Size = new System.Drawing.Size(123, 23);
            this.txtCuhThk.TabIndex = 56;
            // 
            // LBLconangle
            // 
            this.LBLconangle.AutoSize = true;
            this.LBLconangle.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLconangle.Location = new System.Drawing.Point(9, 51);
            this.LBLconangle.Name = "LBLconangle";
            this.LBLconangle.Size = new System.Drawing.Size(72, 17);
            this.LBLconangle.TabIndex = 52;
            this.LBLconangle.Text = "基础角度(°):";
            // 
            // LBLcushH
            // 
            this.LBLcushH.AutoSize = true;
            this.LBLcushH.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLcushH.Location = new System.Drawing.Point(9, 108);
            this.LBLcushH.Name = "LBLcushH";
            this.LBLcushH.Size = new System.Drawing.Size(77, 17);
            this.LBLcushH.TabIndex = 55;
            this.LBLcushH.Text = "垫层厚(mm):";
            // 
            // txtCuhMat
            // 
            this.txtCuhMat.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.txtCuhMat.Location = new System.Drawing.Point(85, 76);
            this.txtCuhMat.Name = "txtCuhMat";
            this.txtCuhMat.Size = new System.Drawing.Size(123, 23);
            this.txtCuhMat.TabIndex = 54;
            // 
            // LBLcushname
            // 
            this.LBLcushname.AutoSize = true;
            this.LBLcushname.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLcushname.Location = new System.Drawing.Point(9, 79);
            this.LBLcushname.Name = "LBLcushname";
            this.LBLcushname.Size = new System.Drawing.Size(59, 17);
            this.LBLcushname.TabIndex = 53;
            this.LBLcushname.Text = "垫层材质:";
            // 
            // txtPEname
            // 
            this.txtPEname.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.txtPEname.Location = new System.Drawing.Point(87, 6);
            this.txtPEname.Name = "txtPEname";
            this.txtPEname.Size = new System.Drawing.Size(371, 29);
            this.txtPEname.TabIndex = 69;
            // 
            // LBLPEname
            // 
            this.LBLPEname.AutoSize = true;
            this.LBLPEname.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLPEname.Location = new System.Drawing.Point(12, 9);
            this.LBLPEname.Name = "LBLPEname";
            this.LBLPEname.Size = new System.Drawing.Size(79, 22);
            this.LBLPEname.TabIndex = 68;
            this.LBLPEname.Text = "原则名称:";
            // 
            // btnOK
            // 
            this.btnOK.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnOK.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnOK.Location = new System.Drawing.Point(464, 5);
            this.btnOK.Name = "btnOK";
            this.btnOK.Size = new System.Drawing.Size(141, 110);
            this.btnOK.TabIndex = 70;
            this.btnOK.Text = "确定";
            this.btnOK.UseVisualStyleBackColor = true;
            this.btnOK.Click += new System.EventHandler(this.btnOK_Click);
            // 
            // btnCancel
            // 
            this.btnCancel.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnCancel.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnCancel.Location = new System.Drawing.Point(464, 121);
            this.btnCancel.Name = "btnCancel";
            this.btnCancel.Size = new System.Drawing.Size(141, 67);
            this.btnCancel.TabIndex = 71;
            this.btnCancel.Text = "取消";
            this.btnCancel.UseVisualStyleBackColor = true;
            this.btnCancel.Click += new System.EventHandler(this.btnCancel_Click);
            // 
            // btnAddPD
            // 
            this.btnAddPD.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnAddPD.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.btnAddPD.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.btnAddPD.Location = new System.Drawing.Point(545, 3);
            this.btnAddPD.Name = "btnAddPD";
            this.btnAddPD.Size = new System.Drawing.Size(41, 30);
            this.btnAddPD.TabIndex = 64;
            this.btnAddPD.Text = "+";
            this.btnAddPD.UseVisualStyleBackColor = true;
            // 
            // dgvPD
            // 
            this.dgvPD.AllowUserToAddRows = false;
            this.dgvPD.AllowUserToResizeColumns = false;
            this.dgvPD.AllowUserToResizeRows = false;
            dataGridViewCellStyle5.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle5.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle5.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle5.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle5.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle5.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle5.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dgvPD.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle5;
            this.dgvPD.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvPD.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.dColDepth,
            this.dColRange,
            this.dCol});
            this.dgvPD.ContextMenuStrip = this.cmsDrop;
            dataGridViewCellStyle8.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle8.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle8.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle8.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle8.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle8.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle8.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dgvPD.DefaultCellStyle = dataGridViewCellStyle8;
            this.dgvPD.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvPD.Location = new System.Drawing.Point(3, 3);
            this.dgvPD.Name = "dgvPD";
            this.dgvPD.RowHeadersVisible = false;
            this.dgvPD.RowTemplate.Height = 23;
            this.dgvPD.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.CellSelect;
            this.dgvPD.Size = new System.Drawing.Size(584, 310);
            this.dgvPD.TabIndex = 63;
            // 
            // dColDepth
            // 
            dataGridViewCellStyle6.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            this.dColDepth.DefaultCellStyle = dataGridViewCellStyle6;
            this.dColDepth.HeaderText = "埋深";
            this.dColDepth.Name = "dColDepth";
            this.dColDepth.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.dColDepth.Width = 70;
            // 
            // dColRange
            // 
            dataGridViewCellStyle7.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            this.dColRange.DefaultCellStyle = dataGridViewCellStyle7;
            this.dColRange.HeaderText = "范围";
            this.dColRange.Name = "dColRange";
            this.dColRange.ReadOnly = true;
            this.dColRange.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.dColRange.Width = 70;
            // 
            // dCol
            // 
            this.dCol.HeaderText = "降水";
            this.dCol.Name = "dCol";
            this.dCol.ReadOnly = true;
            this.dCol.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.dCol.ToolTipText = "双击编辑围护形式";
            this.dCol.Width = 200;
            // 
            // FmPE
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(610, 541);
            this.Controls.Add(this.btnCancel);
            this.Controls.Add(this.btnOK);
            this.Controls.Add(this.txtPEname);
            this.Controls.Add(this.LBLPEname);
            this.Controls.Add(this.gbPEparaFound);
            this.Controls.Add(this.gbPEparaDock);
            this.Controls.Add(this.tcMain);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.Name = "FmPE";
            this.ShowIcon = false;
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "FmPE";
            this.Load += new System.EventHandler(this.FmPE_Load);
            this.tcMain.ResumeLayout(false);
            this.tpPE.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.dgvPE)).EndInit();
            this.tpPD.ResumeLayout(false);
            this.tpPW.ResumeLayout(false);
            this.tcPW.ResumeLayout(false);
            this.gbPEparaDock.ResumeLayout(false);
            this.gbPEparaDock.PerformLayout();
            this.gbPEparaFound.ResumeLayout(false);
            this.gbPEparaFound.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dgvPD)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.TabControl tcMain;
        private System.Windows.Forms.TabPage tpPE;
        private System.Windows.Forms.TabPage tpPD;
        private System.Windows.Forms.TabPage tpPW;
        private System.Windows.Forms.TabControl tcPW;
        private System.Windows.Forms.TabPage tabPage4;
        private System.Windows.Forms.TabPage tabPage5;
        private System.Windows.Forms.TabPage tabPage6;
        private System.Windows.Forms.TabPage tabPage7;
        private System.Windows.Forms.TabPage tabPage8;
        private System.Windows.Forms.TabPage tabPage9;
        private System.Windows.Forms.GroupBox gbPEparaDock;
        private System.Windows.Forms.Label lblBackFill;
        private System.Windows.Forms.ComboBox cboDockMat;
        private System.Windows.Forms.ComboBox cboExv;
        private System.Windows.Forms.Label lblExv;
        private System.Windows.Forms.TextBox txtCovMat;
        private System.Windows.Forms.Label lblCover;
        private System.Windows.Forms.TextBox txtDockMat;
        private System.Windows.Forms.Label lblDock;
        private System.Windows.Forms.GroupBox gbPEparaFound;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.ComboBox cboFndMat;
        private System.Windows.Forms.ComboBox cboFndAgl;
        private System.Windows.Forms.TextBox txtCuhThk;
        private System.Windows.Forms.Label LBLconangle;
        private System.Windows.Forms.Label LBLcushH;
        private System.Windows.Forms.TextBox txtCuhMat;
        private System.Windows.Forms.Label LBLcushname;
        private System.Windows.Forms.TextBox txtPEname;
        private System.Windows.Forms.Label LBLPEname;
        private System.Windows.Forms.Button btnAddPEn;
        private System.Windows.Forms.DataGridView dgvPE;
        private System.Windows.Forms.ContextMenuStrip cmsDrop;
        private System.Windows.Forms.Button btnOK;
        private System.Windows.Forms.Button btnCancel;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColdepth;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColrange;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColPEnDis;
        private System.Windows.Forms.DataGridViewTextBoxColumn eColSWDis;
        private System.Windows.Forms.Button btnAddPD;
        private System.Windows.Forms.DataGridView dgvPD;
        private System.Windows.Forms.DataGridViewTextBoxColumn dColDepth;
        private System.Windows.Forms.DataGridViewTextBoxColumn dColRange;
        private System.Windows.Forms.DataGridViewTextBoxColumn dCol;
    }
}
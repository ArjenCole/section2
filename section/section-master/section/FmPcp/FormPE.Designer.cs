namespace section
{
    partial class FormPE
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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle5 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle8 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle6 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle7 = new System.Windows.Forms.DataGridViewCellStyle();
            this.BTNadd = new System.Windows.Forms.Button();
            this.dGVPE = new System.Windows.Forms.DataGridView();
            this.Coldepth = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Colrange = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColEclsCat = new System.Windows.Forms.DataGridViewComboBoxColumn();
            this.ColEclsDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColWSCat = new System.Windows.Forms.DataGridViewComboBoxColumn();
            this.ColWSDis = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.BTNyes = new System.Windows.Forms.Button();
            this.TXTPEname = new System.Windows.Forms.TextBox();
            this.LBLPEname = new System.Windows.Forms.Label();
            this.CBOconfound = new System.Windows.Forms.ComboBox();
            this.CBOconangle = new System.Windows.Forms.ComboBox();
            this.LBLconangle = new System.Windows.Forms.Label();
            this.groupBox3 = new System.Windows.Forms.GroupBox();
            this.TXTcushH = new System.Windows.Forms.TextBox();
            this.LBLcushH = new System.Windows.Forms.Label();
            this.TXTcushname = new System.Windows.Forms.TextBox();
            this.LBLcushname = new System.Windows.Forms.Label();
            this.groupBox1 = new System.Windows.Forms.GroupBox();
            this.label4 = new System.Windows.Forms.Label();
            this.CBOdock = new System.Windows.Forms.ComboBox();
            this.CBOexcvt = new System.Windows.Forms.ComboBox();
            this.LBLexv = new System.Windows.Forms.Label();
            this.TXTcover = new System.Windows.Forms.TextBox();
            this.LBLcover = new System.Windows.Forms.Label();
            this.TXTdock = new System.Windows.Forms.TextBox();
            this.LBLdock = new System.Windows.Forms.Label();
            this.groupBox4 = new System.Windows.Forms.GroupBox();
            this.LBLpre = new System.Windows.Forms.Label();
            this.BTNcancel = new System.Windows.Forms.Button();
            this.BTNWW = new System.Windows.Forms.Button();
            this.BTNWWpre = new System.Windows.Forms.Button();
            ((System.ComponentModel.ISupportInitialize)(this.dGVPE)).BeginInit();
            this.groupBox3.SuspendLayout();
            this.groupBox1.SuspendLayout();
            this.groupBox4.SuspendLayout();
            this.SuspendLayout();
            // 
            // BTNadd
            // 
            this.BTNadd.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNadd.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.BTNadd.Location = new System.Drawing.Point(759, 189);
            this.BTNadd.Name = "BTNadd";
            this.BTNadd.Size = new System.Drawing.Size(41, 30);
            this.BTNadd.TabIndex = 60;
            this.BTNadd.Text = "+";
            this.BTNadd.UseVisualStyleBackColor = true;
            this.BTNadd.Click += new System.EventHandler(this.BTNadd_Click);
            // 
            // dGVPE
            // 
            this.dGVPE.AllowUserToAddRows = false;
            this.dGVPE.AllowUserToResizeColumns = false;
            this.dGVPE.AllowUserToResizeRows = false;
            dataGridViewCellStyle5.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            dataGridViewCellStyle5.BackColor = System.Drawing.SystemColors.Control;
            dataGridViewCellStyle5.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle5.ForeColor = System.Drawing.SystemColors.WindowText;
            dataGridViewCellStyle5.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle5.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle5.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dGVPE.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle5;
            this.dGVPE.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dGVPE.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Coldepth,
            this.Colrange,
            this.ColEclsCat,
            this.ColEclsDis,
            this.ColWSCat,
            this.ColWSDis});
            dataGridViewCellStyle8.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle8.BackColor = System.Drawing.SystemColors.Window;
            dataGridViewCellStyle8.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            dataGridViewCellStyle8.ForeColor = System.Drawing.SystemColors.ControlText;
            dataGridViewCellStyle8.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle8.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle8.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dGVPE.DefaultCellStyle = dataGridViewCellStyle8;
            this.dGVPE.Location = new System.Drawing.Point(16, 189);
            this.dGVPE.Name = "dGVPE";
            this.dGVPE.RowHeadersVisible = false;
            this.dGVPE.RowTemplate.Height = 23;
            this.dGVPE.Size = new System.Drawing.Size(784, 379);
            this.dGVPE.TabIndex = 59;
            this.dGVPE.CellClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVPE_CellClick);
            this.dGVPE.CellDoubleClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVPE_CellDoubleClick);
            this.dGVPE.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this.dGVPE_CellEndEdit);
            this.dGVPE.KeyUp += new System.Windows.Forms.KeyEventHandler(this.dGVPE_KeyUp);
            // 
            // Coldepth
            // 
            dataGridViewCellStyle6.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleRight;
            this.Coldepth.DefaultCellStyle = dataGridViewCellStyle6;
            this.Coldepth.HeaderText = "埋深";
            this.Coldepth.Name = "Coldepth";
            this.Coldepth.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.Coldepth.Width = 70;
            // 
            // Colrange
            // 
            dataGridViewCellStyle7.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            this.Colrange.DefaultCellStyle = dataGridViewCellStyle7;
            this.Colrange.HeaderText = "范围";
            this.Colrange.Name = "Colrange";
            this.Colrange.ReadOnly = true;
            this.Colrange.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.Colrange.Width = 70;
            // 
            // ColEclsCat
            // 
            this.ColEclsCat.DisplayStyle = System.Windows.Forms.DataGridViewComboBoxDisplayStyle.ComboBox;
            this.ColEclsCat.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.ColEclsCat.HeaderText = "围护类型";
            this.ColEclsCat.Name = "ColEclsCat";
            // 
            // ColEclsDis
            // 
            this.ColEclsDis.HeaderText = "围护形式描述";
            this.ColEclsDis.Name = "ColEclsDis";
            this.ColEclsDis.ReadOnly = true;
            this.ColEclsDis.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColEclsDis.ToolTipText = "双击编辑围护形式";
            this.ColEclsDis.Width = 200;
            // 
            // ColWSCat
            // 
            this.ColWSCat.DisplayStyle = System.Windows.Forms.DataGridViewComboBoxDisplayStyle.ComboBox;
            this.ColWSCat.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.ColWSCat.HeaderText = "止水类型";
            this.ColWSCat.Name = "ColWSCat";
            this.ColWSCat.Resizable = System.Windows.Forms.DataGridViewTriState.True;
            // 
            // ColWSDis
            // 
            this.ColWSDis.HeaderText = "止水形式描述";
            this.ColWSDis.Name = "ColWSDis";
            this.ColWSDis.ReadOnly = true;
            this.ColWSDis.SortMode = System.Windows.Forms.DataGridViewColumnSortMode.NotSortable;
            this.ColWSDis.Width = 200;
            // 
            // BTNyes
            // 
            this.BTNyes.Location = new System.Drawing.Point(735, 12);
            this.BTNyes.Name = "BTNyes";
            this.BTNyes.Size = new System.Drawing.Size(65, 51);
            this.BTNyes.TabIndex = 47;
            this.BTNyes.Text = "确认修改";
            this.BTNyes.UseVisualStyleBackColor = true;
            this.BTNyes.Click += new System.EventHandler(this.BTNyes_Click);
            // 
            // TXTPEname
            // 
            this.TXTPEname.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTPEname.Location = new System.Drawing.Point(99, 9);
            this.TXTPEname.Name = "TXTPEname";
            this.TXTPEname.Size = new System.Drawing.Size(121, 26);
            this.TXTPEname.TabIndex = 41;
            // 
            // LBLPEname
            // 
            this.LBLPEname.AutoSize = true;
            this.LBLPEname.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLPEname.Location = new System.Drawing.Point(25, 12);
            this.LBLPEname.Name = "LBLPEname";
            this.LBLPEname.Size = new System.Drawing.Size(69, 19);
            this.LBLPEname.TabIndex = 40;
            this.LBLPEname.Text = "原则名称:";
            // 
            // CBOconfound
            // 
            this.CBOconfound.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBOconfound.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.CBOconfound.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.CBOconfound.FormattingEnabled = true;
            this.CBOconfound.Location = new System.Drawing.Point(12, 33);
            this.CBOconfound.Name = "CBOconfound";
            this.CBOconfound.Size = new System.Drawing.Size(123, 25);
            this.CBOconfound.TabIndex = 54;
            // 
            // CBOconangle
            // 
            this.CBOconangle.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBOconangle.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.CBOconangle.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.CBOconangle.FormattingEnabled = true;
            this.CBOconangle.Location = new System.Drawing.Point(64, 70);
            this.CBOconangle.Name = "CBOconangle";
            this.CBOconangle.Size = new System.Drawing.Size(59, 25);
            this.CBOconangle.TabIndex = 53;
            // 
            // LBLconangle
            // 
            this.LBLconangle.AutoSize = true;
            this.LBLconangle.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLconangle.Location = new System.Drawing.Point(9, 73);
            this.LBLconangle.Name = "LBLconangle";
            this.LBLconangle.Size = new System.Drawing.Size(129, 17);
            this.LBLconangle.TabIndex = 52;
            this.LBLconangle.Text = "基础角度                 °";
            // 
            // groupBox3
            // 
            this.groupBox3.Controls.Add(this.CBOconfound);
            this.groupBox3.Controls.Add(this.CBOconangle);
            this.groupBox3.Controls.Add(this.TXTcushH);
            this.groupBox3.Controls.Add(this.LBLconangle);
            this.groupBox3.Controls.Add(this.LBLcushH);
            this.groupBox3.Controls.Add(this.TXTcushname);
            this.groupBox3.Controls.Add(this.LBLcushname);
            this.groupBox3.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.groupBox3.Location = new System.Drawing.Point(257, 5);
            this.groupBox3.Name = "groupBox3";
            this.groupBox3.Size = new System.Drawing.Size(141, 178);
            this.groupBox3.TabIndex = 64;
            this.groupBox3.TabStop = false;
            this.groupBox3.Text = "管道基础";
            // 
            // TXTcushH
            // 
            this.TXTcushH.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTcushH.Location = new System.Drawing.Point(71, 142);
            this.TXTcushH.Name = "TXTcushH";
            this.TXTcushH.Size = new System.Drawing.Size(64, 23);
            this.TXTcushH.TabIndex = 56;
            // 
            // LBLcushH
            // 
            this.LBLcushH.AutoSize = true;
            this.LBLcushH.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLcushH.Location = new System.Drawing.Point(9, 145);
            this.LBLcushH.Name = "LBLcushH";
            this.LBLcushH.Size = new System.Drawing.Size(54, 17);
            this.LBLcushH.TabIndex = 55;
            this.LBLcushH.Text = "厚度mm";
            // 
            // TXTcushname
            // 
            this.TXTcushname.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTcushname.Location = new System.Drawing.Point(71, 107);
            this.TXTcushname.Name = "TXTcushname";
            this.TXTcushname.Size = new System.Drawing.Size(64, 23);
            this.TXTcushname.TabIndex = 54;
            // 
            // LBLcushname
            // 
            this.LBLcushname.AutoSize = true;
            this.LBLcushname.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLcushname.Location = new System.Drawing.Point(9, 110);
            this.LBLcushname.Name = "LBLcushname";
            this.LBLcushname.Size = new System.Drawing.Size(56, 17);
            this.LBLcushname.TabIndex = 53;
            this.LBLcushname.Text = "垫层材质";
            // 
            // groupBox1
            // 
            this.groupBox1.Controls.Add(this.label4);
            this.groupBox1.Controls.Add(this.CBOdock);
            this.groupBox1.Controls.Add(this.CBOexcvt);
            this.groupBox1.Controls.Add(this.LBLexv);
            this.groupBox1.Controls.Add(this.TXTcover);
            this.groupBox1.Controls.Add(this.LBLcover);
            this.groupBox1.Controls.Add(this.TXTdock);
            this.groupBox1.Controls.Add(this.LBLdock);
            this.groupBox1.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.groupBox1.Location = new System.Drawing.Point(29, 41);
            this.groupBox1.Name = "groupBox1";
            this.groupBox1.Size = new System.Drawing.Size(214, 142);
            this.groupBox1.TabIndex = 65;
            this.groupBox1.TabStop = false;
            this.groupBox1.Text = "挖填类型";
            // 
            // label4
            // 
            this.label4.AutoSize = true;
            this.label4.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.label4.Location = new System.Drawing.Point(6, 79);
            this.label4.Name = "label4";
            this.label4.Size = new System.Drawing.Size(59, 17);
            this.label4.TabIndex = 70;
            this.label4.Text = "坞塝回填:";
            // 
            // CBOdock
            // 
            this.CBOdock.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.CBOdock.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.CBOdock.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.CBOdock.FormattingEnabled = true;
            this.CBOdock.Location = new System.Drawing.Point(80, 76);
            this.CBOdock.Name = "CBOdock";
            this.CBOdock.Size = new System.Drawing.Size(121, 25);
            this.CBOdock.TabIndex = 69;
            // 
            // CBOexcvt
            // 
            this.CBOexcvt.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.CBOexcvt.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.CBOexcvt.FormattingEnabled = true;
            this.CBOexcvt.Location = new System.Drawing.Point(80, 20);
            this.CBOexcvt.Name = "CBOexcvt";
            this.CBOexcvt.Size = new System.Drawing.Size(121, 25);
            this.CBOexcvt.TabIndex = 68;
            // 
            // LBLexv
            // 
            this.LBLexv.AutoSize = true;
            this.LBLexv.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLexv.Location = new System.Drawing.Point(6, 23);
            this.LBLexv.Name = "LBLexv";
            this.LBLexv.Size = new System.Drawing.Size(59, 17);
            this.LBLexv.TabIndex = 67;
            this.LBLexv.Text = "开挖类型:";
            // 
            // TXTcover
            // 
            this.TXTcover.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTcover.Location = new System.Drawing.Point(80, 105);
            this.TXTcover.Name = "TXTcover";
            this.TXTcover.Size = new System.Drawing.Size(121, 23);
            this.TXTcover.TabIndex = 66;
            // 
            // LBLcover
            // 
            this.LBLcover.AutoSize = true;
            this.LBLcover.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLcover.Location = new System.Drawing.Point(6, 107);
            this.LBLcover.Name = "LBLcover";
            this.LBLcover.Size = new System.Drawing.Size(59, 17);
            this.LBLcover.TabIndex = 65;
            this.LBLcover.Text = "顶部回填:";
            // 
            // TXTdock
            // 
            this.TXTdock.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.TXTdock.Location = new System.Drawing.Point(80, 49);
            this.TXTdock.Name = "TXTdock";
            this.TXTdock.Size = new System.Drawing.Size(121, 23);
            this.TXTdock.TabIndex = 64;
            // 
            // LBLdock
            // 
            this.LBLdock.AutoSize = true;
            this.LBLdock.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLdock.Location = new System.Drawing.Point(6, 51);
            this.LBLdock.Name = "LBLdock";
            this.LBLdock.Size = new System.Drawing.Size(59, 17);
            this.LBLdock.TabIndex = 63;
            this.LBLdock.Text = "坞塝材质:";
            // 
            // groupBox4
            // 
            this.groupBox4.Controls.Add(this.LBLpre);
            this.groupBox4.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.groupBox4.Location = new System.Drawing.Point(419, 5);
            this.groupBox4.Name = "groupBox4";
            this.groupBox4.Size = new System.Drawing.Size(305, 144);
            this.groupBox4.TabIndex = 66;
            this.groupBox4.TabStop = false;
            this.groupBox4.Text = "降水措施";
            // 
            // LBLpre
            // 
            this.LBLpre.Font = new System.Drawing.Font("微软雅黑", 10.5F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            this.LBLpre.Location = new System.Drawing.Point(6, 25);
            this.LBLpre.Name = "LBLpre";
            this.LBLpre.Size = new System.Drawing.Size(280, 107);
            this.LBLpre.TabIndex = 56;
            this.LBLpre.Tag = "";
            this.LBLpre.Text = "降水措施描述";
            // 
            // BTNcancel
            // 
            this.BTNcancel.Location = new System.Drawing.Point(735, 69);
            this.BTNcancel.Name = "BTNcancel";
            this.BTNcancel.Size = new System.Drawing.Size(65, 51);
            this.BTNcancel.TabIndex = 67;
            this.BTNcancel.Text = "取消修改";
            this.BTNcancel.UseVisualStyleBackColor = true;
            this.BTNcancel.Click += new System.EventHandler(this.BTNcancel_Click);
            // 
            // BTNWW
            // 
            this.BTNWW.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNWW.Location = new System.Drawing.Point(592, 153);
            this.BTNWW.Name = "BTNWW";
            this.BTNWW.Size = new System.Drawing.Size(132, 27);
            this.BTNWW.TabIndex = 68;
            this.BTNWW.Text = "编辑工作面宽度原则";
            this.BTNWW.UseVisualStyleBackColor = true;
            this.BTNWW.Click += new System.EventHandler(this.BTNWW_Click);
            // 
            // BTNWWpre
            // 
            this.BTNWWpre.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.BTNWWpre.Location = new System.Drawing.Point(419, 153);
            this.BTNWWpre.Name = "BTNWWpre";
            this.BTNWWpre.Size = new System.Drawing.Size(167, 27);
            this.BTNWWpre.TabIndex = 69;
            this.BTNWWpre.Text = "编辑降水措施原则";
            this.BTNWWpre.UseVisualStyleBackColor = true;
            this.BTNWWpre.Click += new System.EventHandler(this.BTNWWpre_Click);
            // 
            // FormPE
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(816, 581);
            this.Controls.Add(this.BTNWWpre);
            this.Controls.Add(this.BTNWW);
            this.Controls.Add(this.BTNcancel);
            this.Controls.Add(this.groupBox4);
            this.Controls.Add(this.groupBox1);
            this.Controls.Add(this.groupBox3);
            this.Controls.Add(this.BTNadd);
            this.Controls.Add(this.dGVPE);
            this.Controls.Add(this.BTNyes);
            this.Controls.Add(this.TXTPEname);
            this.Controls.Add(this.LBLPEname);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedToolWindow;
            this.KeyPreview = true;
            this.Name = "FormPE";
            this.ShowInTaskbar = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "围护原则编辑";
            this.Load += new System.EventHandler(this.FormPE_Load);
            this.KeyUp += new System.Windows.Forms.KeyEventHandler(this.FormPE_KeyUp);
            ((System.ComponentModel.ISupportInitialize)(this.dGVPE)).EndInit();
            this.groupBox3.ResumeLayout(false);
            this.groupBox3.PerformLayout();
            this.groupBox1.ResumeLayout(false);
            this.groupBox1.PerformLayout();
            this.groupBox4.ResumeLayout(false);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Button BTNadd;
        private System.Windows.Forms.DataGridView dGVPE;
        private System.Windows.Forms.Button BTNyes;
        private System.Windows.Forms.TextBox TXTPEname;
        private System.Windows.Forms.Label LBLPEname;
        private System.Windows.Forms.ComboBox CBOconfound;
        private System.Windows.Forms.ComboBox CBOconangle;
        private System.Windows.Forms.Label LBLconangle;
        private System.Windows.Forms.GroupBox groupBox3;
        private System.Windows.Forms.TextBox TXTcushH;
        private System.Windows.Forms.Label LBLcushH;
        private System.Windows.Forms.TextBox TXTcushname;
        private System.Windows.Forms.Label LBLcushname;
        private System.Windows.Forms.GroupBox groupBox1;
        private System.Windows.Forms.Label label4;
        private System.Windows.Forms.ComboBox CBOdock;
        private System.Windows.Forms.ComboBox CBOexcvt;
        private System.Windows.Forms.Label LBLexv;
        private System.Windows.Forms.TextBox TXTcover;
        private System.Windows.Forms.Label LBLcover;
        private System.Windows.Forms.TextBox TXTdock;
        private System.Windows.Forms.Label LBLdock;
        private System.Windows.Forms.GroupBox groupBox4;
        private System.Windows.Forms.Label LBLpre;
        private System.Windows.Forms.Button BTNcancel;
        private System.Windows.Forms.DataGridViewTextBoxColumn Coldepth;
        private System.Windows.Forms.DataGridViewTextBoxColumn Colrange;
        private System.Windows.Forms.DataGridViewComboBoxColumn ColEclsCat;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColEclsDis;
        private System.Windows.Forms.DataGridViewComboBoxColumn ColWSCat;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColWSDis;
        private System.Windows.Forms.Button BTNWW;
        private System.Windows.Forms.Button BTNWWpre;
    }
}
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace section2
{
    public class mcDataGridView: System.Windows.Forms.DataGridView
    {
        public mcDataGridView(string pName,Dictionary<string,string> pDic)
        {
            this.AllowUserToAddRows = false;
            this.AllowUserToResizeColumns = false;
            this.AllowUserToResizeRows = false;
            DataGridViewCellStyle columnHeadersDefaultCellStyle = new DataGridViewCellStyle();
            columnHeadersDefaultCellStyle.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleCenter;
            columnHeadersDefaultCellStyle.BackColor = System.Drawing.SystemColors.Control;
            columnHeadersDefaultCellStyle.Font = new System.Drawing.Font("微软雅黑", 12F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            columnHeadersDefaultCellStyle.ForeColor = System.Drawing.SystemColors.WindowText;
            columnHeadersDefaultCellStyle.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            columnHeadersDefaultCellStyle.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            columnHeadersDefaultCellStyle.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.ColumnHeadersDefaultCellStyle = columnHeadersDefaultCellStyle;
            this.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            /*
            this.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.eColdepth,
            this.eColrange,
            this.eColPEnDis,
            this.eColSWDis});
            
            this.Columns.Add(pName + "eColdepth", "埋深");
            this.Columns.Add(pName + "eColrange", "范围");
            */

            foreach (string feStr in pDic.Keys)
            {
                this.Columns.Add(pName + "_" + feStr, pDic[feStr]);
                this.Columns[this.Columns.Count - 1].SortMode = DataGridViewColumnSortMode.NotSortable;
            }

            DataGridViewCellStyle DefaultCellStyle = new DataGridViewCellStyle();
            DefaultCellStyle.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            DefaultCellStyle.BackColor = System.Drawing.SystemColors.Window;
            DefaultCellStyle.Font = new System.Drawing.Font("微软雅黑", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(134)));
            DefaultCellStyle.ForeColor = System.Drawing.SystemColors.ControlText;
            DefaultCellStyle.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            DefaultCellStyle.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            DefaultCellStyle.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.DefaultCellStyle = DefaultCellStyle;
            this.Dock = System.Windows.Forms.DockStyle.Fill;
            this.Location = new System.Drawing.Point(3, 3);
            this.Name = pName;
            this.RowHeadersVisible = false;
            this.RowTemplate.Height = 23;
            this.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.CellSelect;
            this.Size = new System.Drawing.Size(584, 310);
            this.TabIndex = 61;

            /*
            this.ContextMenuStrip = this.cmsDrop;
            this.CellDoubleClick += new System.Windows.Forms.DataGridViewCellEventHandler(this_CellDoubleClick);
            this.CellEndEdit += new System.Windows.Forms.DataGridViewCellEventHandler(this_CellEndEdit);
            this.CellMouseUp += new System.Windows.Forms.DataGridViewCellMouseEventHandler(this_CellMouseUp);
            */
        }
        public void Flash()
        {

        }
    }
}

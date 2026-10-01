using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;

using System.Windows.Forms;

namespace section
{
    class mcPictureBox: PictureBox
    {
        private static mcElement mE;
        private static Graphics g;
        private static Pen p;
        private static Brush brush = new SolidBrush(Color.Black);
        private static double zoom = 1;
        private static mcPcpEnclosure LmPE ;
        private static mcPcpEnclosure RmPE ;
        private static mcPcpFoundation mPF ;
        private static mcAtlas At ;
        private static double mC1;//检测C1是读取的表格信息还是原则中的回填厚度

        public mcPictureBox()
        {

        }
        public mcAtlas PaintSection(mcElement pmE = null, string pLPEname = "", string pRPEname = "", string pPFname = "")
        {
            mcAtlas rtmA = null;
            mE = pmE;
            if (mE != null && pLPEname != "" && pRPEname != "" && pPFname != "") 
            {
                LmPE = mscCtrl.DC.PE[pLPEname];
                RmPE = mscCtrl.DC.PE[pRPEname];
                mPF = mscCtrl.DC.PF[pPFname];
                At = new mcAtlas(pmE);
                mC1 = At.C1;
                At.C1 = At.C1 == 0 ? Math.Max(LmPE.Cush.H, RmPE.Cush.H) : At.C1;
                rtmA = At;
                double Hneeded = pmE.DepthD + (At.t + At.C1 + mPF.TiA) / 1000.0;
                mcEnclosure LmEcls = LmPE.ChoiceEcls(Hneeded);
                mcEnclosure RmEcls = RmPE.ChoiceEcls(Hneeded);
            }
            this.Refresh();
            return rtmA;
        }
        protected override void OnPaint(PaintEventArgs pe)
        {
            base.OnPaint(pe);
            g = pe.Graphics;
            g.TranslateTransform((float)(this.Width / 2.0), (float)(this.Height - 10.0));
            g.RotateTransform(180);
            //p = new Pen(Color.Blue, 1);
            p = new Pen(Color.Cyan, 1);
            g.Clear(Color.Black);
            if (mE == null || mE is mcE0) {  return; }
            zoom = 1;
            switch (mE.Type)
            {
                case "mcE1":
                case "mcE2":
                case "mcE3":
                case "mcE6":
                    PaintBackFilled(LmPE, 1f);
                    var z1= zoom;
                    PaintBackFilled(RmPE, -1f);
                    var z2 = zoom;
                    if(z2<z1)
                    {
                        g.Clear(Color.Black);
                        PaintBackFilled(LmPE, 1f);
                        PaintBackFilled(RmPE, -1f);
                    }
                    break;
                case "mcE4":
                case "mcE5":
                    At.C1 = 0;
                    zoom = Math.Min(zoom, (this.Width - 10 * 2) / (mE.mList.First().Dn + At.t * 2 + mPF.TiA));
                    zoom = Math.Min(zoom, (this.Height - 10 - 50) / (mE.mList.First().Dn + At.t * 2 + mPF.TiA));
                    break;
                default:
                    break;
            }
            PaintOntology();
            //g.DrawLine(p, 0, 0, 0, 500);
            #region 图集参数输出
            g.RotateTransform(180);
            string discribe = "t=" + At.t.ToString() + " a=" + At.a.ToString() + " C1=" + At.C1 + " C2=" + At.C2.ToString();
            Font strFont = new Font("Arial", 9);
            Brush strBrush = new SolidBrush(Color.Yellow);
            float tY = -160;
            if (mE.showPEname != mcPcpEnclosure.Multi_PETxt && mE.showPFname != mcPcpFoundation.Multi_PFTxt)
                tY = -230;
            g.DrawString(discribe, strFont, strBrush, -this.Width / 2.0f + 2, tY);
            strFont.Dispose();strBrush.Dispose();
            #endregion
        }
        private void PaintBackFilled(mcPcpEnclosure mPE, double pSide)
        {
            double grooveDepth = mE.DepthD + (mPF.TiA + At.t + At.C1) / 1000.0;
            mcEnclosure mEcls = mPE.ChoiceEcls(grooveDepth);
            List<mcReplacement> Backfill = new List<mcReplacement>();//分层回填列表
            #region 编写分层回填列表
            for (int i = mPF.mList.Count - 1; i >= 0; i--)//把换填加入回填列表
                Backfill.Add(mscGroove.D10E3(mPF.mList[i]));
            grooveDepth = Math.Max(0, grooveDepth);
            double remainDepth = grooveDepth - mPF.TiA / 1000.0;

            mcPcpEnclosure mainPE = mscCtrl.DC.PE[mE.mainPEname];
            Backfill.Add(new mcReplacement("垫层|" + mainPE.Cush.Name + "|m3", mscGroove.minH(mscGroove.D10E3(At.C1 + At.C2), remainDepth, out remainDepth)));
            Backfill.Add(new mcReplacement("回填|" + mainPE.DockL + "|m3", mscGroove.minH(mE.SizeH / 2 + mscGroove.D10E3(At.t - At.C2), remainDepth, out remainDepth)));
            Backfill.Add(new mcReplacement("回填|" + mainPE.DockH + "|m3", mscGroove.minH(mE.SizeH / 2 + mscGroove.D10E3(At.t), remainDepth, out remainDepth)));
            Backfill.Add(new mcReplacement("回填|" + mainPE.Cover50 + "|m3", mscGroove.minH(0.5, remainDepth, out remainDepth)));
            //if(pDepth - pmPF.TiA - mE.SizeH - D10E3(At.t * 2 + At.C1) - 0.5 < 0) { return rtDic; }
            Backfill.Add(new mcReplacement("回填|" + mainPE.Cover + "|m3", mscGroove.minH(grooveDepth - mE.SizeH - mscGroove.D10E3(mPF.TiA + At.t * 2 + At.C1) - 0.5, remainDepth, out remainDepth)));
            #endregion

            double Bcurrent = At.grooveB == 0 ? mE.SizeB + mscGroove.D10E3(At.t * 2 + At.a * 2 + At.workwidth * 2) : mscGroove.D10E3(At.grooveB);
            double Hcurrent = 0;
            double slope = 0;
            int step = mEcls.mList.Count - 1;
            List<double> stepHeight = mscGroove.splitHbyStep(mEcls, grooveDepth);//分级标高
            List<KeyValuePair<string,List<double>>> tBHSS = new List<KeyValuePair<string, List<double>>>();
            #region 根据标高递推计算回填
            for (int i = 0; i < Backfill.Count; i++)
            {
                double Htarget = Hcurrent + Backfill[i].H;//设定此层回填的目标标高
                do
                {
                    double Hdelta = Math.Min(Htarget, stepHeight[step]) - Hcurrent;//确定标高向上移动的距离
                    slope = mEcls.mList[step].Cpnt.param["A"].Key.StartsWith("放坡系数") ? mscMslns.ToDouble(mEcls.mList[step].Cpnt.param["A"].Value) : 0;
                    List<double> tl = new List<double>();
                    tl.Add(Bcurrent * 1000); tl.Add(Hcurrent * 1000); tl.Add(Hdelta * 1000); tl.Add(slope); tl.Add(pSide);
                    tBHSS.Add(new KeyValuePair<string, List<double>>(Backfill[i].Name, tl));

                    Hcurrent = Hcurrent + Hdelta;//标高向上移动
                    Bcurrent += Hdelta * slope * 2;//当前标高宽度计算
                    if ((Hcurrent == stepHeight[step]) && step > 0) //判断是否处于分级标高
                    {
                        step--;//围护分级选择向上移动                        
                        if ((stepHeight[step] != stepHeight[step + 1]) && stepHeight[step + 1] != 0) 
                            Bcurrent += mEcls.mList[step].stepWidth * 2;//根据围护的平台宽度放大当前标高的宽度
                    }
                }
                while (Hcurrent - Htarget < -0.0001);
                //while (Math.Round(Hcurrent,2) < Math.Round(Htarget,2));
            }
            zoom = Math.Min(zoom, (this.Width - 10 * 2) / (Bcurrent * 1000.0));
            zoom = Math.Min(zoom, (this.Height - 10 - 50) / (Hcurrent * 1000.0));
            paintTrapezoid(0, tBHSS[0].Value[0], tBHSS[0].Value[1], tBHSS[0].Value[2], tBHSS[0].Value[3], tBHSS[0].Value[4]);
            for (int i = 1; i < tBHSS.Count; i++)
            {
                var t1 = tBHSS[i].Key;
                var t2 = tBHSS[i - 1].Key;
                if (tBHSS[i].Key == tBHSS[i - 1].Key)
                    paintTrapezoid(tBHSS[i - 1].Value[0] + tBHSS[i - 1].Value[2] * tBHSS[i - 1].Value[3] * 2,
                        tBHSS[i].Value[0], tBHSS[i].Value[1], tBHSS[i].Value[2], tBHSS[i].Value[3], tBHSS[i].Value[4]);
                else
                    paintTrapezoid(tBHSS[i].Value[0], tBHSS[i].Value[1], tBHSS[i].Value[2], tBHSS[i].Value[3], tBHSS[i].Value[4]);

            }
            #endregion
            //g.DrawLine(p, 0, (float)(Hcurrent * 1000 * zoom), (float)(Bcurrent / 2.0 * 1000 * pSide * zoom), (float)(Hcurrent * 1000 * zoom));
            g.DrawLine(p, (float)(Bcurrent / 2.0 * 1000 * pSide * zoom), (float)(Hcurrent * 1000 * zoom), (float)(this.Width * pSide / 2), (float)(Hcurrent * 1000 * zoom));
        }
        private void PaintOntology()
        {
            var tOS = mE.OntologyShape();
            if (tOS == null) return; 
            foreach (KeyValuePair<string, Rectangle> feKVP in tOS)
            {

                g.TranslateTransform(0, (float)((mPF.TiA + At.C1 - mC1) * zoom));
                if (feKVP.Key == "Ellipse")
                {
                    p.Color = Color.Yellow;
                    Rectangle tR = ZoomRect(feKVP.Value);
                    g.FillEllipse(brush, tR);
                    g.DrawEllipse(p, tR);
                }   
                else
                {
                    p.Color = ColorTranslator.FromHtml("#FF00FF");
                    Rectangle tR = ZoomRect(feKVP.Value);
                    g.FillRectangle(brush, tR);
                    g.DrawRectangle(p, ZoomRect(feKVP.Value));
                }   
                g.TranslateTransform(0, -(float)((mPF.TiA + At.C1 - mC1) * zoom));
            }
        }

        private static void paintTrapezoid(double pLowB, double pHcurrent, double pHdelta, double pSlope , double pSide)
        {
            double HeighB = pLowB + pHdelta * pSlope * 2;
            PointF[] pointF = new PointF[3];
            pointF[0] = new PointF(0, (float)(pHcurrent * zoom));
            pointF[1] = new PointF((float)(pLowB / 2.0 * pSide * zoom), (float)(pHcurrent * zoom));
            pointF[2] = new PointF((float)(HeighB / 2.0 * pSide * zoom), (float)((pHcurrent + pHdelta) * zoom));
            //pointF[3] = new PointF(0, (float)((pHcurrent + pHdelta) * zoom));
            g.DrawLines(p, pointF);
            //g.DrawLine(p, -(float)(pLowB / 2.0 * zoom), (float)(pHcurrent * zoom), (float)(pLowB / 2.0 * zoom), (float)(pHcurrent * zoom));
        }

        private static void paintTrapezoid(double pLowB1,double pLowB2, double pHcurrent, double pHdelta, double pSlope, double pSide)
        {
            double HeighB = pLowB2 + pHdelta * pSlope * 2;
            PointF[] pointF = new PointF[3];
            pointF[0] = new PointF((float)(pLowB1 / 2.0 * pSide * zoom), (float)(pHcurrent * zoom));
            pointF[1] = new PointF((float)(pLowB2 / 2.0 * pSide * zoom), (float)(pHcurrent * zoom));
            pointF[2] = new PointF((float)(HeighB / 2.0 * pSide * zoom), (float)((pHcurrent + pHdelta) * zoom));
            g.DrawLines(p, pointF);
        }

        private Rectangle ZoomRect(Rectangle pS)
        {
            int mX = Convert.ToInt32(pS.X * zoom);
            int mY = Convert.ToInt32(pS.Y * zoom);
            int mH = Convert.ToInt32(pS.Height * zoom);
            int mW = Convert.ToInt32(pS.Width * zoom);
            Rectangle rtR = new Rectangle(mX, mY, mW, mH);
            return rtR;
        }
        protected override void Dispose(bool disposing)
        {
            if (g != null)
            {
                base.Dispose(disposing);
                g.Dispose();
                p.Dispose();
            }
        }

    }
}

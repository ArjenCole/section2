using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcE1 : mcElement//直埋管道
    {
        public mcE1()
        {
            unit = "m";
        }
        public mcE1(XElement pXE)
        {
            readXE(pXE);
            unit = "m";
        }
        public mcE1(object[] pData, Dictionary<string, double> pDicPE, Dictionary<string, double> pDicPF)
        {
            GetData(pData, pDicPE, pDicPF);
            unit = "m";
        }
        public override double rtSizeB()
        {
            return mList.First().Dn / 1000.0;
        }
        public override double rtSizeH()
        {
            return mList.First().Dn / 1000.0;
        }
        public override string Specification()
        {
            return mList.First().Mat + " Dn" + mList.First().Dn;
        }
        public override List<KeyValuePair<string, Rectangle>> OntologyShape()
        {
            List<KeyValuePair<string, Rectangle>> rtList = new List<KeyValuePair<string, Rectangle>>();

            mcAtlas At = new mcAtlas(this);

            if (mscCtrl.DC.PE[mainPEname].ConFound && IsConPipe() && !mList.First().Mat.Contains("预应力"))//采用砼基础
            {
                int tW = Convert.ToInt16(SizeB * 1000 + (At.t * 2 + At.a * 2));
                int tH = Convert.ToInt16(At.C1 + At.C2);
                int tX = -Convert.ToInt16(tW / 2.0);
                int ty = 0;
                Rectangle conFound = new Rectangle(tX, ty, tW, tH);
                rtList.Add(new KeyValuePair<string, Rectangle>("Rectangle", conFound));
            }
            Rectangle outsideEllipse = new Rectangle(-Convert.ToInt16(mList.First().Dn / 2.0 + At.t), Convert.ToInt16(At.C1), Convert.ToInt16(mList.First().Dn + At.t * 2), Convert.ToInt16(mList.First().Dn + At.t * 2));
            rtList.Add(new KeyValuePair<string, Rectangle>("Ellipse", outsideEllipse));
            Rectangle insideEllipse = new Rectangle(-Convert.ToInt16(mList.First().Dn / 2.0), Convert.ToInt16(At.t + At.C1), Convert.ToInt16(mList.First().Dn), Convert.ToInt16(mList.First().Dn));
            rtList.Add(new KeyValuePair<string, Rectangle>("Ellipse", insideEllipse));
            return rtList;
        }
        public override Dictionary<string, mcQ> cal_found()
        {
            Dictionary<string, mcQ> rtD = new Dictionary<string, mcQ>();
            mcPcpEnclosure mainPE = mscCtrl.DC.PE[mainPEname];//取出该元素的主围护原则
            mcAtlas At = new mcAtlas(this);
            double outsideDn = (At.oD > 0 ? At.oD : Pipe(0).Dn + At.t * 2) / 1000.0;//外径
            double halfCircle = Circle(outsideDn) / 2.0;
            double foundAngle = mainPE.FoundAngle;
            double remainDepth = DepthD + (At.t + At.C1) / 1000.0;
            #region 计算管道基础并扣减
            if (mainPE.ConFound && IsConPipe())//采用砼基础
            {
                double tmpFound = (At.C1 + At.C2) / 1000.0 * (SizeB + (At.t * 2 + At.a * 2) / 1000.0);
                rtD = mscGroove.PlusDic_StrmcQ(rtD, "管道基础|混凝土|m3", new mcQ(tmpFound - Bow(outsideDn, foundAngle)));
                rtD = mscGroove.PlusDic_StrmcQ(rtD, "管道基础|模板|m2", new mcQ((At.C1 + At.C2) * 2 / 1000.0));

                tmpFound = (-1) * Math.Min(remainDepth, (At.C1 + At.C2) / 1000.0) * (SizeB + (At.t * 2 + At.a * 2) / 1000.0);
                remainDepth -= Math.Min(remainDepth, (At.C1 + At.C2) / 1000.0);

                mcQ tmpQ = new mcQ(tmpFound);//垫层扣减
                rtD = mscGroove.PlusDic_StrmcQ(rtD, "垫层|" + mainPE.Cush.Name + "|m3", tmpQ);
            }
            else//非砼基础
            {
                remainDepth -= Math.Min(remainDepth, At.C2);
                mcQ tmpQ = new mcQ((-1) * Bow(outsideDn, foundAngle));//垫层扣减
                rtD = mscGroove.PlusDic_StrmcQ(rtD, "垫层|" + mainPE.Cush.Name + "|m3", tmpQ);
            }
            #endregion
            double tH = outsideDn / 2.0 - outsideDn / 2.0 * Math.Cos(foundAngle / 2.0 / 180.0 * Math.PI);
            remainDepth -= Math.Min(remainDepth, tH / 1000.0);

            rtD = mscGroove.PlusDic_StrmcQ(rtD, "回填|" + mainPE.DockL + "|m3", new mcQ((-1) * (halfCircle - Bow(outsideDn, foundAngle))));
            rtD = mscGroove.PlusDic_StrmcQ(rtD, "回填|" + mainPE.DockH + "|m3", new mcQ(-halfCircle));
            return rtD;
        }
        public bool IsConPipe()
        {
            if (mList.First().Mat.Contains("混凝土") || mList.First().Mat.Contains("砼"))
            {
                return true;
            }
            return false;
        }
        private double Circle(double pD)
        {
            return Math.PI * pD * pD / 4.0;
        }
        private double Bow(double pD, double pAngel)
        {
            double sector = Circle(pD) * pAngel / 360.0;//扇形面积
            double triangle = 0.5 * pD * pD / (double)4 * Math.Sin(pAngel / 180.0 * Math.PI);//三角形面积
            return (sector - triangle);
        }
    }
}

using System;
using System.Collections.Generic;
using System.Data;
using System.Linq;
using System.Text;


namespace section
{
    public class mcAtlas
    {
        public static string[] Atlas = new[] { "06MS201-1" };

        public double oD, t, a, workwidth, grooveB, C1, C2;//B,

        private mcElement mE;
        private Dictionary<string, Dictionary<int, double>> WorkWidth = new Dictionary<string, Dictionary<int, double>>();
        private Dictionary<string, Dictionary<int, double>> GrooveB = new Dictionary<string, Dictionary<int, double>>();
        private double q;

        static private DataSet pvDS = new DataSet();


        public static void Init()
        {
            try
            {
                pvDS = new DataSet();
                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\06MS201-1--砼管砼基础.CSV").Copy());//0
                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\06MS201-1--砼管砂基础.CSV").Copy());//1

                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\JC-T 640-1996--砼顶管.CSV").Copy());//2

                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\HDPE-PE--HDPE承插式双壁缠绕管.CSV").Copy());//3
                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\HDPE-PE--PE管.CSV").Copy());//4

                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\06MS201-2--硬聚氯乙烯(PVC-U)管.CSV").Copy());//5
                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\06MS201-2--聚氯乙烯(PE)管.CSV").Copy());//6
                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\06MS201-2--钢带增强聚乙烯(PE)管.CSV").Copy());//7

                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\金属管道--球墨铸铁管.CSV").Copy());//8
                pvDS.Tables.Add(mscExcel.OpenCSV(@"Atlas\金属管道--钢管.CSV").Copy());//9
            }
            catch
            {
                mscCtrl.InportDataFromExcel();
            }
        }

        public mcAtlas(mcElement pmE)
        {
            mE = pmE;
            WorkWidth = mscCtrl.DC.PE[mE.mainPEname].WorkWidth;
            GrooveB = mscCtrl.DC.PE[mE.mainPEname].GrooveB;
            Access_06M201_1();
        }

        private void Access_06M201_1()
        {
            string expression;
            string tmpD = mscMslns.ToString(mE.SizeB * 1000);
            string tmpAngel = mscCtrl.DC.PE[mE.mainPEname].FoundAngle.ToString();
            if (mE.Type == "mcE2")
            {
                t = 0;
                a = 100;
                C1 = 100;
                C2 = 0;
                workwidth = GetWidthOrB("包封埋管", 0, WorkWidth);
                grooveB = 0;
                return;
            }
            if ((mE.Type == "mcE3") || (mE.Type == "mcE6")) 
            {
                t = 0;
                a = 100;
                C1 = 100;
                C2 = 0;
                workwidth = GetWidthOrB("箱涵-管廊", 0, WorkWidth);
                grooveB = 0;
                return;
            }
            if (mE.Type == "mcE4")//顶管
            {
                string tmpLevel = "双插口管";
                if (mE.mList.First().Mat.Contains("平口"))
                    tmpLevel = "平口管";
                if (mE.mList.First().Mat.Contains("企口"))
                    tmpLevel = "企口管";
                if (mE.mList.First().Mat.Contains("双插口"))
                    tmpLevel = "双插口管";
                if (mE.mList.First().Mat.Contains("钢承口"))
                    tmpLevel = "钢承口管";
                expression = "D = '" + mE.mList.First().Dn + "' and level = '" + tmpLevel + "'";
                GetRowsByFilter(pvDS.Tables[2], expression);
            }
            if (mE.Type == "mcE5")//拖拉管
            {
                expression = "D = '" + mE.mList.First().Dn + "'";
                GetRowsByFilter(pvDS.Tables[4], expression);
            }
            if (mE.Type == "mcE1")
            {
                if (((mcE1)mE).IsConPipe()) //混凝土管道
                {
                    string tmpLevel = string.Empty;
                    if (mscCtrl.DC.PE[mE.mainPEname].ConFound && !mE.mList.First().Mat.Contains("预应力"))//混凝土基础
                    {
                        if (mE.mList.First().Mat.Contains("Ⅰ") || mE.mList.First().Mat.Contains("一级")) { tmpLevel = "1"; }
                        if (mE.mList.First().Mat.Contains("Ⅱ") || mE.mList.First().Mat.Contains("二级")) { tmpLevel = "2"; }
                        if (mE.mList.First().Mat.Contains("Ⅲ") || mE.mList.First().Mat.Contains("三级")) { tmpLevel = "3"; }

                        expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                        GetRowsByFilter(pvDS.Tables[0], expression);
                        if (t == 0)
                        {
                            expression = "D = '" + TrimDn(tmpD) + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                            GetRowsByFilter(pvDS.Tables[0], expression);
                        }
                        if (t == 0)
                        {
                            expression = "D = '" + tmpD + "' and level = '" + tmpLevel + "'";
                            GetRowsByFilter(pvDS.Tables[0], expression);
                        }
                        if (t == 0)
                        {
                            expression = "D = '" + "3000" + "' and level = '" + tmpLevel + "'";
                            GetRowsByFilter(pvDS.Tables[0], expression);
                        }
                        workwidth = GetWidthOrB("混凝土管-刚性接口", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("混凝土管-刚性接口", mE.SizeB, GrooveB);
                    }
                    else//砂基础
                    {
                        tmpLevel = "非预应力";
                        if (mE.mList.First().Mat.Contains("预应力")) { tmpLevel = "预应力"; }
                        if (mE.mList.First().Mat.Contains("非预应力")) { tmpLevel = "非预应力"; }

                        if (tmpLevel == "预应力" && tmpAngel == "180") tmpAngel = "150";
                        if (tmpLevel == "预应力" && mE.SizeB < 0.6 && tmpAngel == "90") tmpAngel = "120";

                        expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                        GetRowsByFilter(pvDS.Tables[1], expression);
                        if (t == 0)
                        {
                            expression = "D = '" + "3000" + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                            GetRowsByFilter(pvDS.Tables[1], expression);
                        }
                        workwidth = GetWidthOrB("混凝土管-刚性接口", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("混凝土管-刚性接口", mE.SizeB, GrooveB);
                    }
                }
                else//非混凝土管道
                {
                    string tMat = mE.mList.First().Mat;
                    if (tMat.Contains("HDPE"))
                    {
                        expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "'";
                        GetRowsByFilter(pvDS.Tables[3], expression);
                        workwidth = GetWidthOrB("化学建材管道", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("化学建材管道", mE.SizeB, GrooveB);
                    }
                    else if (tMat.Contains("PVC") || tMat.Contains("pvc"))
                    {
                        string tmpLevel = "硬聚氯乙烯(PVC-U)双壁波纹管";
                        if (tMat.Contains("加筋管")) tmpLevel = "硬聚氯乙烯(PVC-U)加筋管";
                        if (tMat.Contains("平壁管"))
                        {
                            tmpLevel = "硬聚氯乙烯(PVC-U)平壁管 4kN/m2";
                            if (tMat.Contains("8")) tmpLevel = "硬聚氯乙烯(PVC-U)平壁管 8kN/m2";
                        }
                        expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                        GetRowsByFilter(pvDS.Tables[5], expression);
                        workwidth = GetWidthOrB("化学建材管道", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("化学建材管道", mE.SizeB, GrooveB);
                    }
                    else if (tMat.Contains("PE"))
                    {
                        string tmpLevel = string.Empty;
                        if (mE.SizeB < 0.15)
                        {
                            expression = "D = '" + tmpD + "'";
                            GetRowsByFilter(pvDS.Tables[4], expression);
                        }
                        else if (tMat.Contains("钢带"))
                        {
                            tmpLevel = "钢带增强聚乙烯(PE)管";
                            expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                            GetRowsByFilter(pvDS.Tables[7], expression);
                        }
                        else
                        {
                            tmpLevel = "聚氯乙烯(PE)双壁波纹管";
                            if (tMat.Contains("缠绕"))
                            {
                                if (tMat.Contains("B") || tMat.Contains("b"))
                                    tmpLevel = "聚氯乙烯(PE)缠绕结构壁管 A型";
                                else
                                    tmpLevel = "聚氯乙烯(PE)缠绕结构壁管 B型";
                            }
                            expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                            GetRowsByFilter(pvDS.Tables[6], expression);
                        }
                        workwidth = GetWidthOrB("化学建材管道", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("化学建材管道", mE.SizeB, GrooveB);
                    }

                    else if (tMat.Contains("球墨") || tMat.Contains("球铁") || tMat.Contains("铸铁"))
                    {
                        string tmpLevel = "K9";
                        if (tMat.Contains("K8") || tMat.Contains("k8")) tmpLevel = "K8";
                        if (tMat.Contains("K10") || tMat.Contains("k10")) tmpLevel = "K10";
                        expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                        GetRowsByFilter(pvDS.Tables[8], expression);
                        workwidth = GetWidthOrB("金属类管道", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("金属类管道", mE.SizeB, GrooveB);
                    }
                    else if (tMat.Contains("钢管"))
                    {
                        string tmpLevel = string.Empty;
                        if (mE.SizeB <= 0.15)
                            tmpLevel = "焊接钢管1.0Mpa";
                        else
                            tmpLevel = "无缝钢管";

                        if (tMat.Contains("焊接"))
                        {
                            tmpLevel = "焊接钢管1.0Mpa";
                            if (tMat.Contains("1.6Mpa") || tMat.Contains("1.6mpa")) tmpLevel = "焊接钢管1.6Mpa";
                        }
                        else if (tMat.Contains("无缝"))
                        {
                            tmpLevel = "无缝钢管";
                        }
                        else
                        {
                            tmpLevel = "给水钢管";
                        }
                        expression = "D = '" + tmpD + "' and angle = '" + tmpAngel + "' and level = '" + tmpLevel + "'";
                        GetRowsByFilter(pvDS.Tables[9], expression);
                        workwidth = GetWidthOrB("金属类管道", mE.SizeB, WorkWidth);
                        grooveB = GetWidthOrB("金属类管道", mE.SizeB, GrooveB);
                    }
                    else//其他未知构件
                    {
                        workwidth = GetWidthOrB("未知构件", mE.SizeB, WorkWidth);
                    }
                }

            }

            if (mscCtrl.DC.PE[mE.mainPEname].grooveWidth == mcPcpEnclosure.GrooveWidth.WorkWidth)
                grooveB = 0;
        }



        /// <summary>
        /// 查阅图集数据
        /// </summary>
        /// <param name="para_DT">查阅图集所在数据集表单</param>
        /// <param name="para_expression">查询表达式</param>
        private void GetRowsByFilter(DataTable para_DT, string para_expression)
        {
            DataTable table = para_DT;
            DataRow[] foundRows;
            //使用选择方法来找到匹配的所有行。
            foundRows = table.Select(para_expression);
            //过滤行,找到所要的行。
            for (int i = 0; i < foundRows.Length; i++)
            {
                try
                {
                    oD = Convert.ToDouble((foundRows[i]["oD"]));
                }
                catch
                {
                    oD = -1;
                }
                t = Convert.ToDouble((foundRows[i]["t"]));
                a = Convert.ToDouble((foundRows[i]["a"]));
                //B = Convert.ToDouble((foundRows[i]["B"]));
                C1 = Convert.ToDouble((foundRows[i]["C1"]));
                C2 = Convert.ToDouble((foundRows[i]["C2"]));
                q = Convert.ToDouble((foundRows[i]["Q"]));
            }
        }

        private double GetWidthOrB(string pCat, double pDN, Dictionary<string, Dictionary<int, double>> pSheet)
        {
            int tInt = Convert.ToInt32(Math.Round(pDN * 1000 / 100.0, 0) * 100);
            if (tInt > pSheet[pCat].Last().Key)
                return pSheet[pCat].Last().Value;
            else
                return pSheet[pCat][tInt];
        }

        /// <summary>
        /// 整理管径
        /// </summary>
        /// <param name="p_Dn">管径</param>
        /// <returns>若管径非标时，调整为图集中最接近的管径</returns>
        private string TrimDn (string p_Dn)
        {
            if (p_Dn == "1400")
                return "1350";
            else if (p_Dn == "1600")
                return "1650";
            else if (p_Dn == "2700")
                return "2800";
            else if (mscMslns.ToDouble(p_Dn) > 2800)
                return "3000";
            else
                return (Math.Round(mscMslns.ToDouble(p_Dn) / 100, 0) * 100).ToString();
        }
    }



}

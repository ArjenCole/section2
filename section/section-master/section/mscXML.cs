using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
//using System.Linq.Xml;
using System.Text;
using System.Text.RegularExpressions;

using System.Xml.Linq;

namespace section
{
    public class mscXML
    {
        #region XMl声明所需的三个参数，分别指定默认值
        static private string version = "1.0";
        static private string encoding = "utf-8";
        static private string standalone = "yes";
        #endregion
        #region 操作文件地址
        static private string filepath = "";
        //public string FilePath
        //{
        //    set { filepath = value; }
        //    get { return filepath; }
        //}
        #endregion
        #region 操作数据类型
        static private mcDataCarrier prvt_mDC;
        //public mc_DataCarrier mDc
        //{
        //    set { prvt_mDC = value; }
        //    get { return prvt_mDC; }
        //}
        #endregion


        static public void SaveXml(XElement pXE, string pPath)
        {
            XDeclaration xd = new XDeclaration(version, encoding, standalone);//创建XML声明
            XDocument doc = new XDocument(xd, pXE);//创建XML文件

            //try
            //{
            //    doc.Save(pPath);//保存XML文件
            //}
            //catch
            //{

            //}

            mscMslns.CheckPath(pPath);
            doc.Save(pPath);//保存XML文件
        }
        static public mcDataCarrier ReadXml(string pPath)
        {
            XElement tXE = XElement.Load(pPath);
            return new mcDataCarrier(tXE);
        }



    }
}

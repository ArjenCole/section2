using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcBasicInfo : ItoXML
    {
        public string FilePath = "";
        public string ProjectName = "新建项目";
        public string ProjectIndex = "001";
        public string Author = Environment.UserName;
        public string AtlasName = "06MS201-1";
        public mcBasicInfo() { }
        public mcBasicInfo(XElement pXE)
        {

            XElement tXE = pXE.Element(this.ToString().Replace("section.", ""));
            ProjectName = tXE.Element("ProjectName").Value;
            ProjectIndex = tXE.Element("ProjectIndex").Value;
            Author = tXE.Element("Author") == null ? "" : tXE.Element("Author").Value;
            AtlasName = tXE.Element("AtlasName") == null ? "06MS201-1" : tXE.Element("AtlasName").Value;
        }
        public XElement toXML()
        {
            mcBasicInfo tmBI = mscCtrl.DC.BI;
            XElement re_XE = new XElement(this.ToString().Replace("section.", ""),
                                new XElement("ProjectName", tmBI.ProjectName),//项目名称
                                new XElement("ProjectIndex", tmBI.ProjectIndex),//项目编号
                                new XElement("Author", tmBI.Author),//编制人
                                new XElement("AtlasName", tmBI.AtlasName)
                            );
            return re_XE;
        }
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

using System.Xml.Linq;

namespace section
{
    [Serializable]//序列化类
    public class mcDataCarrier:mcNameList<mcSegment>
    {
        private string fileversion = System.Reflection.Assembly.GetExecutingAssembly().GetName().Version.ToString();
        public string fileVersion { get { return fileversion; } set { fileversion = value; } }
        public mcBasicInfo BI = new mcBasicInfo();
        public Dictionary<string, mcPcpEnclosure> PE = new Dictionary<string, mcPcpEnclosure>();
        public Dictionary<string, mcPcpFoundation> PF = new Dictionary<string, mcPcpFoundation>();
        public Dictionary<string, double> price = new Dictionary<string, double>();
        public string BackupFile;

        public mcDataCarrier()
        {
            BI = new mcBasicInfo();
            PE = new Dictionary<string, mcPcpEnclosure>();
            PF = new Dictionary<string, mcPcpFoundation>();
            mList = new List<mcSegment>();
            price = new Dictionary<string, double>();
            BackupFile = GetBackupFile();
        }
        public mcDataCarrier(XElement pXE)
        {
            IEnumerable<XElement> elements = from ele in pXE.Elements("Assembly")
                                             select ele;
            foreach (XElement feXE in elements)
            {
                fileVersion = feXE.Element("Version").Value;
            }
            BI = new mcBasicInfo(pXE);

            elements = from ele in pXE.Elements("mcPcpEnclosure")
                       select ele;
            PE = new Dictionary<string, mcPcpEnclosure>();
            foreach (XElement feXE in elements)
            {
                mcPcpEnclosure tmE = new mcPcpEnclosure(feXE);
                PE.Add(tmE.Name,tmE);
            }
            elements = from ele in pXE.Elements("mcPcpFoundation")
                       select ele;
            PF = new Dictionary<string, mcPcpFoundation>();
            foreach (XElement feXE in elements)
            {
                mcPcpFoundation tmE = new mcPcpFoundation(feXE);
                PF.Add(tmE.Name, tmE);
            }
            elements = from ele in pXE.Elements("mcSegment")
                       select ele;
            mList = new List<mcSegment>();
            foreach (XElement feXE in elements)
            {
                mcSegment tmE = new mcSegment(feXE);
                mList.Add(tmE);
            }

            elements = from ele in pXE.Elements("Price")
                       select ele;
            foreach (XElement feXE in elements)
                price.Add(mscMslns.ToString(feXE.Element("name").Value), mscMslns.ToDouble(feXE.Element("price").Value));

            BackupFile = GetBackupFile();
        }

        public mcSegment Segment(string pSegmentName)
        {
            return mList.Find(t => t.Name == pSegmentName);
        }
        public List<string>SegmentNames
        {
            get
            {
                List<string> rtListStr = new List<string>();
                foreach(mcSegment femS in mList)
                {
                    rtListStr.Add(femS.Name);
                }
                return rtListStr;
            }
        }

        public override XElement toXML()
        {
            XElement rtXE = new XElement("Root",
                                new XElement("Assembly",
                                    new XElement("Version", System.Reflection.Assembly.GetExecutingAssembly().GetName().Version.ToString())//程序版本
                    )
                );
            rtXE.Add(BI.toXML());
            foreach(string feKey in PE.Keys)
                rtXE.Add(PE[feKey].toXML());
            foreach (string feKey in PF.Keys)
                rtXE.Add(PF[feKey].toXML());
            foreach (mcSegment femS in mList)
                rtXE.Add(femS.toXML());
            
            foreach (string feKey in price.Keys)
                rtXE.Add(new XElement("Price",
                            new XElement("name",feKey),
                            new XElement("price", price[feKey].ToString())
                            )
                         );

            return rtXE;
        }

        private string GetBackupFile()
        {
            string tEnvironment = System.Windows.Forms.Application.StartupPath + @"\Backup\";
            string tDateTime = DateTime.Now.ToString("yy-MM-dd HH：mm：ss");
            string tDateTimeRest = DateTime.Now.Millisecond.ToString();

            string rtStr = tEnvironment + tDateTime + "." + tDateTimeRest + " [备份] " + BI.ProjectName + @".stn";
            
            return rtStr;
        }
    }

}

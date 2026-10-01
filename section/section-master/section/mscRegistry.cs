using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Microsoft.Win32;
using System.IO;

namespace section
{
    static class mscRegistry
    {
        public static void RefreshSystem()//刷新进程
        {
            System.Diagnostics.Process[] mprocess;
            mprocess = System.Diagnostics.Process.GetProcessesByName("explorer");//创建进程组件的数组，并将它们与共享“explorer”进程名称的所有进程资源关联。
            foreach (System.Diagnostics.Process mp in mprocess)
            {
                mp.Kill();
            }
        }
        public static void RefreshIconCache()//删除系统图标缓存
        {
            System.Diagnostics.Process.Start(System.Windows.Forms.Application.StartupPath + @"\Res\RefreshIconCache.bat");
        }
        /// <summary>
        /// 关联文件并修改图标
        /// </summary>
        /// <param name="pAppPath">程序路径</param>
        /// <param name="pExtName">文件后缀名，带.</param>
        /// <param name="pType">文件类型</param>
        /// <param name="pContent">文件内容</param>
        /// <param name="pIcoPath">图标路径</param>
        public static void FileAssociation(string pAppPath, string pExtName, string pType, string pContent, string pIcoPath)
        {
            try
            {
                RegistryKey MyReg = Registry.ClassesRoot.CreateSubKey(pExtName);
                MyReg.SetValue("", pType);
                MyReg.SetValue("Content Type", pContent);

                RegistryKey MyReg1 = MyReg.CreateSubKey("shell\\open\\command");//设置默认程序
                MyReg1.SetValue("", pAppPath + " \"%1\"");//传入参数两侧加上引号，使传入路径不会被空格截断

                RegistryKey MyReg2 = MyReg.CreateSubKey("DefaultIcon");//设置文件图标
                MyReg2.SetValue("", pIcoPath + ",0", RegistryValueKind.String);

                MyReg.Close();
                RefreshIconCache();
                RefreshSystem();
                System.Windows.Forms.MessageBox.Show("文件关联成功。", "提示", System.Windows.Forms.MessageBoxButtons.OK, System.Windows.Forms.MessageBoxIcon.Information);
                
            }
            catch (Exception ex)
            {
                System.Windows.Forms.MessageBox.Show(ex.Message, "信息提示", System.Windows.Forms.MessageBoxButtons.OK, System.Windows.Forms.MessageBoxIcon.Information);
            }
        }
        /// <summary>
        /// 查找注册表值
        /// </summary>
        /// <param name="pSubKey">自键名称</param>
        /// <param name="pSelfPath">匹配路径</param>
        /// <returns></returns>
        public static bool SearchValueRegEdit(string pSubKey, string pSelfPath)
        {
            string[] subkeyNames;
            Microsoft.Win32.RegistryKey hkml = Microsoft.Win32.Registry.ClassesRoot;
            Microsoft.Win32.RegistryKey stn = hkml.OpenSubKey(pSubKey, true);
            if (stn == null) return false;
            //var tt = stn.GetValue("").ToString();
            subkeyNames = stn.GetValueNames();
            //取得该项下所有键值的名称的序列，并传递给预定的数组中
            foreach (string keyName in subkeyNames)
            {
                if (stn.GetValue(keyName).ToString().ToUpper() == (pSelfPath + " \"%1\"").ToUpper())    //判断键值的名称   
                {
                    hkml.Close();
                    return true;
                }
            }
            hkml.Close();
            return false;
        }


        /// <summary>
            /// 获得要找到的注册表项
            /// </summary>
            /// <param name="path">注册表路经</param>
            /// <returns>返回注册表对象</returns>
        public static bool CreateItemRegEdit(string path)
        {
            try
            {
                Microsoft.Win32.RegistryKey obj = Microsoft.Win32.Registry.LocalMachine;
                obj.CreateSubKey(path);
                return true;
            }
            catch (Exception e)
            {
                return false;
            }
        }
        /// <summary>
            /// 设置注册表项下面的值
            /// </summary>
            /// <param name="path">路经</param>
            /// <param name="name">名称</param>
            /// <param name="value">值</param>
            /// <returns>是否成功</returns>
        public static int SetValueRegEdit(string path, string name, string value)
        {
            try
            {
                Microsoft.Win32.RegistryKey obj = Microsoft.Win32.Registry.LocalMachine;
                Microsoft.Win32.RegistryKey objItem = obj.OpenSubKey(path, true);
                objItem.SetValue(name, value);
            }
            catch (Exception e)
            {
                return 0;
            }
            return 1;
        }
        /// <summary>
            /// 查看注册表指定项的值
            /// </summary>
            /// <param name="path">路经</param>
            /// <param name="name">项名称</param>
            /// <returns>项值</returns>
        public static string getValueRegEdit(string path, string name)
        {
            string value;
            try
            {
                Microsoft.Win32.RegistryKey obj = Microsoft.Win32.Registry.LocalMachine;
                Microsoft.Win32.RegistryKey objItem = obj.OpenSubKey(path);
                value = objItem.GetValue(name).ToString();
            }
            catch (Exception e)
            {
                return "";
            }
            return value;
        }
        /// <summary>
            /// 查看注册表项是否存在
            /// </summary>
            /// <param name="value">路经</param>
            /// <param name="name">项名称</param>
            /// <returns>是否存在</returns>
        public static bool SearchItemRegEdit(string path, string name)
        {
            string[] subkeyNames;
            Microsoft.Win32.RegistryKey hkml = Microsoft.Win32.Registry.LocalMachine;
            Microsoft.Win32.RegistryKey software = hkml.OpenSubKey(path);
            subkeyNames = software.GetSubKeyNames();
            //取得该项下所有子项的名称的序列，并传递给预定的数组中   
            foreach (string keyName in subkeyNames)   //遍历整个数组   
            {
                if (keyName.ToUpper() == name.ToUpper()) //判断子项的名称   
                {
                    hkml.Close();
                    return true;
                }
            }
            hkml.Close();
            return false;

        }


    }


}

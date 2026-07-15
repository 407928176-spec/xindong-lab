// 心动实验室 Windows 启动器。
//
// 这是一个极薄的图形程序：真正的启动逻辑仍然在仓库根目录的 start.ps1 里，
// 这个 exe 唯一的作用是给玩家一个「名字对、图标对、双击就能玩」的入口，
// 替代此前一大堆同名脚本文件里让人无从下手的 start.bat。
//
// 用 Windows 自带的 .NET Framework 编译（见 build.ps1），不引入任何第三方打包工具，
// 也不需要玩家额外安装运行时。
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static void Main()
    {
        // 用 exe 自身所在目录而不是当前工作目录，这样不管玩家从哪里双击
        // （资源管理器、桌面快捷方式、被移动到别的路径……）都能找对 start.ps1。
        string exeDir = AppDomain.CurrentDomain.BaseDirectory;
        string scriptPath = Path.Combine(exeDir, "start.ps1");

        if (!File.Exists(scriptPath))
        {
            MessageBox.Show(
                "没有在当前目录找到 start.ps1。\n\n" +
                "请确认「心动实验室.exe」和 start.ps1、backend、frontend 等文件夹放在同一个目录下，" +
                "不要单独把 exe 移出去。",
                "心动实验室 - 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                // 首次启动要装依赖、建库、构建前端，耗时数分钟，保留可见窗口
                // 让玩家看到进度，而不是像后台服务一样看起来卡死了。
                Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + scriptPath + "\"",
                WorkingDirectory = exeDir,
                UseShellExecute = true,
            };
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "启动失败：" + ex.Message,
                "心动实验室 - 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}

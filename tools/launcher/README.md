# Windows 启动器构建说明

仓库根目录的 `心动实验室.exe` 是从这个目录构建出来的，构建产物直接提交入库，
玩家拿到手就能双击，**不需要自己编译**。这份说明只给需要重新构建的人看
（比如换了新 logo）。

## 文件

- `Launcher.cs`：启动器源码。极薄的一层：定位到 exe 自身所在目录，调用
  `start.ps1` 完成真正的启动逻辑（装依赖、建库、拉起前后端、开浏览器）。
- `logo.ico`：从 `frontend/public/logo.png` 生成的多尺寸图标（16~256px）。
- `build.ps1`：构建脚本，用 Windows 自带的 .NET Framework 编译器
  （`csc.exe`）编译，不依赖任何第三方工具或 SDK。

## 什么时候需要重新构建

- 改了 `Launcher.cs` 的逻辑。
- 换了 `frontend/public/logo.png`，需要重新生成 `logo.ico` 再重新构建 exe。

## 重新生成图标（仅当 logo 变了）

`logo.ico` 由 Pillow 一次性生成，运行期不依赖它，本仓库也不把 Pillow
加进 `requirements.txt`。临时装一个虚拟环境转换即可：

```powershell
python -m venv .tmp-icogen
.\.tmp-icogen\Scripts\pip install --quiet Pillow
.\.tmp-icogen\Scripts\python -c "
from PIL import Image
img = Image.open(r'frontend\public\logo.png').convert('RGBA')
img.save(r'tools\launcher\logo.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
"
Remove-Item -Recurse -Force .tmp-icogen
```

## 重新构建 exe

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\launcher\build.ps1
```

会在仓库根目录覆盖生成 `心动实验室.exe`。

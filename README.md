# SnipTranslate · Snipaste 翻译助手

**简体中文** · [English](README.en.md)

给 Snipaste 加一个翻译按钮：**F1 截图 → 框选 → 点击“翻译” → 在原位置查看译图**。F3 贴图继续由 Snipaste 处理。

这是独立运行的伴随工具，当前适配 **Snipaste 2.11.3 x64**，界面为简体中文。

## 下载与使用

从 [Releases](https://github.com/gulzxeric/SnipTranslate/releases) 下载 **SnipTranslate-v0.1.0-windows-x64.zip**。需要 Windows 10/11 x64，无需安装 Python。

1. 自行安装并启动 [Snipaste](https://www.snipaste.com/)。压缩包不包含 Snipaste。
2. **完整解压**压缩包，保留 `SnipTranslate.exe` 和 `_internal` 文件夹。
3. 双击 `SnipTranslate.exe`。首次使用若未找到 Snipaste，会提示选择已安装的 `Snipaste.exe`。
4. 等待后台加载 OCR 模型，然后按 F1 框选文字，点击原工具栏下方的绿色“翻译”按钮。
5. 可切换原图／译图、复制、保存、贴图，或点击“文字”查看纯文本。

助手只显示托盘图标。右键托盘图标可打开设置、查看最近译图或退出。截图完成或取消时，翻译按钮自动隐藏。

### 开机启动

按 Win+R，输入 `shell:startup`，将 `SnipTranslate.exe` 的**快捷方式**放入打开的文件夹。Snipaste 也需要设置为开机启动。之后不要移动程序文件夹。

## 功能与数据处理

- **本地 OCR**：默认 RapidOCR + ONNX Runtime，中英混排模型随包附带。截图不上传到翻译服务；也可选择 Windows 系统 OCR。
- **谷歌在线翻译**：只发送识别出的文字。默认公共接口免 Key，但并非官方承诺支持的 Cloud API，可能限流或变更。
- **官方 Cloud API**：可切换 Google Cloud Translation，需自行启用服务、计费并提供 API Key。Key 通过 Windows DPAPI 加密保存，也支持 `GOOGLE_TRANSLATE_API_KEY` 环境变量。
- **代理**：无法连接谷歌时，可填写 HTTP / HTTPS 代理，例如 `http://127.0.0.1:7890`。
- **图片排版**：按段落翻译，估计背景、文字颜色和字号，在原位置显示译图，适合网页、文档等平整背景。

设置和日志位于 `%LOCALAPPDATA%\SnipTranslate`。普通使用不会自动将截图保存到磁盘。

## 速度与限制

启动时后台预热 OCR；连续截图复用 HTTPS 连接，多段文字合并请求，并减少图片压缩和排版等待。

完成后的耗时从**点击翻译按钮**开始，包含取图、准备、识别、网络和排版。鼠标悬停可查看分段耗时，日志记录截图尺寸和数值。小图的 OCR 基准不等于整个过程耗时；大图、文字多、首次加载及网络都会影响速度。

当前只在本机 Snipaste 2.11.3 x64 上验证。其他版本、工具栏布局或权限不同，需要另行测试。复杂背景、特殊字体、旋转文字及过长译文可能排版不理想。无法从当前截图日志取得位置时，译图居中显示。Windows OCR 需要对应的系统语言组件，并需在目标机器实际验证。

## 开发与打包

Windows x64、Python 3.11 或更新版本（当前开发环境为 Python 3.13）：

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

也可运行 `Start.cmd`。测试、构建和生成发布包：

```powershell
.venv\Scripts\python.exe -m pip install pytest pyinstaller
.venv\Scripts\python.exe -m pytest -q
.\build.ps1
.venv\Scripts\python.exe tools\package_release.py
```

构建会下载默认 OCR 模型。发布包、SHA-256 校验文件和第三方许可说明输出到 `dist\releases`。必须分发整个程序目录。

性能测试：`tools\benchmark_translation.py 图片路径`。截图选区打开时可运行只读诊断：

```powershell
.venv\Scripts\python.exe -m screen_translate.snipaste_native --diagnose --accessibility
```

## 反馈与第三方组件

请在 [Issues](https://github.com/gulzxeric/SnipTranslate/issues) 中提供 Windows / Snipaste 版本、截图尺寸、耗时和错误信息，分享截图前请移除敏感内容。

发布包附带第三方组件许可、版本和来源说明。SnipTranslate 是独立项目，与 Snipaste 及 Google 无隶属关系。

[Snipaste 命令行文档](https://docs.snipaste.com/zh-cn/command-line-options) · [RapidOCR](https://github.com/RapidAI/RapidOCR) · [Google Cloud Translation](https://cloud.google.com/translate/docs/basic/translating-text) · [Windows OCR](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr)

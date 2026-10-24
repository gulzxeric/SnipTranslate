# Snipaste 翻译助手

保留 Snipaste 原来的操作：**F1 截图 → 框选 → 在原工具栏下方点击绿色“翻译” → 查看译文**。F3 贴图继续由 Snipaste 处理。

这是一个外部伴随按钮，不修改 Snipaste.exe，不注入进程，不改变原快捷键和配置。已针对本机 Snipaste 2.11.3 x64 的工具栏结构适配；其他版本或工具栏布局变化需要重新验证。

## 使用

双击 `dist\SnipTranslate\SnipTranslate.exe`，或在开发目录双击 `Start.cmd`。助手启动后只显示托盘图标，没有独立截图主界面。

1. 正常按 **F1**，用 Snipaste 框选文字。
2. 原工具栏下方出现绿色 **翻译** 按钮，点击即可。
3. 在截图原位置显示译文图片，保留原图布局，并将周围屏幕变暗。可切换原图／译图、复制、保存或贴图；“文字”可查看纯文本。
4. 右键助手托盘图标可设置目标语言、代理、谷歌接口和 Snipaste 路径，也可退出助手。

按钮通过 Windows 无障碍接口定位真实工具栏，点击后调用 Snipaste 自己的复制按钮取得当前截图。没有注册新全局快捷键，也不会自动翻译其他剪贴板图片。截图完成或取消时按钮自动隐藏。

## 翻译与 OCR

- **OCR 在本机运行**，默认使用 RapidOCR + ONNX Runtime 的中英混排模型，模型随程序附带，不上传截图。设置中也可以选择 Windows 系统 OCR；Windows 模式可选择已安装的识别语言，“系统识别语言”不等于自动检测语言。
- **翻译使用谷歌在线接口**，识别出的文字会发送到谷歌。默认公共接口免 Key，但非官方保证的 API，可能变更或限流。
- 多段文字会在长度限制内合并请求，减少网络往返；如谷歌改变换行、无法确认段落对应关系，会自动逐段翻译，保证译文位置。官方 Cloud 接口直接使用其批量参数。
- 连续截图会复用谷歌的 HTTPS 连接，代理变化时自动替换连接。RapidOCR 接收内存中的无损位图，减少 PNG 压缩等待；图片排版通过批量像素采样减少等待，保留原有颜色选择和文字布局。
- 也可在设置中选择 **Google Cloud Translation 官方 API**，需要启用服务、计费并提供 API Key。Key 通过 Windows DPAPI 加密存储；也支持 `GOOGLE_TRANSLATE_API_KEY` 环境变量。
- 谷歌不可达时，可填写 HTTP / HTTPS 代理，例如 `http://127.0.0.1:7890`。

设置和日志保存在 `%LOCALAPPDATA%\SnipTranslate`。截图不会自动保存到磁盘。

图片翻译按段落处理，并根据原图估计背景色、文字颜色和字号。适合网页、文档等平整背景；复杂图片背景、特殊字体或过长译文可能与原图有差异。无法取得原截图位置时，会居中显示结果。当前 Snipaste 版本的坐标通过只读日志辅助定位，不会改动原程序或日志。

启动时会在后台预热本地 OCR 模型。识别过程采用适合截图的缩放和 CPU 推理参数；翻译时分别显示识别、谷歌请求、排版进度，完成后显示从点击按钮到译图完成的总耗时（包含 Snipaste 取图）。鼠标停在耗时文字上可查看取图、准备、等待、识别、谷歌和排版的耗时，日志也记录数值及截图尺寸，方便定位瓶颈。单独 OCR 的基准耗时不等于整个翻译过程耗时，大图、文字多、首次加载或网络延迟都会影响结果。

可用 `tools/benchmark_translation.py 图片路径` 复测本机流水线耗时，或用 `tools/benchmark_ocr_options.py 图片路径` 比较 OCR 参数。

## 开发

Windows 10/11、64 位 Python 3.11 或更新版本：

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

```powershell
.venv\Scripts\python.exe -m pip install pytest pyinstaller
.venv\Scripts\python.exe -m pytest -q
.\build.ps1
```

打包后保留整个 `dist\SnipTranslate` 文件夹，不能只移动 EXE。微软对桌面 Windows.Media.Ocr 的正式支持范围要求包标识；当前便携实现已在本机 Python 环境实测通过，其他机器需要实际验证及对应 OCR 语言组件。

只读诊断（截图选区处于打开状态时运行）：

```powershell
.venv\Scripts\python.exe -m screen_translate.snipaste_native --diagnose --accessibility
```

## 参考

- [Snipaste 官方命令行接口](https://docs.snipaste.com/zh-cn/command-line-options)
- [Google Cloud Translation](https://cloud.google.com/translate/docs/basic/translating-text)
- [Windows OCR](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr)

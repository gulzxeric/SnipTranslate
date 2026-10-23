# Snipaste 翻译助手

保留 Snipaste 原来的操作：**F1 截图 → 框选 → 在原工具栏下方点击绿色“翻译” → 查看译文**。F3 贴图继续由 Snipaste 处理。

这是一个外部伴随按钮，不修改 Snipaste.exe，不注入进程，不改变原快捷键和配置。已针对本机 Snipaste 2.11.3 x64 的工具栏结构适配；其他版本或工具栏布局变化需要重新验证。

## 使用

双击 `dist\SnipTranslate\SnipTranslate.exe`，或在开发目录双击 `Start.cmd`。助手启动后只显示托盘图标，没有独立截图主界面。

1. 正常按 **F1**，用 Snipaste 框选文字。
2. 原工具栏下方出现绿色 **翻译** 按钮，点击即可。
3. 稍候显示译文小窗，可复制译文、展开原文或重试。
4. 右键助手托盘图标可设置目标语言、代理、谷歌接口和 Snipaste 路径，也可退出助手。

按钮通过 Windows 无障碍接口定位真实工具栏，点击后调用 Snipaste 自己的复制按钮取得当前截图。没有注册新全局快捷键，也不会自动翻译其他剪贴板图片。截图完成或取消时按钮自动隐藏。

## 翻译与 OCR

- **OCR 在本机运行**，使用 Windows 自带文字识别，不上传截图。当前机器安装了简体中文 OCR，已实测识别中文和英文。设置可选择已安装的 OCR 语言；系统识别语言不是自动检测语言。
- **翻译使用谷歌在线接口**，识别出的文字会发送到谷歌。默认公共接口免 Key，但非官方保证的 API，可能变更或限流。
- 也可在设置中选择 **Google Cloud Translation 官方 API**，需要启用服务、计费并提供 API Key。Key 通过 Windows DPAPI 加密存储；也支持 `GOOGLE_TRANSLATE_API_KEY` 环境变量。
- 谷歌不可达时，可填写 HTTP / HTTPS 代理，例如 `http://127.0.0.1:7890`。

设置和日志保存在 `%LOCALAPPDATA%\SnipTranslate`。截图不会自动保存到磁盘。

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

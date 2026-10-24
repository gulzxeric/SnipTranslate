# SnipTranslate v0.1.0

## 简体中文

首个公开预览版，适用于 Windows 10/11 x64，当前适配 Snipaste 2.11.3 x64。

- F1 框选后，原工具栏下方显示绿色“翻译”按钮。
- 本地中英 OCR + 谷歌在线翻译，在截图原位置显示译图。
- 支持原图切换、复制、保存、贴图联动及纯文本查看。
- 可选 Windows OCR、Google Cloud 官方 API 及 HTTP / HTTPS 代理。
- 批量翻译、连接复用、OCR 预热，并显示完整阶段耗时。
- 首次启动支持选择已安装的 Snipaste。

下载 `SnipTranslate-v0.1.0-windows-x64.zip` 后**完整解压**，运行 `SnipTranslate.exe`。无需 Python，模型和运行库已包含；Snipaste 需单独安装并启动。压缩包中包含中英文使用说明及第三方许可。

识别在本机完成，识别出的文字会发送到谷歌。复杂背景、其他 Snipaste 版本需要进一步验证；速度取决于截图和网络。本版本未做代码签名。

## English

First public preview for Windows 10/11 x64, currently adapted to Snipaste 2.11.3 x64.

- A green Translate button appears below Snipaste's toolbar after an F1 selection.
- Local Chinese/English OCR and online Google translation produce an image in the capture's original position.
- Source/translation switching, copying, saving, pinning integration, and plain-text results.
- Optional Windows OCR, official Google Cloud Translation API, and HTTP / HTTPS proxy settings.
- Batched requests, connection reuse, OCR warmup, and full pipeline timing.
- First-launch selection of the installed Snipaste executable.

**Extract all files** from `SnipTranslate-v0.1.0-windows-x64.zip`, then run `SnipTranslate.exe`. No Python installation is needed; models and runtime libraries are included. Install and start Snipaste separately. The archive includes Chinese/English instructions and third-party licenses.

OCR runs locally; recognized text is sent to Google. Complex backgrounds and other Snipaste versions require further testing. Latency depends on the capture and network. This release is not code-signed.

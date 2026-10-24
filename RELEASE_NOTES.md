# SnipTranslate v0.2.0

## 简体中文

本次更新重点改善取消翻译、连续截图和发布体验。

- 翻译中按 **Esc** 或点击 **取消**，即可重新截图。旧进度、旧译文和旧错误不会覆盖新任务。
- 支持取消进行中的网络请求和 RapidOCR 推理；取消后模型可继续处理下一张截图。
- 截图工具栏探测与翻译任务分开运行，避免旧翻译占用工具栏连接。
- 托盘新增 **检查更新**：提示版本并提供 GitHub 发布页入口，不会自动替换程序。
- 增加中英文 README、操作示意动图及 **MIT 许可证（Copyright 2026 eric）**。
- 精简未使用的运行组件，保留截图识别、图片排版所需的模型和运行库。

下载 `SnipTranslate-v0.2.0-windows-x64.zip` 后**完整解压**，运行 `SnipTranslate.exe`。更新前先退出旧版，再将新版解压到一个完整目录。无需 Python；Snipaste 需单独安装并启动，当前适配版本为 Snipaste 2.11.3 x64。

OCR 在本机完成，识别出的文字会发送到谷歌。翻译耗时仍取决于截图和网络，动图不代表实际测速。本版本未做代码签名。

## English

This update focuses on cancellation, successive captures, and distribution.

- Press **Esc** or click **Cancel** while translating, then start another capture. Stale progress, results, and errors cannot overwrite the current task.
- In-flight HTTP requests and RapidOCR inference can be cancelled; recognition remains usable afterward.
- Native toolbar discovery runs separately from translation work so older tasks do not occupy the toolbar worker.
- New tray **Check for updates** action shows version information and opens GitHub Releases on request. It does not replace files automatically.
- Bilingual README files, a workflow illustration, and the **MIT License (Copyright 2026 eric)**.
- Smaller portable archive while retaining the required screenshot OCR and rendering components.

**Extract all files** from `SnipTranslate-v0.2.0-windows-x64.zip`, then run `SnipTranslate.exe`. Exit the old application before updating and extract the new version into a complete folder. No Python installation is needed. Install and start Snipaste separately; the currently adapted version is Snipaste 2.11.3 x64.

OCR runs locally; recognized text is sent to Google. Latency depends on the capture and network. Animation timing is not a speed benchmark. This release is not code-signed.

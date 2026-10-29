# FFmpeg 分发材料核对

核对日期：2026-10-29。状态：**部分核实；完整对应源码尚未核实，不能据此宣布分发材料齐全。**

## 已核实的本地构建材料

本记录检查的是 BiliAudio 1.0 本地打包输入，不是重新下载并检验过的 GitHub Release 附件。

| 项目 | 结果 |
| --- | --- |
| 获取途径 | imageio-ffmpeg 0.7.0 Windows wheel 中的 `ffmpeg-win-x86_64-v7.1.exe` |
| 打包文件名 | `ffmpeg.exe`，作为独立子进程运行 |
| 文件大小 | 87,638,016 bytes |
| SHA-256 | `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3` |
| 程序报告版本 | `7.1-essentials_build-www.gyan.dev` |
| 编译器 | GCC 14.2.0 (Rev1, Built by MSYS2 project) |
| 关键配置 | `--enable-gpl --enable-version3 --enable-static` |
| 程序报告许可 | GNU GPL version 3 or later |

执行输出见 [FFmpeg.txt](FFmpeg.txt) 和 [FFmpeg-buildconf.txt](FFmpeg-buildconf.txt)。
完整 GPLv3 文本见 [GPL-3.0.txt](GPL-3.0.txt)。该标准文本原样复制自本机 Git for Windows 附带的 GCC `COPYING3`；它是通用许可正文，不是 FFmpeg 源码或第三方库清单。

## 官方来源证据

- [Gyan 构建说明](https://www.gyan.dev/ffmpeg/builds/)说明其主要构建为静态 GPLv3 构建。
- [Gyan 7.1 发行页](https://github.com/GyanD/codexffmpeg/releases/tag/7.1)标出的 FFmpeg 源码提交为 [`b08d7969c5`](https://github.com/FFmpeg/FFmpeg/commit/b08d7969c5)。
- [imageio-ffmpeg 0.7.0](https://pypi.org/project/imageio-ffmpeg/0.7.0/)是本项目实际使用的中间分发包。

发行页的版本对应关系不等于已完成二进制逐字节校验。此次下载 Gyan 原 ZIP 时发生超时/TLS 连接失败，尚未将其中 EXE 与上述本地哈希比较。

## 尚未完成的材料

1. 获取 Gyan 7.1 原发行包，保留其 README、许可证及第三方库版本/配置说明，比较 EXE 哈希。
2. 确定静态链接依赖的准确版本、补丁和构建脚本。配置中包含 libx264、libx265、libmp3lame、librubberband、GnuTLS 等；配置字符串不是完整依赖清单，也不能确定每个依赖的源码版本。
3. 收集并提供与实际二进制匹配的完整对应源码及必要构建材料，并保留适用的依赖许可和版权声明。仅添加 FFmpeg 主仓库链接或一个源码压缩包不能证明此项完成。
4. 核实软件实际发布渠道的源码获取方式，确保接收二进制的用户能够按适用条款获取所需材料。
5. 对线上 BiliAudio Release 的实际附件重复检查，而不是只检查本地打包输入。

## 新二进制发行检查

发布包含 FFmpeg 的新二进制前，应完成上述材料核对。若无法取得当前构建的对应材料，可另行评估使用具有完整可追溯源码的构建；更换构建属于单独的程序和打包变更，需要重新测试。

发行 ZIP 应同时携带项目的 LICENSE、NOTICE、第三方许可和准确的源码获取说明。源码发布不应只列不可验证的通用主页。

BiliAudio 的 PolyForm Noncommercial 声明不替代、不限制 FFmpeg 及其依赖原有的授权。此记录是技术材料核对结果，不是对整体分发合规性的法律认证，也不对既有发行附件作自动修复声明。

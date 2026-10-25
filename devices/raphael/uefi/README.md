# raphael UEFI

基于 Project Silicium / Mu-Silicium，固定提交见 BASE。设备包位于 files/Platforms/Xiaomi/raphaelPkg，配置在 files/Resources/Configs/raphael.toml。

本机 XBL 提取工具为 tools/extract-raphael-uefi.py。Binaries/raphael 模块和本机 Linux DTB 属于私有构建输入，不提交。POCO X5 Pro 的 UEFI 不能用于本机。

从仓库根目录运行：

```sh
devices/raphael/uefi/apply.sh
# 按 Mu-Silicium 文档安装依赖、配置 Python 环境。
cd Mu-Silicium
python3 build_uefi.py -d raphael -r DEBUG
```

本机固定内存布局为 FD_BASE=0x9fc00000、FD_SIZE=0x300000、PAYLOAD_BASE=0xf0000000。loader USB、八核和 iOS 的成功记录来自历史版本；本轮只检查源码、构建 loader，未重建 UEFI 或启动设备。

`export.sh` 只导出设备包、配置、自有 XnuLoader 源码和 Mu-Silicium 补丁，不复制固件模块或 DTB。它以仓库根 Mu-Silicium 为源目录。

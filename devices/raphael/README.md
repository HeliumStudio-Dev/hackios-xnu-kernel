# Redmi K20 Pro / Mi 9T Pro（raphael）

SM8150、Adreno 640、GT9886，iOS 16.5 20F66。当前跟随 HakiOS main，仅使用 GLES；历史 Metal 结果不适用于当前版本。

## 构建

从仓库根目录运行，使用本机已有工具链和缓存：

```sh
export THEOS="$PWD/out/theos"
export PATH="/home/heliumstudio/toolchains/r596125/bin:$PWD/xnu-deps/host/bin:$PATH"
export XNU_SRC="$PWD/xnu-src/xnu-8796.121.2-baseline-20261027"
devices/raphael/build.sh kernel
devices/raphael/build.sh loader
GL=1 REST=1 QUIET=1 FLASHBOOT=prepared devices/raphael/build.sh images
```

首次创建内核树应运行 `xnu/apply.sh "$XNU_SRC"`；已有树不会自动同步 overlay。Wi-Fi 使用 ath10k，镜像需另行指定私有 `MPSS_FW`。镜像构建所需 Apple 输入由新上游 `sysimage/` 提供；本轮没有重建完整镜像。

UEFI 源码见 [uefi/](uefi/)。`device.conf` 的 DTB 必须由本机内核源码构建；UEFI 模块须从本机 XBL 提取。构建 boot 镜像时显式提供 `UEFI_FD`，禁止复用 POCO 预构建文件。`devices/raphael/build.sh boot` 只生成本地镜像。

## 启动与存储

默认 profile 禁用存储和无线，保留 CPU、GPU、触控、按键及命令模式 `fb_scan=1`。运行 XNU 前显式设置 `XL_KERNEL`；正常 UI 不加 `-v`。本轮未启动手机。

已部署的 userdata 不需重写。prepared init 使用现有系统卷、`/redwood` 挂载路径和双槽 var 归档。只有原有可信参数与边界检查允许的区域可写；新的 DEBUG loader 可能完全只读，不可仅凭参数宣称保存成功。

Wi-Fi 参数、私有文件及未修问题见 [RAPHAEL-WIFI.md](../../docs/RAPHAEL-WIFI.md)。基线迁移与检查见 [迁移记录](../../docs/UPSTREAM-BASELINE-20261027.md)。历史设备调试见 [RAPHAEL.md](../../docs/RAPHAEL.md)，其中旧路径和 Metal 命令不能直接用于当前基线。

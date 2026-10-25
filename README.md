# HakiOS · Redmi K20 Pro / Mi 9T Pro 测试指南

本分支将 XNU 和 iOS 用户态移植到 **Redmi K20 Pro / Mi 9T Pro（代号 `raphael`）**，供开发和实验测试使用。本文面向希望在自己的设备上体验、验证和反馈问题的用户。

**这不是可日用的 iOS ROM。请使用备用机，先完成备份。本文只介绍 RAM 临时启动，不刷写 Boot、Recovery、GPT 或 userdata，不提供持久化安装步骤。** 文中的“刷入”指通过 `fastboot boot` 和 loader 将测试程序上传到内存。

仓库提供移植源码、构建工具，以及 [Releases 中已验证的 raphael UEFI 启动镜像](https://github.com/Helium-Studio/hackios-xnu-kernel/releases/tag/raphael-uefi-debug-r5)。不提供完整 iOS 系统镜像、MPSS/WLAN 固件或 NV 数据。下载 UEFI 后，仍需自行准备配套内核、GLES 用户态和 RAM 系统镜像。

## 项目情况

| 项目 | 当前情况 |
|---|---|
| 目标硬件 | raphael，Snapdragon 855 / SM8150、Adreno 640、GT9886 触控 |
| 系统 | iOS 16.5 `20F66`，XNU `8796.121.2` |
| 当前分支 | [`raphael-bringup`](https://github.com/Helium-Studio/hackios-xnu-kernel/tree/raphael-bringup) |
| 图形路径 | Mesa / Freedreno，OpenGL ES；当前不提供 Metal 驱动 |
| 启动方式 | UEFI → XNU loader → XNU → iOS 用户态，依赖宿主机上传 |
| 推荐测试方式 | 整套系统运行在 RAM，`ufs=0 ufs_write=0 var_store=0` |
| 保存状态 | 本文 RAM 测试不保存设置、应用数据或本轮输入的网络配置；重启后需重新上传 |

本分支基于上游 [HakiOS](https://github.com/oosexgang/hakios-os)。不要将上游 POCO X5 Pro 的功能表、UEFI、固件或默认启动命令直接用于 raphael，也不要用于其他 Snapdragon 855 机型。

### 最近实测：2026-10-27

该轮测试使用的内核、驱动与用户态源码和当前 bringup 提交中的实现一致；后续整理提交历史及更新文档未改变这些实现。UEFI 使用下方 Releases 中发布的 DEBUG r5 原样镜像。

| 功能 | 测试结果及限制 |
|---|---|
| UEFI、loader USB、iOS 桌面 | 已启动，init 的 39 项检查全部通过 |
| CPU 与调频 | 后续达到 7 个 active CPU，并行计算完成，OSM 调频有日志证据；CPU0 留给 loader，不称为八核同时运行 |
| GPU / GLES | FD640，1080×2340 三角形绘制与读回成功，GL error 为 0 |
| 桌面、控制中心、触控、按键 | 用户确认基本功能正常，流畅度尚可；不保证所有场景稳定 60 FPS |
| 网页与字体 | 用户确认本轮 Safari 网页和字体正常；不代表全部网页、控件及应用已覆盖 |
| Wi-Fi 首次连接 | 已验证 5 GHz WPA3 SAE H2E 连接、取得地址及实际网页访问；历史亦有 WPA2 联网记录 |
| Wi-Fi 关闭后重新开启 | **仍有问题：可见网络列表，但无法重连，日志出现 `failed to power on device: -19`**；列表是否来自新扫描或缓存尚未独立确认 |
| Metal、蜂窝网络、蓝牙、音频、相机、充电 | 不在本分支当前用户测试的可用性承诺内；本文不启用这些功能 |
| userdata 固化与恢复 | 历史曾验证特定测试机布局；不属于本文流程，不能套用到其他手机或现有分区内容 |

单次绘制读回成功不代表所有渲染路径正确。复杂 UI 性能、显示同步、无线重连与长期稳定性仍需继续验证。首次取得地址时，自动联网检查也曾先报 DNS / offline 错误，随后用户在 Safari 访问成功；不能仅凭 Wi-Fi 图标判断已经联网。

## 测试前准备

### 1. 确认设备与恢复能力

- 仅在确认代号为 `raphael` 的设备上测试。营销名称相近不代表硬件相同。
- Bootloader 必须已解锁。**解锁通常会清除用户数据，应在解锁前备份。** 解锁方法请遵循设备厂商说明，本文不提供解锁或绕过流程。
- 确认能通过电源键＋音量下进入 Bootloader，并且电脑能识别 fastboot。
- 准备对应机型、区域和版本的原系统恢复资料；先了解如何恢复，再进行实验。
- 保持 Bootloader 解锁，不要在测试系统或混合分区状态下回锁。
- 使用可靠的数据线和 USB 接口，准备充足电量。不要依赖本项目的充电支持或电量显示。

### 2. 备份并验证

至少将照片、文档、聊天记录、联系人、认证器恢复码及其他不可替代数据复制到另一台设备或离线存储，并实际打开、核对关键文件。手机内部的另一目录不算独立备份。

如具备可靠的 Root / Recovery 只读备份条件，可另行备份本机实际存在的 Boot、Recovery、DTBO、persist 及无线相关 NV 分区，并记录固件版本与校验值。备份方式应适用于自己的设备；不要为了完成本指南而随意使用未知分区脚本。

**persist、modemst1 / modemst2、fsg / fsc 等可能含本机校准、身份和网络相关私有数据。不要公开上传，不要与他人交换，不要将其他手机的备份恢复到本机。** 本项目的分区写入工具不作为通用备份或恢复工具使用。

RAM 测试流程不主动写入 userdata，但不能替代备份，也不保证异常启动、固件行为或返回原系统后的行为不会影响数据。

### 3. 准备宿主环境

建议使用 Linux x86-64，或能将 USB 设备接入 Linux 的 WSL2 环境。准备 Android platform-tools（`adb`、`fastboot`）、Git、Python 3，以及可用的 USB 设备权限。

自行构建还需要 LLVM / Clang、LLD、C/C++ 构建工具、Theos / cctools、iPhoneOS 16.5 SDK、7-Zip 23 或更新版本，以及构建脚本要求的工具。建议预留至少 60 GB 空闲磁盘和 16 GB 内存；缓存、UEFI 依赖和备份会增加占用。

WSL 用户须区分 Windows 和 Linux 的 USB 状态：Windows 能看到设备，不代表 WSL 中的 fastboot 可以访问。详见下方 WSL 操作说明。

## 准备匹配的测试文件

一次测试需要以下文件。它们必须来自同一套源码与兼容配置，不能将旧 Metal 用户态、新 GLES 内核和其他机型 loader 混用。

| 文件 | 作用 |
|---|---|
| `raphael-uefi-debug-r5.img` | 从 Releases 下载的已验证 UEFI / USB loader 镜像，供 `fastboot boot` 使用 |
| `mach.development.bcm2837` | 本轮构建的 XNU 内核；文件名中的 bcm2837 是构建目标名，不代表手机型号 |
| `userland/root.apfs` | 配套工具、GLES 库与 init，运行时挂载于 `/redwood` |
| RAM resident 镜像 | 本文采用 Boot、System 两个 APFS container 顺序拼接的镜像，系统来自第二个 container |

**优先使用 Releases 的已验证 UEFI，无需自行提取 XBL、生成 DTB 或编译 UEFI。** 它是最近实测使用的 DEBUG r5 启动镜像，内含 loader。该附件不是完整 iOS 系统，不能替代其他三个测试文件。仓库通用 `prebuilt/` 也不等于已验收的 raphael 配套内核和用户态。

### 下载已验证的 UEFI

打开 [raphael UEFI DEBUG r5 发布页](https://github.com/Helium-Studio/hackios-xnu-kernel/releases/tag/raphael-uefi-debug-r5)，下载 `raphael-uefi-debug-r5.img` 和 `SHA256SUMS`。Linux / WSL 可在仓库根目录运行：

```bash
mkdir -p out/raphael/uefi
curl --fail --location \
  https://github.com/Helium-Studio/hackios-xnu-kernel/releases/download/raphael-uefi-debug-r5/raphael-uefi-debug-r5.img \
  --output out/raphael/uefi/raphael-uefi-debug-r5.img
curl --fail --location \
  https://github.com/Helium-Studio/hackios-xnu-kernel/releases/download/raphael-uefi-debug-r5/SHA256SUMS \
  --output out/raphael/uefi/SHA256SUMS
(cd out/raphael/uefi && sha256sum --check SHA256SUMS)
```

校验必须显示 `OK`，并与以下固定值一致；不匹配时不要启动：

```text
1b672ca1c990d85014274388405b156aaea1ce407a931d3f75f49fa11db5781c  raphael-uefi-debug-r5.img
```

此附件是已验证旧构建的原样归档，不是发布标签源码重新编译的产物。构建来源、范围和限制见发布说明。首次体验使用该附件；只有修改启动固件的开发者才需要后文的 UEFI 源码构建步骤。

### 从源码准备：内核（自行构建 loader 可选）

以下命令使用 Bash，在同一个终端执行；路径中的占位内容必须替换为自己的实际路径。

```bash
git clone --branch raphael-bringup \
  https://github.com/Helium-Studio/hackios-xnu-kernel.git hakios-raphael
cd hakios-raphael

export THEOS="$HOME/theos"       # 修改为已配置工具链和 SDK 的 Theos 目录
export XNU_SRC="$PWD/xnu-src/xnu-8796.121.2-raphael"
export PATH="$PWD/xnu-deps/host/bin:$PATH"

# 仅首次创建该源码树时运行；已有树不会自动同步补丁。
xnu/apply.sh "$XNU_SRC"
xnu-deps/setup.sh
devices/raphael/build.sh kernel
```

内核构建会使用 raphael 的 ath10k 对象；不要回退为上游默认 ath11k。工具链配置详见 [XNU 构建说明](xnu/README.md)。不要将 Theos 的 Darwin `ld` 放到宿主 PATH 最前面。

**使用 Releases 镜像时无需重新构建 loader，可跳过下面这一步。** 自行修改 loader 或重打包 UEFI 时，需要从自己准备的 iOS 16.5 IPSW 中提取、解压后的 Apple DeviceTree，先生成 `identity.h`，再构建。输入应为解压后的树，不是直接传入 `.im4p` 容器；`--placeholder` 只供开放内核实验，不用于启动 iOS 用户态。

```bash
# 替换为自己解压后的 DeviceTree 路径。
python3 xnuloader/mkidentity.py /path/to/DeviceTree.d22ap.bin \
  > xnuloader/identity.h.tmp && \
  mv xnuloader/identity.h.tmp xnuloader/identity.h

devices/raphael/build.sh loader
```

生成的 `identity.h` 含从 Apple 输入派生的数据，保持本地使用，不提交到仓库。

### 可选：自行构建 UEFI；准备本机 GPU / Wi-Fi 固件

使用 Releases 镜像时，跳过下列 XBL 提取、DTB 和 UEFI 编译步骤；GPU / Wi-Fi 固件输入仍需自行准备。自行修改 UEFI 时，需要本机 XBL 中的模块以及适配本机的 Linux DTB。Linux 源码仅用于读取设备定义和生成 DTB，**不需要、也不应另行启动 Linux 实机测试**。

- 先按 [raphael UEFI 说明](devices/raphael/uefi/README.md) 准备 Mu-Silicium 源码和构建环境。
- `tools/extract-raphael-uefi.py` 从本地 `out/raphael/firmware/xbl.img` 提取模块。**当前脚本只接受已核验版本的 XBL 哈希；不匹配时应停止，不能删除校验强行运行。** 它不是适用于任意固件版本的提取器。
- 使用 `tools/build-raphael-dtb.py` 从包含 raphael 下游设备树的源码生成 DTB。该目录需包含 `sm8150-v2.dts`、`raphael-sm8150-overlay.dts` 等输入；任意 6.12 源码树不一定适用。
- GPU 输入应匹配 A640：例如 `a640_gmu.bin`、`a630_sqe.fw`、`a640_zap.*`，放入本地 `fw-gpu/`。不能使用 A642L 的 `a660_*` 固件代替。
- Wi-Fi 还需本机 MPSS / WLAN 固件、匹配的 BDF 和私有 NV 快照。输入清单见 [Wi-Fi 说明](docs/RAPHAEL-WIFI.md)。不确定机型区域或固件匹配关系时，先禁用无线测试。

已安装宿主 `dtc`、`fdtoverlay` 时，DTB 命令示例为：

```bash
DTC=dtc FDTOVERLAY=fdtoverlay \
  python3 tools/build-raphael-dtb.py /path/to/raphael-kernel-source
```

完成 UEFI 的模块准备、DTB 放置及依赖配置后，在 Mu-Silicium 中构建，再从仓库根目录打包：

```bash
(cd Mu-Silicium && python3 build_uefi.py -d raphael -r DEBUG)

UEFI_FD="$PWD/Mu-Silicium/Build/raphaelPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd" \
  devices/raphael/build.sh boot
```

自编译产物为 `out/raphael/boot.img`，需自行验收；下文默认仍使用 Releases 镜像。不要使用 POCO X5 Pro 的 UEFI、DTB 或内存布局代替。若设备固件与当前提取脚本不兼容，应先停止并向维护者提供不含私有内容的版本信息。

### 从源码准备：完整 RAM 用户态

先从自己有权使用的来源准备 iOS 输入。仓库的脚本会获取 iOS 16.5 对应文件并在本地处理，不会将这些文件加入 Git。

```bash
sysimage/fetch.sh

# 可选：仅测试 Wi-Fi 时设置，目录必须包含本机匹配的固件与 NV。
# export MPSS_FW="/absolute/path/to/your/raphael-mpss-fw"

# prepared 用于生成小 Boot container；SYSTEM=1 同时重建配套 System。
# 此处全部是宿主机上的文件构建，不会向手机部署系统。
FLASHBOOT=prepared SYSTEM=1 devices/raphael/build.sh images

mkdir -p out/raphael
cat userland/flashboot.apfs userland/system.apfs \
  > out/raphael/ram-resident.apfs
```

**拼接顺序不能反过来：container 0 是 Boot，container 1 是 System。** 后面的 `root_apfs=md0,c=1` 只对应这一布局。如果使用其他布局的镜像，必须采用与其配套的启动参数。

本地实测的拼接镜像约 2.60 GB，实际大小会随输入和配置变化。GPU 固件与私有 MPSS 文件应在构建前准备好；不要在镜像已经生成后才复制到宿主目录，并假定镜像自动更新。

## RAM 临时启动

### 1. 进入 Bootloader 并启动 UEFI

以下为 Linux 下的操作。确保仅连接目标测试机；多设备环境应先隔离其他设备，避免 `xl` 自动选择错误设备。USB 权限应已配置好，不要让 `fastboot` 一直停在等待设备。

```bash
export BOOT_IMAGE="$PWD/out/raphael/uefi/raphael-uefi-debug-r5.img"
export XL_KERNEL="$PWD/xnu-src/xnu-8796.121.2-raphael/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837"
export XL_RAMDISK="$PWD/userland/root.apfs"

fastboot devices
fastboot boot "$BOOT_IMAGE"
```

等待 loader 枚举后，再执行：

```bash
fastboot getvar product
./xl state
```

应分别看到 product 为 `xnuloader`、状态为 `loader`。**fastboot 返回 `Booting OKAY` 只表示命令被接受，不代表 UEFI 或 iOS 已启动。** 若回到原系统、持续黑屏或没有 loader USB，先停止，不上传后续镜像。

本指南显式通过 `fastboot boot` 临时启动 Releases 的设备专用 UEFI，不使用 `./xl enter` 自动选择默认镜像。后续 `xl` 命令会检查 loader 状态；如果设备已回到原系统，应重新执行上述核验，不要直接重试上传。

### WSL2 的 USB 交接

在 Windows 使用 platform-tools 临时启动 UEFI，看到 `xnuloader` 后，用 usbipd-win 将**当前枚举出的 loader** 接入 WSL。例如在具有相应权限的 PowerShell 中：

```powershell
Invoke-WebRequest -Uri "https://github.com/Helium-Studio/hackios-xnu-kernel/releases/download/raphael-uefi-debug-r5/raphael-uefi-debug-r5.img" -OutFile .\raphael-uefi-debug-r5.img
$expected = "1b672ca1c990d85014274388405b156aaea1ce407a931d3f75f49fa11db5781c"
if ((Get-FileHash .\raphael-uefi-debug-r5.img -Algorithm SHA256).Hash -ne $expected) { throw "UEFI checksum mismatch" }
.\fastboot.exe devices
.\fastboot.exe boot .\raphael-uefi-debug-r5.img
usbipd list
# 必要时先共享；将下面的 3-2 替换为本轮 list 显示的 loader BUSID。
usbipd bind --busid 3-2
usbipd attach --wsl --busid 3-2
```

总线号只是示例，不能沿用上次记录。回到 WSL 后，用 Linux 的 `fastboot devices`、`fastboot getvar product` 和 `./xl state` 再次核对；确认 loader 可访问，再继续上传。不要照搬维护者电脑的 Windows 用户路径、固定串号或本地 `out/host-bin` 包装器。

### 2. 上传 resident 镜像

```bash
./xl ramdisk out/raphael/ram-resident.apfs
```

等待上传完成。2.60 GB 镜像在最近实测中上传约 133 秒，其他 USB 环境可能更慢。这一步将镜像传入 RAM，**不是向 userdata 写入**。

resident 镜像在同一个 loader 会话中可复用；冷重启或更换 loader 会话后，应重新上传。不要将一个旧会话的上传记录当作当前镜像已就绪。

### 3. 选择无线配置并运行

默认先关闭 Wi-Fi；若已准备并打包本机全部无线输入，可在启动前选择无线参数，然后在同一轮测试 CPU、GPU、触控、按键与联网。

```bash
WIFI_ARGS='wifi=0'

# 仅适用于已核验 CN BDF 的本机固件组合；否则保持 wifi=0。
# WIFI_ARGS='wifi_step=15 wifi_lx=2 wifi_ba=1 wifi_wide=1 wifi_new=99 wifi_pause=0 wifi_ask=1 wifi_bdf=bd_f11cn.bin wifi_smmu=2 wifi_keep=1 wifi_wait=10 wifi_listen=15'

export XL_SECS=600
export XL_FOLLOW=15
export XL_FOLLOW_KEEP=1
export XL_CMDLINE="gic_timer_irq=19 bootcpu=7 cpus=8 touchscreen=1 buttons=1 cpufreq=1 gpu=1 fb_scan=1 modem=0 adsp=0 ufs=0 ufs_write=0 var_store=0 root_apfs=md0,c=1 $WIFI_ARGS"
./xl run
```

保持该终端运行；屏幕不加 `-v`，宿主机仍保存日志。初期可能显示 GPU 三角形，并进行短时 CPU / GLES 检查，完成后再评估界面。没有自动手势，触控和按键由用户手动测试。

上述命令不指定 GPU 超频档，A640 默认使用 585 MHz。最近合并实测曾使用 `adreno_speed=5` 的 765 MHz 对照档；这不代表其他设备在该档位稳定，首次测试无需添加。

无线 BDF 不能仅凭网络名称选择。GLOBAL 变体与 CN 不同，应核对本机固件后使用对应输入与参数。Wi-Fi 密码只在手机设置中输入，无需提供宿主保存的密码，也不要写进反馈日志。

## 一轮测试清单

等待启动检查结束后，按顺序完成，避免每测一项就重新启动：

1. 查看锁屏、桌面和壁纸，确认没有持续日志覆盖、花屏或持续横向错位。
2. 左右滑动主页，进入负一屏，展开控制中心和通知面板，打开应用切换；记录卡顿、缺失内容或异常颜色。
3. 慢拖和快速滑动，检查触控与多点触控；短按电源、音量上、音量下，确认有反应。
4. 若启用无线，在设置中连接自己的网络；尝试 Safari 的 HTTP 与 HTTPS 页面，检查加载和字体。不要只看 Wi-Fi 图标。
5. 若希望复现已知无线问题，再关闭、开启 Wi-Fi，检查扫描、重新连接和网页访问。**目前该步骤可能无法重连，需结束并重新开始 RAM 会话。**
6. 记录复现操作、发生时间和现象。长时间运行能力、充电及日常使用可靠性不在本轮通过标准内。

发生明显异常发热、持续黑屏或设备失去响应时，停止测试。不要通过刷写其他分区“修复”RAM 启动问题。

## 结束测试与恢复

默认达到 `XL_SECS=600` 后，内核尝试返回 loader。也可在仓库目录的第二个终端提前正常结束：

```bash
./xl stop
```

等待运行终端输出 `result: returned ...` 并保存最终日志。`xl run` 通常会自动取回日志，不要紧接着盲目执行 `xl log`，以免消耗已经 staged 的日志内容。

确认已返回 loader 后，如需回到手机原有启动路径：

```bash
./xl state
./xl reboot
```

重启后将由手机原有 Boot 分区和系统继续启动，可能是 Android，也可能是之前安装的其他系统。RAM 测试不会替你修复原系统；本文参数不会保存本轮 iOS 数据。

若 USB 失去响应，尝试长按电源重启，或电源键＋音量下回到 Bootloader。若仍无法恢复，按自己预先准备的机型恢复方案处理，避免盲目操作分区。本指南不需要执行任何分区刷写、擦除、格式化或回锁命令。

## 常见问题与反馈

| 现象 | 处理方式 |
|---|---|
| fastboot 没有设备 | 检查线缆、驱动、权限和所处模式；WSL 额外检查 usbipd 当前 BUSID 和 Attached 状态 |
| `Booting OKAY` 后返回原系统 | UEFI 没有成功驻留；确认 raphael 镜像、配套 DTB 和固件版本，不继续上传 |
| `xl state` 不是 `loader` | 先恢复正确 USB 状态；不要依赖自动生成的默认 UEFI |
| APFS 挂载失败 | 核对镜像拼接顺序和 `root_apfs=md0,c=1`；不要改为挂载、格式化或重写 userdata |
| 界面正常但工具提前报告网络 offline | 等待地址、DNS 和系统网络状态就绪，再实际打开网页；记录工具与人工结果的差别 |
| Wi-Fi 开关后无法重连，出现 `-19` | 已知未解决问题，重新开始 RAM 会话；无需擦除网络分区或 NV |
| 控件、字体或复杂界面异常 | 记录应用、页面和操作步骤；基础三角形通过不能排除此类错误 |
| 手机重启或主机无响应 | 保存现有 `.live` 日志，恢复 Bootloader 后再决定是否继续；不要反复盲启动 |

反馈时请提供：机型与区域、原固件版本、Git 提交号、镜像校验值、启用的参数、复现步骤，以及经过脱敏的相关日志。日志一般位于 `logs/`；保留早期 `.live.*` 有助于诊断重启前的状态。

日志、截图可能包含网络地址、设备标识和个人内容。**先脱敏，再分享。不要公开固件、NV、密码、Apple 文件或完整系统镜像。**

开发细节见 [设备说明](devices/raphael/README.md)、[历史移植记录](docs/RAPHAEL.md)、[Wi-Fi 状态](docs/RAPHAEL-WIFI.md) 和 [基线迁移分析](docs/UPSTREAM-BASELINE-20261027.md)。旧记录中的 Metal、`common/`、`/hackios`、userdata 部署命令属于历史，不是本文的 RAM 测试流程。

## 免责声明、许可与致谢

本项目为独立实验项目，与 Apple、Xiaomi、Qualcomm 无隶属或背书关系。iOS、iPhone、Apple 等名称仅用于说明兼容对象，不代表认证、授权或服务可用性。Apple 账户及相关服务不属于本项目当前目标。

软件和说明按现状提供，不保证适用性、稳定性、数据完整性或可恢复性。测试可能造成崩溃、异常发热、数据丢失、无法启动或其他设备故障；RAM 启动也不能消除这些风险。请自行评估、做好备份，并仅在自己拥有或获准操作的设备上进行测试。此说明不替代适用许可条款或法律要求，也不排除依法不可排除的责任。

仓库中的开源部分按各自许可使用：XNU 修改涉及 APSL 2.0，其他源码以文件头及相应许可为准。Releases 的 UEFI 镜像含设备固件派生模块，使用与再分发仍须遵循相关组件许可。iOS 用户态、IPSW 内容、其他专有固件和 NV 不因本项目而获得再分发许可；请自行确认输入文件的使用权限，不将这些输入提交或随测试包公开发布。

许可与第三方信息：[LICENSE](LICENSE)、[LICENSE.APSL](LICENSE.APSL)、[NOTICE](NOTICE)、[第三方许可](THIRD_PARTY_LICENSES.md)、[法律说明](LEGAL.md)、[合规记录](COMPLIANCE.md)。

感谢上游 HakiOS、[Project Silicium / Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)、Mesa / Freedreno，以及相关内核、无线和工具项目的贡献者。保留上游致谢：@oodze、@netusd、@wannqn、@hxfuxyyXD、Rhaenja Hun（杭润嘉）。本分支的机型测试结论以本文注明的版本和范围为限。

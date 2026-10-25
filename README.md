# HakiOS · Redmi K20 Pro / Mi 9T Pro 测试指南

本分支将 XNU 和 iOS 用户态移植到 **Redmi K20 Pro / Mi 9T Pro（代号 `raphael`）**，供开发和实验测试使用。本文面向希望在自己的设备上体验、验证和反馈问题的用户。

**这不是可日用的 iOS ROM。请使用备用机，先完成备份。本文只介绍 RAM 临时启动，不刷写 Boot、Recovery、GPT 或 userdata，不提供持久化安装步骤。** 文中的“刷入”指通过 `fastboot boot` 和 loader 将测试程序上传到内存。

仓库提供移植源码、构建工具，以及 [Releases 中已验证的 raphael UEFI 启动镜像](https://github.com/Helium-Studio/hackios-xnu-kernel/releases/tag/raphael-uefi)。不提供完整 iOS 系统镜像、MPSS/WLAN 固件或 NV 数据。下载 UEFI 后，仍需自行准备配套内核、GLES 用户态和 RAM 系统镜像。

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

本分支基于上游 [HakiOS](https://github.com/oosexgang/hackios-xnu-kernel)。不要将上游 POCO X5 Pro 的功能表、UEFI、固件或默认启动命令直接用于 raphael，也不要用于其他 Snapdragon 855 机型。

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

## 第一步：准备电脑和工具

整个流程分为：**电脑上构建文件 → 从 Releases 下载 UEFI → 手机进入 Bootloader → 上传到 RAM → 手动测试。** 先把文件准备齐，再启动手机。

构建需要 Linux x86-64 环境。下面以 Ubuntu 24.04 或更新版本为例，其他发行版请安装对应工具。建议预留至少 60 GB 空闲磁盘和 16 GB 内存，源码目录不要有空格。

打开 Bash 终端，先安装基础工具：

```bash
sudo apt update
sudo apt install git curl build-essential clang lld llvm python3 python3-venv \
  flex bison m4 perl autoconf automake libtool cmake meson ninja-build \
  pkg-config xz-utils unzip zlib1g-dev libssl-dev 7zip
```

随后按 [Theos 官方 Linux 安装说明](https://theos.dev/docs/installation-linux) 安装 Theos。本文假设安装位置是 `~/theos`；如果你装在其他位置，后面的 `THEOS` 要改成对应路径。Theos 用于提供构建 iOS 程序所需的工具，不会安装到手机。

**手机连接工具按自己的电脑选择一种：**

| 电脑环境 | 如何准备 adb / fastboot |
|---|---|
| 原生 Linux | 从 [Google 官方 platform-tools 页面](https://developer.android.com/tools/releases/platform-tools) 下载 Linux 版本，解压，将目录加入 PATH，并配置 USB 访问权限 |
| Windows + WSL2 | 在 **Windows** 下载 Windows 版本 platform-tools，例如解压到 `C:\platform-tools`，并安装手机所需驱动；WSL2 负责构建，手机通信使用 Windows 的 `adb.exe` / `fastboot.exe` |

Windows 用户先在 PowerShell 中检查工具。手机尚未进入 Bootloader 时，`fastboot devices` 没有输出是正常的；进入 Bootloader 后必须能列出设备。

```powershell
$env:Path = "C:\platform-tools;" + $env:Path
adb.exe version
fastboot.exe --version
```

本文不要求 WSL2 接管手机 USB。使用 WSL2 时，保持设备由 Windows 管理，下一步配置脚本调用 Windows 的 platform-tools。不要混用不同电脑或不同机型的固件目录。

## 第二步：下载源码，设置当前终端

下面的构建和提取命令都在 **Bash** 中运行。第一次下载源码时执行：

```bash
git clone --branch raphael-bringup \
  https://github.com/Helium-Studio/hackios-xnu-kernel.git hakios-raphael
cd hakios-raphael
```

此后除非特别说明，所有命令都在这个仓库目录内执行。**每次打开新 Bash 终端，都要先进入该目录，再执行以下设置：**

```bash
export THEOS="$HOME/theos"
export XNU_SRC="$PWD/xnu-src/xnu-8796.121.2-raphael"
mkdir -p out/user-bin
export PATH="$PWD/out/user-bin:$PWD/xnu-deps/host/bin:$PATH"
```

下载脚本要求名为 `7z` 的命令，且版本至少为 23。Ubuntu 的新版本通常叫 `7zz`，可这样设置兼容名称：

```bash
if command -v 7zz >/dev/null; then
  ln -sf "$(command -v 7zz)" out/user-bin/7z
fi
7z i
```

若显示旧版 p7zip 16.x，应先换成新版 7-Zip；不要继续处理 iOS 镜像。

### 仅 Windows + WSL2：让脚本使用 Windows 工具

原生 Linux 用户跳过本小节。下面假设 Windows 工具位于 `C:\platform-tools`；路径不同时，请修改两处 `/mnt/c/platform-tools/`。

将下面整段复制到仓库目录的 Bash 终端。它只在本机生成两个小启动脚本：设备通信交给 Windows，上传、下载文件时自动转换路径。

```bash
cat > out/user-bin/fastboot <<'SH'
#!/bin/bash
set -e
args=("$@")
case "${args[0]:-}" in
  boot|stage|get_staged) args[1]=$(wslpath -w "${args[1]}") ;;
esac
exec /mnt/c/platform-tools/fastboot.exe "${args[@]}"
SH

cat > out/user-bin/adb <<'SH'
#!/bin/bash
set -e
args=("$@")
if [ "${args[0]:-}" = pull ]; then
  [ "${#args[@]}" -eq 3 ] || { echo '本文的 adb pull 用法：adb pull 手机路径 电脑路径' >&2; exit 2; }
  args[2]=$(wslpath -w "${args[2]}")
fi
exec /mnt/c/platform-tools/adb.exe "${args[@]}"
SH

chmod +x out/user-bin/adb out/user-bin/fastboot
command -v adb
command -v fastboot
adb version
fastboot --version
```

`command -v` 应指向仓库的 `out/user-bin/`，版本输出应来自 Windows platform-tools。后文仍写 `adb`、`fastboot`、`./xl`，但 USB 操作和临时启动实际由 Windows 工具完成。以上脚本只处理本文需要的文件路径用法，不是完整的 adb / fastboot 替代品。

## 第三步：准备本机 GPU / Wi-Fi 固件

**这一节在手机原有 Android 或可用的 Android Recovery 中完成，不是在 Bootloader 中完成。** Android 需要打开 USB 调试，并在手机上允许电脑连接。Recovery 需要支持 adb；若文件未挂载，先以只读方式挂载本机 Vendor / Modem，再确认下面路径存在。

先检查连接和机型：

```bash
adb devices
adb shell getprop ro.product.device
adb shell getprop ro.boot.hwc
```

Android 下应确认设备代号为 `raphael`。`ro.boot.hwc` 用来辅助核对区域，例如 `CN`；Recovery 中该属性可能为空，不能据此猜测区域。若显示 `unauthorized`，先在手机允许 USB 调试；若无设备，先检查线缆、驱动和权限。

下面只读取手机文件，不向手机写入。固件、NV 和生成的镜像只留在本机，不要上传 GitHub。**没有可读取的本机原系统或备份时，不要从其他手机借固件、NV 来凑齐文件。**

### 3.1 提取 GPU 固件：所有图形测试都需要

所需文件共六个，放入仓库的 `fw-gpu/`。这段命令会依次尝试两个常见的手机目录，找到后用 `adb pull` 复制到电脑：

```bash
mkdir -p fw-gpu
(
  set -e
  for name in a640_gmu.bin a630_sqe.fw a640_zap.mdt a640_zap.b00 a640_zap.b01 a640_zap.b02; do
    found=0
    for dir in /vendor/firmware /vendor/firmware_mnt/image; do
      if adb shell "test -f $dir/$name"; then
        adb pull "$dir/$name" "fw-gpu/$name"
        found=1
        break
      fi
    done
    [ "$found" = 1 ] || { echo "缺少 $name，请检查手机固件路径或 Recovery 挂载状态"; exit 1; }
    test -s "fw-gpu/$name"
  done
)
```

看到 `缺少`、`Permission denied` 或其他错误时，先解决问题，不要带着不完整的文件继续。GPU 需要的是 A640 固件，不能用 A642L 的 `a660_*` 文件代替。

**只测试桌面、GPU、触控和按键时，可以跳过 3.2～3.4；后面保持 `WIFI_ARGS='wifi=0'`。** Wi-Fi 不会仅凭 GPU 固件正常工作。

### 3.2 提取 Wi-Fi / MPSS 文件：测试无线时需要

raphael 的 Wi-Fi 依赖本机 Modem 固件。先把手机已挂载的固件目录复制到电脑，再只选需要的文件：

```bash
mkdir -p out/raphael/modem-source fw-raphael
adb pull /vendor/firmware_mnt/image out/raphael/modem-source/

# 手机目录 image 会复制为 out/raphael/modem-source/image。
export MPSS_FW="$PWD/fw-raphael"
cp out/raphael/modem-source/image/modem.mdt "$MPSS_FW/"
cp out/raphael/modem-source/image/modem.b[0-9][0-9] "$MPSS_FW/"
cp out/raphael/modem-source/image/wlanmdsp.mbn "$MPSS_FW/"
```

若手机上没有 `/vendor/firmware_mnt/image`，先检查 Modem 是否已挂载。不要将其他机型的固件目录当作替代品；也不要运行 POCO X5 Pro 的提取脚本。

再选择与本机匹配的 BDF（无线板级配置）。以下示例为已验证的 **CN** 设备：

```bash
export WIFI_BDF=bd_f11cn.bin
cp "out/raphael/modem-source/image/$WIFI_BDF" "$MPSS_FW/"
```

GLOBAL 设备对应文件为 `bd_f11gl.bin`，应在确认本机区域及原固件选择后，将上面的 `WIFI_BDF` 改为该文件名再执行。**不知道区域或找不到匹配文件时，先跳过 Wi-Fi，不要随意选择 `bdwlan.bin`。**

### 3.3 只读备份本机 NV：需要 Root 或支持 root adb 的 Recovery

Wi-Fi 初始化还需要四个本机 NV 分区的完整快照。普通未 Root 的 Android 通常不能读取；无需为了测试 GPU 而强行获取权限。没有读取权限时，可以先不测 Wi-Fi。

检查权限和分区路径：

```bash
adb shell id
adb shell ls -l /dev/block/bootdevice/by-name/modemst1 \
  /dev/block/bootdevice/by-name/modemst2 \
  /dev/block/bootdevice/by-name/fsg /dev/block/bootdevice/by-name/fsc
```

若 `id` 显示 `uid=0`，可以直接读；否则下面命令会调用本机 `su`，手机可能弹出授权提示。只有已 Root 的设备才使用这个分支。路径不存在时先停止，不能根据其他机型的分区号猜测设备路径。

**整段在 Bash 中运行，不要在旧版 PowerShell 中将二进制输出重定向到文件。** 命令中的 `cat` 只读取分区，`>` 后面是电脑文件，不是手机分区。

```bash
(
  set -e
  : "${MPSS_FW:?请先完成 3.2 节}"
  umask 077
  for part in modemst1 modemst2 fsg fsc; do
    if adb shell id | tr -d '\r' | grep -q 'uid=0'; then
      adb exec-out "cat /dev/block/bootdevice/by-name/$part" > "$MPSS_FW/nv-$part.tmp"
    else
      adb exec-out "su -c 'cat /dev/block/bootdevice/by-name/$part'" > "$MPSS_FW/nv-$part.tmp"
    fi
    # 当前驱动要求前三个完整分区为 8 MiB，fsc 为 256 KiB。
    expected=8388608
    [ "$part" != fsc ] || expected=262144
    actual=$(stat -c %s "$MPSS_FW/nv-$part.tmp")
    [ "$actual" -eq "$expected" ] || { echo "$part 大小不符：$actual，请停止并核对本机布局"; exit 1; }
    mv "$MPSS_FW/nv-$part.tmp" "$MPSS_FW/nv-$part"
  done
)
```

这四个文件属于本机私有数据。**大小不符时不要裁剪、补零、拿别人的文件替换，也不要把文件写回手机。** 保留原始读取结果并停止 Wi-Fi 准备，向维护者报告分区大小即可。

### 3.4 在电脑生成两个辅助文件，并检查输入

这两个文件不是从手机提取的固件：`firmware-5.bin` 是 ath10k 使用的接口描述，实际 WLAN 程序仍是刚才提取的 `wlanmdsp.mbn`；`0-rmtfs-ram` 是运行时所需的空白内存预留文件。下面配置与当前已验证的驱动接口一致。

```bash
python3 - <<'PYTHON'
import os
import struct
from pathlib import Path

folder = Path(os.environ['MPSS_FW'])
def entry(kind, data):
    return struct.pack('<II', kind, len(data)) + data + bytes(-len(data) % 4)

header = b'QCA-ATH10K\0'.ljust(12, b'\0')
metadata = header + entry(1, struct.pack('<I', 0x5bbee4a4))
metadata += entry(2, bytes.fromhex('40 00 0c'))
metadata += entry(5, struct.pack('<I', 4))
metadata += entry(6, struct.pack('<I', 3))
(folder / 'firmware-5.bin').write_bytes(metadata)
(folder / '0-rmtfs-ram').write_bytes(bytes(0x310000))

required = ['modem.mdt', 'wlanmdsp.mbn', os.environ['WIFI_BDF'],
            'nv-modemst1', 'nv-modemst2', 'nv-fsg', 'nv-fsc',
            'firmware-5.bin', '0-rmtfs-ram']
assert list(folder.glob('modem.b[0-9][0-9]')), '缺少 modem 分段文件'
for name in required:
    assert (folder / name).is_file() and (folder / name).stat().st_size, '缺少 ' + name
print('Wi-Fi 输入文件已齐备；这不代表手机无线已经验证通过。')
PYTHON
```

文件齐备后，`fw-raphael/` 应包含 `modem.mdt`、所有提取到的 `modem.bNN`、`wlanmdsp.mbn`、所选 BDF、四个 `nv-*` 文件及两个辅助文件。后面的镜像构建会通过 `MPSS_FW` 把它们打包进去；只复制到电脑而不重新构建镜像，不会生效。

## 第四步：从源码构建内核

### 4.1 检查 Theos 和 SDK

回到仓库根目录，确认工具链和 **iPhoneOS 16.5 SDK** 存在：

```bash
test -x "$THEOS/toolchain/linux/iphone/bin/ld" && echo 'Theos linker: OK'
test -f "$THEOS/sdks/iPhoneOS16.5.sdk/SDKSettings.plist" && echo 'iPhoneOS 16.5 SDK: OK'
```

两条都应显示 `OK`。如果缺少 linker，先完成 Theos 安装；如果仅缺少 SDK，可以从 [Theos SDK 仓库](https://github.com/theos/sdks/tree/master/iPhoneOS16.5.sdk) 取到完整的 `iPhoneOS16.5.sdk` 目录。首次下载示例：

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/theos/sdks.git out/theos-sdks
git -C out/theos-sdks sparse-checkout set iPhoneOS16.5.sdk
mkdir -p "$THEOS/sdks"
cp -a out/theos-sdks/iPhoneOS16.5.sdk "$THEOS/sdks/"
```

请使用自己有权使用的 SDK。不要将其他版本 SDK 改名为 16.5；也不要把 Theos 的 Darwin `ld` 加到宿主 PATH 最前面。

### 4.2 下载内核源码、安装依赖、编译

第一次执行下面三条命令，依次等待每一条结束。下载和编译过程可能需要较长时间。

```bash
xnu/apply.sh "$XNU_SRC"
xnu-deps/setup.sh
devices/raphael/build.sh kernel
```

- 第一条下载固定版本的 Apple 开源 XNU，并应用本分支补丁。
- 第二条准备构建内核所需的依赖和工具。
- 第三条构建 raphael 的 ath10k 对象，再链接内核。

如果第一条提示目录已经存在，不要删除已有工作：只有首次创建源码树需要执行它。更新代码后，旧构建树不会自动套用新 overlay；请按 [开发构建说明](xnu/README.md) 同步，或使用新的 `XNU_SRC` 路径重新创建。

完成后检查内核产物：

```bash
export XL_KERNEL="$XNU_SRC/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837"
ls -lh "$XL_KERNEL"
```

文件必须存在且是本轮生成的。构建报错时先解决报错，不要让启动脚本偷偷退回通用 `prebuilt/`。文件名中的 `bcm2837` 是构建目标名，不表示手机型号。

## 第五步：构建完整 RAM 用户态

这一节在电脑上生成 iOS 的测试文件，不会向手机分区部署系统。UEFI 和 loader 已包含在 Release 镜像内，**不用自行编译 UEFI 或 loader**。

### 5.1 下载并解包 iOS 输入

```bash
sysimage/fetch.sh
```

脚本获取 iOS 16.5 `20F66` 所需文件，放在本地 `sysimage/`。需要网络和较多磁盘空间，请等待下载及解包结束；不要用空文件跳过失败步骤。

### 5.2 决定是否打包 Wi-Fi，再构建

如果完成了 3.2～3.4，且仍在同一个终端中，保留 `MPSS_FW` 和 `WIFI_BDF`。如果重新开过终端，按自己的区域重新设置，例如 CN：

```bash
# 仅在已完成无线文件准备时执行。
export MPSS_FW="$PWD/fw-raphael"
export WIFI_BDF=bd_f11cn.bin
```

如果这次不测 Wi-Fi，改为执行：

```bash
unset MPSS_FW WIFI_BDF
```

然后构建用户态及镜像：

```bash
FLASHBOOT=prepared SYSTEM=1 devices/raphael/build.sh images
```

构建时会使用前面准备的 `fw-gpu/`，并在设置了 `MPSS_FW` 时打包无线输入。结束后应能看到三个文件：

```bash
ls -lh userland/root.apfs userland/flashboot.apfs userland/system.apfs
```

| 文件 | 可以怎样理解 |
|---|---|
| `root.apfs` | 本项目的启动工具、init 和 GLES 图形库 |
| `flashboot.apfs` | RAM 启动环境；启用无线时还包含本机私有无线输入 |
| `system.apfs` | 本轮生成的 iOS 系统文件 |

这里的 `FLASHBOOT=prepared` 是构建选项，**不是刷写 userdata 的命令**。

### 5.3 合并成要上传的大镜像

```bash
mkdir -p out/raphael
cat userland/flashboot.apfs userland/system.apfs \
  > out/raphael/ram-resident.apfs
ls -lh out/raphael/ram-resident.apfs
```

合并顺序固定：先 `flashboot.apfs`，后 `system.apfs`。后文的 `root_apfs=md0,c=1` 表示从第二个 APFS 容器读取系统，正好对应这个顺序。最近实测合并镜像约 2.60 GB，大小会随输入变化。

## 第六步：下载 Release 中的 UEFI

打开 [raphael UEFI 发布页](https://github.com/Helium-Studio/hackios-xnu-kernel/releases/tag/raphael-uefi)，使用附件 **`raphael-uefi.img`**。无需准备 XBL、DTB 或 Mu-Silicium。

在仓库根目录下载并校验：

```bash
mkdir -p out/raphael/uefi
curl --fail --location \
  https://github.com/Helium-Studio/hackios-xnu-kernel/releases/download/raphael-uefi/raphael-uefi.img \
  --output out/raphael/uefi/raphael-uefi.img
printf '%s  %s\n' \
  1b672ca1c990d85014274388405b156aaea1ce407a931d3f75f49fa11db5781c \
  out/raphael/uefi/raphael-uefi.img | sha256sum --check -
```

必须显示 `OK`；不一致时不要启动。这里直接使用固定哈希校验，避免附件重命名后旧校验清单里的文件名造成误报。

该附件是已验证 DEBUG r5 的原样归档，只更改发布标签和附件名称，不是由发布标签源码重新编译的文件。它只提供启动环境，**不能单独启动完整 iOS**。

## 第七步：临时启动并上传 RAM 镜像

### 7.1 进入 Bootloader，启动 UEFI

固件提取完成、上述文件准备齐后，再让手机进入 Bootloader。通常可通过电源键＋音量下进入；只连接这一台测试机。

```bash
export BOOT_IMAGE="$PWD/out/raphael/uefi/raphael-uefi.img"
export XL_KERNEL="$XNU_SRC/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837"
export XL_RAMDISK="$PWD/userland/root.apfs"

fastboot devices
fastboot boot "$BOOT_IMAGE"
```

原生 Linux 使用 Linux fastboot；按前文配置的 WSL2 使用 Windows fastboot。两种环境都不刷写 Boot 分区。

等手机重新枚举后检查：

```bash
fastboot getvar product
./xl state
```

应分别看到 `xnuloader` 和 `loader`。`Booting OKAY` 只表示启动命令被接受；如果回到原系统、持续黑屏或没有 loader USB，先停止并检查，不继续上传。

### 7.2 上传大镜像

```bash
./xl ramdisk out/raphael/ram-resident.apfs
```

等待出现上传完成信息。最近实测约 133 秒，不同 USB 环境可能更慢。这一步只上传到 RAM。手机冷重启或换了 loader 会话，就要重新上传。

### 7.3 选择 Wi-Fi，然后开始运行

只测试基本功能时，执行第一段即可。只有完成无线文件准备并已打包进镜像，才执行第二段来启用 Wi-Fi：

```bash
WIFI_ARGS='wifi=0'
```

```bash
# 可选：需要已核对并设置 WIFI_BDF，不能按网络名称猜测 BDF。
: "${WIFI_BDF:?请先完成无线固件准备，或跳过本段保持 wifi=0}"
WIFI_ARGS="wifi_step=15 wifi_lx=2 wifi_ba=1 wifi_wide=1 wifi_new=99 wifi_pause=0 wifi_ask=1 wifi_bdf=$WIFI_BDF wifi_smmu=2 wifi_keep=1 wifi_wait=10 wifi_listen=15"
```

最后启动 10 分钟测试：

```bash
export XL_SECS=600
export XL_FOLLOW=15
export XL_FOLLOW_KEEP=1
export XL_CMDLINE="gic_timer_irq=19 bootcpu=7 cpus=8 touchscreen=1 buttons=1 cpufreq=1 gpu=1 fb_scan=1 modem=0 adsp=0 ufs=0 ufs_write=0 var_store=0 root_apfs=md0,c=1 $WIFI_ARGS"
./xl run
```

保持该终端运行，日志保存在电脑的 `logs/`。开始时会做短时 CPU / GLES 检查，可能出现三角形，完成后再评估界面。没有自动手势；Wi-Fi 密码只在手机设置里输入。

以上参数关闭 UFS、分区写入和数据保存，A640 默认使用 585 MHz。最近实测曾使用 765 MHz 对照档；首次体验不需要自行添加超频参数。

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
| fastboot 没有设备 | 原生 Linux 检查 USB 权限；WSL2 检查 Windows 驱动、platform-tools 路径及 out/user-bin 脚本是否生效 |
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

# raphael 移植与 iOS 用户态启动

目标是 Redmi K20 Pro / Snapdragon 855（SM8150）：先完成 UEFI 启动链，再在同一测试会话验证八核、iOS 锁屏、触控、按键和 GPU 实际渲染。编译成功、fastboot 返回 OKAY、屏幕亮起分别只证明对应的一步。

## 2026-10-27：统一 main，GLES-only

当前入口为 [devices/raphael/README.md](../devices/raphael/README.md)。上游已合并用户态，移除 Metal；按用户选择完整跟随。源码为 `hakios.*`、补丁 `xnu/hakios.patch`，运行路径 `/redwood`。以下日期章节是历史，不能直接运行其中的 common/、/hackios 或 Metal 命令。迁移、构建与验证详见 [基线分析](UPSTREAM-BASELINE-20261027.md)。

raphael 的 `fb_scan=1` 保留命令 TE 相位后端，位于 `hakios.display.c`；没有恢复旧视频后端。主机检查通过，本轮没有实机验收。最近旧版硬件反馈为基本流畅，但组件和 Safari 字体仍有渲染问题。

## 2026-10-25：切换上游 metal 基线

按用户要求，Wi-Fi 与配套私有 MPSS 打包逻辑先单独提交，再将内核和用户态分别 rebase 到上游 `metal`。UniXNU NativeMetal/NativeAdreno 整合已从当前工作树撤下并完整归档；当前使用上游 Mesa/AIR 前端。上游文件和接口现为 `hk_*`、`HKMetal`、`/hackios`，内核补丁为 `xnu/hackios.patch`。以下旧路径与测试结果属于历史，不是 rebase 后实机验收。

Wi-Fi 的当前结果与剩余问题见 [RAPHAEL-WIFI.md](RAPHAEL-WIFI.md)。当前用户测试流程与备份准备见根 [README.md](../README.md)；本节保留历史迁移记录。本轮没有重新部署或改写手机分区。

## Raphael 的 fb_scan=1

raphael 使用 DSI 命令模式，不能读取 redwood 视频模式的 `INTF_HSYNC_CTL`、`INTF_VSYNC_PERIOD` 或照搬其 GCC/DISPCC 偏移。当前 `hk_display.c` 在识别 raphael 后，改用 `hk_adreno.c` 中现有 page-flip 后端提供的 TE 只读相位。后端先检查寄存器时钟、tear-check 和外部 TE 是否开启，再读取 `INTF_TEAR_INT_COUNT_VAL` 的低 16 位并减去 `VSYNC_INIT_VAL`。

启动时最多用 150 ms 观察三个 TE 复位边沿，从实际时间与计数变化测量刷新周期及 tick 时长；不把固件的 `0xffff` tear height 当作帧高，也不依赖本机不递增的 frame counter。成功后，原 framebuffer 的模式发布和 CoreAnimation VSync 通知使用测量值。raphael 仍在离屏缓冲完成合成，再由原有 TE latch 确认 page flip；不使用视频模式的前台拷贝窗口，不读取并清除共用 IRQ。

`common/devices/raphael.conf` 已加入 `fb_scan=1`。关闭参数保持原计时通知；时钟、计数或校准异常也回退计时通知，TE page flip 自身的超时保护保持不变。主机回归 `tools/check-raphael-scan.py` 覆盖模拟 30/60/120 Hz、相位、停计数、掉时钟、非法周期和原视频后端；`tools/check-raphael-display.py` 覆盖 TE 读取不消费 latch 中断及既有翻转/超时恢复。ASan/UBSan 与新内核构建通过，日志在 `out/raphael/fb-scan/`。尚未实机验证刷新相位、视觉效果或性能，不声称低帧率已经解决。

## 第二阶段：壁纸、组件与存储（2026-10-23）

- 壁纸：`mkjobs.py --rest` 的环境变量循环覆盖了 plist 文件名，导致按需服务反复写入同一个文件。修正后 PosterBoard 等服务正常注册，用户确认壁纸完整。
- 触控：连续返回 loader 再启动时，GENI I²C 的空闲 RX FIFO 可能留下数据。初始化时仅清理空闲 sequencer 的残留，返回时停止事务并清理；忙事务不会被直接丢弃。用户确认触控和三个按键恢复。
- 组件与负一屏：RenderBox 的只读 Metal buffer 使用非 64 字节对齐的偏移，原桥接直接拒绝绘制。现在将该绑定的完整剩余范围复制到对齐的临时 SSBO，保留写缓冲的对齐检查。`logs/065008-run.log` 的 Metal 1×/2×/4× 回读通过，用户确认天气、日历内容正常、负一屏错色消失。无网络时天气显示无天气数据。
- UFS：loader 与原生控制器驱动已只读对照全部六个 LUN 的 GPT、固件和多个分区范围；30 个范围共 426446848 字节无差异。原生模式正常返回并恢复 UEFI transfer list。`tools/ufs-read.py` 可通过空闲 loader 的 `oem read-part` 提取本机固件，不修改手机。
- 性能：257/427 MHz 两轮相同自动手势均正常返回，提高 GPU 频率缩短了部分绘制/回读耗时，但仍有约 32–34 ms 的长帧。采样窗口不完全一致，不能据此声称稳定 60 fps 或给出精确提升比例；默认仍为 257 MHz。

持久化方案经用户确认：只接管 `userdata`，分区开头保存 2376 MiB 的 `system.apfs`，8–12 GiB 保存两个 2 GiB 的 `/private/var` 归档槽。保留 GPT、Boot 和其他分区，UEFI 继续通过 `fastboot boot` 临时启动；这不是脱离宿主机的自动开机方案。`FLASHBOOT=prepared` 生成 4 MiB 的引导容器，`root_apfs=ufs_userdata` 让 init 直接挂载已准备好的系统卷，`var_store=1 ufs_write=1` 启用正常结束时保存。突然断电只保证上一个成功提交的归档仍可恢复，不保证本轮尚未保存的数据。

写权限只对实测手机的 userdata GUID、LBA、容量和单元号开放；其他手机必须重新只读核对，不能照搬这些身份常量。系统前 2042368 个 4096 字节块不可由运行中的 XNU 写入。主机边界检查：`tools/check-loader-store.py`、`tools/check-loader-read.py`；用户态与 Mesa 回归：`userland/check-mkjobs.py`、`tools/air/bufferoffsetcheck.py`。

**固化实测**：fastboot 的 19 段 userdata 写入均成功；loader 完整读回 2492227584 字节，SHA-256 与主机镜像一致（`5d926771c0ee365d4f8100c1def1a6c0770a2e75f4895286e68d4c693e1370ed`）。`logs/070428-run.log` 确认根文件系统来自 `/dev/ufs_userdata`，39 项 init 检查无失败，用户确认壁纸、组件、触控正常；运行结束保存 generation 1（15601 条目、132098704 字节），34 次写入全部读回一致，用时 7420 ms，正常返回 loader。`logs/070750-run.log.live` 的下一次启动成功校验并恢复该归档，保存于上一轮的 29 字节标记原样出现，再追加为 58 字节；证明跨 XNU 启动保存和恢复确实访问了 userdata。

部署完成后，从 Bootloader 运行以下命令；这几行本身不会重新刷写系统镜像。`bootcpu=7` 留下 CPU0 服务 UEFI 写请求：

```sh
. common/lib.sh; load_device raphael
./xl enter
./xl ramdisk userland/flashboot.apfs
XL_SECS=300 XL_CMDLINE='gic_timer_irq=19 bootcpu=7 cpus=8 touchscreen=1 buttons=1 cpufreq=1 gpu=1 metal=1 metal_profile=1 wifi=0 adsp=0 ufs=2 ufs_native=1 ufs_write=1 var_store=1 root_apfs=ufs_userdata' ./xl run
```

先使用 `common/build.sh raphael FLASHBOOT=prepared` 构建配套镜像。运行时上传的 `root.apfs` 应与当前内核、Mesa 配套；更新这个小镜像不需要重新写 system.apfs。开发测试记录和本机身份位于忽略的 `out/raphael/userdata-plan.json`。

早期 Wi-Fi 状态（固件初始化阶段；后续联网结果见 [RAPHAEL-WIFI.md](RAPHAEL-WIFI.md)）：raphael 使用 WCN399x / ICNSS、MPSS（PAS 4）和 ath10k SNOC，原项目的 WCN6750 / WPSS / ath11k 路径不能直接运行。`zundamon-miui-5.4` 的 `raphael_defconfig` 实际启用 `CONFIG_ICNSS=y`，控制顺序应优先参考 `drivers/soc/qcom/{icnss,icnss_qmi}.c`；同树 `icnss2` 的其他芯片分支不能直接套用。硬件定义参考 `qcacld-3.0`、`qca-wifi-host-cmn` 和 `fw-api`。

已实测通过本机 modem 固件签名、150 MiB RAM 装载与读回、APCS 通知、SMEM 分配、MPSS 启停、GLINK 和 QRTR。APCS 的 AOP、SMP2P、GLINK 均使用 `0x17c0000c`，分别为 bit 0、14、12；QRTR node 0 是有效节点。RMTFS 使用只读提取的 modemst1/modemst2/fsg/fsc 快照，共享区在 MPSS 启动前授权，写请求只修改私有 RAM 副本。停止 MPSS 后归还共享区权限，测试不调用块设备写入。

TFTP 仅导出本机 `wlanmdsp.mbn`，并在 RAM 中处理固件启动必需的 `server_check.txt` 写入与读回；PD mapper 使用本机固件的服务映射。`logs/201513-run.log` 首次完成 4054436 字节 WLAN 固件传输并发现服务 `0x45`。后续多次运行正常返回 loader；`logs/205023-run.log` 确认 ICNSS 注册、MSA 两区权限、capability、五段 BDF 和校准报告均成功，四路 PMIC 电源实际开启，电压分别为 752/1800/1304/3312 mV。现在分别注册 KNEL 和 DMON 两个客户端，BDF 的 file_id/type 以及校准报告与本机 cnss-daemon 一致；DMS `0x5c` 返回的本机 WLAN MAC 经校验后用 WLFW `0x33` 提交，日志不输出 MAC。

`logs/081950-run.log` 已确认未收到 FW-ready 的直接现象：校准握手后 SMP2P `wlan` bit 1 置位，随后 WLAN PD DOWN/UP 并重新发布服务。这是固件 early crash，不能再只按 ready 超时处理。QRTR DEL_CLIENT 现在正确撤回其服务，避免继续使用失效端点；PDR 状态通知收到有效 ACK，当前测试能够返回 loader。早先一次 PDR 测试未返回的原因仍未证明。

2026-10-24 核对本机 cnss-daemon 的机型选择逻辑后，修正了一个文件选择错误：QMI board ID 缺省为 `0xff` 不代表这台 Xiaomi 应使用通用 `bdwlan.bin`。本机 Recovery FDT 中 `hwversion=4.9.0、hwc=CN`，原生 daemon 选择 `bd_f11cn.bin`；GLOBAL 变体选择 `bd_f11gl.bin`。诊断现在要求显式 `wifi_bdf=bd_f11cn.bin` 或 `bd_f11gl.bin`，拒绝缺省值和其他路径，固件文件从本机 modem 只读提取。`logs/085338-run.log` 确认 CN 文件下载成功，但仍发生 early crash，因此这不是完整修复。选择依据和文件哈希保存在忽略的 `out/raphael/wifi-bdf-selection.json`。

`logs/083635-run.log` 验证原生 SID `0x640`、mask 1 的 SMMU 上下文和 `0x8bc00000 + 0x180000` MSA 恒等映射均成功写入、读回，并在 MPSS 停止后恢复旧配置；但固件仍 early crash，不能把 SMMU 初始化等同于修复。PAS 停止并归还 HLOS 权限后检查 MSA，头部为零，未找到可用错误字符串。`wifi_diag=1` 用本机 diagfwd_socket 协议发布 MPSS 控制/数据服务，尝试获取更多崩溃信息；日志有长度和数量限制。

`logs/084857-run.log` 的 LDO 高功耗模式对照也未改变崩溃，诊断选项已移除，恢复原生默认模式。`logs/085918-run.log` 中 MPSS DIAG 功能握手、根进程日志 ID、掩码和实时模式请求已发送成功，但尚无 WLAN 错误正文；SMEM 611 在 WLAN 启动前后均为 4096 字节且 SHA256 完全一致，只包含旧的 APPS force stop，不能作为本次崩溃原因。曾在忽略的 `out/raphael/native-wifi/` 准备并发送 Linux RAM 对照镜像，但没有收到 ADB 日志，未证明内核启动。按用户要求已停止 Linux 实机测试，后续仅使用 UEFI/XNU；该私有镜像含固件、NV 和 Android 文件，禁止发布。

2026-10-24 按本机 6.12 分支四个提交核对并修复供电和时钟：

| 提交 | 对 XNU 移植的作用 |
| --- | --- |
| `4c37abf82a78` | 确认 ICNSS/MPSS 控制链、MSA 权限、SID `0x640`、12 路 level-high CE 中断；不同时启动 ath10k 和 qcacld 两个 WLAN 主机。XNU 已有的 ICNSS 控制链与该硬件定义一致。 |
| `f48d0a8dfc4e` | 增加 PM8150L L10C 的 CH1 供电：3312 mV、HPM，PMIC 外设 `0x549`；与现有四路电源共同管理，关闭时逆序撤销。该提交单独未解决 Linux 固件崩溃。 |
| `ad7584e9454f` | 确认 6.12 使用 ICNSS + qcacld，不能把其配置误当作 ath10k 已工作的证据；Kconfig 本身不适用于 XNU。 |
| `0ad06c1c3f64` | WLAN 上电后，通过现有 AOSS QMP 发送 `{class: clock, res: qdss, val: 1}`。固件初始化会解锁并读取 CoreSight 寄存器，因此在 MPSS 关闭前保持 QDSS 时钟；随后发送 `val: 0`。失败的时钟投票也保留清理记录。 |

`logs/132122-run.log` 和 `logs/132219-run.log` 连续两轮 XNU RAM 真机测试均收到 `0x21 FW_READY`，报告 `ICNSS WLAN firmware READY; MSA indication received`，step 14 完成，未再出现此前的 WLAN early crash。首轮在 BDF/校准完成后约 4.6 秒 ready；L10C 实测 3312 mV、mode 7，其余电源读回正常。两轮均正常关闭 MPSS、撤销 QDSS/五路电源、归还 MSA/RMTFS 权限并返回 loader；RMTFS 均读取 6144 扇区、写入 0 扇区，UFS 和分区写入始终禁用。结果只证明固件初始化已打通；SNOC CE/HTC/WMI 主机数据通路、扫描、关联及网络收发仍未接通。

诊断入口保留 `wifi_step=1` 的只读 SMEM 检查及 `wifi_step=6..14` 的分步启动；`wifi_ask=1` 运行上述 MPSS/WLAN 控制链。`tools/test-raphael-wifi.sh` 检查内核和 RAM 固件镜像是否过期，并以 `ufs=0 ufs_write=0` 进行有时限的真机测试。可传入已验证的启动镜像；`--loader-only <image>` 只验证 UEFI/loader USB，不上传 XNU。2026-10-24 的一次 RELEASE 冷启动回退 Boot，当前诊断改用已验证的 `out/raphael/boot-debug-r5.img`，其 loader USB 返回版本 0.5。该早期阶段尚不支持扫描、连接或联网；后续已验证 WPA2/WPA3 网页访问，当前限制见 [RAPHAEL-WIFI.md](RAPHAEL-WIFI.md)。固件、NV 快照、Apple 文件、反汇编和原始分区镜像均保留在忽略的本地输出中，禁止发布。

新增主机检查覆盖实际源码中的 MDT、SMEM、doorbell、RPMh、电源、共享区授权、RMTFS、TFTP、PD mapper、PDR、QRTR、ICNSS、DMS、DIAG、MSA 诊断、SMEM 微型转储和 SMMU：`tools/check-wifi-{mdt,smem,doorbell,proxy,memory,rmtfs,tftp,pd,pdr,qrtr,icnss,dms,diag,dump,microdump,smmu}.py`。这些检查不能代替芯片初始化及实际扫描、关联、数据收发测试。

## 当前源码与设备树

当前真机已通过 UEFI → loader USB → XNU → Apple launchd → SpringBoard；用户确认触控和三个按键有效。
2026-10-23 的最终合并复测 `logs/011423-run.log` 使用 RELEASE UEFI、无 `-v` 的 graphics mode 和 quiet 用户态，确认 8 个 active CPU，8 线程实际并行约 6.4 个处理器（487 ms 墙钟时间内使用 3131 ms CPU 时间）。
A640 全部初始化步骤、TrustZone zap shader 认证、`freedreno / FD640 / OpenGL ES 3.2`、1080×2340 三角形回读无错误（26% 覆盖率）、CoreAnimation accelerated renderer 与连续 GPU 提交均通过；三角形绘制 42 ms、回读 25 ms。用户确认界面正常、没有日志文字、触控和三个按键有效。120 秒会话正常返回 loader（`returned 720810 0`），shader 卸载成功，USB `result` / `version: 0.5` 查询恢复响应。这是第一阶段的启动基线；后续 GPU/Metal 与调频修复的进度见下节。上述基线不包含 Metal 应用或长期稳定性。

## GPU / Metal 与 CPU 调频修复（2026-10-23）

用户报告主屏滑动、控制中心和应用切换撕裂、卡顿。本轮修复涉及内核、loader、Mesa 和用户态驱动，必须配套构建；raphael profile 已默认启用 `cpufreq=1 metal=1 metal_profile=1`，保持 quiet 用户态。`prebuilt/mach.development.bcm2837` 与 `prebuilt/loader.efi` 已同步为本轮实测产物，用户态配套提交为 `e41cc8a`。Mesa 和 RedwoodMetal 仍需从源码构建，不能只更新内核或依赖旧用户态预编译库。

发现和处理的具体问题：

- **CPU**：SM8150 使用 OSM，而原驱动使用 SM7325 的 EPSS 地址。现在读取三个 OSM 域的硬件 LUT（`0x18323000 / 0x18325800 / 0x18327800`，LUT `+0x110`、32 字节一行，性能请求 `+0x920`），只使用非 boost 行。真机上限分别为 1785、2419、2841 MHz。每 50 ms 采样负载，活动时使用高档，连续 200 ms 空闲后使用低档；触控立即请求 200 ms 高档。返回 loader 时恢复固件原始请求。保留 loader 核心的诊断模式下，共用时钟域不能按 XNU 的空闲统计降频；完全不归 XNU 管理的域不改动。
- **显示**：原实现直接覆写正在扫描的 framebuffer，且 SwapWait 不等待复制完成。现在在 DT 的 36 MiB 显示保留区内使用三个缓冲（`0x9c000000 / 0x9ca00000 / 0x9d400000`），完成整帧后通过 VIG0/CTL0 flush 和 INTF1 TE 中断状态确认切换。固件开启 autorefresh 时不发送 CTL_START。只有局部更新保留前帧，整屏更新省去额外的 10 MiB 读写；SwapWait 在复制、切换完成后释放生产者。GPU fence 超时会丢帧，不能显示尚未完成的表面。大帧缓冲使用 XNU 的大映射接口，避免耗尽只有 8 MiB 的永久 I/O 子映射。
- **Metal**：现有纹理模板缺少 `nr_storage_samples`，使 freedreno 拒绝多重采样 resolve。已配齐该字段，增加颜色附件的 GPU resolve，补上 viewport 和 scissor，并修复同一 render pass 每次 draw 都重复执行 LoadActionClear 的问题。采样能力来自 Mesa 查询。动态矩形使用独立入口，保留旧 `rwa_render_draw` ABI；旧库遇到新矩形状态会明确报错。
- **诊断**：loader 截图读取当前 front buffer；GPU 温度读取改为 raphael 的 TSENS0/15、TSENS1/11。屏幕仍使用 graphics mode，USB 日志保留。

已有真机证据：

| 检查 | 结果 |
|---|---|
| OSM / CPU | `logs/012710-run.log`：单线程 270 ms（原基线 748 ms）；另一次合并运行测得 195 ms。这些是启动环境中的样本，不是受控持续性能测试 |
| GLES / A640 | 同轮 1080×2340 三角形绘制 17 ms、回读 18 ms，覆盖率 26%；持续 FD640 提交和 CoreAnimation 绘制 |
| Metal 基础 | 独立片元绘制、Depth32Float 比较/写入、UInt16/UInt32 索引绘制均通过 |
| Metal 矩形 / resolve | `logs/020002-run.log`：1×、2×、4× 均 0/256 错误像素，命令缓冲状态为 Completed；同时验证局部 viewport、scissor 和两次 draw 的 LoadAction |
| DPU / 返回 | 同轮三个缓冲依次 latch，flush 清零；180 秒运行正常返回，`returned 1441823 0` |
| 主机检查 | `tools/check-raphael-cpufreq.py`、`tools/check-raphael-display.py`、`tools/air/rendercheck.py` 使用实际函数做 ASan/UBSan 检查，包括 LUT、缓冲轮换/超时回退、ABI 和 resolve 参数校验 |

**早期合并测试与后续复测**：`logs/020405-run.log.live*` 的合并手势/延迟跟踪运行在解锁后失去响应，最后存在大量 `tl: a` 主循环跟踪，宿主机随后仅看到 USB 描述符请求失败；没有保存到 panic。日志量与挂起的因果关系尚未确认。随后修正固件共用小核簇被降到 300 MHz 的问题，并关闭大量 SpringBoard 主循环跟踪。`logs/054953-run.log` 的 300 秒复测已正常返回（`returned 1441823 0`），USB 保持响应，无 GPU fence 超时或显示切换失败。1×/2×/4× 均 0/256 错误像素；2×、4× 边缘平均分别检测到 6、8 个部分覆盖像素。CPU 单线程 223 ms、七线程 409 ms；GPU 温度样本约 51～58 ℃。用户完成主屏、控制中心与应用切换测试，确认“没有撕裂，流畅度明显改善”。这证明当前复现场景改善，不代表锁定 60 fps。

**完整八核复测**：`logs/055537-run.log` 使用默认 quiet profile，未指定 `bootcpu` 或触控延迟跟踪，240 秒后正常返回（`returned 1092705 0`），USB `version: 0.5` 恢复响应。延迟 CPU 测试确认 8 个 active CPU，单线程 227 ms，八线程 397 ms、处理器时间 1865 ms；启动早期的 5 核采样不代表最终 CPU 数。小核簇实际在 300/1785 MHz 间切换，大核与超大核在当前界面负载下使用高档。Metal 1×/2×/4× 均 0/256 错误像素，2×/4× 边缘平均分别为 6/8 个部分覆盖像素；片元、深度比较和索引绘制检查通过。1080×2340 GLES 三角形绘制 16 ms、回读 18 ms、覆盖率 26%。三个显示缓冲完成切换，自动主屏/控制中心/应用切换操作完成，未见 GPU fence 或显示切换超时、kernel panic。

本轮用户态入口是 `userland/rc.launchd.metal`：先发布 Metal 设备属性，再启动 Apple launchd。需要 `metal=1 metal_profile=1` 和匹配的 `libredwoodair` / `RedwoodMetal`；backboardd 继续使用项目已有的 GLES CoreAnimation 路径，其他进程可发现 Metal。`metal_render_test` 检查整帧结果、裁剪、2×/4× resolve 和分数像素边缘的采样平均。Metal 的 heaps、blit encoder、跨队列 events 等上游尚未实现的接口仍不完整，不能把本轮 A640 修复表述为完整 Metal API 支持。OSM 当前也是两档负载策略，尚未实现完整的热管理和能耗策略。

`xnu-build.sh` 默认使用 XNU 的 `build` 目标，生成可启动 Mach-O 并完成所需 dSYM/strip 步骤，避免额外 KDK 符号集被项目尚未实现的 DriverKit RPC 导出阻断；仍可显式指定其他 make 目标。本轮默认构建成功退出，产物 SHA256 与真机测试内核一致。

## 设备树来源

设备树来自 `$HOME/kernel/zundamon_raphael` 当前的 `zundamon-miui-5.4` 分支（`c50effadd8f6c`）；不切换、不修改该内核树。运行：

```sh
python3 tools/build-raphael-dtb.py
```

输出 `out/raphael/raphael.dtb`、反编译的 `.dts`、源码位置/提交 `.source` 和编译警告 `.build.log`。基础树是 `sm8150-v2.dts`，板级树是 `raphael-sm8150-overlay.dts`。脚本把 overlay 的根节点内容也转换为根路径 fragment，再应用 overlay；否则 libfdt 合并后会保留基础树的型号和 board-id。源树中的旧绑定警告保留在日志，不能据此宣称通过现代 DT schema 检查。

已核对的数据：

| 项目 | raphael |
|---|---|
| GICD / GICR | `0x17a00000` / `0x17a60000` |
| CPU | 8 核；MPIDR `0x000..0x700`，步长 `0x100`；小核 mask `0x0f` |
| PSCI | SMC |
| 虚拟定时器 | PPI 19（Linux 中断描述第三项 `<1 3 flags>`，对应 INTID `16 + 3`），profile 设置 `gic_timer_irq=19` |
| Framebuffer | `0x9c000000`，1080 × 2340，BGRA，stride 4320 |
| 显示保留区 | `0x9c000000 + 0x02400000`，来自 DT 和本机 XBL |
| UEFI FD | `0x9fc00000 + 0x00300000`，来自本机 XBL `uefiplat.cfg` |
| 触控 | QUPv3 SE19 的 I²C，地址 `0x5d`；GT9886 配置文件，DT compatible 为 `goodix,gt9889` |
| GPU | Adreno 640 v2，chip ID `0x06040001` |

Linux DTB 交给 Android Bootloader/UEFI。XNU 接收的是 `xnuloader` 另外生成的 Apple Device Tree；它保留与所选 iOS 用户态一致的 iPhone 身份，并写入实际 CPU、GIC、内存和显示信息。因此替换 Linux DTB 不会自动替换 XNU 驱动。

## UEFI

`uefi/files/Platforms/Xiaomi/raphaelPkg` 以同 SoC 的 Mu-Silicium `cepheusPkg` 为结构参考；寄存器和固定缓冲区来自本机 XBL，RAM 分配同时核对本机 Recovery FDT，保留 64 MiB 的 XNU payload 区域。XBL 原来的 28 MiB DXE 堆与实际 CDSP 保留区重叠，且真机报 Out of Resources；已迁到 `0xc0000000 + 0x10000000`（256 MiB），其余 RAM 由现有 RamManagerDxe 按固件 RAM 分区补齐。栈使用同平台的 `0x9ffb0000 + 0x20000`，避开 USB UCSI 临时区。固定基线见 `uefi/BASE`。显示使用 SimpleFb 保留 ABL 配置，不加载其他机型的面板初始化数据。`xnuloader` 在检测到 raphael 命令模式显示已开启时启用 PP 自动刷新；能否持续更新仍需真机检查。

本机的 `xbl`、`xbl_config` 和 Recovery FDT 保存在 `out/raphael/firmware/`，导出时校验了设备端与主机 SHA256。它们及提取后的驱动不提交到仓库。平台驱动必须来自这些本机文件；`tools/extract-raphael-uefi.py` 从本机 XBL 提取 78 个 AArch64 模块，并按 `uefi/raphael-firmware-patches.json` 的完整 SHA256 和原字节验证 DAL、USB、按键修补。参考是 `Project-Silicium/Device-Binaries` 的 cepheus `a1501e0`：模块代码已逐字节核对一致，设备名字符串保持 raphael；其他版本 XBL 会拒绝，不能直接套用。解析器使用 `out/host-python` 中的 `uefi_firmware` 1.16。

BootShim、UEFI 的 `XnuLoader.h`、`xnuloader/loader.c` 和打包器必须使用相同的 `PAYLOAD_BASE`，目前统一为 `0xf0000000`。改变地址时四处都要改，并检查固件内存映射。

`common/devices/raphael.conf` 把配置传给构建及运行链。缺少对应 UEFI 时，`mkxnuimg.py` 拒绝退回 redwood 的预编译固件。`xl enter` 会重新打包镜像，因此运行链也必须继承设备配置，不能只确认 `out/raphael-boot.img` 的文件名。

UEFI 编译时的 `XNU_NO_DISK_LOG` 关闭诊断阶段的磁盘日志；loader 的持久日志只对原有 redwood 平台启用。raphael 使用 USB 取日志。RAM 启动期间不启用 UFS 写入或 `/var` 持久化。

## UEFI 完整性与真机状态（2026-10-22）

已核对固定 Mu 基线、BootShim/XNUP 补丁、平台源文件和本机固件：78 个模块的完整 SHA256 匹配；当前配置的 86 处二进制引用（含重复引用）均存在，未启用的自定义面板分支不计入依赖。审计记录为 `out/raphael/uefi-source-audit.json`。RELEASE 与 DEBUG 均完成构建，构建器验证 48 个 EFI 镜像。BrotliCompress 的源码子模块已恢复到 Mu_Basecore 固定的 `e230f47`；`uefi/export.sh` 已补上 raphael 平台及配置的导出，避免再次导出时丢失适配。

这证明本次 UEFI 构建所需文件齐全，不等于所有高通驱动都公开了源码：78 个本机模块仍是闭源 PE/TE 二进制，仓库保留提取与校验步骤。可选的未启用组件及整个 Mu 工程的所有测试子模块不在本次完整性结论内；运行时仍需逐步验证。最初两次 RELEASE 临时启动均只得到 fastboot 的 Sending/Booting OKAY，手机黑屏数秒后回退到原 Boot 分区；没有观察到 loader USB。第三次 DEBUG 镜像加入 SEC 早期标记后停在黑屏，仍未观察到 SEC 文字或 fastboot/ADB/Qualcomm USB 枚举。用户已手动返回 Bootloader。DEBUG 镜像 SHA256 为 `f4f8e709caec1ec51db1c19a548c2f171b00a812f3314222bfb4341dc5b80887`。

第四次 DEBUG 启动修正了早期日志清屏顺序，真机已出现日志，用户记录到 `ASSERT_EFI_ERROR (Status = Out of Resources)` 后重启。内存表检查同时发现旧堆与 Recovery 的 CDSP 保留区重叠，已修正堆地址/容量及低地址保留区；`python3 tools/check-raphael-uefi.py` 检查实际 FDT 的 RAM、20 处固定保留区、分配区间和栈 PCD，回归检查拒绝旧堆布局。第五次 DEBUG 启动（SHA256 `1b672ca1c990d85014274388405b156aaea1ce407a931d3f75f49fa11db5781c`）显示 Project Silicium Logo 和日志，Windows 枚举到 `USB\VID_18D1&PID_D00D\XNULOADER`，确认执行到了 EFI loader。Windows 错误码 28 表示未绑定驱动，已用宿主机现有的 usbipd 将该设备转交 WSL，并安装 Linux fastboot；转交操作只针对 xnuloader 实例。

已通过实际 fastboot 协议读取 `product: xnuloader`、`version: 0.5` 和 loader 日志：`XNULOADER v3`、`platform raphael`、`display 1080 x 2340 at 9c000000`、`usb: started`。日志保存在 `out/raphael/loader-first.log`。UEFI → loader → USB 日志的第一里程碑已通过。系统镜像已通过 USB 上传（2376 MiB / 138 秒），loader 申请到 `0xf4000000 + 0x10c000000` 的物理窗口，XNU 真机已输出 BSD 网络初始化日志；首次 8 核合并测试停在 `skip attaching fsw to lo0 using legacy TX model` 附近，尚未观察到用户态。 随后改为 `bootcpu=7 -enable_kprintf_spam` 保留 loader USB，真机屏幕到 `cpu 1 online` 后停住，loader 50 秒无心跳检测取回日志并重启；此时 UART 不存在，原 `kprintf` 帧缓冲回退路径未写入 USB 日志，因此仅保存到更早的调度器文字（`logs/222722-run.log`）。已补齐无 UART 时的日志转存并重新编译，`logs/223406-run.log` 已确认 BSD 到 `setconf`、CPU1 到 `arm_cpu_init(): cpu 1 online` 后停止，尚未到板级驱动初始化。单核对照同样停在 `setconf` / `cpu_start() cpu: 0`（`logs/224050-run.log`），因此此前 CPU1 的最后输出不能证明是 SMP 独有问题。源码核对发现 SM8150 虚拟定时器实际为 PPI 19，而通用 GIC 驱动固定 27；已增加 profile 的 `gic_timer_irq=19` 并检查 PPI 范围（其他设备保持默认 27），等待真机复测。普通 printf/IOLog 的共用 `console_printbuf_putc` 路径也已加入 USB 日志，避免继续漏掉根设备等待信息；已启用现有从核 `load_context` 跟踪，并按本机 Linux GICv3 的发送顺序补上 IPI 前 `DSB ST`（可见性修正，是否解决本机停顿仍待测试）。修正为 PPI 19 后，`logs/224908-run.log` 已确认 stage0 → init → Apple launchd → SpringBoard，7 个 XNU CPU 全部上线；当前还保留 1 个物理 CPU 给 loader。用户确认已进入系统、触控有效、三个按键有反应，截图为 `out/raphael/ios-first.png`（软件绘制，调试文字叠加）。首轮并行测试实际只创建了启动时记录的 4 个线程（3.1 个 CPU 的处理时间），虽结束时已有 7 核；已把 cpu_test 的 CPU 数采样移到等待之后，重新打包并校验小镜像。GPU 在 step 5 的计数器校准失败，仍为 softpipe；已根据 SM8150 Linux 修正测量基准时钟地址 `0x43008`，继续真机验证。不能把软件界面或主机检查写成 A640 硬件渲染通过。上述测试均为 `fastboot boot`，没有刷写分区。

## README 中的 iOS 用户态究竟如何启动

本仓库不是完整的 iOS 镜像。`common/setup.sh` 把 `hackios-xnu-userland` 检出到同一目录，使用独立的 `.userland.git`；用户态脚本、APFS 构建工具和预编译程序由那个仓库提供。

配套源码目前固定为 **iOS 16.5 / 20F66 / iPhone X arm64**，XNU 固定为 `xnu-8796.121.2`。`ios165/fetch.sh` 从 Apple 的 IPSW 中提取 OS、SystemOS cryptex、AppOS cryptex，以及匹配的 dyld shared cache。已有的其他版本 IPSW 不能直接代替：文件路径、cache、注入库所依赖的私有接口和设备身份需要配套。

`userland/build.sh` 制作两个 APFS 容器：

| 镜像 | 内容 | 内核中的用途 |
|---|---|---|
| `system.apfs` | 选定的 iOS 程序、framework、dyld cache、cryptex 文件，以及 stage0 | 驻留 RAM 的 `/dev/md0`，挂载为根文件系统 |
| `root.apfs` | 本项目 init、注入库、服务 plist、配置、测试程序和需要早期加载的固件 | 随内核发送的 `/dev/md1`，挂载到 `/redwood` |

具体执行链：

```text
fastboot boot → BootShim → Mu-Silicium UEFI → xnuloader EFI
  → 装载 Mach-O XNU、Apple DT、boot_args 和两个 RAM disk
  → XNU 挂载 md0，执行 /sbin/launchd（本项目的 stage0）
  → stage0 挂载 md1 到 /redwood，exec /redwood/sbin/init
  → init 挂载 /private/var 的 ramfs、准备目录、执行自检
  → init 通过 kern.exec_inject 配置注入库，读取 /redwood/etc/rc
  → rc.launchd 执行 /sbin/launchd.ios（Apple 原始 launchd）
  → notifyd/cfprefsd/logd/runningboardd/backboardd 等服务
  → SpringBoard → 锁屏和应用
```

“未修改 iOS 用户态”指保留 Apple 程序本体；系统布局仍由构建脚本调整：原 launchd 改名为 `launchd.ios`，入口换成 stage0，LaunchDaemons 指向 `/redwood/LaunchDaemons`。`REST=1` 生成其余按需启动的服务，不是把所有 Apple 原机服务一次性强行启动。

没有公开 Apple 驱动的功能由本仓库的 `MiniIOSurface`、`MiniIOMobileFramebuffer`、`MiniAppleKeyStore` 等实现补足。`libredwood.dylib` 注入 backboardd，把 `/dev/redwood-touch` 事件转换为虚拟 HID；`libredwood-sb.dylib` 和 `libredwood-media.dylib` 分别补足 SpringBoard 与 mediaserverd 的平台接口。新触控/按键驱动应继续输出现有事件格式，用户态不需要另做一套输入系统。

首次上传 `system.apfs` 后，loader 可跨多次 XNU 运行保留它；适配代码和服务配置主要在小镜像中，修改后不用反复发送整个系统镜像。loader 重启后需重新上传大镜像。

## GPU 路线与合并测试

GPU 以本仓库 `redwood_adreno.c` 的 642L 实现为起点，参考 SM8150 Linux 源码适配 A640；不采用 `ios-raphael` 的 GPU WIP。保留 `RedwoodGPU` IOKit 接口、现有内存/提交接口以及 Mesa freedreno 的 Darwin 适配。

必须替换或核实的部分包括 GPU/GPUCC/GMU/SMMU/RSC/PDC 地址、GCC 投票与时钟、GMU TCM/外部内存布局、HFI 消息、RPMh 电源与总线表、SMMU stream/context 和 CP 初始化寄存器。A640 固件是 `a640_gmu.bin`、`a630_sqe.fw`、`a640_zap.*`；642L 使用的 `a660_*` 文件不能混用。

`GL=1` 把 Mesa/OpenGL ES 桥接库放进小镜像；`gpu=1` 让内核启动 GPU。两者缺一，或固件缺失，都不能得到 README 所说的 GPU CoreAnimation。`gl_test` 应报告 Adreno renderer，提交完成并读回正确图像；亮屏、存在 RedwoodGPU 服务或软件 renderer 的三角形均不证明 A640 可用。应用 Metal 是独立目标，README 本身也未声明所有应用 Metal 已完成。

测试尽量合并到同一镜像、同一次会话：

| 功能 | 通过证据 |
|---|---|
| UEFI/loader | 真机显示、USB `product: xnuloader`、正确平台和内存映射；能取日志和重启 |
| CPU | 8 核实际 online，`cpu_test` 报告 8 个 active CPU，并显示多线程实际并行 |
| iOS | stage0/init/launchd 链完整，SpringBoard 锁屏可见且没有持续崩溃重启 |
| 触控 | 多点、滑动解锁、底边手势与坐标方向正常；事件确实经过 backboardd |
| 按键 | 电源键锁屏/唤醒，两个音量键产生正确操作 |
| GPU | Adreno 640 renderer、命令完成、图像读回和屏幕结果一致；再验证 CoreAnimation |

当前 profile 已启用 `cpus=8 touchscreen=1 buttons=1 cpufreq=1 gpu=1 metal=1 metal_profile=1`，并用 `GL=1` 和 `common/devices/raphael.jobs` 合并测试：增加 Metal 矩形和 MSAA resolve 检查，先报告 CPU 数，20 秒后画三角形并回读，45 秒后检查多线程并行，随后保留 iOS 界面供真机滑动及按键测试。存储和无线驱动关闭；所有系统文件驻留 RAM。

A640 分支已调整物理地址、GCC PLL vote、GPUCC 时钟/测量选择（XO/4 基准 `0x43008`）、GMU 固定缓存 VMA 与 DTCM、旧固件 `BABEFACE` 成功状态、PDC/RSC 序列、257/345/427 MHz 表、1 MiB GMEM 与 UBWC bank 15。按 SM8150 Linux 的 `a6xx_gmu_cache_finalize` 补上 `0x60000000 + 0x1000` 共享区；固件装载和读回只复用已分配页，禁止校验轮次重新分配/覆盖代码映射。SMMU ACTLR 为本机 DT 的 `0x303`，GPU stream 0/1 使用 `0x401` 合并 mask，GMU stream 5 使用 `0x400`；原 642L 的分开映射保持不变。ZAP 区域使用本机 Recovery FDT 和 Linux 合并 DT 同时确认的 `0x98f15000 + 0x2000`。固件来自本机 `/vendor/firmware` 与 modem 的只读挂载，逐个校验 SHA256。

`logs/230627-run.log` 已通过 step 18，随后首次 `PAS_SHUTDOWN`（尚未加载 zap shader）没有返回，loader 取日志并自动重启到 Bootloader。A640 改按本机 Linux 的加载顺序，不预先卸载未知 shader；正常结束时仍卸载本轮成功加载的 shader。`logs/231120-run.log` 已确认加载、认证与结束卸载均返回成功。连续运行还发现旧 loader 日志填满后 `running` 状态为空；已把清空旧日志移到设置状态之前，主机也会继续等待空状态，避免过早收尾。本次换用新 loader 的 DEBUG 镜像 SHA256 为 `ea56c480a4eae33a18289b19067a92a81cdf4d50486b02b578c71dc06ecd2793`，UEFI FD 与第五次成功镜像相同。默认 profile 已移除 `-v`，按原项目的 graphics-mode 路径避免内核文字覆盖 iOS；诊断时可在 `XL_CMDLINE` 中加回 `-v`。

主机检查运行实际驱动函数：

```sh
python3 tools/check-raphael-uefi.py
python3 tools/check-raphael-input.py
python3 tools/check-raphael-touch.py
python3 tools/check-raphael-gpu.py
```

覆盖设备匹配、按键 PMIC 选择、GT9886 多点/错误报告、按下移动抬起/边缘坐标、时钟守卫、真实 A640 固件与损坏块、实际共享区分配和固件装载/读回、GPU/GMU SMMU stream、PDC/RSC 和 GPU 参数，并检查原 642L 分支。使用 ASan/UBSan；这不能代替硬件验证。

本次已生成并校验 `userland/system.apfs`（62,362 条目录项）与含 GL 的 `root.apfs`（120 条目录项）。XNU 和 EFI loader 已编译；XNU 构建的 DriverKit 导出检查仍有 README 已说明的错误，不能把 make 返回 2 写成完整构建检查通过。

原项目的 AMFI/Sandbox/KeyStore 是兼容替代实现，不具备原生 iPhone 的安全隔离和密钥保护；本移植面向研究测试。


## 本机构建顺序

本轮配套源码发布在两个 fork 的 `raphael-bringup` 分支。新工作区可运行：

```sh
git clone -b raphael-bringup https://github.com/Helium-Studio/hackios-xnu-kernel.git hackios
cd hackios
USERLAND_URL=https://github.com/Helium-Studio/hackios-xnu-userland.git \
  USERLAND_REF=raphael-bringup common/setup.sh
```

用户态提交 `3204ef8` 默认启用已有的 launchd quiet 路径（`QUIET=0` 可恢复其 stderr），并修正 CPU 并行测试的采样时机。raphael profile 使用 graphics mode（没有 `-v`）、`QUIET=1 OSLOG=`；关闭屏幕文字不需要删除 USB 诊断通道或重新制作 2.5 GB 的系统镜像。小镜像增加 `etc/quiet` 后为 121 条目录项，已读回校验。

第一次完整八核会话在结束后出现 UEFI 的 `Spurious GIC interrupt: 0x13`，USB 无法恢复，日志未取回，该轮不能认定八核测试通过。已在 XNU 共用 GIC 返回清理中屏蔽自身虚拟定时器，再交还 UEFI；保留 UEFI 的物理定时器配置。修正版本在最终 RELEASE 合并复测中正常返回并恢复 USB，见 `logs/011423-run.log`。

用户态与内核的构建前置见仓库 README。此次工具链放在 `out/theos`，使用 iPhoneOS 16.5 SDK、Android clang 22 和 cctools；Mu Python 工具使用隔离环境，避免宿主机不完整的 Python 包元数据中断构建。 本机执行时设置 `THEOS=$PWD/out/theos`、`LDID=$PWD/out/theos/toolchain/linux/iphone/bin/ldid`，PATH 加入 Android clang 工具链；不要把 Theos 的 Darwin `ld` 放在主机 PATH 前面，否则 APFS 主机检查器会错误调用 Darwin 链接器。

```sh
python3 tools/build-raphael-dtb.py
# Mu-Silicium 已按 uefi/BASE 检出，并应用 uefi/mu-silicium.patch 与 uefi/files/。
python3 tools/extract-raphael-uefi.py
cp out/raphael/raphael.dtb Mu-Silicium/Resources/DTBs/raphael.dtb
# 使用已安装的 Mu 构建环境
(cd Mu-Silicium && python3 build_uefi.py -d raphael -r RELEASE)
python3 tools/check-raphael-uefi.py
# THEOS/PATH 设置为本机工具链，WSL 测试使用本机 USB 包装脚本
common/build.sh raphael
PATH="$PWD/out/host-bin:$PATH" common/run.sh raphael 300
```

raphael 的 `DeviceBuild.py` 不递归拉取 Mu_Basecore 的单元测试源码。构建依赖的嵌套子模块需在固定的 Mu_Basecore 下初始化：

```sh
git -C Mu-Silicium/Mu_Basecore submodule update --init --depth 1 --filter=blob:none \
  MdePkg/Library/BaseFdtLib/libfdt \
  MdePkg/Library/MipiSysTLib/mipisyst \
  MdeModulePkg/Library/BrotliCustomDecompressLib/brotli \
  SecurityPkg/DeviceSecurity/SpdmLib/libspdm
```

`libspdm` 只需其 `include/` 供包声明使用；本次使用 sparse checkout，且 HEAD 已核对为 Mu_Basecore 固定的 `f55cf6d`。

本宿主机是 WSL，USB 在 Windows；实际会话通过 Windows 的 `adb.exe` / `fastboot.exe`，并将文件参数转换为 Windows 路径。普通 Linux `fastboot devices` 为空不能证明手机未连接。设备序列号需始终绑定到目标手机；Android/Bootloader 为 `d11b018e`，EFI loader 的序列号为 `xnuloader`。loader 可通过 `usbipd attach --wsl --busid <实际总线号>` 交给 WSL，再使用 Linux fastboot；本机 `out/host-bin/fastboot` 按实际连接选择原生 Linux 或 Windows fastboot。

QEMU 预检日志为 `out/raphael/qemu-userland.log`：init → Apple launchd → SpringBoard 成功派生；`cpu_test` 8 个 active CPU，8 线程取得约 6.0 个 CPU 的并行处理时间；Mesa softpipe 三角形回读 error 0、内部像素占比与几何预期均为 26%。这不证明真机 UEFI、A640 或输入已通过；QEMU 的 backboardd 仍报告软件 renderer 模拟崩溃。

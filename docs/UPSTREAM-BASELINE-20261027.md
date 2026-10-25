# 2026-10-27 上游基线迁移

上游 `origin/main` 为 `88513176b1e96ecf0b764cd62c6f4e6ac71345e3`，旧地址已转向 oosexgang/hakios-os。上游重写历史，删除 metal 分支；新 main 与旧 raphael 分支没有共同祖先。采用 `rebase --onto origin/main c2ddff4` 重放七个功能提交，再补齐统一仓库接口，避免合并两套发布历史。

## 上游变化与选择

- 内核、用户态、构建工具合并为单仓；common/ 移除，设备资源迁到 devices/，ios165/ 改为 sysimage/。
- hk_* 文件改为 hakios.*，标识符为 hakios_*；补丁改名 xnu/hakios.patch。运行挂载路径实际仍为 /redwood。
- 上游移除 Metal 驱动和通用 fb_scan。用户明确选择完全跟随新基线，仅保留 GLES，因此不重放本地 HKMetal、NativeMetal、AIR Metal buffer/MSAA 修补或 Metal jobs。
- 最新提交主要涉及蜂窝 MPSS/IPA：SoC 参数生成、GSI 环长度、QMI DPM/WDA/WDS 初始化顺序，以及 NAS 信号缓存。保留这些上游改动，但不启用 raphael 蜂窝功能。

## 保留与适配

保留 UEFI/loader、GT9886/按键、OSM 调频、A640、受限 userdata 存储，以及 ath10k/ICNSS/WPA3。设备源码归 devices/raphael，其他设备 UEFI 保持上游原状。

显示仅保留 raphael 命令模式 TE 相位测量，继续三缓冲 page flip、异常回退和不消费 latch IRQ 的约束。没有恢复上游已移除的视频模式路径。

用户态采用新上游代码，增补 prepared 系统卷启动、私有 MPSS 打包和 userdata var_store 设备选择。现有系统卷和双槽归档不重新部署。旧 .userland.git 保存历史，当前文件统一由根 .git 管理。

## 验证

固定 Apple tag 创建全新 xnu-src/xnu-8796.121.2-baseline-20261027；补丁应用、完整 XNU、ath10k 和 loader 构建通过。28 项设备/loader/Wi-Fi 主机检查、WPA2 的 195 项检查、WPA3 SAE/PMF 和上游 SoC 参数测试通过。init/var_store 语法检查通过。

日志、旧树 Git bundles 和逐文件迁移计划保存在 out/rebase-baseline-20261027/；旧引用为 backup/raphael-before-baseline-20261027。原生 Metal 旧备份保持不动。

本轮未构建完整用户态镜像、未重建 UEFI、未运行手机、未推送。GLES 新镜像与现有 userdata 的实际兼容性、控件/Safari 字体、复杂 UI 帧率、Wi-Fi 开关后的扫描恢复均需后续合并实测，不能用构建通过代替验收。

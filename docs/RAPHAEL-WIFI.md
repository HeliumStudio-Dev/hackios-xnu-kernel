# Raphael Wi-Fi 状态与构建

本机使用 WCN399x / ICNSS、MPSS（PAS 4）和 ath10k SNOC。不要使用 redwood 的 WCN6750 / WPSS / ath11k 配置，也不要同时启动 qcacld 与 ath10k。

## 已验证与剩余问题

- ICNSS 控制链包含 MPSS 签名装载、SMEM、SMP2P、GLINK、QRTR、RMTFS、TFTP、PD mapper、PDR、DMS、BDF、MSA/SMMU 和五路 PMIC 供电。
- PM8150L L10C 使用 3312 mV / HPM。MPSS 运行期间保持 AOSS QDSS 时钟投票，退出时逆序撤销供电、共享内存权限及投票。
- SNOC 主机路径包含 12 路 level-high CE 中断、NAPI、HTC/WMI 和数据收发。
- 已通过 2.4 GHz WPA2、5 GHz WPA3 SAE 的关联和实际网页加载。WPA3 包括 H2E、PMF、IGTK 和管理帧重放检查；密码由用户在手机设置中输入。
- 连接仍不稳定；关闭再开启 Wi-Fi 后无法正常扫描。此次提交保存已有实现，不声称已经修复该问题。

硬件依据是本机内核源码中的 qcacld-3.0、fw-api、qcacmn，以及 6.12 分支的 `4c37abf82a78`、`f48d0a8dfc4e`、`ad7584e9454f`、`0ad06c1c3f64`。禁止继续运行 Linux 实机对照测试。

## 构建与私有输入

```sh
export XNU_SRC="$PWD/xnu-src/xnu-8796.121.2-baseline-20261027"
export THEOS="$PWD/out/theos"
export PATH="/home/heliumstudio/toolchains/r596125/bin:$PWD/xnu-deps/host/bin:$PATH"
python3 tools/mk-ath10k.py
WIFI_OBJECT="$PWD/xnu-deps/build/ath10k/out/ath10k.o" ./xnu-build.sh -j8
```

`devices/raphael/device.conf` 的 `WIFI_ATH10K=1` 选择该对象。构建依赖的下载地址、版本和 SHA-256 固定在 `tools/mk-ath10k.py`；源码补丁在 `wifi/lx/ath10k/patches/`。

用户态的 `MPSS_FW` 输入包含本机提取的 `modem.mdt`、`wlanmdsp.mbn`、`firmware-5.bin`、匹配机型的 BDF，以及 modemst1/modemst2/fsg/fsc 的私有 NV 快照。固件与快照只打包到本机 resident 镜像；RMTFS 写入只修改 RAM 副本。禁止提交、发布这些文件或读取宿主机保存的 Wi-Fi 密码。`wifi_bdf=bd_f11cn.bin` 用于当前已验证的 CN 测试机，其他变体必须重新核验。

当前使用的控制与主机参数：

```text
wifi_step=15 wifi_lx=2 wifi_ba=1 wifi_wide=1 wifi_new=99 wifi_pause=0 wifi_ask=1 wifi_bdf=bd_f11cn.bin wifi_smmu=2 wifi_keep=1 wifi_wait=10 wifi_listen=15
```

上述参数不部署系统、不授权分区写入。继续使用已有 userdata 系统卷与归档，不重新格式化。`devices/raphael/raphael-wifi.jobs` 在用户手动连接后检查地址、DNS、TCP 和 HTTPS。

## 主机回归

```sh
python3 tools/mk-ath10k.py --sae-test
tools/wpa-test/run.sh
for check in tools/check-wifi-*.py; do python3 "$check" || exit; done
```

这些检查覆盖协议边界、WPA2/WPA3/PMF 算法、IRQ/NAPI 与固件控制路径。ASan/UBSan 通过不能替代实机扫描、重新关联及网络稳定性验证。`tools/test-raphael-wifi.sh` 是早期有时限的 RAM 诊断入口，不是完整用户态的验收测试。

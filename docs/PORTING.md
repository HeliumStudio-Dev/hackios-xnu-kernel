# Porting HackiOS to another device

HackiOS was brought up on the POCO X5 Pro 5G (Snapdragon 778G). A Qualcomm phone with an unlockable bootloader
is the realistic next target: the boot chain (Mu-Silicium UEFI started with `fastboot boot`) and most of the kernel's
platform code carry over. Start with:

```sh
common/new-device.sh <codename> path/to/device.dtb
```

It writes `common/devices/<codename>.conf` (the profile `common/build.sh` and `common/run.sh` read) and
`common/devices/<codename>.platform.c` (the loader's description of the SoC), filling in what the device tree says.
Get the device tree from the phone's `vendor_boot` image, or from a running Android: `adb pull /sys/firmware/fdt`.

## 1. The UEFI

The phone needs a UEFI that our loader can run under. Port [Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)
the way `uefi/` ports redwood (it follows `lisa`, the same SoC package):

- `Platforms/<Vendor>/<codename>Pkg`: memory map and driver list (copy the closest device of the same SoC);
- `Binaries/<codename>`: the UEFI drivers of the phone's own firmware, extracted with
  [UEFIReader](https://github.com/WOA-Project/UEFIReader) from its `xbl.img`;
- apply our two changes from `uefi/mu-silicium.patch`: the boot shim copies the "XNUP" container after the UEFI
  image to `PAYLOAD_BASE`, and `BootManagerLib` starts the XNU loader from it instead of the menu.

Put the addresses in the profile: `FD_BASE`, `FD_SIZE` (where the shim puts the UEFI image) and `PAYLOAD_BASE`
(free RAM for the kernel and images). The prebuilt `BootShim.bin` is built for redwood's addresses: build the
shim from your Mu-Silicium tree (`mkxnuimg.py` does it when `Mu-Silicium/` is there).

## 2. The loader

`xnuloader/loader.c` describes each device with a `struct platform` and picks it by the framebuffer base the UEFI
reports. Paste `common/devices/<codename>.platform.c` next to `platform_redwood` and add it to `platforms[]`:

| Field | Where it comes from |
|---|---|
| `io_base`, `io_size` | one window that covers the SoC's peripherals; it must not start at 0 (XNU then skips clock setup) |
| `gic_dist`, `gic_redist` | the `arm,gic-v3` node's `reg` (filled in by `new-device.sh`) |
| `cores`, `core_shift` | the `cpu@` nodes; Qualcomm numbers cores in MPIDR's second affinity field (shift 8) |
| `small_cores` | a bit per core of the little cluster (lowest `capacity-dmips-mhz`) |
| `psci_hvc` | 1 if the firmware's PSCI is called with HVC (QEMU), 0 for SMC (phones) |
| `fb_base` | the framebuffer address; the loader prints it at start (`display W x H at ...`) |

Rebuild with `xnuloader/build.sh`; QEMU must still pick `qemu-virt` (no match = ramfb).

## 3. The kernel

What is generic: GICv3, the timer, PSCI SMP, the display (the UEFI's framebuffer), APFS and ramfs, the driver
replacements, the return-to-loader path. What is redwood-specific and needs looking at:

- **touch**: `bsd/dev/hk_goodix.c` (Goodix GT9916 over bit-banged SPI) — another panel needs its own driver
  feeding `/dev/hk-touch` (`bsd/dev/hk_input.c`);
- **buttons, CPU frequency, watchdog**: GPIO/PMIC numbers and the EPSS block in `hk_input.c`,
  `hk_cpufreq.c`, `osfmk/arm64/loader_return.c`;
- **GPU / Wi-Fi / sound**: `hk_adreno.c` (Adreno 642L), `hk_wifi.c` (WCN6750 + ath11k), `hk_audio.c`
  — the same Qualcomm subsystems (SMEM, SMP2P, GLINK, QRTR, QMI) are reused, the addresses and firmware differ.

Check the architectural timer's interrupt too: the third entry of its Linux `interrupts` property is the virtual
PPI, whose GIC INTID is `16 + PPI number`. Set `gic_timer_irq=<INTID>` in the profile's `BOOTARGS` if it differs
from the generic default 27. For example, SM8150 raphael uses `<1 3 flags>` and needs `gic_timer_irq=19`;
copying the GIC addresses alone leaves timer wakeups broken.

Start with no extras: the system boots to the lock screen with only the framebuffer, touch and the CPU.

## 4. Firmware

Vendor firmware never goes into the repository; it comes from the phone's own Android (`FIRMWARE` in the profile
lists what to pull, see README "On the phone"). Without `fw-gpu/` the kernel does not start the GPU and says so only
deep in the log (`adreno: THE GPU IS NOT STARTED`); `userland/build.sh` prints which firmware went into the image.

## 5. Run

```sh
common/build.sh <codename>
common/run.sh <codename>
```

The first useful milestone is the loader's own screen and log over USB (`./xl log`), the next one is the kernel's
verbose boot text (`-v`), then SpringBoard. Read [checks.md](checks.md) before trusting a "it is not in the log".

## The SoC's blocks: BOARD_ARGS

The kernel's drivers were brought up on the POCO X5 Pro (SM7325), and every block they map -- the CPU frequency
domains, the temperature sensors, the clock controllers, the display's timing engine, the UFS controller, the
PMIC arbiter -- defaults to that phone's address. Another phone gives its own on the kernel's command line,
`board_<block>=0x...` (bsd/sys/hk_board.h lists them). `common/new-device.sh <codename> <dtb>` reads them out
of the phone's device tree (`tools/board-from-dt.py`) into the profile's `BOARD_ARGS`, which `common/run.sh` and
`common/flash/install.sh` pass on. On redwood's own device tree the tool reads back exactly the defaults.

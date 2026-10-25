/*
 * raphael GT9886 Normandy over QUPv3 SE19 I2C, feeding /dev/redwood-touch.
 * Reuses the local ios-raphael FIFO/Normandy implementation; board data is from
 * zundamon_raphael. No PMIC writes or touch firmware/config uploads.
 */
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <kern/clock.h>
#include <kern/thread.h>
#include <kern/sched_prim.h>
#include <machine/machine_routines.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern kern_return_t thread_terminate(thread_t);
extern void hakios_tl(const char *, ...) __printflike(1, 2);

#define TOUCH_GPIO_CFG(n) ((uint32_t)(n) * 0x1000u)
#define TOUCH_GPIO_IO(n) (TOUCH_GPIO_CFG(n) + 4u)
#define TOUCH_MAX 10u
#define NORMANDY_PID 0x4535u
#define NORMANDY_EVENT 0x4100u
#define NORMANDY_ESD 0x30f3u
#define SE_STATUS       0x040u
#define SE_MCLK         0x048u
#define SE_FW           0x068u
#define SE_CLK_SEL      0x07cu
#define SE_DMA          0x258u
#define SE_TX_LEN       0x26cu
#define SE_RX_LEN       0x270u
#define SE_SCL          0x278u
#define SE_CMD          0x600u
#define SE_CTRL         0x604u
#define SE_IRQ          0x610u
#define SE_IRQ_EN       0x614u
#define SE_IRQ_CLR      0x618u
#define SE_TX           0x700u
#define SE_RX           0x780u
#define SE_TX_COUNT     0x800u
#define SE_RX_COUNT     0x804u
#define SE_HW_TX        0xe24u
#define SE_HW_RX        0xe28u
#define SE_TX_WM        0x80cu
#define SE_RX_WM_IRQ    (1u << 26)
#define SE_RX_LAST      (1u << 27)
#define SE_TX_WM_IRQ    (1u << 30)
#define SE_DONE         (1u << 0)
#define SE_NACK         (1u << 10)
#define SE_ERRORS       (0x3eu | (1u << 9) | (1u << 10) | (1u << 12) | \
                         (1u << 13) | (3u << 24) | (3u << 28))
#define SE_EVENTS       (SE_DONE | SE_ERRORS | SE_RX_WM_IRQ | SE_RX_LAST | SE_TX_WM_IRQ)
/* geni_se_config_packing(8, 4, true, true, true): start bits 7/15/23/31,
 * MSB-to-LSB, length 8, STOP only on vector 3. FIFO bytes remain LSB first. */
#define SE_PACK0        0x0007f8feu
#define SE_PACK1        0x000ffefeu

static struct {
	vm_offset_t se, gcc, gpio;
	bool started, dead, probing, invert;
	uint32_t irq_status, irq_last, active;
	uint32_t latency;
	uint64_t poll_time;
	unsigned sent, got;
	int x[TOUCH_MAX], y[TOUCH_MAX];
} st;
static int touch_sleep_chan;

static uint32_t
touch_rd(vm_offset_t base, uint32_t off)
{
	uint32_t v = *(volatile uint32_t *)(base + off);
	__asm__ volatile("dmb oshld" ::: "memory");
	return v;
}

static void
touch_wr(vm_offset_t base, uint32_t off, uint32_t val)
{
	__asm__ volatile("dmb oshst" ::: "memory");
	*(volatile uint32_t *)(base + off) = val;
	__asm__ volatile("dsb osh" ::: "memory");
}

static void
touch_wait_until(uint64_t deadline)
{
	(void)assert_wait_deadline(&touch_sleep_chan, THREAD_UNINT, deadline);
	thread_block(THREAD_CONTINUE_NULL);
}

static void
touch_wait(unsigned ms)
{
	uint64_t deadline;
	clock_interval_to_deadline(ms, NSEC_PER_MSEC, &deadline);
	touch_wait_until(deadline);
}

static bool
touch_wait_clear(vm_offset_t base, uint32_t off, uint32_t mask)
{
	for (unsigned i = 0; i < 5000; ++i) {
		if (!(touch_rd(base, off) & mask)) {
			return true;
		}
		delay(1);
	}
	return false;
}

static void
touch_gpio(unsigned pin, unsigned mux, unsigned pull, unsigned drive, bool out, bool high)
{
	uint32_t off = TOUCH_GPIO_CFG(pin);
	uint32_t cfg = touch_rd(st.gpio, off);
	if (out) {
		/* Set the desired latch before enabling output (reset is active low). */
		touch_wr(st.gpio, TOUCH_GPIO_IO(pin),
		    (touch_rd(st.gpio, TOUCH_GPIO_IO(pin)) & ~2u) | (high ? 2u : 0u));
	}
	cfg &= ~0x3ffu;
	cfg |= (mux << 2) | pull | (drive << 6) | (out ? 0x200u : 0u);
	touch_wr(st.gpio, off, cfg);
}

static bool
touch_clocks(void)
{
	/* SE19 is wrapper2 LOCAL S2; global numbering is not a GCC index. */
	uint32_t vote = 0x52014u;
	uint32_t mask = (1u << 1) | (1u << 2) | (1u << 6);
	uint32_t rcg = 0x1e3a8u;
	touch_wr(st.gcc, vote, touch_rd(st.gcc, vote) | mask);
	uint32_t dfs = touch_rd(st.gcc, rcg + 0x14u);
	uint32_t cfg = touch_rd(st.gcc, rcg + 4u);
	printf("raphael-touch: gcc vote=%#x rcg=%#x cfg=%#x dfs=%#x\n",
	    touch_rd(st.gcc, vote), touch_rd(st.gcc, rcg), cfg, dfs);
	if (dfs & 1u) {
		/* SE CLK_SEL=0 selects DFS performance level 0. Do not alter tables. */
		cfg = touch_rd(st.gcc, rcg + 0x1cu);
		if ((cfg & 0x371fu) != 1u) {
			printf("raphael-touch: DFS level0=%#x is not XO/1; need clock integration\n", cfg);
			return false;
		}
	} else {
		/* XO parent 0, HID divider 1 => 19.2 MHz. No PLL or voltage change. */
		cfg = (cfg & ~(0x371fu | (1u << 20))) | 1u;
		touch_wr(st.gcc, rcg + 4u, cfg);
		touch_wr(st.gcc, rcg, touch_rd(st.gcc, rcg) | 1u);
		if (!touch_wait_clear(st.gcc, rcg, 1u)) {
			printf("raphael-touch: RCG update timeout\n");
			return false;
		}
	}
	const uint32_t branch[] = {0x1e004, 0x1e008, 0x1e3a4};
	unsigned count = sizeof(branch) / sizeof(branch[0]);
	for (unsigned i = 0; i < count; ++i) {
		/* Linux clk_branch_wait also skips halt polling in HWCG mode. */
		if (branch[i] == 0x1e008 &&
		    (touch_rd(st.gcc, branch[i]) & 2u)) {
			printf("raphael-touch: wrapper2 S-AHB hardware clock gating active\n");
			continue;
		}
		if (!touch_wait_clear(st.gcc, branch[i], 1u << 31)) {
			printf("raphael-touch: GCC branch %#x halted (%#x)\n", branch[i],
			    touch_rd(st.gcc, branch[i]));
			return false;
		}
	}
	return true;
}

static void
touch_abort(void)
{
	touch_wr(st.se, SE_CTRL, 2); /* abort M command, release held bus */
	bool done = false;
	for (unsigned i = 0; i < 5000; ++i) {
		if (touch_rd(st.se, SE_IRQ) & (1u << 5)) {
			done = true;
			break;
		}
		delay(1);
	}
	if (!done || !touch_wait_clear(st.se, SE_STATUS, 1u)) {
		st.dead = true;
		printf("raphael-touch: abort failed status=%#x irq=%#x; stopping\n",
		    touch_rd(st.se, SE_STATUS), touch_rd(st.se, SE_IRQ));
	}
	/* Bound drain even if the hardware reports an impossible FIFO count. */
	for (unsigned i = 0; i < 64 && (touch_rd(st.se, SE_RX_COUNT) & 0x1ffffffu); ++i) {
		(void)touch_rd(st.se, SE_RX);
	}
	touch_wr(st.se, SE_IRQ_CLR, 0xffffffffu);
	if (touch_rd(st.se, SE_TX_COUNT) & 0xfffffffu) {
		st.dead = true;
		printf("raphael-touch: TX FIFO not empty after abort; stopping\n");
	}
}

static bool
touch_idle_fifo(void)
{
	/* A previous kernel can stop between RX arrival and its drain; never discard an active transfer. */
	if (touch_rd(st.se, SE_STATUS) & 0x1001u) return false;
	unsigned drained = 0;
	while (drained < 64 && (touch_rd(st.se, SE_RX_COUNT) & 0x1ffffffu)) {
		(void)touch_rd(st.se, SE_RX);
		drained++;
	}
	if (drained) printf("raphael-touch: drained %u stale RX FIFO words\n", drained);
	touch_wr(st.se, SE_IRQ_CLR, 0xffffffffu);
	return !(touch_rd(st.se, SE_TX_COUNT) & 0xfffffffu) &&
	       !(touch_rd(st.se, SE_RX_COUNT) & 0x1ffffffu);
}

void
raphael_touch_quiesce(void)
{
	/* Called after the other CPUs stop, so no thread can start another I2C command. */
	if (!st.started || !st.se) return;
	if (touch_rd(st.se, SE_STATUS) & 1u) touch_abort();
	if (!touch_idle_fifo()) printf("raphael-touch: FIFO not idle on return\n");
	st.dead = true;
}

static uint32_t
touch_irq(void)
{
	st.irq_last = touch_rd(st.se, SE_IRQ);
	st.irq_status |= st.irq_last;
	return st.irq_last;
}

static int
touch_msg_run(uint8_t addr, const uint8_t *tx, unsigned nt, uint8_t *rx,
    unsigned nr, bool stretch)
{
	if (st.dead || nt > 3 || nr > 90 || (nt && nr) || (!nt && !nr)) {
		return EIO;
	}
	if (!touch_wait_clear(st.se, SE_STATUS, 1u)) {
		st.dead = true; /* no other serial-engine owner is supported */
		return EBUSY;
	}
	touch_wr(st.se, SE_IRQ_CLR, 0xffffffffu);
	touch_wr(st.se, SE_TX_WM, nt ? 1u : 0u);
	touch_wr(st.se, nr ? SE_RX_LEN : SE_TX_LEN, nr ? nr : nt);
	touch_wr(st.se, SE_CMD, ((nr ? 2u : 1u) << 27) |
	    ((uint32_t)addr << 9) | (stretch ? 4u : 0u));
	int err = ETIMEDOUT;
	for (unsigned i = 0; i < 20000; ++i) {
		uint32_t irq = touch_irq();
		if (irq & SE_ERRORS) {
			err = (irq & SE_NACK) ? ENXIO : EIO;
			/* A completed NACK is normal during address probing. Aborting an
			 * idle sequencer may never produce ABORT_DONE. Wait for completion
			 * and leave a clean idle engine available for the other IC. */
			for (unsigned j = 0; j < 5000 && !(irq & SE_DONE); ++j) {
				delay(1);
				irq = touch_irq();
			}
			if ((irq & SE_DONE) && !(touch_rd(st.se, SE_STATUS) & 1u) &&
			    !(touch_rd(st.se, SE_TX_COUNT) & 0xfffffffu) &&
			    !(touch_rd(st.se, SE_RX_COUNT) & 0x1ffffffu)) {
				touch_wr(st.se, SE_IRQ_CLR, irq);
				return err;
			}
			break;
		}
		if (nt && !st.sent && (irq & SE_TX_WM_IRQ)) {
			uint32_t word = 0;
			for (unsigned j = 0; j < nt; ++j) {
				word |= (uint32_t)tx[j] << (8u * j);
			}
			touch_wr(st.se, SE_TX, word);
			st.sent = nt;
			touch_wr(st.se, SE_TX_WM, 0);
		}
		uint32_t count = touch_rd(st.se, SE_RX_COUNT) & 0x1ffffffu;
		if (count > 64 || count > (nr - st.got + 3u) / 4u) {
			err = EIO;
			break;
		}
		while (count--) {
			uint32_t word = touch_rd(st.se, SE_RX);
			for (unsigned j = 0; j < 4 && st.got < nr; ++j) {
				rx[st.got++] = (uint8_t)(word >> (8u * j));
			}
		}
		/* DONE is checked after draining RX, so final short words aren't lost. */
		if (irq & SE_DONE) {
			/* Re-sample after the final drain; a late error must beat DONE. */
			irq = touch_irq();
			if (irq & SE_ERRORS) {
				continue;
			}
			touch_wr(st.se, SE_IRQ_CLR, irq);
			if (st.got == nr && st.sent == nt) {
				return 0;
			}
			err = EIO;
			break;
		}
		/* Preserve DONE/errors if they arrive during this iteration. */
		touch_wr(st.se, SE_IRQ_CLR, irq & (SE_RX_WM_IRQ | SE_RX_LAST | SE_TX_WM_IRQ));
		delay(1);
	}
	touch_abort();
	return err;
}

static int
touch_msg(uint8_t addr, const uint8_t *tx, unsigned nt, uint8_t *rx,
    unsigned nr, bool stretch)
{
	st.irq_status = st.irq_last = 0;
	st.sent = st.got = 0;
	int err = touch_msg_run(addr, tx, nt, rx, nr, stretch);
	if (st.probing) {
		printf("raphael-touch: probe xfer addr=%#x %s len=%u stretch=%u err=%d irq=%#x seen=%#x tx=%u rx=%u status=%#x\n",
		    addr, nr ? "read" : "write", nr ? nr : nt, stretch ? 1u : 0u,
		    err, st.irq_last, st.irq_status, st.sent, st.got,
		    touch_rd(st.se, SE_STATUS));
	}
	return err;
}

static int
touch_read(uint8_t addr, uint16_t reg, bool wide, uint8_t *buf, unsigned len)
{
	uint8_t ptr[2] = {(uint8_t)(reg >> 8), (uint8_t)reg};
	int err = touch_msg(addr, wide ? ptr : ptr + 1, wide ? 2u : 1u,
	    NULL, 0, true);
	if (err) {
		return err;
	}
	/* STOP_STRETCH on the pointer write retains the bus for a repeated START. */
	return touch_msg(addr, NULL, 0, buf, len, false);
}

static void
touch_report(uint32_t mask, const int *x, const int *y)
{
	for (unsigned id = 0; id < TOUCH_MAX; id++) {
		uint32_t bit = 1u << id;
		if (mask & bit) {
			if (!(st.active & bit) || x[id] != st.x[id] || y[id] != st.y[id]) {
				hakios_touch_post(st.active & bit ? HAKIOS_TOUCH_MOVE : HAKIOS_TOUCH_DOWN, id,
				    (uint32_t)x[id] * 65535u / 1079u, (uint32_t)y[id] * 65535u / 2339u);
			}
			st.x[id] = x[id];
			st.y[id] = y[id];
		} else if (st.active & bit) {
			hakios_touch_post(HAKIOS_TOUCH_UP, id,
			    (uint32_t)st.x[id] * 65535u / 1079u, (uint32_t)st.y[id] * 65535u / 2339u);
		}
	}
	st.active = mask;
}

static int
touch_normandy_write(uint16_t reg, uint8_t value)
{
	const uint8_t data[3] = {reg >> 8, reg & 0xffu, value};
	return touch_msg(0x5d, data, sizeof(data), NULL, 0, false);
}

static int
touch_normandy_probe(void)
{
	uint8_t awake = 0, pid[4] = {0}, sensor = 0xff;
	/* Vendor Normandy doze handshake. Keep awake for polled reports. */
	for (unsigned i = 0; i < 10; ++i) {
		if (touch_normandy_write(0x30f0, 0xaa)) {
			return EIO;
		}
		touch_wait(10);
		if (!touch_read(0x5d, 0x3100, true, &awake, 1) && awake == 0xbb) {
			break;
		}
	}
	if (awake != 0xbb) {
		printf("raphael-touch: Normandy doze handshake failed status=%#x\n", awake);
		return ETIMEDOUT;
	}
	int err = touch_read(0x5d, NORMANDY_PID, true, pid, sizeof(pid));
	if (!err) {
		err = touch_read(0x5d, 0x4541, true, &sensor, 1);
	}
	printf("raphael-touch: Normandy pid=%02x%02x%02x%02x sensor=%u err=%d\n",
	    pid[0], pid[1], pid[2], pid[3], sensor, err);
	if (err || memcmp(pid, "9886", sizeof(pid)) || (sensor & 15u) > 1u) {
		return ENODEV;
	}
	/* Sensor0's board profile mirrors both axes; sensor1 is unmirrored. */
	st.invert = (sensor & 15u) == 0;
	return touch_normandy_write(NORMANDY_ESD, 0xaa);
}

static int
touch_normandy_decode(const uint8_t *buf, unsigned len, bool invert,
    uint32_t *mask, int *x, int *y)
{
	if (len < 4 || !(buf[0] & 0x80u)) {
		return EINVAL;
	}
	unsigned n = buf[1] & 15u, sum = 0;
	if (n > TOUCH_MAX || len != 4u + n * 8u) {
		return EINVAL;
	}
	for (unsigned i = 0; i < len; ++i) {
		sum += buf[i];
	}
	if (sum & 255u) {
		return EIO;
	}
	uint32_t contacts = 0;
	for (unsigned i = 0; i < n; ++i) {
		const uint8_t *p = buf + 2u + i * 8u;
		unsigned id = p[0] & 15u;
		unsigned px = p[1] | ((unsigned)p[2] << 8);
		unsigned py = p[3] | ((unsigned)p[4] << 8);
		if ((p[0] & 0x80u) || id >= TOUCH_MAX || (contacts & (1u << id)) ||
		    px > 1079 || py > 2339) {
			return EINVAL;
		}
		contacts |= 1u << id;
		x[id] = invert ? 1079 - (int)px : (int)px;
		y[id] = invert ? 2339 - (int)py : (int)py;
	}
	*mask = contacts;
	return 0;
}

static int
touch_normandy(void)
{
	uint8_t buf[84];
	int x[TOUCH_MAX] = {0}, y[TOUCH_MAX] = {0};
	uint32_t mask = 0;
	uint64_t previous = st.poll_time, seen = 0;
	uint32_t irq = 0;
	if (st.latency) {
		st.poll_time = seen = mach_absolute_time();
		irq = touch_rd(st.gpio, TOUCH_GPIO_IO(122)) & 1u;
	}
	int err = touch_read(0x5d, NORMANDY_EVENT, true, buf, 12);
	if (err) {
		return err;
	}
	if (!(buf[0] & 0x80u)) {
		/* Do not discard a firmware/config request we cannot service. */
		return (buf[0] & 0x40u) ? ENOTSUP : 0;
	}
	unsigned n = buf[1] & 15u;
	if (n > TOUCH_MAX) {
		return EINVAL;
	}
	if (n > 1) {
		err = touch_read(0x5d, NORMANDY_EVENT + 12, true, buf + 12, (n - 1u) * 8u);
		if (err) {
			return err;
		}
	}
	if (st.latency) {
		uint64_t before_ns, seen_ns, read_ns;
		absolutetime_to_nanoseconds(previous, &before_ns);
		absolutetime_to_nanoseconds(seen, &seen_ns);
		absolutetime_to_nanoseconds(mach_absolute_time(), &read_ns);
		hakios_tl("tl: c before %llu seen %llu read %llu irq %u\n",
		    before_ns / 1000, seen_ns / 1000, read_ns / 1000, irq);
	}
	err = touch_normandy_decode(buf, 4u + n * 8u, st.invert, &mask, x, y);
	if (!err) {
		err = touch_normandy_write(NORMANDY_EVENT, 0);
	}
	if (!err) {
		touch_report(mask, x, y);
	}
	return err;
}

static bool
touch_se_init(void)
{
	uint32_t fw = touch_rd(st.se, SE_FW);
	uint32_t tx = touch_rd(st.se, SE_HW_TX), rx = touch_rd(st.se, SE_HW_RX);
	printf("raphael-touch: se%u fw=%#x proto=%u status=%#x tx=%#x rx=%#x ios=%#x\n",
	    19u, fw, (fw >> 8) & 0xffu, touch_rd(st.se, SE_STATUS), tx, rx,
	    touch_rd(st.se, 0x908));
	if (((fw >> 8) & 0xffu) != 3u || (touch_rd(st.se, 0x64) & 1u) ||
	    ((tx >> 24) & 0x3fu) != 32u || ((rx >> 24) & 0x3fu) != 32u ||
	    ((tx >> 16) & 0x3fu) < 2u || ((rx >> 16) & 0x3fu) < 2u) {
		printf("raphael-touch: need ABL-loaded I2C firmware and 32-bit FIFOs; probes skipped\n");
		return false;
	}
	if (touch_rd(st.se, SE_STATUS) & 0x1001u) {
		printf("raphael-touch: serial engine already busy; probes skipped\n");
		return false;
	}
	touch_wr(st.se, 0xe18, 0); /* no GSI events */
	touch_wr(st.se, 0xe1c, 0); /* mask external IRQ routing; poll local status */
	touch_wr(st.se, 0x644, 0);
	touch_wr(st.se, SE_IRQ_CLR, 0xffffffffu);
	touch_wr(st.se, 0x648, 0xffffffffu);
	touch_wr(st.se, SE_DMA, 0);
	touch_wr(st.se, 0x28, touch_rd(st.se, 0x28) | 0x7fu);
	touch_wr(st.se, 0xe30, touch_rd(st.se, 0xe30) | 0x0fu);
	touch_wr(st.se, 0x24, 0x7f);
	touch_wr(st.se, 0x20, 1);
	touch_wr(st.se, SE_CLK_SEL, 0);
	touch_wr(st.se, SE_MCLK, (7u << 4) | 1u);
	touch_wr(st.se, SE_SCL, (10u << 20) | (11u << 10) | 26u); /* 100 kHz */
	/* Linux 8-bit I2C packing: MSB on the wire, LSB byte first in FIFO. */
	touch_wr(st.se, 0x254, 0);
	touch_wr(st.se, 0x260, SE_PACK0);
	touch_wr(st.se, 0x264, SE_PACK1);
	touch_wr(st.se, 0x284, SE_PACK0);
	touch_wr(st.se, 0x288, SE_PACK1);
	touch_wr(st.se, SE_TX_WM, 0);
	touch_wr(st.se, 0x810, 0);
	touch_wr(st.se, 0x814, ((rx >> 16) & 0x3fu) - 1u);
	touch_wr(st.se, SE_IRQ_EN, SE_EVENTS);
	printf("raphael-touch: packing tx=%#x/%#x rx=%#x/%#x gran=%#x\n",
	    touch_rd(st.se, 0x260), touch_rd(st.se, 0x264),
	    touch_rd(st.se, 0x284), touch_rd(st.se, 0x288), touch_rd(st.se, 0x254));
	if (touch_rd(st.se, 0x260) != SE_PACK0 || touch_rd(st.se, 0x264) != SE_PACK1 ||
	    touch_rd(st.se, 0x284) != SE_PACK0 || touch_rd(st.se, 0x288) != SE_PACK1 ||
	    touch_rd(st.se, 0x254) != 0) {
		printf("raphael-touch: packing readback mismatch; probes skipped\n");
		return false;
	}
	if (!touch_idle_fifo()) {
		printf("raphael-touch: FIFO could not be cleared while idle; probes skipped\n");
		return false;
	}
	return true;
}

static void
touch_thread(void *arg __unused, wait_result_t result __unused)
{
	bool awake = false;
	unsigned errors = 0;
	uint64_t deadline, esd_deadline;

	st.gcc = ml_io_map(0x00100000u, 0x60000);
	st.gpio = ml_io_map(0x03d00000u, 0x7b000);
	st.se = ml_io_map(0x00c88000u, 0x4000);
	if (!st.gcc || !st.gpio || !st.se || !touch_clocks() || !touch_se_init()) {
		printf("raphael-touch: initialization failed\n");
		goto out;
	}
	/* All six pins are in SM8150's SOUTH tile; keep reset asserted while rails settle. */
	touch_gpio(122, 0, 3, 3, false, false);
	touch_gpio(54, 0, 3, 3, true, false);
	touch_gpio(98, 0, 0, 0, true, true);
	touch_gpio(100, 0, 0, 0, true, true);
	touch_wait(300);
	touch_gpio(57, 2, 0, 0, false, false);
	touch_gpio(58, 2, 0, 0, false, false);
	touch_gpio(54, 0, 3, 3, true, false);
	touch_wait(2);
	touch_gpio(54, 0, 3, 3, true, true);
	touch_wait(100);
	st.probing = true;
	int err = touch_normandy_probe();
	st.probing = false;
	if (err) {
		printf("raphael-touch: Normandy probe failed %d\n", err);
		goto out;
	}
	awake = true;
	printf("raphael-touch: GT9886 ready, 1080x2340\n");
	clock_interval_to_deadline(1, NSEC_PER_SEC, &esd_deadline);
	/* shortcut: 8 ms includes I2C time; add IRQ/suspend with power management. */
	while (!st.dead) {
		clock_interval_to_deadline(8, NSEC_PER_MSEC, &deadline);
		err = touch_normandy();
		if (err) {
			if ((errors++ % 100u) == 0) {
				printf("raphael-touch: report error %d, IRQ %#x\n", err, st.irq_status);
			}
			if (errors == 10) touch_report(0, st.x, st.y);
		} else {
			errors = 0;
		}
		if (mach_absolute_time() >= esd_deadline) {
			clock_interval_to_deadline(1, NSEC_PER_SEC, &esd_deadline);
			if (touch_normandy_write(NORMANDY_ESD, 0xaa)) {
				printf("raphael-touch: ESD tick failed\n");
				break;
			}
		}
		touch_wait_until(deadline);
	}
	touch_report(0, st.x, st.y);
out:
	if (awake && !st.dead) (void)touch_normandy_write(0x30f0, 0xcc);
	thread_terminate(current_thread());
}

void
raphael_touch_init(void)
{
	uint32_t enabled = 0;
	thread_t thread;

	if (st.started || !hakios_is_raphael() ||
	    !PE_parse_boot_argn("touchscreen", &enabled, sizeof(enabled)) || !enabled) return;
	st.started = true;
	PE_parse_boot_argn("touch_lat", &st.latency, sizeof(st.latency));
	if (kernel_thread_start(touch_thread, NULL, &thread) == KERN_SUCCESS) {
		thread_deallocate(thread);
	} else {
		printf("raphael-touch: cannot create polling thread\n");
	}
}

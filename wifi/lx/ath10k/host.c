/* SM8150 SNOC platform and the LinuxKPI calls used by ath10k, on the existing XNU layer. */
#define LX_QMI_AS_IT_IS
#include <linux/kernel.h>
#include <linux/device.h>
#include <linux/platform_device.h>
#include <linux/of_reserved_mem.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/netdevice.h>
#include <linux/skbuff.h>
#include <linux/clk.h>
#include <linux/regulator/consumer.h>
#include <linux/pwrseq/consumer.h>
#include <linux/remoteproc/qcom_rproc.h>
#include <linux/firmware/qcom/qcom_scm.h>
#include <linux/soc/qcom/smem.h>
#include <linux/soc/qcom/qmi.h>
#include <net/mac80211.h>
#include <lx_os.h>
#include "lx.h"
#include "core.h"
#include "snoc.h"

static struct platform_device phone;
static struct platform_driver *driver;
static struct device_node node = { .name = "wifi", .full_name = "/soc/wifi@18800000" };
static struct resource membase = { .start = 0x18800000, .end = 0x18ffffff, .flags = IORESOURCE_MEM };
static struct ath10k_snoc_drv_priv chip = { .hw_rev = ATH10K_HW_WCN3990, .dma_mask = DMA_BIT_MASK(35), .msa_size = 0x180000 };
static bool ready;
static void irq_detach(void);

const void *device_get_match_data(const struct device *dev) { return dev == &phone.dev ? &chip : NULL; }
struct resource *platform_get_resource_byname(struct platform_device *p, unsigned type, const char *name)
{ return p == &phone && type == IORESOURCE_MEM && !strcmp(name, "membase") ? &membase : NULL; }
int platform_get_irq(struct platform_device *p, unsigned i) { return p == &phone && i < 12 ? 446 + i : -EINVAL; }
int platform_driver_register(struct platform_driver *d)
{
	if (driver || !lx_os_radio_powered()) return -ENODEV;
	phone.name = "ath10k_snoc"; phone.id = -1; phone.dev.of_node = &node;
	phone.dev.dma_priv = &chip; phone.dev.driver = &d->driver;
	int ret = d->probe(&phone);
	if (!ret) driver = d;
	else irq_detach();
	return ret;
}
void platform_driver_unregister(struct platform_driver *d)
{ if (driver == d) { d->remove(&phone); driver = NULL; } }

const struct property *of_find_property(const struct device_node *np, const char *name, int *length)
{
	static const struct property tz = { .name = "qcom,msa-fixed-perm", .length = 0 };
	if (length) *length = 0;
	return np == &node && !strcmp(name, tz.name) ? &tz : NULL;
}
const void *of_get_property(const struct device_node *np, const char *name, int *length)
{ const struct property *p = of_find_property(np, name, length); return p ? p->value : NULL; }
int of_property_read_string(const struct device_node *np, const char *name, const char **out) { return -EINVAL; }
int of_property_read_u32_index(const struct device_node *np, const char *name, u32 index, u32 *out) { return -EINVAL; }
struct device_node *of_get_child_by_name(const struct device_node *np, const char *name) { return NULL; }
int of_reserved_mem_region_to_resource(const struct device_node *np, unsigned index, struct resource *r)
{
	if (np != &node || index || !r) return -EINVAL;
	*r = (struct resource){ .start = 0x8bc00000, .end = 0x8bd7ffff, .flags = IORESOURCE_MEM };
	return 0;
}
void *devm_memremap(struct device *dev, unsigned long address, size_t size, unsigned long flags)
{
	if (dev != &phone.dev || address != 0x8bc00000 || size != 0x180000) return ERR_PTR(-EINVAL);
	void *p = lx_os_map_registers(address, size);
	return p ? p : ERR_PTR(-ENOMEM);
}

/* ICNSS owns the five rails and QDSS until PAS shutdown; these clients borrow its powered state. */
int devm_regulator_bulk_get(struct device *dev, int count, struct regulator_bulk_data *rails)
{
	static const char *const names[] = { "vdd-0.8-cx-mx", "vdd-1.8-xo", "vdd-1.3-rfa", "vdd-3.3-ch0", "vdd-3.3-ch1" };
	if (dev != &phone.dev || count != 5 || !rails) return -EINVAL;
	for (int i = 0; i < count; i++) {
		if (strcmp(rails[i].supply, names[i])) return -EINVAL;
		rails[i].consumer = (void *)&chip;
	}
	return lx_os_radio_powered() ? 0 : -ENODEV;
}
int regulator_bulk_enable(int count, struct regulator_bulk_data *rails) { return count == 5 && rails && lx_os_radio_powered() ? 0 : -ENODEV; }
int regulator_bulk_disable(int count, struct regulator_bulk_data *rails) { return count == 5 && rails ? 0 : -EINVAL; }
int devm_clk_bulk_get_optional(struct device *dev, int count, struct clk_bulk_data *clocks)
{
	if (dev != &phone.dev || count != 2 || !clocks) return -EINVAL;
	for (int i = 0; i < count; i++) if (strcmp(clocks[i].id, "cxo_ref_clk_pin") && strcmp(clocks[i].id, "qdss")) return -EINVAL;
	return lx_os_radio_powered() ? 0 : -ENODEV;
}
int clk_bulk_prepare_enable(int count, struct clk_bulk_data *clocks) { return count == 2 && clocks && lx_os_radio_powered() ? 0 : -ENODEV; }
void clk_bulk_disable_unprepare(int count, struct clk_bulk_data *clocks) { }
struct pwrseq_desc *devm_pwrseq_get(struct device *dev, const char *name) { return ERR_PTR(-EPROBE_DEFER); }
int pwrseq_power_on(struct pwrseq_desc *p) { return p ? -EOPNOTSUPP : 0; }
int pwrseq_power_off(struct pwrseq_desc *p) { return p ? -EOPNOTSUPP : 0; }
void *qcom_register_ssr_notifier(const char *name, struct notifier_block *nb)
{ return !strcmp(name, "mpss") && nb ? nb : ERR_PTR(-EINVAL); }
int qcom_unregister_ssr_notifier(void *cookie, struct notifier_block *nb) { return cookie == nb ? 0 : -EINVAL; }
void *qcom_smem_get(unsigned host, unsigned item, size_t *size) { return ERR_PTR(-ENOENT); }
int qcom_scm_assign_mem(phys_addr_t address, size_t size, u64 *src, const struct qcom_scm_vmperm *dst, unsigned count)
{ return -EOPNOTSUPP; } /* MSA permissions are established by ICNSS before this driver starts. */

int linux_dma_tag_init(struct device *dev, u64 mask) { return dev == &phone.dev && mask == DMA_BIT_MASK(35) ? 0 : -EINVAL; }
int linux_dma_tag_init_coherent(struct device *dev, u64 mask) { return linux_dma_tag_init(dev, mask); }
void *linuxkpi_dmam_alloc_coherent(struct device *dev, size_t size, dma_addr_t *handle, gfp_t flags)
{ return linux_dma_alloc_coherent(dev, size, handle, flags); }
struct net_device *linuxkpi_alloc_netdev(size_t size, const char *name, uint32_t type, void (*setup)(struct net_device *))
{
	struct net_device *dev = kzalloc(sizeof(*dev) + size, GFP_KERNEL);
	if (dev) { strlcpy(dev->name, name, sizeof(dev->name)); if (setup) setup(dev); }
	return dev;
}
void linuxkpi_free_netdev(struct net_device *dev) { kfree(dev); }
void netif_threaded_enable(struct net_device *dev) { dev->threaded = 1; }

struct managed { struct managed *next; void (*release)(struct device *, void *); size_t size; uint8_t data[]; };
static struct managed *managed;
void *lkpi_devres_alloc(void (*release)(struct device *, void *), size_t size, gfp_t flags)
{
	struct managed *m = kzalloc(sizeof(*m) + size, flags);
	if (!m) return NULL;
	m->release = release; m->size = size;
	return m->data;
}
void lkpi_devres_add(struct device *dev, void *p)
{ struct managed *m = container_of(p, struct managed, data); m->next = managed; managed = m; }
void lkpi_devm_kmalloc_release(struct device *dev, void *p) { }
static void managed_free(void)
{
	while (managed) { struct managed *m = managed; managed = m->next; m->release(&phone.dev, m->data); kfree(m); }
}

static struct { irq_handler_t call; void *arg; unsigned irq; bool enabled; } irqs[12];
static void irq_run(void *arg)
{
	unsigned n = (uintptr_t)arg;
	if (irqs[n].enabled) irqs[n].call(irqs[n].irq, irqs[n].arg);
	if (irqs[n].enabled) lx_os_irq_enable(n);
}
int lkpi_request_irq(struct device *dev, unsigned irq, irq_handler_t call, irq_handler_t thread,
    unsigned long flags, const char *name, void *arg)
{
	if (irq < 446 || irq >= 458 || !call || thread) return -EINVAL;
	unsigned n = irq - 446;
	if (irqs[n].call) return -EBUSY;
	irqs[n].call = call; irqs[n].arg = arg; irqs[n].irq = irq;
	int error = lx_os_irq_attach(n, irq_run, (void *)(uintptr_t)n);
	if (error) { irqs[n].call = NULL; return -error; }
	irqs[n].enabled = !(flags & IRQF_NO_AUTOEN);
	if (irqs[n].enabled) lx_os_irq_enable(n);
	return 0;
}
int lkpi_enable_irq(unsigned irq)
{ if (irq < 446 || irq >= 458 || !irqs[irq-446].call) return -EINVAL; irqs[irq-446].enabled = true; lx_os_irq_enable(irq-446); return 0; }
void lkpi_disable_irq(unsigned irq)
{ if (irq >= 446 && irq < 458) { irqs[irq-446].enabled = false; lx_os_irq_disable(irq-446); } }
void lkpi_free_irq(unsigned irq, void *arg)
{ if (irq >= 446 && irq < 458 && irqs[irq-446].arg == arg) { lkpi_disable_irq(irq); irqs[irq-446].call = NULL; } }
static void irq_detach(void)
{ lx_os_irq_detach_all(); memset(irqs, 0, sizeof(irqs)); }

static struct { struct napi_struct *napi; struct work_struct work; struct workqueue_struct *queue; bool enabled, rerun; } poller;
static void napi_work(struct work_struct *work)
{
	for (;;) {
		lx_os_lock(); bool enabled = poller.enabled; poller.rerun = false; lx_os_unlock();
		int done = enabled ? poller.napi->poll(poller.napi, 64) : 0;
		lx_os_lock();
		bool again = poller.enabled && (done >= 64 || poller.rerun);
		if (!again) clear_bit(NAPI_STATE_SCHED, &poller.napi->state);
		lx_os_unlock();
		if (!again) break;
	}
}
void linuxkpi_netif_napi_add(struct net_device *dev, struct napi_struct *napi, int (*poll)(struct napi_struct *, int))
{ napi->dev = dev; napi->poll = poll; napi->budget = 64; poller.napi = napi; INIT_WORK(&poller.work, napi_work); }
void linuxkpi_napi_synchronize(struct napi_struct *napi) { flush_work(&poller.work); }
void linuxkpi_napi_disable(struct napi_struct *napi) { lx_os_lock(); poller.enabled = false; lx_os_unlock(); cancel_work_sync(&poller.work); clear_bit(NAPI_STATE_SCHED, &napi->state); }
void linuxkpi_napi_enable(struct napi_struct *napi) { lx_os_lock(); poller.enabled = true; lx_os_unlock(); }
void linuxkpi_netif_napi_del(struct napi_struct *napi) { linuxkpi_napi_disable(napi); poller.napi = NULL; }
bool linuxkpi_napi_schedule(struct napi_struct *napi)
{
	lx_os_lock();
	if (!poller.enabled) { lx_os_unlock(); return false; }
	poller.rerun = true; set_bit(NAPI_STATE_SCHED, &napi->state);
	lx_os_unlock();
	return queue_work(poller.queue, &poller.work);
}
bool linuxkpi_napi_complete(struct napi_struct *napi) { return true; }

/* This stack sends through ops->tx; it has no mac80211 TX queues. */
void linuxkpi_ieee80211_txq_schedule_start(struct ieee80211_hw *hw, uint8_t ac) { }
struct ieee80211_txq *linuxkpi_ieee80211_next_txq(struct ieee80211_hw *hw, uint8_t ac) { return NULL; }
void linuxkpi_ieee80211_schedule_txq(struct ieee80211_hw *hw, struct ieee80211_txq *q, bool without) { }
struct sk_buff *linuxkpi_ieee80211_tx_dequeue(struct ieee80211_hw *hw, struct ieee80211_txq *q) { return NULL; }
void linuxkpi_ieee80211_txq_get_depth(struct ieee80211_txq *q, unsigned long *frames, unsigned long *bytes) { if (frames) *frames = 0; if (bytes) *bytes = 0; }
void linuxkpi_ieee80211_stop_queue(struct ieee80211_hw *hw, int q) { ieee80211_stop_queues(hw); }
void linuxkpi_ieee80211_wake_queue(struct ieee80211_hw *hw, int q) { ieee80211_wake_queues(hw); }
uint8_t linuxkpi_ieee80211_get_tid(struct ieee80211_hdr *hdr, bool nonqos) { return ieee80211_is_data_qos(hdr->frame_control) ? *ieee80211_get_qos_ctl(hdr) & 15 : 0; }
uint32_t linuxkpi_cfg80211_calculate_bitrate(struct rate_info *r) { return r->legacy; }
struct linuxkpi_ieee80211_regdomain *lkpi_get_linuxkpi_ieee80211_regdomain(size_t n)
{ return kzalloc(sizeof(struct linuxkpi_ieee80211_regdomain) + n * sizeof(struct ieee80211_reg_rule), GFP_KERNEL); }
int linuxkpi_device_get_mac_address(struct device *dev, char *address) { return lx_os_radio_address((void *)address) ? 0 : -ENOENT; }

struct sk_buff *linuxkpi_skb_copy(const struct sk_buff *skb, gfp_t flags)
{
	struct sk_buff *copy = dev_alloc_skb(skb_headroom(skb) + skb->len);
	if (!copy) return NULL;
	skb_reserve(copy, skb_headroom(skb)); skb_put_data(copy, skb->data, skb->len);
	memcpy(copy->cb, skb->cb, sizeof(copy->cb)); copy->priority = skb->priority; copy->protocol = skb->protocol;
	return copy;
}
const u8 rfc1042_header[] = { 0xaa, 0xaa, 3, 0, 0, 0 };
void nanouptime(struct timespec *t) { unsigned long long now = lx_os_nanoseconds(); t->tv_sec = now / 1000000000; t->tv_nsec = now % 1000000000; }
void DELAY(int us) { if (us > 0) lx_pause_ms((us + 999) / 1000); }
int pause_sbt(const char *name, sbintime_t sbt, sbintime_t precision, int flags) { if (sbt > 0) lx_pause_ms((unsigned)(((uint64_t)sbt * 1000) >> 32)); return 0; }
int eventratecheck(struct timeval *last, int *count, int max)
{ unsigned long long now = lx_os_nanoseconds() / 1000000000; if ((unsigned long long)last->tv_sec != now) { last->tv_sec = now; *count = 0; } return max < 0 || (*count)++ < max; }
int device_printf(device_t dev, const char *fmt, ...)
{
	char line[400]; va_list ap; va_start(ap, fmt);
	int n;
	if (!strcmp(fmt, "%pV")) { struct va_format *v = va_arg(ap, struct va_format *); n = vsnprintf(line, sizeof(line), v->fmt, *v->va); }
	else n = vsnprintf(line, sizeof(line), fmt, ap);
	va_end(ap); lx_os_print(line); lx_os_print("\n"); return n;
}
int lkpi_hex_dump_to_buffer(const void *buf, size_t len, int rows, int group, char *line, size_t size, bool ascii)
{ size_t at = 0; const u8 *p = buf; for (size_t i = 0; i < len && i < 32 && at + 4 < size; i++) at += snprintf(line + at, size - at, "%02x ", p[i]); if (size) line[at] = 0; return at; }

int lx_qmi_send_request(struct qmi_handle *h, struct sockaddr_qrtr *sq, struct qmi_txn *tx, int id, size_t size,
    const struct qmi_elem_info *ei, const void *data) { return qmi_send_request(h, sq, tx, id, size, ei, data); }
extern int ath10k_snoc_host_register(void);
extern void ath10k_snoc_host_unregister(void);
int lx_prepare(void) { return lx_pool_init(); }
int lx_start(void)
{
	ath10k_frame_mode = ATH10K_HW_TXRX_ETHERNET;
	int error = lx_base_init();
	if (!error) error = lx_pool_init();
	if (!error && !poller.queue && !(poller.queue = alloc_ordered_workqueue("ath10k-napi", 0))) error = ENOMEM;
	if (!error) error = ath10k_snoc_host_register();
	if (error) { managed_free(); return error < 0 ? -error : error; }
	struct ath10k *ar = platform_get_drvdata(&phone);
	for (unsigned ms = 0; ms < 20000 && !test_bit(ATH10K_SNOC_FLAG_REGISTERED, &ath10k_snoc_priv(ar)->flags); ms++) lx_pause_ms(1);
	flush_work(&ar->register_work);
	if (!ar->hw->wiphy->bands[NL80211_BAND_2GHZ]) return ENODEV;
	ready = true;
	if (lx_os_option("wifi_scan")) error = lx_station_scan();
	if (!error && lx_os_option("wifi_join")) error = lx_station_join();
	if (!error && lx_os_option("wifi_keep")) error = lx_station_offer();
	return error;
}
void lx_stop(void)
{
	if (!driver) return;
	if (ready) { lx_station_withdraw(); lx_station_leave(); ready = false; }
	ath10k_snoc_host_unregister(); irq_detach(); managed_free();
}
int lx_transmit(const unsigned char *p, unsigned long n) { return ready ? lx_station_send(p, n) : ENXIO; }

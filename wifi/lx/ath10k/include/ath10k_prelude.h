#include <linux/delay.h>
#include <linux/spinlock.h>
DEFINE_LOCK_GUARD_1(spinlock_bh, spinlock_t,
    spin_lock_bh(_T->lock), spin_unlock_bh(_T->lock))
#ifndef IRQF_NO_AUTOEN
#define IRQF_NO_AUTOEN 0x00080000
#endif
struct net_device;
void netif_threaded_enable(struct net_device*);
struct device;
void *devm_memremap(struct device*,unsigned long,size_t,unsigned long);

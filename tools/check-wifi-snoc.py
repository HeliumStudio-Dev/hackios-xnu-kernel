#!/usr/bin/env python3
"""Exercise the SNOC IRQ and NAPI bridge from its actual source without hardware."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
s = (root / 'wifi/lx/ath10k/host.c').read_text()
irq = s[s.index('static struct { irq_handler_t call;'):s.index('/* This stack sends')]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#define IRQF_NO_AUTOEN 0x80000
#define NAPI_STATE_SCHED 1
#define INIT_WORK(w,fn) ((w)->func=(fn))
struct work_struct { void (*func)(struct work_struct *); };
struct workqueue_struct { int unused; };
struct device { int unused; };
struct net_device { int unused; };
struct napi_struct { struct net_device *dev;int (*poll)(struct napi_struct*,int);int budget;unsigned long state; };
typedef int (*irq_handler_t)(int,void*);
static void set_bit(unsigned n, unsigned long *v) { *v|=1ul<<n; }
static void clear_bit(unsigned n, unsigned long *v) { *v&=~(1ul<<n); }
static unsigned locked, queued, flushed, canceled, attaches, enables, disables, detached, calls;
static bool fail_attach;
static void lx_os_lock(void) { assert(!locked);locked=1; }
static void lx_os_unlock(void) { assert(locked);locked=0; }
static int lx_os_irq_attach(unsigned n,void (*fn)(void*),void *p) { assert(n<12&&fn&&p==(void*)(uintptr_t)n);attaches++;return fail_attach?EBUSY:0; }
static void lx_os_irq_enable(unsigned n) { assert(n<12);enables++; }
static void lx_os_irq_disable(unsigned n) { assert(n<12);disables++; }
static void lx_os_irq_detach_all(void) { detached++; }
static bool queue_work(struct workqueue_struct *q,struct work_struct *w) { assert(!locked&&w);queued++;return true; }
static void flush_work(struct work_struct *w) { assert(!locked);flushed++; }
static void cancel_work_sync(struct work_struct *w) { assert(!locked);canceled++; }
''' + irq + r'''
static int handler(int irq,void *p) { assert(irq==446&&p==(void*)123);calls++;return 1; }
static unsigned polls, scenario;
static int poll(struct napi_struct *n,int budget) {
 assert(budget==64&&!locked);polls++;
 if(scenario==1&&polls==1)return 64;
 if(scenario==2&&polls==1)linuxkpi_napi_schedule(n);
 if(scenario==3)linuxkpi_napi_disable(n);
 return 0;
}
int main(void) {
 assert(lkpi_request_irq(NULL,445,handler,NULL,0,"",(void*)123)==-EINVAL&&!attaches);
 assert(lkpi_request_irq(NULL,458,handler,NULL,0,"",(void*)123)==-EINVAL&&!attaches);
 assert(lkpi_request_irq(NULL,446,NULL,NULL,0,"",(void*)123)==-EINVAL&&!attaches);
 fail_attach=true;assert(lkpi_request_irq(NULL,446,handler,NULL,0,"",(void*)123)==-EBUSY&&!irqs[0].call);fail_attach=false;
 assert(!lkpi_request_irq(NULL,446,handler,NULL,IRQF_NO_AUTOEN,"",(void*)123)&&!enables);
 assert(lkpi_request_irq(NULL,446,handler,NULL,0,"",(void*)123)==-EBUSY);
 irq_run(0);assert(!calls&&!enables);
 assert(!lkpi_enable_irq(446)&&enables==1);irq_run(0);assert(calls==1&&enables==2);
 lkpi_disable_irq(446);irq_run(0);assert(calls==1&&disables==1);
 lkpi_free_irq(446,(void*)456);assert(irqs[0].call);
 lkpi_free_irq(446,(void*)123);assert(!irqs[0].call);
 irq_detach();assert(detached==1);
 struct napi_struct n={0};struct net_device dev={0};
 linuxkpi_netif_napi_add(&dev,&n,poll);assert(n.dev==&dev&&n.budget==64);
 assert(!linuxkpi_napi_schedule(&n)&&!queued);
 for(scenario=0;scenario<4;scenario++) {
  polls=0;linuxkpi_napi_enable(&n);assert(linuxkpi_napi_schedule(&n));napi_work(&poller.work);
  assert(polls==(scenario==1||scenario==2?2u:1u)&&!(n.state&(1ul<<NAPI_STATE_SCHED))&&!locked);
 }
 linuxkpi_napi_synchronize(&n);assert(flushed==1);
 linuxkpi_netif_napi_del(&n);assert(!poller.napi&&!poller.enabled&&canceled>=2&&!locked);
 puts("PASS: SNOC IRQ bounds, deferred enable, failed attach, handler lifecycle, NAPI budget/races and shutdown");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-snoc-') as tmp:
    p = Path(tmp)
    (p / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                    str(p / 'check.c'), '-o', str(p / 'check')], check=True)
    subprocess.run([str(p / 'check')], check=True)

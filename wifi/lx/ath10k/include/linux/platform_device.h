#ifndef _ATH10K_PLATFORM_DEVICE_H
#define _ATH10K_PLATFORM_DEVICE_H
#include <linux/device.h>
#include <linux/ioport.h>
struct platform_device {
 const char *name;int id;struct device dev;
 struct resource *resource;unsigned num_resources;
};
struct platform_driver {
 int (*probe)(struct platform_device*);
 void (*remove)(struct platform_device*);
 void (*shutdown)(struct platform_device*);
 struct device_driver driver;
};
struct resource *platform_get_resource_byname(struct platform_device*,unsigned,const char*);
int platform_get_irq(struct platform_device*,unsigned);
int platform_driver_register(struct platform_driver*);
void platform_driver_unregister(struct platform_driver*);
static inline void platform_set_drvdata(struct platform_device *p,void *v) { dev_set_drvdata(&p->dev,v); }
static inline void *platform_get_drvdata(struct platform_device *p) { return dev_get_drvdata(&p->dev); }
#define module_platform_driver(drv) \
 int ath10k_snoc_host_register(void) { return platform_driver_register(&(drv)); } \
 void ath10k_snoc_host_unregister(void) { platform_driver_unregister(&(drv)); }
#endif

#ifndef _ATH10K_PWRSEQ_H
#define _ATH10K_PWRSEQ_H
#include <linux/device.h>
struct pwrseq_desc;
struct pwrseq_desc *devm_pwrseq_get(struct device*,const char*);
int pwrseq_power_on(struct pwrseq_desc*);
int pwrseq_power_off(struct pwrseq_desc*);
#endif

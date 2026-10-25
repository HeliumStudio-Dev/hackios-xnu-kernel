#ifndef _ATH10K_REGULATOR_CONSUMER_H
#define _ATH10K_REGULATOR_CONSUMER_H
#include <linux/device.h>
struct regulator;
struct regulator_bulk_data { const char *supply;struct regulator *consumer; };
int devm_regulator_bulk_get(struct device*,int,struct regulator_bulk_data*);
int regulator_bulk_enable(int,struct regulator_bulk_data*);
int regulator_bulk_disable(int,struct regulator_bulk_data*);
#endif

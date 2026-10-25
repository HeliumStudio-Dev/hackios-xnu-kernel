#ifndef _ATH10K_CLK_H
#define _ATH10K_CLK_H
#include <linux/device.h>
struct clk;
struct clk_bulk_data { const char *id;struct clk *clk; };
int devm_clk_bulk_get_optional(struct device*,int,struct clk_bulk_data*);
int clk_bulk_prepare_enable(int,struct clk_bulk_data*);
void clk_bulk_disable_unprepare(int,struct clk_bulk_data*);
#endif

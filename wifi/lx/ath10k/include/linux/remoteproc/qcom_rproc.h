#ifndef _ATH10K_RPROC_H
#define _ATH10K_RPROC_H
#include <linux/notifier.h>
struct qcom_ssr_notify_data { const char *name;bool crashed; };
#define QCOM_SSR_BEFORE_POWERUP 0
#define QCOM_SSR_AFTER_POWERUP 1
#define QCOM_SSR_BEFORE_SHUTDOWN 2
#define QCOM_SSR_AFTER_SHUTDOWN 3
void *qcom_register_ssr_notifier(const char*,struct notifier_block*);
int qcom_unregister_ssr_notifier(void*,struct notifier_block*);
#endif

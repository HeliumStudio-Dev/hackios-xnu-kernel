#ifndef _ATH10K_QCOM_SMEM_H
#define _ATH10K_QCOM_SMEM_H
#include <linux/types.h>
#define QCOM_SMEM_HOST_ANY UINT_MAX
void *qcom_smem_get(unsigned,unsigned,size_t*);
#endif

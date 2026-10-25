#ifndef _ATH10K_QCOM_SCM_H
#define _ATH10K_QCOM_SCM_H
#include <linux/types.h>
#define QCOM_SCM_VMID_HLOS 3
#define QCOM_SCM_VMID_MSS_MSA 15
#define QCOM_SCM_VMID_WLAN 24
#define QCOM_SCM_VMID_WLAN_CE 25
#define QCOM_SCM_PERM_RW 6
struct qcom_scm_vmperm { int vmid,perm; };
int qcom_scm_assign_mem(phys_addr_t,size_t,u64*,const struct qcom_scm_vmperm*,unsigned);
#endif

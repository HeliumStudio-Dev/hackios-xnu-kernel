#ifndef _ATH10K_COMPAT_NVMEM_H
#define _ATH10K_COMPAT_NVMEM_H
#include <linux/err.h>
#include <linux/errno.h>
struct nvmem_cell;
static inline struct nvmem_cell *devm_nvmem_cell_get(struct device *dev,const char *name) { return ERR_PTR(-ENOENT); }
static inline void *nvmem_cell_read(struct nvmem_cell *cell,size_t *size) { return ERR_PTR(-EOPNOTSUPP); }
#endif

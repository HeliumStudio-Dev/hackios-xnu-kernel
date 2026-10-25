#ifndef _ATH10K_COMPAT_OF_H
#define _ATH10K_COMPAT_OF_H
#include_next <linux/of.h>
static inline int of_property_read_u8_array(const struct device_node *np, const char *name, u8 *out, size_t count) {
    int size=0; const void *data=of_get_property(np,name,&size);
    if (!data) return -EINVAL;
    if (size<0 || (size_t)size<count) return -EOVERFLOW;
    memcpy(out,data,count); return 0;
}
static inline int of_property_read_u8(const struct device_node *np,const char *name,u8 *out) { return of_property_read_u8_array(np,name,out,1); }
static inline int of_property_read_string_index(const struct device_node *np,const char *name,int index,const char **out) {
    int size=0; const char *data=of_get_property(np,name,&size);
    if (!data || size<0 || index<0) return -EINVAL;
    for (int i=0;size>0;i++) {
        size_t length=strnlen(data,(size_t)size);
        if (length==(size_t)size) return -EILSEQ;
        if (i==index) { *out=data;return 0; }
        size-=(int)length+1;data+=length+1;
    }
    return -ENODATA;
}
static inline int device_property_read_u32(struct device *dev,const char *name,u32 *out) { return of_property_read_u32(dev->of_node,name,out); }

const void *device_get_match_data(const struct device*);
#endif

#ifndef LX_SAE_PLATFORM_H
#define LX_SAE_PLATFORM_H
#include <stddef.h>
#include <stdint.h>
void *lx_sae_malloc(size_t);
void *lx_sae_calloc(size_t, size_t);
void *lx_sae_realloc(void *, size_t);
void lx_sae_free(void *);
char *lx_sae_strdup(const char *);
void lx_sae_abort(void) __attribute__((noreturn));
int lx_sae_random(void *, size_t);
#ifndef LX_SAE_HOST
#define abs lx_sae_abs
int lx_sae_abs(int);
#endif
#define os_malloc lx_sae_malloc
#define os_realloc lx_sae_realloc
#define os_free lx_sae_free
#define os_strdup lx_sae_strdup
#define abort lx_sae_abort
#endif


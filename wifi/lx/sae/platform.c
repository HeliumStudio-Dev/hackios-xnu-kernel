#include "utils/includes.h"
#include "utils/common.h"
#ifdef LX_SAE_HOST
#include <time.h>
#else
#include LX_HAKIOS_LX_H
int lx_sae_abs(int n) { return n < 0 ? -n : n; }
#endif

void *lx_sae_malloc(size_t n)
{
	if (n > SIZE_MAX - sizeof(size_t)) return NULL;
#ifdef LX_SAE_HOST
	size_t *p = calloc(1, sizeof(size_t) + n);
#else
	size_t *p = lx_os_alloc(sizeof(size_t) + n);
#endif
	if (p) *p++ = n;
	return p;
}
void lx_sae_free(void *ptr)
{
	if (!ptr) return;
	size_t *p = (size_t *)ptr - 1;
#ifdef LX_SAE_HOST
	free(p);
#else
	lx_os_free(p, sizeof(size_t) + *p);
#endif
}
void *lx_sae_calloc(size_t count, size_t size) { return size && count > SIZE_MAX / size ? NULL : lx_sae_malloc(count * size); }
void *os_zalloc(size_t n) { return lx_sae_malloc(n); }
void *lx_sae_realloc(void *old, size_t n)
{
	void *p = lx_sae_malloc(n);
	if (p && old) { size_t was = ((size_t *)old)[-1]; memcpy(p, old, was < n ? was : n); lx_sae_free(old); }
	return p;
}
char *lx_sae_strdup(const char *s) { size_t n = strlen(s) + 1; char *p = lx_sae_malloc(n); if (p) memcpy(p, s, n); return p; }
void lx_sae_abort(void)
{
#ifdef LX_SAE_HOST
	__builtin_trap();
#else
	lx_os_panic("SAE buffer invariant failed");
#endif
}
int lx_sae_random(void *p, size_t n)
{
#ifdef LX_SAE_HOST
	FILE *f = fopen("/dev/urandom", "rb"); if (!f) return -1;
	int good = fread(p, 1, n, f) == n; fclose(f); return good ? 0 : -1;
#else
	lx_os_random(p, n); return 0;
#endif
}
int os_get_random(unsigned char *p, size_t n) { return lx_sae_random(p, n); }
int random_get_bytes(void *p, size_t n) { return lx_sae_random(p, n); }
int os_get_reltime(struct os_reltime *t)
{
#ifdef LX_SAE_HOST
	struct timespec now; if (clock_gettime(CLOCK_MONOTONIC, &now)) return -1;
	t->sec = now.tv_sec; t->usec = now.tv_nsec / 1000;
#else
	unsigned long long us = lx_os_nanoseconds() / 1000; t->sec = us / 1000000; t->usec = us % 1000000;
#endif
	return 0;
}
void forced_memzero(void *p, size_t n) { volatile unsigned char *v = p; while (n--) *v++ = 0; }
void bin_clear_free(void *p, size_t n) { if (p) { forced_memzero(p, n); os_free(p); } }
int os_memcmp_const(const void *a, const void *b, size_t n)
{ const unsigned char *x = a, *y = b; unsigned diff = 0; while (n--) diff |= *x++ ^ *y++; return diff; }
void buf_shift_right(u8 *p, size_t n, size_t bits)
{
	if (!n || !bits) return;
	if (bits >= 8) lx_sae_abort();
	for (size_t i = n - 1; i; i--) p[i] = p[i-1] << (8-bits) | p[i] >> bits;
	p[0] >>= bits;
}
size_t int_array_len(const int *p) { size_t n = 0; while (p && p[n]) n++; return n; }
int hexstr2bin(const char *s, u8 *out, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		unsigned byte = 0;
		for (unsigned j = 0; j < 2; j++) {
			unsigned char c = *s++; unsigned v;
			if (c >= '0' && c <= '9') v = c-'0';
			else if (c >= 'a' && c <= 'f') v = c-'a'+10;
			else if (c >= 'A' && c <= 'F') v = c-'A'+10;
			else return -1;
			byte = byte * 16 + v;
		}
		out[i] = byte;
	}
	return 0;
}


/* hostap crypto.h on Mbed TLS: group 19 (P-256), with XNU's random source. */
#include "utils/includes.h"
#include "utils/common.h"
#include "crypto/crypto.h"
#include "common/wpa_common.h"
#include <mbedtls/bignum.h>
#include <mbedtls/ecp.h>
#include <mbedtls/sha256.h>
#include <mbedtls/cipher.h>
#include <mbedtls/cmac.h>

struct crypto_bignum { mbedtls_mpi n; };
struct crypto_ec_point { mbedtls_ecp_point p; };
struct crypto_ec { mbedtls_ecp_group group; struct crypto_bignum a; };

static int rng(void *arg, unsigned char *buf, size_t n) { return lx_sae_random(buf, n); }
struct crypto_bignum *crypto_bignum_init(void)
{ struct crypto_bignum *b = os_zalloc(sizeof(*b)); if (b) mbedtls_mpi_init(&b->n); return b; }
void crypto_bignum_deinit(struct crypto_bignum *b, int clear)
{ if (b) { mbedtls_mpi_free(&b->n); os_free(b); } }
struct crypto_bignum *crypto_bignum_init_set(const u8 *data, size_t n)
{ struct crypto_bignum *b = crypto_bignum_init(); if (b && mbedtls_mpi_read_binary(&b->n, data, n)) { crypto_bignum_deinit(b, 1); b = NULL; } return b; }
struct crypto_bignum *crypto_bignum_init_uint(unsigned int n)
{ struct crypto_bignum *b = crypto_bignum_init(); if (b && mbedtls_mpi_lset(&b->n, n)) { crypto_bignum_deinit(b, 1); b = NULL; } return b; }
int crypto_bignum_to_bin(const struct crypto_bignum *b, u8 *out, size_t size, size_t pad)
{ size_t n = mbedtls_mpi_size(&b->n); if (n < pad) n = pad; return n > size || mbedtls_mpi_write_binary(&b->n, out, n) ? -1 : (int)n; }
int crypto_bignum_cmp(const struct crypto_bignum *a, const struct crypto_bignum *b) { return mbedtls_mpi_cmp_mpi(&a->n, &b->n); }
int crypto_bignum_is_zero(const struct crypto_bignum *a) { return mbedtls_mpi_cmp_int(&a->n, 0) == 0; }
int crypto_bignum_is_one(const struct crypto_bignum *a) { return mbedtls_mpi_cmp_int(&a->n, 1) == 0; }
int crypto_bignum_is_odd(const struct crypto_bignum *a) { return mbedtls_mpi_get_bit(&a->n, 0); }
int crypto_bignum_rand(struct crypto_bignum *a, const struct crypto_bignum *max) { return mbedtls_mpi_random(&a->n, 0, &max->n, rng, NULL); }
int crypto_bignum_add(const struct crypto_bignum *a, const struct crypto_bignum *b, struct crypto_bignum *c) { return mbedtls_mpi_add_mpi(&c->n, &a->n, &b->n); }
int crypto_bignum_sub(const struct crypto_bignum *a, const struct crypto_bignum *b, struct crypto_bignum *c) { return mbedtls_mpi_sub_mpi(&c->n, &a->n, &b->n); }
int crypto_bignum_mod(const struct crypto_bignum *a, const struct crypto_bignum *b, struct crypto_bignum *c) { return mbedtls_mpi_mod_mpi(&c->n, &a->n, &b->n); }
int crypto_bignum_div(const struct crypto_bignum *a, const struct crypto_bignum *b, struct crypto_bignum *c) { return mbedtls_mpi_div_mpi(&c->n, NULL, &a->n, &b->n); }
int crypto_bignum_rshift(const struct crypto_bignum *a, int n, struct crypto_bignum *c) { return n < 0 || mbedtls_mpi_copy(&c->n, &a->n) ? -1 : mbedtls_mpi_shift_r(&c->n, n); }
int crypto_bignum_inverse(const struct crypto_bignum *a, const struct crypto_bignum *mod, struct crypto_bignum *c) { return mbedtls_mpi_inv_mod(&c->n, &a->n, &mod->n); }
int crypto_bignum_exptmod(const struct crypto_bignum *a, const struct crypto_bignum *b, const struct crypto_bignum *mod, struct crypto_bignum *c)
{
	/* hostap permits output to alias its exponent; Mbed TLS does not. */
	mbedtls_mpi t; mbedtls_mpi_init(&t);
	int e = mbedtls_mpi_exp_mod(&t, &a->n, &b->n, &mod->n, NULL);
	if (!e) e = mbedtls_mpi_copy(&c->n, &t);
	mbedtls_mpi_free(&t); return e;
}
int crypto_bignum_addmod(const struct crypto_bignum *a, const struct crypto_bignum *b, const struct crypto_bignum *mod, struct crypto_bignum *c)
{ return crypto_bignum_add(a, b, c) || crypto_bignum_mod(c, mod, c) ? -1 : 0; }
int crypto_bignum_mulmod(const struct crypto_bignum *a, const struct crypto_bignum *b, const struct crypto_bignum *mod, struct crypto_bignum *c)
{ mbedtls_mpi t; mbedtls_mpi_init(&t); int e = mbedtls_mpi_mul_mpi(&t, &a->n, &b->n); if (!e) e = mbedtls_mpi_mod_mpi(&c->n, &t, &mod->n); mbedtls_mpi_free(&t); return e; }
int crypto_bignum_sqrmod(const struct crypto_bignum *a, const struct crypto_bignum *mod, struct crypto_bignum *c) { return crypto_bignum_mulmod(a, a, mod, c); }
int crypto_bignum_legendre(const struct crypto_bignum *a, const struct crypto_bignum *p)
{
	mbedtls_mpi exponent, value; mbedtls_mpi_init(&exponent); mbedtls_mpi_init(&value);
	int e = mbedtls_mpi_sub_int(&exponent, &p->n, 1);
	if (!e) e = mbedtls_mpi_shift_r(&exponent, 1);
	if (!e) e = mbedtls_mpi_exp_mod(&value, &a->n, &exponent, &p->n, NULL);
	int result = e ? -2 : mbedtls_mpi_cmp_int(&value, 0) == 0 ? 0 : mbedtls_mpi_cmp_int(&value, 1) == 0 ? 1 : -1;
	mbedtls_mpi_free(&exponent); mbedtls_mpi_free(&value); return result;
}

struct crypto_ec *crypto_ec_init(int group)
{
	if (group != 19) return NULL;
	struct crypto_ec *e = os_zalloc(sizeof(*e));
	if (!e) return NULL;
	mbedtls_ecp_group_init(&e->group); mbedtls_mpi_init(&e->a.n);
	if (mbedtls_ecp_group_load(&e->group, MBEDTLS_ECP_DP_SECP256R1) || mbedtls_mpi_sub_int(&e->a.n, &e->group.P, 3)) {
		mbedtls_ecp_group_free(&e->group); mbedtls_mpi_free(&e->a.n); os_free(e); return NULL;
	}
	return e;
}
void crypto_ec_deinit(struct crypto_ec *e) { if (e) { mbedtls_ecp_group_free(&e->group); mbedtls_mpi_free(&e->a.n); os_free(e); } }
size_t crypto_ec_prime_len(struct crypto_ec *e) { return mbedtls_mpi_size(&e->group.P); }
size_t crypto_ec_prime_len_bits(struct crypto_ec *e) { return mbedtls_mpi_bitlen(&e->group.P); }
size_t crypto_ec_order_len(struct crypto_ec *e) { return mbedtls_mpi_size(&e->group.N); }
const struct crypto_bignum *crypto_ec_get_prime(struct crypto_ec *e) { return (const void *)&e->group.P; }
const struct crypto_bignum *crypto_ec_get_order(struct crypto_ec *e) { return (const void *)&e->group.N; }
const struct crypto_bignum *crypto_ec_get_a(struct crypto_ec *e) { return &e->a; }
const struct crypto_bignum *crypto_ec_get_b(struct crypto_ec *e) { return (const void *)&e->group.B; }
struct crypto_ec_point *crypto_ec_point_init(struct crypto_ec *e)
{ struct crypto_ec_point *p = os_zalloc(sizeof(*p)); if (p) mbedtls_ecp_point_init(&p->p); return p; }
void crypto_ec_point_deinit(struct crypto_ec_point *p, int clear) { if (p) { mbedtls_ecp_point_free(&p->p); os_free(p); } }
int crypto_ec_point_to_bin(struct crypto_ec *e, const struct crypto_ec_point *p, u8 *x, u8 *y)
{ size_t n = crypto_ec_prime_len(e); return (x && mbedtls_mpi_write_binary(&p->p.MBEDTLS_PRIVATE(X), x, n)) || (y && mbedtls_mpi_write_binary(&p->p.MBEDTLS_PRIVATE(Y), y, n)) ? -1 : 0; }
struct crypto_ec_point *crypto_ec_point_from_bin(struct crypto_ec *e, const u8 *xy)
{
	struct crypto_ec_point *p = crypto_ec_point_init(e); if (!p) return NULL;
	size_t n = crypto_ec_prime_len(e);
	if (mbedtls_mpi_read_binary(&p->p.MBEDTLS_PRIVATE(X), xy, n) || mbedtls_mpi_read_binary(&p->p.MBEDTLS_PRIVATE(Y), xy + n, n) ||
	    mbedtls_mpi_lset(&p->p.MBEDTLS_PRIVATE(Z), 1) || mbedtls_ecp_check_pubkey(&e->group, &p->p)) { crypto_ec_point_deinit(p, 1); return NULL; }
	return p;
}
int crypto_ec_point_add(struct crypto_ec *e, const struct crypto_ec_point *a, const struct crypto_ec_point *b, struct crypto_ec_point *c)
{ mbedtls_mpi one; mbedtls_mpi_init(&one); int r = mbedtls_mpi_lset(&one, 1); if (!r) r = mbedtls_ecp_muladd(&e->group, &c->p, &one, &a->p, &one, &b->p); mbedtls_mpi_free(&one); return r; }
int crypto_ec_point_mul(struct crypto_ec *e, const struct crypto_ec_point *p, const struct crypto_bignum *b, struct crypto_ec_point *c)
{ return mbedtls_ecp_mul(&e->group, &c->p, &b->n, &p->p, rng, NULL); }
int crypto_ec_point_invert(struct crypto_ec *e, struct crypto_ec_point *p)
{ return mbedtls_mpi_cmp_int(&p->p.MBEDTLS_PRIVATE(Y), 0) == 0 ? 0 : mbedtls_mpi_sub_mpi(&p->p.MBEDTLS_PRIVATE(Y), &e->group.P, &p->p.MBEDTLS_PRIVATE(Y)); }
int crypto_ec_point_is_at_infinity(struct crypto_ec *e, const struct crypto_ec_point *p) { return mbedtls_ecp_is_zero((void *)&p->p); }
int crypto_ec_point_is_on_curve(struct crypto_ec *e, const struct crypto_ec_point *p) { return mbedtls_ecp_check_pubkey(&e->group, &p->p) == 0; }
int crypto_ec_point_cmp(const struct crypto_ec *e, const struct crypto_ec_point *a, const struct crypto_ec_point *b) { return mbedtls_ecp_point_cmp(&a->p, &b->p); }
struct crypto_bignum *crypto_ec_point_compute_y_sqr(struct crypto_ec *e, const struct crypto_bignum *x)
{
	struct crypto_bignum *y = crypto_bignum_init(), *t = crypto_bignum_init();
	const struct crypto_bignum *p = crypto_ec_get_prime(e);
	if (!y || !t || crypto_bignum_sqrmod(x, p, y) || crypto_bignum_mulmod(y, x, p, y) ||
	    crypto_bignum_mulmod(&e->a, x, p, t) || crypto_bignum_addmod(y, t, p, y) ||
	    crypto_bignum_addmod(y, crypto_ec_get_b(e), p, y)) { crypto_bignum_deinit(y, 1); y = NULL; }
	crypto_bignum_deinit(t, 1); return y;
}
int sha256_vector(size_t count, const u8 *data[], const size_t *length, u8 *out)
{
	mbedtls_sha256_context c; mbedtls_sha256_init(&c); int e = mbedtls_sha256_starts(&c, 0);
	for (size_t i = 0; !e && i < count; i++) e = mbedtls_sha256_update(&c, data[i], length[i]);
	if (!e) e = mbedtls_sha256_finish(&c, out);
	mbedtls_sha256_free(&c); return e;
}
int omac1_aes_128_vector(const u8 *key, size_t count, const u8 *data[], const size_t *length, u8 *out)
{
	mbedtls_cipher_context_t c; mbedtls_cipher_init(&c);
	int e = mbedtls_cipher_setup(&c, mbedtls_cipher_info_from_type(MBEDTLS_CIPHER_AES_128_ECB));
	if (!e) e = mbedtls_cipher_cmac_starts(&c, key, 128);
	for (size_t i = 0; !e && i < count; i++) e = mbedtls_cipher_cmac_update(&c, data[i], length[i]);
	if (!e) e = mbedtls_cipher_cmac_finish(&c, out);
	mbedtls_cipher_free(&c); return e;
}
int omac1_aes_128(const u8 *key, const u8 *data, size_t n, u8 *out)
{ return omac1_aes_128_vector(key, 1, &data, &n, out); }
const struct dh_group *dh_groups_get(int id) { return NULL; } /* Only the mandatory ECC group 19 is offered. */
u32 wpa_akm_to_suite(int akm) { return akm == WPA_KEY_MGMT_SAE ? RSN_AUTH_KEY_MGMT_SAE : 0; }

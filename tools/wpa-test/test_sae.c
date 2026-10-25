/* Exercise hostap SAE through the same adapter used on the phone. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "utils/includes.h"
#include "utils/common.h"
#include "crypto/crypto.h"
#include "sae.h"
#include "wpa3.inc"

static void arithmetic(void)
{
	struct crypto_bignum *two=crypto_bignum_init_uint(2), *exponent=crypto_bignum_init_uint(3), *mod=crypto_bignum_init_uint(17);
	assert(two&&exponent&&mod);
	assert(!crypto_bignum_exptmod(two,exponent,mod,exponent));
	unsigned char out[64];assert(crypto_bignum_to_bin(exponent,out,sizeof(out),1)==1&&out[0]==8);
	struct crypto_ec *e=crypto_ec_init(19);assert(e&&!crypto_ec_init(20));
	struct crypto_ec_point *g=crypto_ec_point_from_bin(e,point1), *result=crypto_ec_point_init(e);assert(g&&result);
	assert(!crypto_ec_point_mul(e,g,two,result));
	assert(!crypto_ec_point_to_bin(e,result,out,out+32)&&!memcmp(out,point2,64));
	memset(out,0,sizeof(out));assert(!crypto_ec_point_from_bin(e,out));
	crypto_ec_point_deinit(g,1);crypto_ec_point_deinit(result,1);crypto_ec_deinit(e);
	crypto_bignum_deinit(two,1);crypto_bignum_deinit(exponent,1);crypto_bignum_deinit(mod,1);
}

static void exchange(int h2e, int wrong)
{
	const unsigned char a[6] = { 2, 0, 0, 0, 0, 1 }, b[6] = { 2, 0, 0, 0, 0, 2 };
	const unsigned char name[] = "SAE test", password[] = "known test password", bad[] = "wrong test password";
	struct lx_sae *one = lx_sae_new(a, b, name, sizeof(name)-1, password, sizeof(password)-1, h2e);
	struct lx_sae *two = lx_sae_new(b, a, name, sizeof(name)-1, wrong ? bad : password, sizeof(password)-1, h2e);
	if (!one || !two) fprintf(stderr, "SAE creation failed: h2e=%d wrong=%d\n", h2e, wrong);
	assert(one && two);
	unsigned char c1[1024], c2[1024], f1[128], f2[128], k1[32], k2[32], id1[16], id2[16];
	unsigned n1=sizeof(c1), n2=sizeof(c2), l1=sizeof(f1), l2=sizeof(f2);
	assert(!lx_sae_commit(one, NULL, 0, c1, &n1));
	assert(!lx_sae_commit(two, NULL, 0, c2, &n2));
	assert(n1>=98 && n2>=98);
	assert(lx_sae_accept_commit(one, c1, n1)); /* reflected commit */
	assert(!lx_sae_accept_commit(one, c2, n2));
	assert(!lx_sae_accept_commit(two, c1, n1));
	assert(!lx_sae_confirm(one, f1, &l1) && l1==34);
	assert(!lx_sae_confirm(two, f2, &l2) && l2==34);
	if (wrong) {
		assert(lx_sae_accept_confirm(one, f2, l2, k1, id1));
		assert(lx_sae_accept_confirm(two, f1, l1, k2, id2));
	} else {
		f2[5]^=1; assert(lx_sae_accept_confirm(one, f2, l2, k1, id1)); f2[5]^=1;
		assert(!lx_sae_accept_confirm(one, f2, l2, k1, id1));
		assert(!lx_sae_accept_confirm(two, f1, l1, k2, id2));
		assert(!memcmp(k1, k2, 32) && !memcmp(id1, id2, 16));
	}
	memset(c1, 0, sizeof(c1)); c1[0]=19;
	assert(lx_sae_accept_commit(one, c1, 98)); /* invalid scalar and point */
	assert(lx_sae_accept_commit(one, c1, 1));
	lx_sae_delete(one); lx_sae_delete(two);
}
int main(void)
{
	arithmetic();
	for (unsigned i=0;i<3;i++) for (int h2e=0;h2e<2;h2e++) { exchange(h2e, 0); exchange(h2e, 1); }
	puts("PASS: SAE group 19 H&P/H2E, matching PMK/PMKID, wrong password, reflection, corrupt confirm and malformed points");
}

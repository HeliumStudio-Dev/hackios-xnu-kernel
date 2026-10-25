#include "utils/includes.h"
#include "utils/common.h"
#include "utils/wpabuf.h"
#include "common/sae.h"
#include "common/defs.h"
#include "crypto/sha256.h"
#include "crypto/aes_wrap.h"
#include "sae.h"

struct lx_sae { struct sae_data sae; int h2e, committed; };
static int groups[] = { 19, 0 };
struct lx_sae *lx_sae_new(const unsigned char own[6], const unsigned char peer[6],
    const unsigned char *ssid, unsigned ssid_len, const unsigned char *password, unsigned password_len, int h2e)
{
	if (!ssid_len || ssid_len > 32 || !password_len || password_len > 63 || !memcmp(own, peer, 6)) return NULL;
	struct lx_sae *s = os_zalloc(sizeof(*s)); if (!s) return NULL;
	s->h2e = !!h2e;
	int error = sae_set_group(&s->sae, 19);
	s->sae.akmp = WPA_KEY_MGMT_SAE;
	if (!error && h2e) {
		struct sae_pt *pt = sae_derive_pt(groups, ssid, ssid_len, password, password_len, NULL);
		error = pt ? sae_prepare_commit_pt(&s->sae, pt, own, peer, NULL, NULL) : -1;
		sae_deinit_pt(pt);
	} else if (!error) error = sae_prepare_commit(own, peer, password, password_len, &s->sae);
	if (error) { lx_sae_delete(s); return NULL; }
	return s;
}
void lx_sae_delete(struct lx_sae *s) { if (s) { sae_clear_data(&s->sae); bin_clear_free(s, sizeof(*s)); } }
static int output(struct wpabuf *b, unsigned char *out, unsigned *size, int error)
{
	if (!error && wpabuf_len(b) <= *size) { *size = wpabuf_len(b); memcpy(out, wpabuf_head(b), *size); }
	else { *size = 0; error = -1; }
	wpabuf_clear_free(b); return error;
}
int lx_sae_commit(struct lx_sae *s, const unsigned char *token, unsigned token_len, unsigned char *out, unsigned *out_len)
{
	if (!s || token_len > 255) return -1;
	struct wpabuf *b = wpabuf_alloc(1024), *t = token_len ? wpabuf_alloc_copy(token, token_len) : NULL;
	if (!b || (token_len && !t)) { wpabuf_free(b); wpabuf_free(t); return -1; }
	int e = sae_write_commit(&s->sae, b, t, NULL); wpabuf_free(t);
	return output(b, out, out_len, e);
}
int lx_sae_accept_commit(struct lx_sae *s, const unsigned char *in, unsigned n)
{
	if (!s || n < 98 || n > 1024 || in[0] != 19 || in[1]) return -1;
	u16 error = sae_parse_commit(&s->sae, in, n, NULL, NULL, groups, s->h2e, NULL);
	if (error || sae_process_commit(&s->sae)) return -1;
	s->committed = 1; return 0;
}
int lx_sae_confirm(struct lx_sae *s, unsigned char *out, unsigned *out_len)
{
	if (!s || !s->committed) return -1;
	struct wpabuf *b = wpabuf_alloc(128); if (!b) return -1;
	return output(b, out, out_len, sae_write_confirm(&s->sae, b));
}
int lx_sae_accept_confirm(struct lx_sae *s, const unsigned char *in, unsigned n, unsigned char pmk[32], unsigned char pmkid[16])
{
	if (!s || !s->committed || n != 34 || sae_check_confirm(&s->sae, in, n, NULL)) return -1;
	memcpy(pmk, s->sae.pmk, 32); memcpy(pmkid, s->sae.pmkid, 16); return 0;
}
int lx_sae_prf(const unsigned char pmk[32], const unsigned char *data, unsigned n, unsigned char keys[48])
{ return sha256_prf(pmk, 32, "Pairwise key expansion", data, n, keys, 48); }
int lx_sae_cmac(const unsigned char key[16], const unsigned char *data, unsigned n, unsigned char mic[16])
{ return omac1_aes_128(key, data, n, mic); }

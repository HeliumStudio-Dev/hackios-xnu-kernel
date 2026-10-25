/* Hostap SAE group 19; payloads exclude the 802.11 authentication header. */
#ifndef LX_SAE_H
#define LX_SAE_H
struct lx_sae;
struct lx_sae *lx_sae_new(const unsigned char own[6], const unsigned char peer[6],
    const unsigned char *ssid, unsigned ssid_len, const unsigned char *password, unsigned password_len, int h2e);
void lx_sae_delete(struct lx_sae *);
int lx_sae_commit(struct lx_sae *, const unsigned char *token, unsigned token_len, unsigned char *out, unsigned *out_len);
int lx_sae_accept_commit(struct lx_sae *, const unsigned char *, unsigned);
int lx_sae_confirm(struct lx_sae *, unsigned char *out, unsigned *out_len);
int lx_sae_accept_confirm(struct lx_sae *, const unsigned char *, unsigned, unsigned char pmk[32], unsigned char pmkid[16]);
int lx_sae_prf(const unsigned char pmk[32], const unsigned char *data, unsigned n, unsigned char keys[48]);
int lx_sae_cmac(const unsigned char key[16], const unsigned char *data, unsigned n, unsigned char mic[16]);
#endif


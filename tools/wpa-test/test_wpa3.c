#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lx_wpa.h"
#include "wpa3.inc"

int main(void)
{
	struct lx_wpa w = { .sae = 1 };
	memcpy(w.pmk, pmk, 32); memcpy(w.own, own, 6); memcpy(w.peer, peer, 6); memcpy(w.own_nonce, snonce, 32);
	w.rsn = rsn; w.rsn_length = sizeof(rsn);
	unsigned char reply[LX_WPA_REPLY_MOST], wrong[sizeof(m3)], f[sizeof(deauth)]; unsigned n; const char *why;
	assert(lx_wpa_message(&w, m1, sizeof(m1), reply, &n, &why) == LX_WPA_ANSWER);
	assert(n == sizeof(m2) && !memcmp(reply, m2, n) && !memcmp(w.pairwise, tk, 16));
	memcpy(wrong, m3, sizeof(m3)); wrong[81] ^= 1;
	assert(lx_wpa_message(&w, wrong, sizeof(wrong), reply, &n, &why) == LX_WPA_BAD);
	assert(lx_wpa_message(&w, m3, sizeof(m3), reply, &n, &why) == LX_WPA_KEYS);
	assert(n == sizeof(m4) && !memcmp(reply, m4, n));
	assert(w.igtk_valid && w.igtk_index == 4 && !memcmp(w.igtk, igtk, 16) && !memcmp(w.group, gtk, 16));
	assert(lx_wpa_message(&w, m3, sizeof(m3), reply, &n, &why) == LX_WPA_BAD);
	memcpy(f, deauth, sizeof(f)); f[sizeof(f)-1] ^= 1;
	assert(lx_wpa_mgmt(&w, f, sizeof(f), 0));
	assert(!lx_wpa_mgmt(&w, deauth, sizeof(deauth), 0));
	assert(lx_wpa_mgmt(&w, deauth, sizeof(deauth), 0));
	w.group_counter[0] = 9;
	assert(lx_wpa_message(&w, same_rekey, sizeof(same_rekey), reply, &n, &why) == LX_WPA_GROUP);
	assert(w.group_counter[0] == 9 && w.igtk_counter[0] == 2);
	assert(lx_wpa_message(&w, igtk_only, sizeof(igtk_only), reply, &n, &why) == LX_WPA_GROUP);
	assert(w.group_counter[0] == 9 && w.igtk_counter[0] == 2);
	struct lx_wpa before = w;
	assert(lx_wpa_message(&w, bad_kde, sizeof(bad_kde), reply, &n, &why) == LX_WPA_BAD);
	assert(!memcmp(&before, &w, sizeof(w)));
	assert(lx_wpa_message(&w, m1, sizeof(m1), reply, &n, &why) == LX_WPA_BAD);
	assert(!memcmp(&before, &w, sizeof(w)));
	f[4] = 2; assert(lx_wpa_mgmt(&w, f, sizeof(f), 0));
	assert(!lx_wpa_mgmt(&w, f, sizeof(f), 1));
	for (unsigned i = 0; i < sizeof(m3); i++) {
		assert(lx_wpa_message(&w, m3, i, reply, &n, &why) != LX_WPA_KEYS);
	}
	puts("PASS: independent WPA3 PTK/MIC/M2/M3/M4 vectors, IGTK, BIP, replay and truncation rejection");
}

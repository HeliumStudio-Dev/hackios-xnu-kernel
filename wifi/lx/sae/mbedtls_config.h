/* Only the primitives needed by hostap SAE and PMF; randomness comes from XNU. */
#define MBEDTLS_BIGNUM_C
/* XNU has no compiler runtime for 128-bit division. */
#define MBEDTLS_NO_UDBL_DIVISION
#define MBEDTLS_ECP_C
#define MBEDTLS_ECP_DP_SECP256R1_ENABLED
#define MBEDTLS_ECP_NIST_OPTIM
#define MBEDTLS_SHA256_C
#define MBEDTLS_AES_C
#define MBEDTLS_CIPHER_C
#define MBEDTLS_CMAC_C
#define MBEDTLS_PLATFORM_C
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_NO_STD_FUNCTIONS
#define MBEDTLS_PLATFORM_CALLOC_MACRO lx_sae_calloc
#define MBEDTLS_PLATFORM_FREE_MACRO lx_sae_free


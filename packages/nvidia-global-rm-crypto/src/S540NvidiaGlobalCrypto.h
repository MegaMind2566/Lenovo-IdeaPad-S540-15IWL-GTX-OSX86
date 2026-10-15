/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_CRYPTO_H
#define S540_NVIDIA_GLOBAL_CRYPTO_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * The TU117 profile has no SPDM cryptographic backend. These exact ABI
 * boundaries refuse every operation. They do not implement cryptography.
 *
 * Counters are process/kernel-lifetime monotonic and cannot be reset. A global
 * RM/adapter trial is successful only if all counters below are still zero
 * after startup, every subsequent operation, and complete shutdown. Checking
 * only a difference between snapshots is insufficient: an earlier invocation
 * permanently invalidates this loaded profile.
 *
 * Read the snapshot after the trial is quiescent; fields are atomic but not a
 * transactional snapshot. Every invocation, including a NULL-context free,
 * records a refusal. No buffer, context, output length, or caller-owned memory
 * is modified. No contexts can be created by this implementation.
 */
typedef struct S540NvidiaGlobalCryptoSnapshot {
    uint32_t unavailable_calls;
    uint32_t unavailable_symbol_mask;
    uint32_t counter_overflow;
    uint32_t unavailable_symbol_mask_high;
} S540NvidiaGlobalCryptoSnapshot;

enum { S540_NVIDIA_GLOBAL_CRYPTO_SYMBOL_COUNT = 64 };

bool s540Global_crypto_available(void);
void s540Global_crypto_snapshot(S540NvidiaGlobalCryptoSnapshot *out);

/* The exact upstream RSA key tag values, with a local type namespace. */
#ifndef S540_GLOBAL_RSA_TYPE_FROM_UPSTREAM
typedef enum {
    S540_GLOBAL_RSA_KEY_N,
    S540_GLOBAL_RSA_KEY_E,
    S540_GLOBAL_RSA_KEY_D,
    S540_GLOBAL_RSA_KEY_P,
    S540_GLOBAL_RSA_KEY_Q,
    S540_GLOBAL_RSA_KEY_DP,
    S540_GLOBAL_RSA_KEY_DQ,
    S540_GLOBAL_RSA_KEY_Q_INV
} S540GlobalRsaKeyTag;
#endif

bool s540Global_libspdm_aead_aes_gcm_decrypt_prealloc(void *context, const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, const uint8_t *tag, size_t tag_size, uint8_t *data_out, size_t *data_out_size);
bool s540Global_libspdm_aead_aes_gcm_encrypt_prealloc(void *context, const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, uint8_t *tag_out, size_t tag_size, uint8_t *data_out, size_t *data_out_size);
void s540Global_libspdm_aead_free(void *context);
bool s540Global_libspdm_aead_gcm_prealloc(void **context);
bool s540Global_libspdm_hkdf_sha256_expand(const uint8_t *prk, size_t prk_size, const uint8_t *info, size_t info_size, uint8_t *out, size_t out_size);
bool s540Global_libspdm_hkdf_sha384_expand(const uint8_t *prk, size_t prk_size, const uint8_t *info, size_t info_size, uint8_t *out, size_t out_size);
bool s540Global_libspdm_hmac_sha256_final(void *hmac_sha256_ctx, uint8_t *hmac_value);
void s540Global_libspdm_hmac_sha256_free(void *hmac_sha256_ctx);
void * s540Global_libspdm_hmac_sha256_new(void);
bool s540Global_libspdm_hmac_sha256_set_key(void *hmac_sha256_ctx, const uint8_t *key, size_t key_size);
bool s540Global_libspdm_hmac_sha256_update(void *hmac_sha256_ctx, const void *data, size_t data_size);
bool s540Global_libspdm_random_bytes(uint8_t *output, size_t size);
void s540Global_libspdm_sha256_free(void *sha256_context);
void s540Global_libspdm_sha384_free(void *sha384_context);
bool s540Global_libspdm_aead_aes_gcm_decrypt(const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, const uint8_t *tag, size_t tag_size, uint8_t *data_out, size_t *data_out_size);
bool s540Global_libspdm_aead_aes_gcm_encrypt(const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, uint8_t *tag_out, size_t tag_size, uint8_t *data_out, size_t *data_out_size);
bool s540Global_libspdm_asn1_get_tag(uint8_t **ptr, const uint8_t *end, size_t *length, uint32_t tag);
bool s540Global_libspdm_check_crypto_backend(void);
bool s540Global_libspdm_decode_base64(const uint8_t *src, uint8_t *dst, size_t srclen, size_t *p_dstlen);
bool s540Global_libspdm_ec_compute_key(void *ec_context, const uint8_t *peer_public, size_t peer_public_size, uint8_t *key, size_t *key_size);
void s540Global_libspdm_ec_free(void *ec_context);
bool s540Global_libspdm_ec_generate_key(void *ec_context, uint8_t *public_key, size_t *public_key_size);
bool s540Global_libspdm_ec_get_public_key_from_x509(const uint8_t *cert, size_t cert_size, void **ec_context);
void * s540Global_libspdm_ec_new_by_nid(size_t nid);
bool s540Global_libspdm_ecdsa_sign(void *ec_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, uint8_t *signature, size_t *sig_size);
bool s540Global_libspdm_ecdsa_verify(void *ec_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, const uint8_t *signature, size_t sig_size);
bool s540Global_libspdm_encode_base64(const uint8_t *src, uint8_t *dst, size_t srclen, size_t *p_dstlen);
bool s540Global_libspdm_hkdf_sha256_extract(const uint8_t *key, size_t key_size, const uint8_t *salt, size_t salt_size, uint8_t *prk_out, size_t prk_out_size);
bool s540Global_libspdm_hkdf_sha384_extract(const uint8_t *key, size_t key_size, const uint8_t *salt, size_t salt_size, uint8_t *prk_out, size_t prk_out_size);
bool s540Global_libspdm_hmac_sha256_all(const void *data, size_t data_size, const uint8_t *key, size_t key_size, uint8_t *hmac_value);
bool s540Global_libspdm_hmac_sha384_all(const void *data, size_t data_size, const uint8_t *key, size_t key_size, uint8_t *hmac_value);
void s540Global_libspdm_rsa_free(void *rsa_context);
bool s540Global_libspdm_rsa_get_public_key_from_x509(const uint8_t *cert, size_t cert_size, void **rsa_context);
void * s540Global_libspdm_rsa_new(void);
bool s540Global_libspdm_rsa_pss_sign(void *rsa_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, uint8_t *signature, size_t *sig_size);
bool s540Global_libspdm_rsa_pss_verify(void *rsa_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, const uint8_t *signature, size_t sig_size);
bool s540Global_libspdm_rsa_set_key(void *rsa_context, const S540GlobalRsaKeyTag key_tag, const uint8_t *big_number, size_t bn_size);
bool s540Global_libspdm_sha256_duplicate(const void *sha256_context, void *new_sha256_context);
bool s540Global_libspdm_sha256_final(void *sha256_context, uint8_t *hash_value);
bool s540Global_libspdm_sha256_hash_all(const void *data, size_t data_size, uint8_t *hash_value);
bool s540Global_libspdm_sha256_init(void *sha256_context);
void * s540Global_libspdm_sha256_new(void);
bool s540Global_libspdm_sha256_update(void *sha256_context, const void *data, size_t data_size);
bool s540Global_libspdm_sha384_duplicate(const void *sha384_context, void *new_sha384_context);
bool s540Global_libspdm_sha384_final(void *sha384_context, uint8_t *hash_value);
bool s540Global_libspdm_sha384_hash_all(const void *data, size_t data_size, uint8_t *hash_value);
bool s540Global_libspdm_sha384_init(void *sha384_context);
void * s540Global_libspdm_sha384_new(void);
bool s540Global_libspdm_sha384_update(void *sha384_context, const void *data, size_t data_size);
int32_t s540Global_libspdm_x509_compare_date_time(const void *date_time1, const void *date_time2);
bool s540Global_libspdm_x509_get_cert_from_cert_chain(const uint8_t *cert_chain, size_t cert_chain_length, const int32_t cert_index, const uint8_t **cert, size_t *cert_length);
bool s540Global_libspdm_x509_get_extended_basic_constraints(const uint8_t *cert, size_t cert_size, uint8_t *basic_constraints, size_t *basic_constraints_size);
bool s540Global_libspdm_x509_get_extended_key_usage(const uint8_t *cert, size_t cert_size, uint8_t *usage, size_t *usage_size);
bool s540Global_libspdm_x509_get_extension_data(const uint8_t *cert, size_t cert_size, const uint8_t *oid, size_t oid_size, uint8_t *extension_data, size_t *extension_data_size);
bool s540Global_libspdm_x509_get_issuer_name(const uint8_t *cert, size_t cert_size, uint8_t *cert_issuer, size_t *issuer_size);
bool s540Global_libspdm_x509_get_key_usage(const uint8_t *cert, size_t cert_size, size_t *usage);
bool s540Global_libspdm_x509_get_serial_number(const uint8_t *cert, size_t cert_size, uint8_t *serial_number, size_t *serial_number_size);
bool s540Global_libspdm_x509_get_signature_algorithm(const uint8_t *cert, size_t cert_size, uint8_t *oid, size_t *oid_size);
bool s540Global_libspdm_x509_get_subject_name(const uint8_t *cert, size_t cert_size, uint8_t *cert_subject, size_t *subject_size);
bool s540Global_libspdm_x509_get_validity(const uint8_t *cert, size_t cert_size, uint8_t *from, size_t *from_size, uint8_t *to, size_t *to_size);
bool s540Global_libspdm_x509_get_version(const uint8_t *cert, size_t cert_size, size_t *version);
bool s540Global_libspdm_x509_set_date_time(const char *date_time_str, void *date_time, size_t *date_time_size);
bool s540Global_libspdm_x509_verify_cert(const uint8_t *cert, size_t cert_size, const uint8_t *ca_cert, size_t ca_cert_size);
bool s540Global_libspdm_x509_verify_cert_chain(const uint8_t *root_cert, size_t root_cert_length, const uint8_t *cert_chain, size_t cert_chain_length);
#ifdef __cplusplus
}
#endif

#endif

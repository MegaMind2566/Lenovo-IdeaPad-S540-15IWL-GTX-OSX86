/* SPDX-License-Identifier: MIT */
#include "S540NvidiaGlobalCrypto.h"

_Static_assert(__atomic_always_lock_free(sizeof(uint32_t), 0),
               "Refusal counters require lock-free 32-bit atomics");

static uint32_t unavailable_calls;
static uint32_t unavailable_symbol_mask;
static uint32_t unavailable_symbol_mask_high;
static uint32_t counter_overflow;

static void refuse(uint32_t symbol)
{
    uint32_t previous;
    __atomic_fetch_or(symbol < 32U ? &unavailable_symbol_mask :
                      &unavailable_symbol_mask_high,
                      (uint32_t)1U << (symbol & 31U), __ATOMIC_RELAXED);
    previous = __atomic_load_n(&unavailable_calls, __ATOMIC_RELAXED);
    for (;;) {
        if (previous == UINT32_MAX) {
            __atomic_store_n(&counter_overflow, 1U, __ATOMIC_RELAXED);
            return;
        }
        if (__atomic_compare_exchange_n(&unavailable_calls, &previous,
                previous + 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED))
            return;
    }
}

bool s540Global_crypto_available(void)
{
    return false;
}

void s540Global_crypto_snapshot(S540NvidiaGlobalCryptoSnapshot *out)
{
    if (out == NULL)
        return;
    out->unavailable_calls = __atomic_load_n(&unavailable_calls,
                                            __ATOMIC_RELAXED);
    out->unavailable_symbol_mask = __atomic_load_n(&unavailable_symbol_mask,
                                                  __ATOMIC_RELAXED);
    out->unavailable_symbol_mask_high = __atomic_load_n(
        &unavailable_symbol_mask_high, __ATOMIC_RELAXED);
    out->counter_overflow = __atomic_load_n(&counter_overflow,
                                           __ATOMIC_RELAXED);
}

bool s540Global_libspdm_aead_aes_gcm_decrypt_prealloc(void *context, const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, const uint8_t *tag, size_t tag_size, uint8_t *data_out, size_t *data_out_size)
{
    (void)context;
    (void)key;
    (void)key_size;
    (void)iv;
    (void)iv_size;
    (void)a_data;
    (void)a_data_size;
    (void)data_in;
    (void)data_in_size;
    (void)tag;
    (void)tag_size;
    (void)data_out;
    (void)data_out_size;
    refuse(0);
    return false;
}

bool s540Global_libspdm_aead_aes_gcm_encrypt_prealloc(void *context, const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, uint8_t *tag_out, size_t tag_size, uint8_t *data_out, size_t *data_out_size)
{
    (void)context;
    (void)key;
    (void)key_size;
    (void)iv;
    (void)iv_size;
    (void)a_data;
    (void)a_data_size;
    (void)data_in;
    (void)data_in_size;
    (void)tag_out;
    (void)tag_size;
    (void)data_out;
    (void)data_out_size;
    refuse(1);
    return false;
}

void s540Global_libspdm_aead_free(void *context)
{
    (void)context;
    refuse(2);
}

bool s540Global_libspdm_aead_gcm_prealloc(void **context)
{
    (void)context;
    refuse(3);
    return false;
}

bool s540Global_libspdm_hkdf_sha256_expand(const uint8_t *prk, size_t prk_size, const uint8_t *info, size_t info_size, uint8_t *out, size_t out_size)
{
    (void)prk;
    (void)prk_size;
    (void)info;
    (void)info_size;
    (void)out;
    (void)out_size;
    refuse(4);
    return false;
}

bool s540Global_libspdm_hkdf_sha384_expand(const uint8_t *prk, size_t prk_size, const uint8_t *info, size_t info_size, uint8_t *out, size_t out_size)
{
    (void)prk;
    (void)prk_size;
    (void)info;
    (void)info_size;
    (void)out;
    (void)out_size;
    refuse(5);
    return false;
}

bool s540Global_libspdm_hmac_sha256_final(void *hmac_sha256_ctx, uint8_t *hmac_value)
{
    (void)hmac_sha256_ctx;
    (void)hmac_value;
    refuse(6);
    return false;
}

void s540Global_libspdm_hmac_sha256_free(void *hmac_sha256_ctx)
{
    (void)hmac_sha256_ctx;
    refuse(7);
}

void * s540Global_libspdm_hmac_sha256_new(void)
{
    refuse(8);
    return NULL;
}

bool s540Global_libspdm_hmac_sha256_set_key(void *hmac_sha256_ctx, const uint8_t *key, size_t key_size)
{
    (void)hmac_sha256_ctx;
    (void)key;
    (void)key_size;
    refuse(9);
    return false;
}

bool s540Global_libspdm_hmac_sha256_update(void *hmac_sha256_ctx, const void *data, size_t data_size)
{
    (void)hmac_sha256_ctx;
    (void)data;
    (void)data_size;
    refuse(10);
    return false;
}

bool s540Global_libspdm_random_bytes(uint8_t *output, size_t size)
{
    (void)output;
    (void)size;
    refuse(11);
    return false;
}

void s540Global_libspdm_sha256_free(void *sha256_context)
{
    (void)sha256_context;
    refuse(12);
}

void s540Global_libspdm_sha384_free(void *sha384_context)
{
    (void)sha384_context;
    refuse(13);
}

bool s540Global_libspdm_aead_aes_gcm_decrypt(const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, const uint8_t *tag, size_t tag_size, uint8_t *data_out, size_t *data_out_size)
{
    (void)key;
    (void)key_size;
    (void)iv;
    (void)iv_size;
    (void)a_data;
    (void)a_data_size;
    (void)data_in;
    (void)data_in_size;
    (void)tag;
    (void)tag_size;
    (void)data_out;
    (void)data_out_size;
    refuse(14);
    return false;
}

bool s540Global_libspdm_aead_aes_gcm_encrypt(const uint8_t *key, size_t key_size, const uint8_t *iv, size_t iv_size, const uint8_t *a_data, size_t a_data_size, const uint8_t *data_in, size_t data_in_size, uint8_t *tag_out, size_t tag_size, uint8_t *data_out, size_t *data_out_size)
{
    (void)key;
    (void)key_size;
    (void)iv;
    (void)iv_size;
    (void)a_data;
    (void)a_data_size;
    (void)data_in;
    (void)data_in_size;
    (void)tag_out;
    (void)tag_size;
    (void)data_out;
    (void)data_out_size;
    refuse(15);
    return false;
}

bool s540Global_libspdm_asn1_get_tag(uint8_t **ptr, const uint8_t *end, size_t *length, uint32_t tag)
{
    (void)ptr;
    (void)end;
    (void)length;
    (void)tag;
    refuse(16);
    return false;
}

bool s540Global_libspdm_check_crypto_backend(void)
{
    refuse(17);
    return false;
}

bool s540Global_libspdm_decode_base64(const uint8_t *src, uint8_t *dst, size_t srclen, size_t *p_dstlen)
{
    (void)src;
    (void)dst;
    (void)srclen;
    (void)p_dstlen;
    refuse(18);
    return false;
}

bool s540Global_libspdm_ec_compute_key(void *ec_context, const uint8_t *peer_public, size_t peer_public_size, uint8_t *key, size_t *key_size)
{
    (void)ec_context;
    (void)peer_public;
    (void)peer_public_size;
    (void)key;
    (void)key_size;
    refuse(19);
    return false;
}

void s540Global_libspdm_ec_free(void *ec_context)
{
    (void)ec_context;
    refuse(20);
}

bool s540Global_libspdm_ec_generate_key(void *ec_context, uint8_t *public_key, size_t *public_key_size)
{
    (void)ec_context;
    (void)public_key;
    (void)public_key_size;
    refuse(21);
    return false;
}

bool s540Global_libspdm_ec_get_public_key_from_x509(const uint8_t *cert, size_t cert_size, void **ec_context)
{
    (void)cert;
    (void)cert_size;
    (void)ec_context;
    refuse(22);
    return false;
}

void * s540Global_libspdm_ec_new_by_nid(size_t nid)
{
    (void)nid;
    refuse(23);
    return NULL;
}

bool s540Global_libspdm_ecdsa_sign(void *ec_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, uint8_t *signature, size_t *sig_size)
{
    (void)ec_context;
    (void)hash_nid;
    (void)message_hash;
    (void)hash_size;
    (void)signature;
    (void)sig_size;
    refuse(24);
    return false;
}

bool s540Global_libspdm_ecdsa_verify(void *ec_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, const uint8_t *signature, size_t sig_size)
{
    (void)ec_context;
    (void)hash_nid;
    (void)message_hash;
    (void)hash_size;
    (void)signature;
    (void)sig_size;
    refuse(25);
    return false;
}

bool s540Global_libspdm_encode_base64(const uint8_t *src, uint8_t *dst, size_t srclen, size_t *p_dstlen)
{
    (void)src;
    (void)dst;
    (void)srclen;
    (void)p_dstlen;
    refuse(26);
    return false;
}

bool s540Global_libspdm_hkdf_sha256_extract(const uint8_t *key, size_t key_size, const uint8_t *salt, size_t salt_size, uint8_t *prk_out, size_t prk_out_size)
{
    (void)key;
    (void)key_size;
    (void)salt;
    (void)salt_size;
    (void)prk_out;
    (void)prk_out_size;
    refuse(27);
    return false;
}

bool s540Global_libspdm_hkdf_sha384_extract(const uint8_t *key, size_t key_size, const uint8_t *salt, size_t salt_size, uint8_t *prk_out, size_t prk_out_size)
{
    (void)key;
    (void)key_size;
    (void)salt;
    (void)salt_size;
    (void)prk_out;
    (void)prk_out_size;
    refuse(28);
    return false;
}

bool s540Global_libspdm_hmac_sha256_all(const void *data, size_t data_size, const uint8_t *key, size_t key_size, uint8_t *hmac_value)
{
    (void)data;
    (void)data_size;
    (void)key;
    (void)key_size;
    (void)hmac_value;
    refuse(29);
    return false;
}

bool s540Global_libspdm_hmac_sha384_all(const void *data, size_t data_size, const uint8_t *key, size_t key_size, uint8_t *hmac_value)
{
    (void)data;
    (void)data_size;
    (void)key;
    (void)key_size;
    (void)hmac_value;
    refuse(30);
    return false;
}

void s540Global_libspdm_rsa_free(void *rsa_context)
{
    (void)rsa_context;
    refuse(31);
}

bool s540Global_libspdm_rsa_get_public_key_from_x509(const uint8_t *cert, size_t cert_size, void **rsa_context)
{
    (void)cert;
    (void)cert_size;
    (void)rsa_context;
    refuse(32);
    return false;
}

void * s540Global_libspdm_rsa_new(void)
{
    refuse(33);
    return NULL;
}

bool s540Global_libspdm_rsa_pss_sign(void *rsa_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, uint8_t *signature, size_t *sig_size)
{
    (void)rsa_context;
    (void)hash_nid;
    (void)message_hash;
    (void)hash_size;
    (void)signature;
    (void)sig_size;
    refuse(34);
    return false;
}

bool s540Global_libspdm_rsa_pss_verify(void *rsa_context, size_t hash_nid, const uint8_t *message_hash, size_t hash_size, const uint8_t *signature, size_t sig_size)
{
    (void)rsa_context;
    (void)hash_nid;
    (void)message_hash;
    (void)hash_size;
    (void)signature;
    (void)sig_size;
    refuse(35);
    return false;
}

bool s540Global_libspdm_rsa_set_key(void *rsa_context, const S540GlobalRsaKeyTag key_tag, const uint8_t *big_number, size_t bn_size)
{
    (void)rsa_context;
    (void)key_tag;
    (void)big_number;
    (void)bn_size;
    refuse(36);
    return false;
}

bool s540Global_libspdm_sha256_duplicate(const void *sha256_context, void *new_sha256_context)
{
    (void)sha256_context;
    (void)new_sha256_context;
    refuse(37);
    return false;
}

bool s540Global_libspdm_sha256_final(void *sha256_context, uint8_t *hash_value)
{
    (void)sha256_context;
    (void)hash_value;
    refuse(38);
    return false;
}

bool s540Global_libspdm_sha256_hash_all(const void *data, size_t data_size, uint8_t *hash_value)
{
    (void)data;
    (void)data_size;
    (void)hash_value;
    refuse(39);
    return false;
}

bool s540Global_libspdm_sha256_init(void *sha256_context)
{
    (void)sha256_context;
    refuse(40);
    return false;
}

void * s540Global_libspdm_sha256_new(void)
{
    refuse(41);
    return NULL;
}

bool s540Global_libspdm_sha256_update(void *sha256_context, const void *data, size_t data_size)
{
    (void)sha256_context;
    (void)data;
    (void)data_size;
    refuse(42);
    return false;
}

bool s540Global_libspdm_sha384_duplicate(const void *sha384_context, void *new_sha384_context)
{
    (void)sha384_context;
    (void)new_sha384_context;
    refuse(43);
    return false;
}

bool s540Global_libspdm_sha384_final(void *sha384_context, uint8_t *hash_value)
{
    (void)sha384_context;
    (void)hash_value;
    refuse(44);
    return false;
}

bool s540Global_libspdm_sha384_hash_all(const void *data, size_t data_size, uint8_t *hash_value)
{
    (void)data;
    (void)data_size;
    (void)hash_value;
    refuse(45);
    return false;
}

bool s540Global_libspdm_sha384_init(void *sha384_context)
{
    (void)sha384_context;
    refuse(46);
    return false;
}

void * s540Global_libspdm_sha384_new(void)
{
    refuse(47);
    return NULL;
}

bool s540Global_libspdm_sha384_update(void *sha384_context, const void *data, size_t data_size)
{
    (void)sha384_context;
    (void)data;
    (void)data_size;
    refuse(48);
    return false;
}

int32_t s540Global_libspdm_x509_compare_date_time(const void *date_time1, const void *date_time2)
{
    (void)date_time1;
    (void)date_time2;
    refuse(49);
    return -2;
}

bool s540Global_libspdm_x509_get_cert_from_cert_chain(const uint8_t *cert_chain, size_t cert_chain_length, const int32_t cert_index, const uint8_t **cert, size_t *cert_length)
{
    (void)cert_chain;
    (void)cert_chain_length;
    (void)cert_index;
    (void)cert;
    (void)cert_length;
    refuse(50);
    return false;
}

bool s540Global_libspdm_x509_get_extended_basic_constraints(const uint8_t *cert, size_t cert_size, uint8_t *basic_constraints, size_t *basic_constraints_size)
{
    (void)cert;
    (void)cert_size;
    (void)basic_constraints;
    (void)basic_constraints_size;
    refuse(51);
    return false;
}

bool s540Global_libspdm_x509_get_extended_key_usage(const uint8_t *cert, size_t cert_size, uint8_t *usage, size_t *usage_size)
{
    (void)cert;
    (void)cert_size;
    (void)usage;
    (void)usage_size;
    refuse(52);
    return false;
}

bool s540Global_libspdm_x509_get_extension_data(const uint8_t *cert, size_t cert_size, const uint8_t *oid, size_t oid_size, uint8_t *extension_data, size_t *extension_data_size)
{
    (void)cert;
    (void)cert_size;
    (void)oid;
    (void)oid_size;
    (void)extension_data;
    (void)extension_data_size;
    refuse(53);
    return false;
}

bool s540Global_libspdm_x509_get_issuer_name(const uint8_t *cert, size_t cert_size, uint8_t *cert_issuer, size_t *issuer_size)
{
    (void)cert;
    (void)cert_size;
    (void)cert_issuer;
    (void)issuer_size;
    refuse(54);
    return false;
}

bool s540Global_libspdm_x509_get_key_usage(const uint8_t *cert, size_t cert_size, size_t *usage)
{
    (void)cert;
    (void)cert_size;
    (void)usage;
    refuse(55);
    return false;
}

bool s540Global_libspdm_x509_get_serial_number(const uint8_t *cert, size_t cert_size, uint8_t *serial_number, size_t *serial_number_size)
{
    (void)cert;
    (void)cert_size;
    (void)serial_number;
    (void)serial_number_size;
    refuse(56);
    return false;
}

bool s540Global_libspdm_x509_get_signature_algorithm(const uint8_t *cert, size_t cert_size, uint8_t *oid, size_t *oid_size)
{
    (void)cert;
    (void)cert_size;
    (void)oid;
    (void)oid_size;
    refuse(57);
    return false;
}

bool s540Global_libspdm_x509_get_subject_name(const uint8_t *cert, size_t cert_size, uint8_t *cert_subject, size_t *subject_size)
{
    (void)cert;
    (void)cert_size;
    (void)cert_subject;
    (void)subject_size;
    refuse(58);
    return false;
}

bool s540Global_libspdm_x509_get_validity(const uint8_t *cert, size_t cert_size, uint8_t *from, size_t *from_size, uint8_t *to, size_t *to_size)
{
    (void)cert;
    (void)cert_size;
    (void)from;
    (void)from_size;
    (void)to;
    (void)to_size;
    refuse(59);
    return false;
}

bool s540Global_libspdm_x509_get_version(const uint8_t *cert, size_t cert_size, size_t *version)
{
    (void)cert;
    (void)cert_size;
    (void)version;
    refuse(60);
    return false;
}

bool s540Global_libspdm_x509_set_date_time(const char *date_time_str, void *date_time, size_t *date_time_size)
{
    (void)date_time_str;
    (void)date_time;
    (void)date_time_size;
    refuse(61);
    return false;
}

bool s540Global_libspdm_x509_verify_cert(const uint8_t *cert, size_t cert_size, const uint8_t *ca_cert, size_t ca_cert_size)
{
    (void)cert;
    (void)cert_size;
    (void)ca_cert;
    (void)ca_cert_size;
    refuse(62);
    return false;
}

bool s540Global_libspdm_x509_verify_cert_chain(const uint8_t *root_cert, size_t root_cert_length, const uint8_t *cert_chain, size_t cert_chain_length)
{
    (void)root_cert;
    (void)root_cert_length;
    (void)cert_chain;
    (void)cert_chain_length;
    refuse(63);
    return false;
}


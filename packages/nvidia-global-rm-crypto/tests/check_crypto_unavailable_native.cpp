/* SPDX-License-Identifier: MIT */
#include "../src/S540NvidiaGlobalCrypto.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <thread>

namespace {
unsigned checks;
unsigned failures;
void expect(bool condition)
{
    ++checks;
    if (!condition)
        ++failures;
}
void recordIs(unsigned calls, unsigned mask, unsigned high = 0)
{
    S540NvidiaGlobalCryptoSnapshot state{};
    s540Global_crypto_snapshot(&state);
    expect(state.unavailable_calls == calls);
    expect(state.unavailable_symbol_mask == mask);
    expect(state.counter_overflow == 0);
    expect(state.unavailable_symbol_mask_high == high);
}
}

int main()
{
    unsigned char output[64], tag[16], key[32], input[64];
    std::memset(output, 0xC3, sizeof(output));
    std::memset(tag, 0xA5, sizeof(tag));
    std::memset(key, 0x72, sizeof(key));
    std::memset(input, 0x37, sizeof(input));
    unsigned char originalOutput[64], originalTag[16];
    std::memcpy(originalOutput, output, sizeof(output));
    std::memcpy(originalTag, tag, sizeof(tag));
    void *context = input;
    size_t outputSize = sizeof(output);

    expect(!s540Global_crypto_available());
    recordIs(0, 0);
    s540Global_crypto_snapshot(nullptr);
    recordIs(0, 0);

    expect(!s540Global_libspdm_aead_aes_gcm_decrypt_prealloc(
        context, key, sizeof(key), input, 12, input, 8,
        input, sizeof(input), tag, sizeof(tag), output, &outputSize));
    recordIs(1, 1);
    expect(!s540Global_libspdm_aead_aes_gcm_encrypt_prealloc(
        context, key, sizeof(key), input, 12, input, 8,
        input, sizeof(input), tag, sizeof(tag), output, &outputSize));
    recordIs(2, 3);
    s540Global_libspdm_aead_free(context);
    recordIs(3, 7);
    expect(!s540Global_libspdm_aead_gcm_prealloc(&context));
    recordIs(4, 15);
    expect(context == input);
    expect(!s540Global_libspdm_hkdf_sha256_expand(
        key, sizeof(key), input, sizeof(input), output, sizeof(output)));
    recordIs(5, 31);
    expect(!s540Global_libspdm_hkdf_sha384_expand(
        key, sizeof(key), input, sizeof(input), output, sizeof(output)));
    recordIs(6, 63);
    expect(!s540Global_libspdm_hmac_sha256_final(context, output));
    recordIs(7, 127);
    s540Global_libspdm_hmac_sha256_free(context);
    recordIs(8, 255);
    expect(s540Global_libspdm_hmac_sha256_new() == nullptr);
    recordIs(9, 511);
    expect(!s540Global_libspdm_hmac_sha256_set_key(context, key, sizeof(key)));
    recordIs(10, 1023);
    expect(!s540Global_libspdm_hmac_sha256_update(context, input, sizeof(input)));
    recordIs(11, 2047);
    expect(!s540Global_libspdm_random_bytes(output, sizeof(output)));
    recordIs(12, 4095);
    s540Global_libspdm_sha256_free(context);
    recordIs(13, 8191);
    s540Global_libspdm_sha384_free(context);
    recordIs(14, 16383);

    expect(outputSize == sizeof(output));
    expect(std::memcmp(originalOutput, output, sizeof(output)) == 0);
    expect(std::memcmp(originalTag, tag, sizeof(tag)) == 0);
    expect(input[0] == 0x37 && input[63] == 0x37);
    expect(key[0] == 0x72 && key[31] == 0x72);

    /* Refusals accept no memory even when all pointers are NULL or lengths huge. */
    expect(!s540Global_libspdm_aead_aes_gcm_decrypt_prealloc(
        nullptr, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX,
        nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    expect(!s540Global_libspdm_aead_aes_gcm_encrypt_prealloc(
        nullptr, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX,
        nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    s540Global_libspdm_aead_free(nullptr);
    expect(!s540Global_libspdm_aead_gcm_prealloc(nullptr));
    expect(!s540Global_libspdm_hkdf_sha256_expand(
        nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    expect(!s540Global_libspdm_hkdf_sha384_expand(
        nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    expect(!s540Global_libspdm_hmac_sha256_final(nullptr, nullptr));
    s540Global_libspdm_hmac_sha256_free(nullptr);
    expect(s540Global_libspdm_hmac_sha256_new() == nullptr);
    expect(!s540Global_libspdm_hmac_sha256_set_key(nullptr, nullptr, SIZE_MAX));
    expect(!s540Global_libspdm_hmac_sha256_update(nullptr, nullptr, SIZE_MAX));
    expect(!s540Global_libspdm_random_bytes(nullptr, SIZE_MAX));
    s540Global_libspdm_sha256_free(nullptr);
    s540Global_libspdm_sha384_free(nullptr);
    recordIs(28, 16383);

    /* Exercise every additional adapter/GSP/ISR metadata ABI dependency. */
    uint8_t *mutablePointer = input;
    const uint8_t *constantPointer = input;
    expect(!s540Global_libspdm_aead_aes_gcm_decrypt(input, sizeof(input), input, sizeof(input), input, sizeof(input), input, sizeof(input), input, sizeof(input), output, &outputSize));
    recordIs(29, 32767U, 0U);
    expect(!s540Global_libspdm_aead_aes_gcm_encrypt(input, sizeof(input), input, sizeof(input), input, sizeof(input), input, sizeof(input), output, sizeof(input), output, &outputSize));
    recordIs(30, 65535U, 0U);
    expect(!s540Global_libspdm_asn1_get_tag(&mutablePointer, input, &outputSize, 0U));
    recordIs(31, 131071U, 0U);
    expect(!s540Global_libspdm_check_crypto_backend());
    recordIs(32, 262143U, 0U);
    expect(!s540Global_libspdm_decode_base64(input, output, sizeof(input), &outputSize));
    recordIs(33, 524287U, 0U);
    expect(!s540Global_libspdm_ec_compute_key(context, input, sizeof(input), output, &outputSize));
    recordIs(34, 1048575U, 0U);
    s540Global_libspdm_ec_free(context);
    recordIs(35, 2097151U, 0U);
    expect(!s540Global_libspdm_ec_generate_key(context, output, &outputSize));
    recordIs(36, 4194303U, 0U);
    expect(!s540Global_libspdm_ec_get_public_key_from_x509(input, sizeof(input), &context));
    recordIs(37, 8388607U, 0U);
    expect(s540Global_libspdm_ec_new_by_nid(sizeof(input)) == nullptr);
    recordIs(38, 16777215U, 0U);
    expect(!s540Global_libspdm_ecdsa_sign(context, sizeof(input), input, sizeof(input), output, &outputSize));
    recordIs(39, 33554431U, 0U);
    expect(!s540Global_libspdm_ecdsa_verify(context, sizeof(input), input, sizeof(input), input, sizeof(input)));
    recordIs(40, 67108863U, 0U);
    expect(!s540Global_libspdm_encode_base64(input, output, sizeof(input), &outputSize));
    recordIs(41, 134217727U, 0U);
    expect(!s540Global_libspdm_hkdf_sha256_extract(input, sizeof(input), input, sizeof(input), output, sizeof(input)));
    recordIs(42, 268435455U, 0U);
    expect(!s540Global_libspdm_hkdf_sha384_extract(input, sizeof(input), input, sizeof(input), output, sizeof(input)));
    recordIs(43, 536870911U, 0U);
    expect(!s540Global_libspdm_hmac_sha256_all(context, sizeof(input), input, sizeof(input), output));
    recordIs(44, 1073741823U, 0U);
    expect(!s540Global_libspdm_hmac_sha384_all(context, sizeof(input), input, sizeof(input), output));
    recordIs(45, 2147483647U, 0U);
    s540Global_libspdm_rsa_free(context);
    recordIs(46, 4294967295U, 0U);
    expect(!s540Global_libspdm_rsa_get_public_key_from_x509(input, sizeof(input), &context));
    recordIs(47, 4294967295U, 1U);
    expect(s540Global_libspdm_rsa_new() == nullptr);
    recordIs(48, 4294967295U, 3U);
    expect(!s540Global_libspdm_rsa_pss_sign(context, sizeof(input), input, sizeof(input), output, &outputSize));
    recordIs(49, 4294967295U, 7U);
    expect(!s540Global_libspdm_rsa_pss_verify(context, sizeof(input), input, sizeof(input), input, sizeof(input)));
    recordIs(50, 4294967295U, 15U);
    expect(!s540Global_libspdm_rsa_set_key(context, S540_GLOBAL_RSA_KEY_N, input, sizeof(input)));
    recordIs(51, 4294967295U, 31U);
    expect(!s540Global_libspdm_sha256_duplicate(context, context));
    recordIs(52, 4294967295U, 63U);
    expect(!s540Global_libspdm_sha256_final(context, output));
    recordIs(53, 4294967295U, 127U);
    expect(!s540Global_libspdm_sha256_hash_all(context, sizeof(input), output));
    recordIs(54, 4294967295U, 255U);
    expect(!s540Global_libspdm_sha256_init(context));
    recordIs(55, 4294967295U, 511U);
    expect(s540Global_libspdm_sha256_new() == nullptr);
    recordIs(56, 4294967295U, 1023U);
    expect(!s540Global_libspdm_sha256_update(context, context, sizeof(input)));
    recordIs(57, 4294967295U, 2047U);
    expect(!s540Global_libspdm_sha384_duplicate(context, context));
    recordIs(58, 4294967295U, 4095U);
    expect(!s540Global_libspdm_sha384_final(context, output));
    recordIs(59, 4294967295U, 8191U);
    expect(!s540Global_libspdm_sha384_hash_all(context, sizeof(input), output));
    recordIs(60, 4294967295U, 16383U);
    expect(!s540Global_libspdm_sha384_init(context));
    recordIs(61, 4294967295U, 32767U);
    expect(s540Global_libspdm_sha384_new() == nullptr);
    recordIs(62, 4294967295U, 65535U);
    expect(!s540Global_libspdm_sha384_update(context, context, sizeof(input)));
    recordIs(63, 4294967295U, 131071U);
    expect(s540Global_libspdm_x509_compare_date_time(context, context) == -2);
    recordIs(64, 4294967295U, 262143U);
    expect(!s540Global_libspdm_x509_get_cert_from_cert_chain(input, sizeof(input), 0, &constantPointer, &outputSize));
    recordIs(65, 4294967295U, 524287U);
    expect(!s540Global_libspdm_x509_get_extended_basic_constraints(input, sizeof(input), output, &outputSize));
    recordIs(66, 4294967295U, 1048575U);
    expect(!s540Global_libspdm_x509_get_extended_key_usage(input, sizeof(input), output, &outputSize));
    recordIs(67, 4294967295U, 2097151U);
    expect(!s540Global_libspdm_x509_get_extension_data(input, sizeof(input), input, sizeof(input), output, &outputSize));
    recordIs(68, 4294967295U, 4194303U);
    expect(!s540Global_libspdm_x509_get_issuer_name(input, sizeof(input), output, &outputSize));
    recordIs(69, 4294967295U, 8388607U);
    expect(!s540Global_libspdm_x509_get_key_usage(input, sizeof(input), &outputSize));
    recordIs(70, 4294967295U, 16777215U);
    expect(!s540Global_libspdm_x509_get_serial_number(input, sizeof(input), output, &outputSize));
    recordIs(71, 4294967295U, 33554431U);
    expect(!s540Global_libspdm_x509_get_signature_algorithm(input, sizeof(input), output, &outputSize));
    recordIs(72, 4294967295U, 67108863U);
    expect(!s540Global_libspdm_x509_get_subject_name(input, sizeof(input), output, &outputSize));
    recordIs(73, 4294967295U, 134217727U);
    expect(!s540Global_libspdm_x509_get_validity(input, sizeof(input), output, &outputSize, output, &outputSize));
    recordIs(74, 4294967295U, 268435455U);
    expect(!s540Global_libspdm_x509_get_version(input, sizeof(input), &outputSize));
    recordIs(75, 4294967295U, 536870911U);
    expect(!s540Global_libspdm_x509_set_date_time("20260101000000Z", context, &outputSize));
    recordIs(76, 4294967295U, 1073741823U);
    expect(!s540Global_libspdm_x509_verify_cert(input, sizeof(input), input, sizeof(input)));
    recordIs(77, 4294967295U, 2147483647U);
    expect(!s540Global_libspdm_x509_verify_cert_chain(input, sizeof(input), input, sizeof(input)));
    recordIs(78, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_aead_aes_gcm_decrypt(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(79, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_aead_aes_gcm_encrypt(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(80, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_asn1_get_tag(nullptr, nullptr, nullptr, UINT32_MAX));
    recordIs(81, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_check_crypto_backend());
    recordIs(82, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_decode_base64(nullptr, nullptr, SIZE_MAX, nullptr));
    recordIs(83, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_ec_compute_key(nullptr, nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(84, 4294967295U, 4294967295U);
    s540Global_libspdm_ec_free(nullptr);
    recordIs(85, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_ec_generate_key(nullptr, nullptr, nullptr));
    recordIs(86, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_ec_get_public_key_from_x509(nullptr, SIZE_MAX, nullptr));
    recordIs(87, 4294967295U, 4294967295U);
    expect(s540Global_libspdm_ec_new_by_nid(SIZE_MAX) == nullptr);
    recordIs(88, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_ecdsa_sign(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(89, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_ecdsa_verify(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    recordIs(90, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_encode_base64(nullptr, nullptr, SIZE_MAX, nullptr));
    recordIs(91, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_hkdf_sha256_extract(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    recordIs(92, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_hkdf_sha384_extract(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    recordIs(93, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_hmac_sha256_all(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr));
    recordIs(94, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_hmac_sha384_all(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr));
    recordIs(95, 4294967295U, 4294967295U);
    s540Global_libspdm_rsa_free(nullptr);
    recordIs(96, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_rsa_get_public_key_from_x509(nullptr, SIZE_MAX, nullptr));
    recordIs(97, 4294967295U, 4294967295U);
    expect(s540Global_libspdm_rsa_new() == nullptr);
    recordIs(98, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_rsa_pss_sign(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(99, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_rsa_pss_verify(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    recordIs(100, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_rsa_set_key(nullptr, S540_GLOBAL_RSA_KEY_N, nullptr, SIZE_MAX));
    recordIs(101, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha256_duplicate(nullptr, nullptr));
    recordIs(102, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha256_final(nullptr, nullptr));
    recordIs(103, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha256_hash_all(nullptr, SIZE_MAX, nullptr));
    recordIs(104, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha256_init(nullptr));
    recordIs(105, 4294967295U, 4294967295U);
    expect(s540Global_libspdm_sha256_new() == nullptr);
    recordIs(106, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha256_update(nullptr, nullptr, SIZE_MAX));
    recordIs(107, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha384_duplicate(nullptr, nullptr));
    recordIs(108, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha384_final(nullptr, nullptr));
    recordIs(109, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha384_hash_all(nullptr, SIZE_MAX, nullptr));
    recordIs(110, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha384_init(nullptr));
    recordIs(111, 4294967295U, 4294967295U);
    expect(s540Global_libspdm_sha384_new() == nullptr);
    recordIs(112, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_sha384_update(nullptr, nullptr, SIZE_MAX));
    recordIs(113, 4294967295U, 4294967295U);
    expect(s540Global_libspdm_x509_compare_date_time(nullptr, nullptr) == -2);
    recordIs(114, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_cert_from_cert_chain(nullptr, SIZE_MAX, INT32_MAX, nullptr, nullptr));
    recordIs(115, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_extended_basic_constraints(nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(116, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_extended_key_usage(nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(117, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_extension_data(nullptr, SIZE_MAX, nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(118, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_issuer_name(nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(119, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_key_usage(nullptr, SIZE_MAX, nullptr));
    recordIs(120, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_serial_number(nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(121, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_signature_algorithm(nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(122, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_subject_name(nullptr, SIZE_MAX, nullptr, nullptr));
    recordIs(123, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_validity(nullptr, SIZE_MAX, nullptr, nullptr, nullptr, nullptr));
    recordIs(124, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_get_version(nullptr, SIZE_MAX, nullptr));
    recordIs(125, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_set_date_time(nullptr, nullptr, nullptr));
    recordIs(126, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_verify_cert(nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    recordIs(127, 4294967295U, 4294967295U);
    expect(!s540Global_libspdm_x509_verify_cert_chain(nullptr, SIZE_MAX, nullptr, SIZE_MAX));
    recordIs(128, 4294967295U, 4294967295U);
    expect(context == input && mutablePointer == input && constantPointer == input);
    expect(outputSize == sizeof(output));
    expect(std::memcmp(originalOutput, output, sizeof(output)) == 0);
    expect(std::memcmp(originalTag, tag, sizeof(tag)) == 0);
    expect(input[0] == 0x37 && input[63] == 0x37);
    expect(key[0] == 0x72 && key[31] == 0x72);

    /* The shared refusal evidence must remain exact under concurrent callers. */
    constexpr unsigned workers = 8;
    constexpr unsigned perWorker = 2048;
    std::atomic<unsigned> unexpectedSuccess{0};
    std::thread threads[workers];
    for (auto &worker : threads)
        worker = std::thread([&] {
            for (unsigned i = 0; i < perWorker; ++i)
                if (s540Global_libspdm_random_bytes(nullptr, 0))
                    ++unexpectedSuccess;
        });
    for (auto &worker : threads)
        worker.join();
    expect(unexpectedSuccess.load() == 0);
    recordIs(128 + workers * perWorker, UINT32_MAX, UINT32_MAX);
    expect(!s540Global_crypto_available());
    std::printf("{\"component\":\"nvidia-global-rm-crypto-unavailable\","
        "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"abi_symbols\":64,\"serial_refusals\":128,"
        "\"concurrent_refusals\":%u,\"crypto_implemented\":false,"
        "\"caller_memory_unchanged\":%s,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n",
        failures ? "failed" : "passed", checks, failures,
        workers * perWorker, failures ? "false" : "true");
    return failures ? 1 : 0;
}

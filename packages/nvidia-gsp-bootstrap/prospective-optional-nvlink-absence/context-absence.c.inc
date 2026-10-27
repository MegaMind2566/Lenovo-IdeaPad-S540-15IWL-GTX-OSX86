static void s540LogOptionalNvlinkAbsence(S540GspContext *context)
{
    S540OptionalNvlinkAbsence absent;
    NV_STATUS status = s540OptionalNvlinkRead(&context->nv, &absent);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 optional NVLink absence: available=0 status=%u\n", (NvU32)status);
        return;
    }
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 optional NVLink absence: available=1 status=0 format=%u bytes=%u "
        "absent=%u classId=0x%x instance=%llu\n",
        absent.format, absent.bytes, absent.absent, absent.classId,
        (unsigned long long)absent.instance);
}

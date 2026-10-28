static void s540LogOptionalAcpiAbsence(S540GspContext *context)
{
    S540OptionalAcpiAbsence absent;
    NV_STATUS status = s540OptionalAcpiRead(&context->nv, &absent);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 optional ACPI capability absence: available=0 status=%u\n", (NvU32)status);
        return;
    }
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 optional ACPI capability absence: available=1 status=0 format=%u bytes=%u "
        "scope=selected-backend-capabilities dsmAbsentMask=0x%x dsmQueries=%u dodQueries=%u "
        "amlExecuted=0 hardwareAbsenceClaimed=0\n",
        absent.format, absent.bytes, absent.dsmAbsentMask, absent.dsmQueries, absent.dodQueries);
}

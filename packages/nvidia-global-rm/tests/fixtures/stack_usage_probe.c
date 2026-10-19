/* Compiler-only stack measurement control. Never linked or executed. */
__attribute__((noinline)) int s540StackUsageLeaf(int value)
{
    volatile unsigned char bytes[64];
    bytes[0] = (unsigned char)value;
    bytes[63] = (unsigned char)(value + 1);
    return (int)bytes[0] + (int)bytes[63];
}
__attribute__((noinline)) int s540StackUsageCaller(int value)
{
    volatile unsigned char bytes[96];
    bytes[0] = (unsigned char)value;
    bytes[95] = (unsigned char)s540StackUsageLeaf(value);
    return (int)bytes[0] + (int)bytes[95];
}

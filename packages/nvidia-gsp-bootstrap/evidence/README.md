# Observation of original GSP and adapter initialization

`s540GspObserveOriginal` reads the original NVIDIA object state after
`rm_init_adapter` returns true. It acquires the original API lock followed by the
device GPU lock, observes the protected objects, and releases both locks. The
outer owner keeps the stack, nv_state, and initialized adapter alive throughout
the observation. The observer reads fields and does not issue GPU commands,
firmware uploads or changes to success markers. The original GPU-lock wrappers
retain their normal interrupt mask/restore operations, including hardware
access when required by the original loaded-GPU lock protocol.

## Actual GSP response evidence

In the pinned `kgspSendInitRpcs_IMPL`, the original `gmcapiCommand` for
`GMCAPI_CMD_GSP_INIT` must return `NV_OK`. The returned static information must
then decode successfully through `_kgspDecodeGspStaticInfo`. Only after both
operations succeed does the original source set `OBJGPU.gspRmInitialized` true.
GPU construction sets this marker false. No new marker or upstream semantic
patch is needed.

The observer also requires the original GPU to be fully constructed and state
loaded, with its DMA, manager attachment, HAL, GPU state and core-logic init
flags present. It checks that the object belongs to the supplied TU117 device,
GSP client mode is selected, loading and unloading are inactive, the GPU is
connected and not lost, and GSP has no fatal, lockdown or unloaded state.

`adapterReady` is true only when all these checks and both lock releases
succeed. The coordinator must additionally require the original adapter entry
to have returned true and all OS/crypto service refusal counters to remain zero.

Firmware requests and byte delivery are not accepted as response evidence.
The decoded response establishes a real host/GSP exchange through the original
message transport. It does not establish that interrupt delivery was used:
the original initialization path can poll for responses. It also does not
establish execution of an application GPU command, rendering or Metal support.

Output contains booleans, check/failure counts and the original `bootAttempts`
counter. Resource addresses, pointers, register values and firmware contents are
not published. `bootAttempts` is not relabeled as an exact count of successful
responses, interrupts or GPU jobs.

`PROVENANCE.json` records exact source hashes and line anchors for this meaning.
The observer compiles against the complete original structures and global-RM
namespace; it does not substitute a reduced or guessed object layout.

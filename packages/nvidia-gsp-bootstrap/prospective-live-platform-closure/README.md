# Live platform ABI boundary

This isolated participant defines seven callbacks retained by the linked RM image.

The BIF answer preserves the original `!init_on_probe` meaning. It requires the explicit manual-adapter-start profile and the exact retained transaction state. It does not certify hardware reset safety. The original inverse macro also controls software persistence, so a generic false capability answer would change unrelated behavior.

Temporary-file allocation returns the official disabled-filesystem error without publishing a handle. Reads and writes return `NV_ERR_NOT_SUPPORTED` without changing buffers. Each attempt records an unavailable operation. Only closing a NULL handle is an empty-owner operation; a non-NULL handle stops execution because no backend in this profile can create one.

Console lock callbacks also stop execution. The selected provider must exclude NVIDIA from all active consoles before entry. The real original console query then reports false and its guarded console calls are not taken. These definitions provide no console implementation.

The checker compiles the original headers, executes five pinned official bodies and seven original callers with explicit Linux-layout, transaction-identity and console-metadata fixtures, and verifies failure paths. Production defaults, hardware entry and stack admission remain unchanged.

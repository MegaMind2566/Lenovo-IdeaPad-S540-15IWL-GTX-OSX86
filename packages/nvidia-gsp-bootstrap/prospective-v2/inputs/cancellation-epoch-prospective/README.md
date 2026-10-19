# Isolated source-body fixtures

The exact kgspBootstrap_TU102 body invalidates an old stop marker before every tested hardware/firmware stage. Ninety checks per plain/fatal variant use explicit stage fixtures. No stopped receipt is issued.

Run the parent `check_body_controls.py` CLI; it regenerates the exact bodies from pinned upstream bytes and these patches. No original source tree or executable is stored here.

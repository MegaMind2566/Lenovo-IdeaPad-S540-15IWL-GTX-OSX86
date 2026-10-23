Context disable and shutdown now call the real checked original wrappers and
propagate their exact error status. A failed call quarantines the Context and
preserves its disabled/shutdown/initialized state rather than publishing a
successful teardown after a void wrapper discarded the error.

The public Context ABI and older source profiles stay unchanged. There is no
new DMA-stop receipt, memory-release authority, kernel admission or claim of
successful device initialization. CPU fault controls and complete original-
header compilation are recorded separately from native image and Lenovo tests.

# Persistent secret publication on Linux and PRoot

`app/core/secret_file_access.py` publishes a complete protected secret once.
It must keep an existing or concurrent winner unchanged, reject unverified
links, and clean up incomplete temporary files. It never rotates a key to
recover from a missing or inaccessible key in an existing data directory.

On Linux, publication uses libc `renameat2` with `AT_FDCWD` (-100) and
`RENAME_NOREPLACE` (1). The temporary file and destination share a directory.
The temporary file is mode 0600 and is flushed before publication. An existing
destination wins atomically. An unsupported syscall/filesystem or other I/O
failure fails closed; there is no fallback to an overwriting rename. The
official Linux images provide the required libc interface. Windows keeps its
protected creation, handle/ACL verification and non-replacing hardlink path.

This avoids PRoot's hardlink-to-symlink emulation moving the actual secret into
the image root's `.l2s` directory. Such a link in the persistent data bind can
look like a regular file inside the original guest, but cannot be reopened by
a later image root. An application secret must remain in persistent data,
independent of the disposable image. PRoot's normal sandbox and link emulation
settings are preserved; key path protections are not relaxed.

An existing affected key requires explicit recovery from its verified old
backing file while the application is stopped. Preserve the old root and
backup both the link metadata and actual secret bytes privately. Replace only
the verified data-directory link with a regular 0600 file containing those
same bytes, and verify equality before restarting. Do not follow arbitrary
links automatically or generate a replacement key. A tar archive containing
only the old link is not a self-contained secret backup.

Regression scope: existing key/ACL preservation, concurrent first-writer-wins,
no hardlink call on Linux, publication failure cleanup and contributor refusal
to initialize existing data without its secret. Real PRoot validation also
checks that the host sees a regular file and that the same synthetic secret
survives opening it from two independent image roots. Synthetic probes do not
read application credentials.

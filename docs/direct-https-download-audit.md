# Direct HTTPS download audit

This change hardens and improves the existing PS4 direct-URL transfer path. It does not discover commercial titles, obtain entitlements, bypass PSN authentication, or supply copyrighted package links. The caller must provide a URL it is authorized to download.

## Findings in the previous implementation

- The SSL callback returned success for every certificate result, and the HTTPS template disabled an SSL option. That defeated certificate validation.
- The main transfer loop read only 255 bytes per sceHttpReadData call. The metadata/range helper used 1 KiB reads. Both create avoidable syscall/service-call overhead.
- The resume path accepted HTTP 200 after sending a non-zero Range request. If a server ignored Range, the response could be appended to a partial file and corrupt it.
- The main body loop searched the received body for an HTTP header terminator, although sceHttpReadData supplies response-body data.
- Transient errors deleted the partial file, preventing the existing resume constructor from reusing it.

## Changes

- Remove the always-success SSL callback and the HTTPS option override; leave platform TLS verification enabled.
- Send Accept-Encoding: identity so byte ranges map to the stored representation.
- Require HTTP 206 for non-zero resume offsets.
- Increase body read buffers to 64 KiB and check signed read results, writes, and flushes.
- Preserve partial files after transient failures; explicit deletion still removes them.

## Limits and validation

This is a throughput and correctness improvement, not a promise of a particular Mbps rate. It cannot remove a CDN-side cap or make a server support parallel ranges. Parallel segmented transfers are intentionally not enabled until range behavior, thread safety, and disk-write coordination are validated on real PS4 hardware.

Build with the project's OpenOrbis toolchain, then test a small authorized HTTPS file, a large authorized file, pause/resume, a server that ignores Range, and a certificate failure. Do not ship if certificate validation is not enforced on the target firmware.
# Citraverse iPhone call fix — 0.1.1 build 2

Cloud calls previously read the microphone through the legacy PCB `/call/pcm`
proxy, which returned HTTP 502 during live tests and immediately ended the call.
Cloud receive now uses the already-running, authenticated `/audio/live` stream.
LAN receive retains its original token-protected direct endpoint. Speaker uploads,
call start/stop, exclusive lease, idle mute and foreground-only behavior remain.

Retryable HTTP/network failures get a bounded two-second recovery window instead
of ending a call on the first failure. Uncertain speaker packets are not replayed;
the next upload uses fresh capture. Access-denied and malformed audio stay terminal.
Audio-session notifications end a call only when an interruption begins.

## Validation

Signed iPhone build passed and was installed/launched wirelessly on the existing
paired iPhone. The source URL/auth-scope/retry-category tests passed. A four-second
silent live GCP probe completed 13 speaker uploads, 38 microphone reads and 84
radar frames; hang-up returned 200 and muted the amplifier. Phone UI/acoustic
confirmation is recorded separately; these transport checks do not establish it.

Previous source checkpoint: `ios-before-call-fix-20261127`. Firmware and existing
cloud keys were not changed by this app update. Signed binaries and pairing
credentials remain local, outside Git.

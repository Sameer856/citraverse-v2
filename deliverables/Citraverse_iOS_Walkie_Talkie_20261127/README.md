# Walkie-talkie test — iPhone build 4

Requires PCB 1.1.0-audio-rc9 (normal fixed 1× gain).

Open Device → Call room. The call starts listening to the room. Hold the large
Hold to talk button to send the iPhone microphone to the PCB speaker; release to
listen again. App playback and microphone polling pause while talking. Late
receive responses from a previous turn are discarded, and playback resumes after
the current upload completes plus a 300 ms speaker queue drain.

Outbound audio uses 100–120 ms batches with a bounded 240 ms pending buffer.
A five-second authenticated microphone RPC keeps listening-only calls alive; its
body is not played. Calls still stop on leaving the screen or backgrounding.

PCB microphone capture, SD recording and GCP archival continue independently.
This changes conversational playback direction, not continuous recording.
Weak Wi-Fi may still cause gaps; no loss-free delivery is promised.

The signed build passed. Installation and PCB normal-gain boot validation passed;
physical speech quality awaits the user's test with the replacement speaker.

## Connected-device checks

The phase test passed: 25 seconds listening with five-second lease renewals,
eight seconds of silent speaker uploads, then five seconds listening. It read
213 microphone batches, sent 46 speaker packets and hung up successfully.
One read-only power diagnostic needed a retry; call-phase requests succeeded.
The PCB reported gain 65536/65536 (1×), no new I2S errors, and muted after the
return to listening and at hang-up. Network throughput is still variable.

A separate 0.5-second tone passed: 25 blocks accepted and played, input/output
peaks both 4000, zero I2S errors, zero observed radar frame-index gaps.
These checks do not substitute for the user's acoustic feedback.

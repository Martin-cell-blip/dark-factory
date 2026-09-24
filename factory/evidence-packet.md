# Evidence packet

Every handoff from the builder carries one of these, posted in the room as a message and
saved in the folder as `evidence/<commit-short>.md`. A handoff without a packet is
returned unread.

```
EVIDENCE PACKET
commit:      <full sha>
folder:      <folder name>
claims:      <ledger item numbers, comma separated>
environment: <container image tag or "host">, <os>, <runtime version>

commands (in order, each with its own exit code and output digest):
  1. cmd:    <exact command, copy-pasteable>
     exit:   <integer>
     digest: sha256 of stdout+stderr, first 12 hex
     tail:   last 3 lines of output, verbatim
  2. ...

tests: <count run>, <count passed>, <count failed>
changed files: <list>
not claimed: <anything the commit touches that is NOT covered by a ledger item, or "none">
```

## Paths

Every path in a packet is relative to the repository root. Never an absolute path, never a
home directory, never a machine name: the packet is committed, and the judge clones the
repository on another machine.

## Why a digest and not a log

A log can be edited. A digest over the captured output lets the auditor re-run the same
command and compare twelve characters. If they differ, the packet does not reproduce and
the discussion ends there.

## How the auditor uses it

1. `git checkout <sha>`
2. Run each `cmd` exactly, capture stdout+stderr, hash it, compare to `digest`.
3. Only then run the ledger checks for `claims`.
4. Only then run the adversarial sweep.

## How the gatekeeper uses it

The release note references the last accepted packet per ledger item. Items with no
accepted packet cannot be released.

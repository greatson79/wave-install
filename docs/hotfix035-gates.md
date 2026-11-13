# Installer hotfix release gates

Gate A (`scripts/check-installer-launch.py ROOT`) parses PowerShell command nodes without executing the installer. It checks the three cmd launcher helpers and the ASCII, BOM-free win-start entry. Comments and here-string literals do not count as commands. The assembler runs it on both source and generated assets; the pack builder checks source.

Gate B (`scripts/check-hotfix-coverage.py`) prints the historical upload inventory in `hotfix-uploads.json` and checks stable patch identities in repository history. The latest exact forward/reverse patch decides whether each of the 15 restored hotfix patches is present. This is a provenance and exact-revert guard, not a semantic verifier: partial or combined regressions require the behavior tests and Gate A. Both the release assembler and `tests/win-pin-check.py` run the gates before release/pin work; CI must fetch complete history.

The inventory is generated from preserved `release*/UPLOAD_hf*` directories, not entered by hand:

```sh
python3 scripts/check-hotfix-coverage.py --discover /path/to/round --history /path/to/hotfix-source
python3 scripts/check-hotfix-coverage.py --published /path/to/published-readback
```

Asset source bindings identify the earliest normalized source-equivalent commit, not an asserted build checkout. Release URL/hash substitutions are normalized; ZIP bindings compare the embedded bootstrap member only. SHA256SUMS bindings list the sibling source commits. The original evidence paths and exact uploaded hashes remain in the inventory. A missing binding blocks the gate. The published-assets table separately shows which historical source binding can be found in today's readback.

The 0.3.3 migration branch is a separate feature and is not restored by this hotfix.

## Diagnostic identity

`J-AV-04` recognizes Win32 exception native error 4551 and HRESULT `0x800711C7`, including nested exceptions. It also preserves returned cmd error 4551 through the setup/bounded helpers. A numeric cmd exit is treated as that error identity; it does not independently prove which security product caused the exit. Other codes retain the existing rules. Source: [Microsoft WinSDK winerror.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/winerror.h), `ERROR_SYSTEM_INTEGRITY_POLICY_VIOLATION`. This change is tested with injected failures; a real policy block has not been measured on a runner. The user guidance and its Microsoft sources are generated in [help-codes.md](help-codes.md).

## Help replies

The help service returns 410 for GET replies. A receipt confirms submission, not an in-window answer. Windows and the shared Python client tell the user to give that receipt number to the responsible person, who provides the answer directly. Existing polling/close behavior remains unchanged and is tested against a scripted 410 response.

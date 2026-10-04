# Signal-run evidence fixture provenance

Copied byte-for-byte from `개발본부/_round/evidence/rc5-signal1-37188325110/rc-evidence-win-nonhome-37188325110/` on 2026-10-04. The source run evidence was supplied by the pulse lead; no response text or state was synthesized.

| File | Source SHA-256 | Fixture SHA-256 |
|---|---|---|
| `win/run.exit` | `53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3` | same |
| `win/G1_state.json` | `d4ab690998c8976dabf171deb7f92204f997fa30278feb92b0558d2261b96ee6` | same |

`identity.json`, `win/G4_status.json`, and `win/G6/G4_status.json` are likewise copied byte-for-byte and preserve the original CWD check inputs. The fixture supports a paired regression: the former seat-CWD-only check returns 0, while the first-run exit/state check returns 1 for this exact run.

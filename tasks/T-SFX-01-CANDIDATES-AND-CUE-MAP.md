# SFX-01 — independent sound design / candidate preparation
Status: candidate acquisition implemented, offline CI pending; no actual download,
audition, placement or mix. No manuscript available to the lead; never invent
chapter events. Parallel to voice QA, no production synth or cache changes.

## Public source audit (2026-11-27)
- Wikimedia Commons: CC0 recordings with author, permanent file page, size and
  published checksum. Selected first two self-published samples are listed in
  sfx/public-candidates.json. No inference that all Commons content is CC0.
- Freesound: per-file CC0/CC BY/NC; API terms distinguish commercial and
  noncommercial use. No automatic commercial API integration on free access.
  https://freesound.org/docs/api/terms_of_use.html
- Pixabay: license supports incorporated creative works; standalone
  redistribution restricted; music may have Content ID claims. Manual
  item-specific rights/terms check first. https://pixabay.com/service/terms/
- Mixkit: license is item/type specific; permitted uses enumerated, audiobook
  distribution not assumed. https://mixkit.co/license/
- Candidate music The Wind (Komiku) on Commons has a license-review-needed
  flag; do not download automatically or approve until original license verified.
  https://commons.wikimedia.org/wiki/File:Komiku_-_13_-_The_Wind.ogg
- Wind chime (Membeth), CC0 own work, potential transition after audition;
  not in first automated manifest because source checksum was not established.
  https://commons.wikimedia.org/wiki/File:Windglockenspiel.Koshi.ogg

## Explicit download
From reviewed research checkout, with approved network access:
`python scripts/sfx_fetch.py --out <new-local-candidate-directory>`
Directory must be new, outside production/cache and not tracked. Downloads
only the two fixed inventory originals via HTTPS; redirects rejected; exact
size and published SHA1 checked, local SHA256 recorded. No auth, no scraping
or inference. No automatic retry. Partial batch has no ready receipt.
No audio committed; retain originals, receipt and source license evidence
locally. A byte match does not establish suitability or independent legal
ownership. Audition and check third-party rights before approving.

## Placement map contract (proposed, local/private)
One cue = stable cue_id, section_id, source unit ID, chunk_id, source fingerprint,
anchor edge (before/after/within), signed offset_ms, duration_ms, asset_id,
asset SHA256, cue type (ambience/transition/music), gain_db, fade_in_ms,
fade_out_ms, ducking policy, status (draft/reviewed/approved), revision.
A resolved mix plan additionally binds exact assembled voice SHA256, manifest
and index SHA256, actual timing, accepted seed/override and full chunk identity.
Existing assemble.py INDEX_COLUMNS are id/start_ms/lead_ms/hash16/seed/dur_ms;
the index alone is not full identity. Resolve against exact manifest/WAVs,
reject stale identities, duplicate cue IDs, negative resolved time, out of
bounds or unknown asset. Re-resolve when assembly/pause timing changes;
never edit source text or TTS cache just to add SFX.

## Mix and acceptance
Start with sparse cues (scene transitions, ambience only where justified,
music at chapter boundaries). No continuous bed by default. Keep narration
intelligible; choose conservative levels and fades after listening, not
fixed production values yet. Render isolated dry/wet previews from identical
voice; keep separate stems and untouched dry output. Run existing final
mastering after mix using project tools, check clipping/loudness and sample
alignment, no overwrite of canonical section.wav. Compare one short A/B
before applying any library of effects. Private placement cannot be done
without the actual source and owner/auditor-approved cues. No full render.

Next: actual candidate acquisition + audition when network permitted, then
real local chapter placement using the existing source/manifest/index.
Only after candidate/placement approval implement bounded mixer tests.

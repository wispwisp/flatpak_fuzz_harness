# Flatpak fuzz harness reference

A per-harness description of the AFL++ fuzz harnesses landed in
[`FUZZ_HARNESS.patch`](FUZZ_HARNESS.patch). Eight harnesses total. For
build-system rationale and the wider attack-surface model see
[`docs/superpowers/specs/2026-05-14-fuzzing-source-prep-design.md`](docs/superpowers/specs/2026-05-14-fuzzing-source-prep-design.md);
this document is descriptive, not normative.

All file:line references point into the flatpak-1.12.9 source tree
(`common/`). They were verified once when the design spec was written;
the harnesses themselves call the symbols by name, so a line drift in a
point release does not invalidate the attack-surface claim.

## Summary

| Harness | Target symbol(s) | Input | Selector | Max size | Dict | Persist-loop |
|---|---|---|---|---|---|---|
| `fuzz-smoke` | (none — sanity check) | raw bytes | — | unbounded | — | 10000 |
| `fuzz-ref` | `flatpak_decomposed_new_from_{ref,refspec,col_ref}` | NUL-terminated string | byte 0 mod 3 | 4 KiB | `ref.dict` | 10000 |
| `fuzz-oci-versioned` | `flatpak_oci_versioned_from_json` | JSON | byte 0 mod 4 (content_type) | 1 MiB | `oci.dict` | 10000 |
| `fuzz-oci-image` | `flatpak_oci_image_from_json` | JSON | — | 1 MiB | `oci.dict` | 10000 |
| `fuzz-repofile` | `flatpak_parse_repofile` | GKeyFile | — | 256 KiB | `keyfile.dict` | 10000 |
| `fuzz-filter` | `flatpak_parse_filters` | text | — | 256 KiB | `keyfile.dict` | 10000 |
| `fuzz-metadata` | `flatpak_context_load_metadata` | GKeyFile | — | 256 KiB | `keyfile.dict` | 10000 |
| `fuzz-oci-registry-local` | `flatpak_oci_registry_load_{versioned,image_config,index}` | bytes (manifest/config/index) | byte 0 mod 3 | 512 KiB | `oci.dict` | 1000 |

## Attack-surface taxonomy

The harnesses cover three input vectors:

- **Local file, attacker-handed-to-user.** `fuzz-repofile`,
  `fuzz-filter`, `fuzz-metadata`. User runs `flatpak remote-add
  ./mal.flatpakrepo`, `flatpak --filter=./bad`, or installs an app whose
  bundled `metadata` is malicious.
- **String parsing.** `fuzz-ref`. Refs flow in from CLI args, OCI tags,
  summary indexes, and many other places. Any code path that accepts an
  untrusted ref string reaches the decomposed-ref parser.
- **Network-shaped, post-fetch.** `fuzz-oci-versioned`, `fuzz-oci-image`,
  `fuzz-oci-registry-local`. Bytes that arrived (or would arrive) over
  HTTPS from an OCI registry the user pulls from. The local-registry
  variant goes deeper, exercising the on-disk layout reader, digest
  arithmetic, and mediaType dispatch in addition to JSON parsing.
- **None.** `fuzz-smoke` is a build/link sanity harness only — it
  reaches no flatpak code.

The two attack vectors *not* exercised in this set are D-Bus (the portal
and system-helper services) and OSTree summary GVariant parsing. The
design spec lists those as out-of-scope (D-Bus) or v2 (summaries); see
its §4 "Out-of-scope surfaces" and §4 "Parser entry points planned for
v2".

---

## `fuzz-smoke`

**Source.** `fuzz/fuzz-smoke.c`.

**Target.** None. The harness only exercises `fuzz_dup_cstring` and
`fuzz_sha256_hex` from `fuzz-common.c`.

**Why it exists.** A no-op harness that compiles and links exactly the
same way as the real harnesses. If `make fuzz/fuzz-smoke` fails, no
other harness will build; if `fuzz/fuzz-smoke @@seed` runs, the
AFL-instrumentation toolchain and the persistent-mode glue are working.
The CI image (`fuzz-runtime`) and the instrumentation-fix plan use this
as a probe.

**Bug classes detectable.** Only build/runtime failure of the harness
infrastructure itself. Not a security harness.

**Known gaps.** No corpus directory, no dictionary. Nothing in flatpak
proper is reached.

---

## `fuzz-ref`

**Source.** `fuzz/fuzz-ref.c`.

**Target.** Three sibling constructors and the read-side accessors:

- `flatpak_decomposed_new_from_ref` — `common/flatpak-ref-utils.c:721`
- `flatpak_decomposed_new_from_refspec` — `common/flatpak-ref-utils.c:728`
- `flatpak_decomposed_new_from_col_ref` — `common/flatpak-ref-utils.c:749`
- accessors: `flatpak_decomposed_dup_id` / `_dup_arch` / `_dup_branch` /
  `_dup_pref` / `_dup_readable_id` / `_get_collection_id`

**Input shape.** Byte 0 is a selector (`% 3`) that picks which
constructor to call. Bytes `[1..]` are duplicated to a NUL-terminated
heap string and passed in.

**Size constraints.** `2 ≤ size ≤ 4096`. Refs are small in practice.

**Transitive coverage.**

- Slash-tokenization of `kind/id/arch/branch` quadruples.
- Optional `remote:` prefix split for refspecs.
- Optional `collection-id:` prefix split for collection refs.
- Read-back through every accessor — pulls the parser's internal
  offsets through user-visible code paths.

**Bug classes catchable.** Heap-buffer-overflow on truncated input,
allocator-size confusion in the slash-counting loop, UAF in error
paths, signedness bugs around `g_str_has_prefix`. Logic bugs are not
catchable — there is no oracle here.

**Security relevance.** Refs are the universal coordinate in flatpak.
Any path that accepts an attacker-controlled ref string (CLI install,
remote-add, OCI tag, summary index) reaches one of these three
constructors. A heap bug here is reachable pre-auth from any
attacker-controlled registry or repository.

**Dictionary.** `fuzz/dict/ref.dict` — `app/`, `runtime/`, common
arches (`x86_64`, `aarch64`, `arm`, `arm64`, `i386`, `riscv64`),
branches (`stable`, `master`, `22.08`, `23.08`, `24.08`), subref
suffixes (`.Locale`, `.Debug`, …), and the `:` collection separator.

**Seeds.** `fuzz/corpus/ref/`: `seed-app`, `seed-runtime`,
`seed-refspec` (`flathub:app/org.example.Hello/x86_64/stable`),
`seed-col-ref` (`org.example:app/org.example.Hello/x86_64/stable`).

**Known gaps.** Doesn't cross-check the parsed `FlatpakDecomposed`
against any consumer (e.g., `flatpak_decomposed_is_app`, equality
comparisons), so logic bugs in the parse output are invisible unless
they corrupt memory.

---

## `fuzz-oci-versioned`

**Source.** `fuzz/fuzz-oci-versioned.c`.

**Target.** `flatpak_oci_versioned_from_json(GBytes *bytes, const char
*content_type, GError **error)` — `common/flatpak-json-oci.c:176`. On a
non-NULL return, the harness also exercises
`flatpak_oci_versioned_get_mediatype` and
`flatpak_oci_versioned_get_version`.

**Input shape.** Byte 0 selects the `content_type` hint (`% 4`):

| byte 0 % 4 | content_type passed |
|---|---|
| 0 | `NULL` (force schema-driven detection) |
| 1 | `FLATPAK_OCI_MEDIA_TYPE_IMAGE_MANIFEST` |
| 2 | `FLATPAK_OCI_MEDIA_TYPE_IMAGE_INDEX` |
| 3 | `FLATPAK_DOCKER_MEDIA_TYPE_IMAGE_MANIFEST2` |

Bytes `[1..]` are the JSON body, wrapped in a `GBytes`.

**Size constraints.** `2 ≤ size ≤ 1 MiB`.

**Transitive coverage.**

- json-glib parse of an arbitrary JSON document.
- Dispatch on `schemaVersion` + `mediaType` to one of the OCI subclass
  readers.
- Field validation: `config.{digest,size}`, `layers[]`,
  `manifests[]` (for indexes).
- Descriptor-list walks where attacker-controlled `size` fields
  participate in allocation arithmetic.

**Bug classes catchable.** Heap-buffer-overflow in JSON string copy,
integer overflow on `size` fields, type-confusion on
`schemaVersion`/`mediaType` mismatch, UB in array-length arithmetic.

**Security relevance.** Every OCI pull touches this. The bytes are
attacker-controlled in the sense that a malicious registry can serve
any JSON it wants; the user only need point `flatpak install` at it.
This is pre-authentication relative to GPG signature checks (signatures
are checked over the *commit*, not the registry manifest).

**Dictionary.** `fuzz/dict/oci.dict` — OCI/Docker mediatypes, manifest
field names (`schemaVersion`, `mediaType`, `config`, `layers`,
`manifests`, `digest`, `size`, `platform`, …), digest prefixes
(`sha256:`, `sha512:`).

**Seeds.** `fuzz/corpus/oci-versioned/`: `seed-index`, `seed-manifest`.
Both seeds are well-formed OCI v2 documents.

**Known gaps.** Skips the HTTPS transport. Doesn't fuzz the post-parse
*use* of the result (layer extraction, ref→commit walks) — those have
their own (planned) harnesses.

---

## `fuzz-oci-image`

**Source.** `fuzz/fuzz-oci-image.c`.

**Target.** `flatpak_oci_image_from_json(GBytes *bytes, GError **error)`
— `common/flatpak-json-oci.c:221`.

**Input shape.** Raw JSON, wrapped in `GBytes`. No selector byte.

**Size constraints.** `1 ≤ size ≤ 1 MiB`.

**Transitive coverage.**

- json-glib parse of an OCI image-config JSON.
- Field validation on `created`, `architecture`, `os`,
  `config.{Env, Entrypoint, Cmd, WorkingDir, Labels, Volumes}`,
  `rootfs.{type, diff_ids[]}`, `history[]`.
- Array walks over `Env` and `diff_ids` where every element is an
  attacker-controlled string.

**Bug classes catchable.** Heap-buffer-overflow in env-string copy,
type-confusion when fields disagree with their JSON-Schema types,
allocator-size bugs in `diff_ids[]` parsing.

**Security relevance.** The image config is parsed for every OCI-format
flatpak install. Its `Env` and `Entrypoint` ultimately flow into the
sandbox launch path, so bugs that survive parsing into the FlatpakOciImage
struct also have downstream consequences — but this harness only catches
crashes/UB during parsing itself.

**Dictionary.** `fuzz/dict/oci.dict`.

**Seeds.** `fuzz/corpus/oci-image/seed-1` — a minimal but well-formed
image-config JSON.

**Known gaps.** Doesn't exercise the use of the parsed config (env
merging into `flatpak run`, label-driven behavior).

---

## `fuzz-repofile`

**Source.** `fuzz/fuzz-repofile.c`.

**Target.** `flatpak_parse_repofile("fuzz-remote", FALSE, keyfile,
&gpg_data, NULL, &error)` — `common/flatpak-utils.c:2205`.

The harness is two-step: it first calls `g_key_file_load_from_data` and
only invokes `flatpak_parse_repofile` if the keyfile parses. This is
intentional — the GKeyFile loader is a GLib upstream concern and most
bug surface in flatpak's repofile parser sits *after* a keyfile is
successfully loaded.

**Input shape.** A `.flatpakrepo` body (GKeyFile syntax). No selector.

**Size constraints.** `1 ≤ size ≤ 256 KiB`.

**Transitive coverage.**

- `[Flatpak Repo]` group required-key extraction (`Url`).
- Optional keys: `Title`, `DefaultBranch`, `Description`, `Homepage`,
  `Icon`, `GPGKey`, `NoDeps`, `Comment`, …
- Base64 decode of `GPGKey=` into a `GBytes` (`g_base64_decode`).
- URI canonicalization on `Url`.
- GVariant assembly for the parsed remote config.

**Bug classes catchable.** Heap issues in the base64 decoder path,
URI-validation oddities, GVariant assembly bugs on truncated or
malformed inputs.

**Security relevance.** Pre-auth in the "user clicked a `.flatpakrepo`
link in a browser and ran `flatpak remote-add`" sense. The result is
also used to seed the GPG verification material for the new remote, so
a bug that survives parsing here has implications for the trust
boundary of subsequent installs from that remote.

**Dictionary.** `fuzz/dict/keyfile.dict` (covers `[Flatpak Repo]`,
common key names, value tokens).

**Seeds.** `fuzz/corpus/repofile/seed-1` — minimal repofile with title,
URL, branch, and empty GPGKey.

**Known gaps.** Doesn't exercise the *application* of the parsed
repofile (the code path that actually mutates the local config). GPG
signature verification of the repo is not in scope here.

---

## `fuzz-filter`

**Source.** `fuzz/fuzz-filter.c`.

**Target.** `flatpak_parse_filters(s, &allow, &deny, &error)` —
`common/flatpak-utils.c:879`.

**Input shape.** Filter-file text, duplicated to a NUL-terminated heap
string. No selector.

**Size constraints.** `1 ≤ size ≤ 256 KiB`.

**Transitive coverage.**

- Line-by-line scan of the filter file.
- Per-line dispatch on `allow ` / `deny ` keywords.
- Wildcard-to-regex translation of the ref pattern on each line
  (internal `flatpak_filter_glob_to_regex`).
- GRegex compilation of the resulting pattern.
- Construction of two combined `GRegex` objects (allow / deny).

**Bug classes catchable.** Heap issues in the line tokenizer, GRegex
compilation failures that the parser does not handle gracefully,
allocator bugs in glob→regex translation. Less likely but possible:
regex catastrophic-backtracking patterns reaching live code via
`flatpak_filter_glob_to_regex`.

**Security relevance.** Filter files are typically authored by org
admins, not arbitrary attackers, so the threat surface is narrower than
the network-facing parsers. Still: filter parsing happens for any
remote that has a filter attached, and any parser is worth fuzzing.

**Dictionary.** `fuzz/dict/keyfile.dict` — reused because
`fuzz/scripts/run.sh` groups filter with the other text/keyfile
harnesses. It is not actually well-tuned for filter syntax (the verbs
`allow` / `deny`, the `app/` and `runtime/` prefixes that *do* live in
`ref.dict`, and glob metacharacters are all missing). A
filter-specific dict is a low-effort follow-up.

**Seeds.** `fuzz/corpus/filter/seed-1` — three lines exercising both
`allow` and `deny`, the `app/` and `runtime/` namespaces, and a
trailing wildcard.

**Known gaps.** Doesn't exercise filter *application* (matching parsed
filters against ref lists). That's where a TOCTOU-style logic bug
would manifest.

---

## `fuzz-metadata`

**Source.** `fuzz/fuzz-metadata.c`.

**Target.** `flatpak_context_load_metadata(FlatpakContext *ctx,
GKeyFile *metakey, GError **error)` — `common/flatpak-context.c:1603`.

The harness is two-step: `g_key_file_load_from_data` first, then
`flatpak_context_load_metadata` on a fresh `FlatpakContext`. Both calls
return errors silently; only crashes / sanitizer trips count as
findings.

**Input shape.** A `metadata` keyfile body (the same file that lives at
the root of every deployed flatpak app). No selector.

**Size constraints.** `1 ≤ size ≤ 256 KiB`.

**Transitive coverage.**

- `[Application]` / `[Runtime]` group key reads.
- `[Context]` parsing — and this is the high-value part:
  - `shared=` parsed as `FlatpakContextShares` flags
    (`network`, `ipc`, …).
  - `sockets=` parsed as `FlatpakContextSockets` flags
    (`x11`, `wayland`, `pulseaudio`, `session-bus`,
    `system-bus`, `fallback-x11`, `ssh-auth`, `pcsc`, `cups`).
  - `devices=` parsed as `FlatpakContextDevices` flags
    (`dri`, `all`, `kvm`, `shm`).
  - `features=` parsed as `FlatpakContextFeatures` flags
    (`devel`, `multiarch`, `bluetooth`, `canbus`,
    `per-app-dev-shm`).
  - `filesystems=` parsed as a list of paths with optional
    `:create` / `:ro` mode suffixes and optional `!` negation
    prefix. Goes through `parse_filesystem_flags`.
  - `persistent=` parsed as a path list.
- `[Session Bus Policy]` / `[System Bus Policy]` parsing into
  per-name `FlatpakPolicy` enum values.
- `[Environment]` parsing into a name→value map.

**Bug classes catchable.** Memory safety in the flags-parsing loops
and filesystem-mode token handling; UB on malformed input; assertion
trips on inputs the parser was not expected to receive.

**Security relevance.** **This is the highest-value Tier A harness.**
Metadata is bundled with every flatpak app — anyone who can publish to
flathub (or to any remote a user adds) can supply arbitrary metadata.
The parsed result drives the sandbox policy: `--filesystem=` paths,
`--share=` shares, `--device=` device exposure, bus policies. A
parser bug that misreads a `filesystems=` token has direct
sandbox-confidence implications, even if it never crashes — though
this harness only catches the crash/UB subset.

**Dictionary.** `fuzz/dict/keyfile.dict` — covers all the group names
this parser cares about plus the value tokens (`home`, `host`, `x11`,
`wayland`, `dri`, `all`, `kvm`, `talk`, `own`, …).

**Seeds.** `fuzz/corpus/metadata/seed-1` — a realistic application
metadata file with `[Application]`, `[Context]` (covering shared,
sockets, devices, filesystems with `:create` mode + `!` negation,
features), `[Session Bus Policy]`, and `[Environment]`.

**Known gaps.** No oracle for the parser *output*. A bug that turns
`!/etc` into a non-negated `/etc` exposure would not produce a crash.
A future "differential" harness — comparing the parsed policy against a
reference reimplementation — is the way to close this gap, but is out
of scope for v1.

---

## `fuzz-oci-registry-local`

**Source.** `fuzz/fuzz-oci-registry-local.c`.

**Target.** One of three (selector chosen per iteration):

- `flatpak_oci_registry_load_versioned` — `common/flatpak-oci-registry.c:591`
- `flatpak_oci_registry_load_image_config` — `common/flatpak-oci-registry.c:1225`
- `flatpak_oci_registry_load_index` — `common/flatpak-oci-registry.c:1248`

**Input shape.** Byte 0 is a load-function selector (`% 3`). The
remaining bytes are written as the manifest blob in a per-iteration
tmpdir, then loaded via a `file://` URI registry. Specifically:

```
/tmp/flatpak-fuzz-reg-XXXXXX/
  oci-layout              { "imageLayoutVersion": "1.0.0" }
  blobs/sha256/<hex>      <input bytes>
  index.json              <generated, references the blob>
```

The tmpdir is torn down (`fuzz_rm_rf`) at the end of each iteration.

**Size constraints.** `1 ≤ size ≤ 512 KiB`.

**Transitive coverage.**

- `flatpak_oci_registry_new("file://…", FALSE, …)` — opens the
  local-FS-backed registry, including `oci-layout` validation.
- `local_load_file` at `common/flatpak-oci-registry.c:293` — the on-disk
  layout reader that mirrors HTTPS GET on the live network path.
- Digest computation over the blob (`sha256:<hex>`).
- mediaType dispatch (for `_load_versioned`).
- Descriptor walks (for `_load_index`).

**Bug classes catchable.** Everything `fuzz-oci-versioned` /
`fuzz-oci-image` catch, *plus* logic bugs around digest mismatch,
oversized blobs, mediaType-vs-content disagreement, and the
directory-vs-blob lookup logic. Catches bugs that bare JSON fuzzing
misses precisely because the registry-layer dispatch is involved.

**Security relevance.** This is the closest in-process analogue to "an
attacker-controlled registry served you bytes." Every OCI flatpak pull
goes through these load functions on the live network path. Bugs here
are reachable from any flatpak install/update against an attacker
endpoint.

**Dictionary.** `fuzz/dict/oci.dict`.

**Seeds.** `fuzz/corpus/oci-registry-local/`: `seed-1` (manifest with
config + one layer), `seed-2` (image config), `seed-3` (empty index).

**Known gaps.**

- HTTPS transport, redirect handling, and the `WWW-Authenticate`
  registry-auth dance are not exercised. Those are HTTP/libsoup
  concerns and would belong in a separate harness if pursued.
- Persistent-loop count is 1000 (vs. 10000 elsewhere) because the
  per-iteration tmpdir setup is the dominant cost. Expected throughput
  is ~1–3k exec/s vs. ~10k for the bare JSON harnesses.
- The seed corpus only covers one selector value per file; in
  practice AFL's bit-flips on byte 0 will rotate selectors quickly,
  but cmin won't preserve a "balanced selector" property.

---

## Coverage matrix

Rows are attack vectors; columns are harnesses. ✔ = primary target,
◌ = partial / overlaps via another harness.

| Vector | smoke | ref | oci-versioned | oci-image | repofile | filter | metadata | oci-registry-local |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Build/link check | ✔ | | | | | | | |
| Attacker ref string | | ✔ | | | | | | ◌ |
| OCI manifest JSON | | | ✔ | | | | | ✔ |
| OCI image-config JSON | | | | ✔ | | | | ✔ |
| OCI index JSON | | | ◌ | | | | | ✔ |
| `.flatpakrepo` keyfile | | | | | ✔ | | | |
| Filter file | | | | | | ✔ | | |
| `metadata` keyfile (sandbox policy) | | | | | | | ✔ | |
| OCI on-disk layout (digest, dispatch) | | | | | | | | ✔ |

## Known gaps and v2 candidates

Carried forward from the design spec's §4 "Parser entry points planned
for v2":

- **`flatpak_bundle_load`** (`common/flatpak-utils.c:6526`).
  Single-file `.flatpak` bundles. Users routinely run `flatpak install
  ./bundle.flatpak` from web downloads, so this is attacker-controlled
  in the same threat-model sense as `fuzz-repofile`.
- **`flatpak_repo_load_summary` / `_load_summary_index`**
  (`common/flatpak-utils.c:2882,3052`). OSTree summary GVariant — the
  network metadata layer that complements the OCI parsers we already
  fuzz. Would be fed bytes through `g_variant_new_from_data` with the
  summary type.
- **AppStream XML** (`common/flatpak-appdata.c`). A 388-line custom XML
  parser that runs against attacker-controlled appdata files.

Out of scope across both v1 and v2:

- D-Bus / GVariant fuzzing of `flatpak-system-helper`,
  `flatpak-portal`, `flatpak-session-helper`,
  `flatpak-oci-authenticator`. Different tooling (`dfuzzer` or similar).
- `revokefs` FUSE protocol.
- `flatpak-bwrap` / bubblewrap (upstream concern).
- `flatpak-validate-icon` (gdk-pixbuf upstream concern).

## Cross-references

- Design rationale: [`docs/superpowers/specs/2026-05-14-fuzzing-source-prep-design.md`](docs/superpowers/specs/2026-05-14-fuzzing-source-prep-design.md)
- Generalized howto for other packages: [`docs/superpowers/notes/package-aflpp-instrumentation.md`](docs/superpowers/notes/package-aflpp-instrumentation.md)
- Project guidance (fuzzing context, upper-system build contract, open
  symbol-visibility issue): [`CLAUDE.md`](CLAUDE.md)
- Per-harness layout inside the tarball after patching:
  `fuzz/README.md` (created by the patch).
- Build container and operational workflow live in the upper fuzzing
  system, not in this tree.

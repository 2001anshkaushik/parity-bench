# TICKET DRAFT: extract PDF inline images only when something listens, and probe external tools once per process

> **DRAFT — NOT FILED.** Written by an autonomous benchmark run. It has not been filed, posted or sent anywhere (campaign
> rule: nothing reaches a person from an autonomous run). Ansh decides whether and where it goes.

## Summary

For every PDF, the Tika wrapper extracts and streams every inline image, even when no node in the pipeline consumes
the image lane. The engine then drops each image, because nothing listens. For each of those embedded images, the
wrapper also rebuilds its whole Tika configuration, and that rebuild spawns external processes to probe for
ffmpeg/exiftool/sox. On image-heavy PDFs this dominates document time. The benchmark's workaround (P1-B) was a
one-byte patch that turns inline-image extraction off for **every** pipeline. That is not shippable, because it would
silently break any pipeline that does consume images (OCR, captioning, thumbnails).

## Evidence (benchmark campaign, committed artifacts)

- The pathology (P0 E1, `working/results/parity_p0_20260923T083031Z/e1_engine_tika/exec_census.json`): across eleven
  PDFs, `jspawnhelper` was exec'd 2,249,820 times and `/usr/bin/env` 1,124,910 times, an exact 2:1 ratio. There were no
  ffmpeg, exiftool or sox executions, because the tools are absent from the image.
- The workaround's effect (P1-B, `working/results/parity_p1_20260923T184000Z/P1_REPORT.md`): the text output was
  chunk-identical on the 384 slice (the correctness gate) and on the full corpus (context). On the eleven, p50 per-document
  wall went from 342.7 s to 5.70 s, and the box-wide exec census from 3,380,028 to 452. That measures a pipeline with
  **no image consumer**; nothing was measured for pipelines that consume images.

## Root cause (from the 3.3.1.35 bytecode, `engine/java/lib/tika.jar`, package `com.rocketride.tika_api`; checked 2026-09-24)

1. **Inline images are hard-coded on.** `TikaApi#getPdfConfig()` (public static, no arguments) calls
   `PDFParserConfig.setExtractInlineImages(true)`; the `iconst_1` is at code byte 9, which is the byte P1-B patched. It is
   called for every top-level document (`TikaApi#extractInformation @564-571`) and for every nested document
   (`EmbeddedContentProcessor#processStream @72-79`). **Configuration cannot override it.** Tika's `PDFParser` merges only the
   fields a caller set explicitly (`PDFParserConfig#cloneAndUpdate` / `userConfigured`), so the wrapper's `true` wins over any
   `tika-config.xml` parameter.
2. **The engine already knows whether anything listens, but asks too late.** In the C++ parse filter,
   `IFilterInstance::onImage` drops an image when `!binder.hasListener("image")` (the engine binary logs "Skipping image: no
   listeners on the image lane"). That check runs only after Tika has decoded each image and streamed it through
   `onWriteMediaBuffer`.
3. **The configuration is rebuilt, and the tools re-probed, for every embedded image.**
   `EmbeddedContentProcessor#parseEmbedded @0` calls `ConfigBuilder.getConfig()` and then constructs a new
   `AutoDetectParser`, which it uses only for detection.
   - `getConfig()` has no cache. Each call re-reads `tika-config.xml`, calls `excludeExternalParserIfUnavailable` twice
     (CompositeExternalParser, ExternalParser), and builds a new `TikaConfig`.
   - The probe (`ConfigBuilder#externalMediaToolsAvailable`) runs `ExternalParser.check` for `env`, then `ffmpeg`, `exiftool`
     and `sox`. Each check is a `Runtime.exec`, and nothing caches the result.
   - The result goes into a static field that every thread writes (`EmbeddedContentProcessor.tikaConfig`), which is a data
     race.
   - With no tools installed, each `getConfig()` accounts for exactly the 2:1 jspawnhelper:env pattern in the census.
   - The top-level configuration, by contrast, is built once per JVM (`TikaApi#init @91-94`, guarded).
4. **A way to pass the needed information in already exists.** The C++ side passes the entry's flags as a `long` into
   `extractTextFromStream(…, flags, …)`. `extractInformation` reads that value only to log it (`@29`). The engine's
   `ENTRY_FLAGS` bits above 9 are free.

## Proposed fix (to be written against the CURRENT branch, not 3.3.1.35; see "Version drift")

**C++ (engine):**
- `packages/server/engine-core/apLib/entry.hpp` (`ENTRY_FLAGS`): add `EXTRACT_IMAGES = BIT(10)`, or use a separate
  Tika-only flag word.
- `packages/server/engine-lib/engLib/store/filters/parse/parse-instance.cpp`, `IFilterInstance::tikaThreadProc`: compute
  `flags = currentEntry->flags() | (binder.hasListener("image") ? EXTRACT_IMAGES : 0)` once per filter instance (or in
  `beginFilterInstance`), and pass it to `extractTextFromBuffer`.
  - Do not write it back into the entry, since entry flags are persisted later.
  - Keep the late `onImage` check as a backstop.
  - `Binder::hasListener` returns true outside pipeline mode, so classic (non-pipeline) tasks keep extracting images.

**Java (wrapper, `packages/tika/lib/tika/src/main/java/com/rocketride/tika_api/`):**
- `TikaApi.java`: `getPdfConfig(long flags)` → `setExtractInlineImages((flags & EXTRACT_IMAGES) != 0)`. Pass `flags` from
  `extractInformation` into `getPdfConfig` and into every `new EmbeddedContentProcessor(…)`. Expose the `TikaConfig` built
  once in `init` to the package.
- `EmbeddedContentExtractor.java` (`EmbeddedContentProcessor`):
  - Carry `flags` in a field.
  - In `parseEmbedded` and `processStream`, reuse `TikaApi`'s once-built `TikaConfig` instead of calling
    `ConfigBuilder.getConfig()`, and remove the racy static field.
  - Pass `flags` to `getPdfConfig` and to child processors.
  - When the bit is off, skip `image/*` resources. That covers images inside DOCX, PPTX and email, which never go through
    `PDFParserConfig`.
- `ConfigBuilder.java`: memoise `externalMediaToolsAvailable()` in a `static volatile Boolean`, so the probe runs at most once
  per JVM. The existing package-private `toolsAvailableOverrideForTest` stays the test hook.

**Configuration:** after the two Java changes, `tika-config.xml` needs no change. The benchmark's `<parser-exclude>` lines
for CompositeExternalParser / ExternalParser should **not** ship. They remove the probe by disabling those parsers
everywhere, which would change behaviour on hosts that do have ffmpeg, exiftool and sox.

## Tests that prove image pipelines still work

- **A: text-only pipeline unchanged.** `product_pdf.pipe` (webhook → parse → preprocessor → embedding → response):
  - chunk-identical text on the benchmark's 384 slice and the eleven stragglers;
  - no image callbacks;
  - the box-wide exec census at or near P1-B's (a handful of process spawns, not millions).
- **B: image lane still delivers**, with no model needed.
  - Pipeline: `product_pdf.pipe` plus the bundle's `response_image` node (`engine/nodes/response/services.image.json`,
    lane `image`), fed from `parse_1`'s image lane.
  - Pass condition: per document, the image count and bytes equal those of the unpatched engine (rr:patched) on the
    eleven stragglers and the 384 slice.
  - **Null control:** the documents known to carry images must return more than 0 images; a 0 means the harness is broken
    and the test fails.
- **C: a real image consumer.** A parse → OCR pipeline, e.g. the source tree's `examples/document-processor.pipe` (webhook →
  parse → ocr on `image`): OCR text unchanged against the unpatched engine.
- **D: tool probing once per process.** On an image that has ffmpeg, exiftool and sox installed, a PDF with many images
  spawns the probe once per JVM, not once per image. The census counts `ffmpeg -version` etc. at most once, and the
  external parsers still run on media that need them.

## Version drift to account for

- The bundle's bytecode (3.3.1.35) is older than the local source checkouts. A newer `EmbeddedContentExtractor.java` also
  parses every embedded image a second time for media metadata. On a host with exiftool, that would run exiftool once per
  image, the same per-image cost in a new place.
- A newer `ConfigBuilder.getConfig` adds a RAR/7-Zip parser swap. The patch must be rebased onto the current branch.
- The C++ citations are from a source checkout outside this repository. They are consistent with the symbols and log
  strings in the bundle's `engine` binary, but they were not compiled against it here.

## Out of scope

- Any change to the text lane or to OCR behaviour.
- Tika version upgrades.
- The benchmark's single-instance mandate, which is not affected by this change.

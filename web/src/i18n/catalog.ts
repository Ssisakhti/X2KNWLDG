/**
 * Message catalogues (T-110, D-012).
 *
 * English is the source of truth and the default locale. Every other
 * catalogue is typed as `Messages`, so a missing or misspelled key is a
 * compile error rather than a blank label at runtime.
 *
 * D-014: all code, comments and documentation in this repository are English.
 * Persian appears in exactly one place -- the translated UI strings below --
 * and in the extracted knowledge content the API serves.
 */

export const LOCALES = ["en", "fa"] as const;

export type Locale = (typeof LOCALES)[number];

/** Text direction per locale. `dir` is data, not a stylesheet (D-012). */
export const DIRECTION: Record<Locale, "ltr" | "rtl"> = {
  en: "ltr",
  fa: "rtl",
};

export const DEFAULT_LOCALE: Locale = "en";

export const en = {
  "app.title": "Knowledge Canvas",
  "app.subtitle": "Local, read-only view of the canonical pipeline output.",

  "nav.library": "Library",
  "nav.map": "Map",
  "nav.sections": "Sections",
  "nav.skipToContent": "Skip to content",

  "locale.label": "Language",
  "locale.en": "English",
  "locale.fa": "فارسی",

  "common.loading": "Loading…",
  "common.loadingNamed": "Loading {name}…",
  "common.pageFailed": "That page did not arrive. What is listed here is still complete.",
  "common.retry": "Retry",
  "common.notStated": "not stated",
  "common.notRecorded": "not recorded",
  "common.any": "any",
  "common.yes": "yes",
  "common.no": "no",
  "common.back": "Back to the library",
  "common.total": "{count} total",
  "common.more": "More results exist beyond this page.",
  "common.unknownTotal": "The server did not count the matches.",

  "status.legend": "Run status",
  "status.validation": "Validation",
  "status.coverage": "Coverage",
  "status.overall": "Overall",
  "status.auditAttempts": "Audit attempts",
  "status.PASS": "PASS",
  "status.PARTIAL": "PARTIAL",
  "status.FAIL": "FAIL",
  "status.UNKNOWN": "UNKNOWN",
  "status.note":
    "Copied from validation.json and coverage.json. Never recomputed, never raised toward PASS.",

  "provenance.source": "Source-grounded",
  "provenance.derived": "Derived",
  "provenance.user": "User-authored",

  "vocabulary.canonical": "Canonical relation",
  "vocabulary.library_synthetic": "Library-synthetic relation",
  "vocabulary.user": "User relation",

  "error.title": "The server refused this request",
  "error.invalid_id": "That identifier is malformed, so nothing was looked up.",
  "error.invalid_request": "The request itself was refused before anything was read.",
  "error.not_found": "That identifier is well formed, and names nothing here.",
  "error.unavailable":
    "The record exists; its bytes do not. An external artifact never has a local file.",
  "error.index_unavailable":
    "The index has not been built, so this server cannot say what your library holds. This is not the same as an empty library.",
  "error.internal": "The server hit an error it did not expect.",
  "error.transport": "The server could not be reached.",
  "error.code": "Code",
  "error.boundary.title": "This view stopped working",
  "error.boundary.body":
    "Something in this part of the page threw an error, so it was taken down rather than left half-drawn. Nothing in your library was changed.",
  "error.boundary.retry": "Try this view again",

  "index.title": "Index",
  "index.state.absent": "No index has been built yet.",
  "index.state.building": "The index is being built.",
  "index.state.ready": "Index ready.",
  "index.state.error": "The index reported an error.",
  "index.builtAt": "Built at",
  "index.version": "Schema version",
  "index.counts.sources": "Sources",
  "index.counts.artifacts": "Artifacts",
  "index.counts.entities": "Entities",
  "index.counts.relations": "Relations",
  "index.runs.title": "Last scan",
  "index.runs.discovered": "Run directories discovered",
  "index.runs.indexed": "Indexed",
  "index.runs.skipped": "Skipped, and why",
  "index.runs.noneSkipped": "Nothing was skipped.",
  "index.runs.unreported": "This server does not report what the last scan skipped.",

  "library.title": "Library",
  "library.group.mode": "What to browse",
  "library.group.layout": "Layout",
  "library.mode.sources": "Sources",
  "library.mode.units": "Knowledge units",
  "library.view.list": "List",
  "library.view.grid": "Grid",
  "library.filter.sourceType": "Source type",
  "library.filter.status": "Validation status",
  "library.filter.kind": "Kind",
  "library.filter.sourceClass": "Source class",
  "library.filter.minConfidence": "Minimum confidence",
  "library.empty": "The index holds no source matching these filters.",
  "library.unitsEmpty": "No knowledge unit in scope matches these filters.",
  "library.unitsScopeNote":
    "The frozen contract filters knowledge units per source, so each source below was queried separately and reports its own total.",

  "search.label": "Search",
  "search.placeholder": "Search knowledge units and transcripts",
  "search.submit": "Search",
  "search.clear": "Clear",
  "search.results": "Results for “{query}”",
  "search.empty": "No result for this query.",
  "search.includeTranscript": "Include transcript text",
  "search.hit.knowledge_unit": "Knowledge unit",
  "search.hit.transcript_caption": "Transcript caption",
  "search.captionNotAddressable":
    "A caption is not an addressable entity in v1, so this hit links to its source and timestamp rather than to an entity page.",
  "search.openSource": "Open the source",
  "search.openExternal": "Open at this timestamp on the source site",

  "map.title": "Knowledge Map",
  "map.subtitle":
    "The graph the index actually holds: entities as nodes, indexed relations as directed edges.",
  "map.stage.label": "Knowledge graph, drawn",
  "map.stage.companion":
    "The drawing is one view of this graph. The same entities are listed under “What this Map holds”, where each one can be previewed, focused and opened without a pointer.",
  "map.controls": "Map view controls",
  "map.zoomIn": "Zoom in",
  "map.zoomOut": "Zoom out",
  "map.resetView": "Reset the view",
  "map.loadMore": "Load the next page",
  "map.stopLoading": "Stop loading",
  "map.empty":
    "The index holds no graph node, so there is nothing to draw. This is not a drawing that failed.",
  "map.reading.unasked":
    "No page of the graph has been read yet, so this Map states nothing about what your library holds.",
  "map.reading.loading": "Reading a page of the graph…",
  "map.reading.stale":
    "The counts below are from the pages that did arrive. They are not an answer to the request that failed.",
  "map.canvas.pending": "Nothing has been drawn yet.",
  "map.canvas.nothing": "There is no node to draw, so the stage is empty rather than broken.",
  "map.state.title": "What is drawn",
  "map.state.summary": "{nodes} nodes · {edges} edges",
  "map.state.nodes": "Nodes loaded",
  "map.state.edges": "Edges drawn",
  "map.state.held": "Edges held",
  "map.state.heldNote":
    "waiting for an endpoint on a page that is not loaded yet, and never dropped",
  "map.state.pages": "Pages loaded",
  "map.state.extent": "Extent",
  "map.state.complete": "This is the whole graph these filters describe.",
  "map.state.partial": "Part of the graph. More of it exists than is drawn.",
  "map.state.truncated":
    "the server cut the last page's node list short at the requested limit",
  "map.conflict.title": "Two pages disagreed, so the page was refused",
  "map.conflict.detail":
    "One {kind} arrived twice with different content: {field} differs for {id}. The page was refused whole rather than merged, because a merge would draw a record no request returned.",
  "map.renderer.failed": "The graph could not be drawn",
  "map.renderer.failedNote":
    "The counts above are what the index returned; only the drawing is missing. The renderer refuses a container with no size, so a stage that has not been laid out yet is the usual cause, and the next layout recovers it.",
  "map.renderer.unavailable": "This browser did not provide the graphics the drawing needs",
  "map.renderer.unavailableNote":
    "The renderer needs WebGL2, and loading it was refused. Nothing else on this Map depends on it: the counts, the list of what the Map holds, search, focus, related knowledge and Quick Read all work as they are.",

  "map.search.title": "Search this Map",
  "map.search.noQuery": "nothing searched yet",
  "map.search.matched": "{count} loaded {count|node|nodes} {count|matches|match}",
  "map.search.hint":
    "Loaded nodes are matched here, in the browser. The index is searched over the API.",
  "map.search.transcriptNote":
    "Transcript captions are not entities in v1, so they can be read but never focused.",
  "map.search.loaded.title": "On the Map",
  "map.search.loaded.count": "{shown} of {matched} matching {matched|node|nodes}, out of {searched} loaded.",
  "map.search.loaded.empty": "No node loaded on the Map matches this query.",
  "map.search.loaded.none": "The Map has loaded no nodes yet, so there is nothing to match.",
  "map.search.index.title": "In the index",
  "map.search.index.scope": "Scoped to the source this Map is filtered to: {source}",
  "map.search.result.onMap": "Loaded on the Map",
  "map.search.result.notLoaded": "Not loaded on the Map yet.",
  "map.search.result.focus": "Focus",
  "map.search.result.focused": "Focused",
  "map.search.result.truncated": "shortened here; the stored text is longer",
  "map.search.result.noGlobalId":
    "This unit's run states no video id, so the index gives it no global id. There is no entity for the Map to focus.",
  "map.focus.title": "Focus",
  "map.focus.none": "Nothing is focused. Choose a result to focus it.",
  "map.focus.clear": "Clear the focus",
  "map.focus.notLoaded":
    "This entity is not among the nodes loaded so far, so it is not drawn yet.",
  "map.panel.nothingFocused": "nothing focused",

  "map.peek.title": "Peek",
  "map.peek.note": "A preview. Nothing is selected, and no history is written.",
  "map.peek.close": "Close the peek",

  "map.outline.title": "What this Map holds",
  "map.outline.summary": "{listed} of {loaded} loaded {loaded|node|nodes} listed",
  "map.outline.hint":
    "Every entity the Map has drawn, in the order the server returned it — never by importance. Move to a row to preview it, focus it to read it, or open its source in the Reader. None of that needs a pointer or a drawn graph.",
  "map.outline.none":
    "No node is loaded, so there is nothing to list. What the Map has read is stated above.",
  "map.outline.edges": "{count} {count|relation|relations} drawn at this mark",
  "map.outline.unlisted": "{count} more loaded {count|node is|nodes are} not on this page of the list.",
  "map.outline.more": "List more nodes",

  "map.legend.title": "What the marks mean",
  "map.legend.nodesShape": "Nodes: where the knowledge came from, by shape",
  "map.legend.nodesColour": "Nodes: what kind of knowledge it is, by colour",
  "map.legend.edges": "Edges: vocabulary by head, provenance by colour and tail",
  "map.legend.shape": "Shape",
  "map.legend.head": "Head",
  "map.legend.tail": "Tail",
  "map.legend.unrecognised": "A value this build does not recognise",
  "map.legend.unrecognisedNote":
    "Drawn as itself rather than as the nearest known value, so a vocabulary this page is older than is visible instead of silently wrong.",
  "map.legend.noColourOnly":
    "Shape carries provenance and vocabulary; colour never carries either on its own.",
  "map.legend.kindNote":
    "Kind is not a server-side graph filter: GET /api/graph does not accept one, so it is styled and named here and never offered as a filter.",
  "map.legend.shape.circle": "circle",
  "map.legend.shape.diamond": "diamond",
  "map.legend.shape.square": "square",
  "map.legend.shape.triangle": "triangle",
  "map.legend.family.thesis": "Core thesis",
  "map.legend.family.evidence": "Evidence",
  "map.legend.family.concept": "Concepts and definitions",
  "map.legend.family.framework": "Frameworks and mental models",
  "map.legend.family.process": "Processes and how-to",
  "map.legend.family.example": "Examples and case studies",
  "map.legend.family.fact": "Facts and statistics",
  "map.legend.family.recommendation": "Recommendations",
  "map.legend.family.caveat": "Caveats and limitations",
  "map.legend.family.question": "Open questions",
  "map.legend.family.synthesis": "Derived synthesis",
  "map.legend.family.reference": "References and quotes",
  "map.legend.family.unstated": "No kind stated",
  "map.legend.family.unrecognised": "A kind this build does not recognise",
  "map.filters.group": "Graph filters",
  "map.filters.source": "Source",
  "map.filters.vocabulary": "Relation vocabulary",
  "map.filters.note":
    "These three are the filters the graph endpoint accepts. Changing one asks the server a new question and replaces the drawing.",
  "map.filters.summary": "{count} {count|filter|filters} applied",
  "map.filters.unfiltered": "no filter applied",
  "map.filters.moreSources": "More sources exist than are listed here.",
  "map.filters.sourcesFailed":
    "The source list could not be read, so the other two filters are the ones offered.",

  "map.relation.thisEntity": "this entity",
  "map.relation.theFocus": "the focus",
  "map.relation.self": "a relation the pipeline recorded onto the entity itself",

  "map.stage.primary": "Focused",
  "map.stage.neighbour": "Related",
  "map.stage.omitted":
    "{count} related {count|entity has|entities have} no card on the stage. Every one of them is listed below.",
  "map.stage.omitted.noRoom":
    "{count} {count|has|have} no room on the field at this size, in any position the orbit allows.",
  "map.stage.omitted.crowded":
    "{count} would have covered a card already placed, so {count|its card|their cards} {count|was|were} not drawn.",
  "map.stage.omitted.budget":
    "{count} {count|is|are} beyond the cards this field's composition places a side.",
  "map.stage.omitted.unanchored":
    "{count} {count|is|are} further out than one hop with no card for the neighbour {count|it hangs|they hang} off, so no relation could be drawn without inventing one.",

  "map.orbit.focus": "focus",
  "map.orbit.incoming": "incoming",
  "map.orbit.incomingGloss": "into the focus",
  "map.orbit.outgoing": "outgoing",
  "map.orbit.outgoingGloss": "out of the focus",
  "map.orbit.ring": "hop {hops}",
  "map.orbit.hopBadge": "hop {hops}",

  "map.quickRead.title": "Quick Read",
  "map.quickRead.hint":
    "The stored record, in full and in order. Nothing here is summarised or completed.",
  "map.quickRead.noFocus": "Nothing is focused, so there is no record to read.",
  "map.quickRead.statement": "Stored statement",
  "map.quickRead.statementNote":
    "The complete statement as the index stores it — not shortened here.",
  "map.quickRead.evidence": "Recorded evidence",
  "map.quickRead.relations": "Active relations",
  "map.quickRead.noRelations":
    "The bounded neighbourhood returned no relation for this entity at this depth.",
  "map.quickRead.derivation": "Derivation",
  "map.quickRead.noDerivation": "This entity records no derivation.",
  "map.quickRead.provenance": "Provenance and source",
  "map.quickRead.provenanceClass": "Provenance class",
  "map.quickRead.source": "Source",
  "map.quickRead.technical": "Technical metadata",
  "map.quickRead.kind": "Kind",
  "map.quickRead.openReader": "Open the full source",
  "map.quickRead.readerAt": "The Reader opens at {time}, the time the locator records.",
  "map.quickRead.readerNoTime":
    "This entity records no time, so the Reader opens at the start of the source.",

  "map.related.title": "Related knowledge",
  "map.related.summary": "{count} related {count|entity|entities}",
  "map.related.hint":
    "Every entity the bounded neighbourhood returned, listed in full. The stage carries only the cards that fit.",
  "map.related.noFocus": "Nothing is focused, so there is no neighbourhood to list.",
  "map.related.depth": "Depth",
  "map.related.depthNote": "Hops from the focus. The server refuses more than three.",
  "map.related.count": "{count} related {count|entity|entities} within {depth} {depth|hop|hops}, over {edges} returned {edges|relation|relations}.",
  "map.related.none": "The index records no relation for this entity at this depth.",
  "map.related.truncated":
    "The server cut the walk short at its own limit, so more neighbours exist than were returned.",
  "map.related.hops": "{count} {count|hop|hops} from the focus",
  "map.related.viaPath":
    "Reached through another entity {hops} {hops|hop|hops} out; it states no relation to the focus itself.",
  "map.related.onStage": "its card is on the stage",
  "map.related.viaParent":
    "It has no relation to the focus. What the response does record is how it joins the neighbour one hop closer:",
  "map.related.unjoinable":
    "{count} returned {count|relation names|relations name} an endpoint the response did not return, so {count|it is|they are} counted rather than drawn.",
  "map.related.unreachable":
    "{count} returned {count|entity has|entities have} no path to the focus over the relations this response returned.",

  "reader.tablist": "Reader sections",
  "reader.tab.overview": "Overview",
  "reader.tab.transcript": "Transcript",
  "reader.tab.report": "Report",
  "reader.tab.units": "Knowledge units",
  "reader.tab.relations": "Relations",
  "reader.tab.artifacts": "Artifacts",

  "reader.meta.title": "Title",
  "reader.meta.author": "Author",
  "reader.meta.language": "Language",
  "reader.meta.duration": "Duration",
  "reader.meta.url": "Source URL",
  "reader.meta.importedAt": "Imported",
  "reader.meta.extractedAt": "Extracted",
  "reader.meta.canonicalDir": "Canonical directory",
  "reader.meta.adapter": "Adapter",
  "reader.meta.sourceId": "Source id",
  "reader.meta.sourceType": "Source type",
  "reader.meta.externalId": "External id",

  "reader.counts.title": "Counts",
  "reader.counts.knowledge_units": "Knowledge units",
  "reader.counts.source_units": "Source units",
  "reader.counts.derived_units": "Derived units",
  "reader.counts.relationships": "Relationships",
  "reader.counts.captions": "Captions",
  "reader.counts.segments": "Segments",

  "reader.diagnostics.title": "What the adapter could not map",
  "reader.diagnostics.unmappable": "Artifacts skipped and named",
  "reader.diagnostics.unreadable": "Canonical files present but damaged",
  "reader.diagnostics.note":
    "Reported by the adapter so an omission does not disappear between the run and this page.",

  "reader.transcript.title": "Transcript",
  "reader.transcript.count": "{count} captions",
  "reader.transcript.unavailable": "This source has no readable transcript artifact.",
  "reader.transcript.malformed":
    "The transcript artifact was served, and does not hold a caption list this reader recognises.",
  "reader.transcript.seek": "Play from here",
  "reader.transcript.noTime": "This caption states no start time.",
  "reader.transcript.noCaptionAt":
    "No caption covers the linked timestamp, so none is highlighted.",

  "reader.report.unavailable": "This source has no report artifact.",

  "reader.units.confidence": "Confidence",
  "reader.units.locator": "Locator",
  "reader.units.locatorNone": "No locator is recorded for this unit.",
  "reader.units.derivedFrom": "Derived from",
  "reader.units.derivationNote": "Derivation note",
  "reader.units.libraryId": "Library id",
  "reader.units.canonicalPath": "Canonical file",
  "reader.units.empty": "No knowledge unit matches these filters.",

  "reader.relations.confidence": "Confidence",
  "reader.relations.vocabulary": "Vocabulary",
  "reader.relations.empty": "No relation matches this filter.",

  "reader.artifacts.mediaType": "Media type",
  "reader.artifacts.path": "Path",
  "reader.artifacts.bytes": "Bytes",
  "reader.artifacts.available": "Present at index time",
  "reader.artifacts.immutable": "Immutable evidence",
  "reader.artifacts.open": "Open the bytes",
  "reader.artifacts.externalOnly": "External — no local bytes",

  "player.title": "Media",
  "player.noLocalMedia":
    "No local media file is indexed for this source. The pipeline stores the transcript, not necessarily the medium.",
  "player.externalOnly": "This source's medium lives at a remote URL.",
  "player.load": "Load the embedded player",
  "player.privacyNote":
    "Nothing is requested from the embed host until you load it. Loading it contacts {host}.",
  "player.loaded": "Player loaded from {host}.",
  "player.unload": "Unload the player",
  "player.openExternal": "Open on the source site",
  "player.seekPending": "Loading the player will start at {time}.",
  "player.noEmbed": "No embeddable player is known for this source type.",
  "player.localTitle": "Local media",

  "time.at": "at {time}",
  "time.range": "{start} – {end}",
} as const;

export type MessageKey = keyof typeof en;

export type Messages = Record<MessageKey, string>;

export const fa: Messages = {
  "app.title": "بوم دانش",
  "app.subtitle": "نمای محلی و فقط‌خواندنی از خروجی متعارف خط لوله.",

  "nav.library": "کتابخانه",
  "nav.map": "نقشه",
  "nav.sections": "بخش‌ها",
  "nav.skipToContent": "پرش به محتوا",

  "locale.label": "زبان",
  "locale.en": "English",
  "locale.fa": "فارسی",

  "common.loading": "در حال بارگذاری…",
  "common.loadingNamed": "در حال بارگذاری {name}…",
  "common.pageFailed": "آن صفحه نرسید. آنچه در اینجا فهرست شده است هنوز کامل است.",
  "common.retry": "تلاش دوباره",
  "common.notStated": "بیان نشده",
  "common.notRecorded": "ثبت نشده",
  "common.any": "همه",
  "common.yes": "بله",
  "common.no": "خیر",
  "common.back": "بازگشت به کتابخانه",
  "common.total": "در مجموع {count}",
  "common.more": "نتایج بیشتری فراتر از این صفحه وجود دارد.",
  "common.unknownTotal": "سرور تعداد نتایج را نشمرده است.",

  "status.legend": "وضعیت اجرا",
  "status.validation": "اعتبارسنجی",
  "status.coverage": "پوشش",
  "status.overall": "کلی",
  "status.auditAttempts": "دفعات بازبینی",
  "status.PASS": "PASS",
  "status.PARTIAL": "PARTIAL",
  "status.FAIL": "FAIL",
  "status.UNKNOWN": "UNKNOWN",
  "status.note":
    "از validation.json و coverage.json عیناً نقل شده است؛ هرگز بازمحاسبه یا به PASS ارتقا داده نمی‌شود.",

  "provenance.source": "متکی بر منبع",
  "provenance.derived": "استنتاجی",
  "provenance.user": "نوشتهٔ کاربر",

  "vocabulary.canonical": "رابطهٔ متعارف",
  "vocabulary.library_synthetic": "رابطهٔ ساختگی کتابخانه",
  "vocabulary.user": "رابطهٔ کاربر",

  "error.title": "سرور این درخواست را نپذیرفت",
  "error.invalid_id": "این شناسه نادرست است، بنابراین چیزی جست‌وجو نشد.",
  "error.invalid_request": "خودِ درخواست پیش از هر خواندنی رد شد.",
  "error.not_found": "این شناسه درست است و به چیزی در اینجا اشاره نمی‌کند.",
  "error.unavailable":
    "رکورد وجود دارد؛ بایت‌هایش نه. یک قلم بیرونی هرگز فایل محلی ندارد.",
  "error.index_unavailable":
    "نمایه ساخته نشده است، پس این سرور نمی‌تواند بگوید کتابخانهٔ شما چه دارد. این با «کتابخانهٔ خالی» یکی نیست.",
  "error.internal": "سرور به خطایی غیرمنتظره برخورد.",
  "error.transport": "دسترسی به سرور ممکن نشد.",
  "error.code": "کد",
  "error.boundary.title": "این نما از کار افتاد",
  "error.boundary.body":
    "چیزی در این بخش از صفحه خطا داد، بنابراین به‌جای رها شدن نیمه‌کشیده، برداشته شد. هیچ‌چیزی در کتابخانهٔ شما تغییر نکرد.",
  "error.boundary.retry": "دوباره این نما را باز کن",

  "index.title": "نمایه",
  "index.state.absent": "هنوز هیچ نمایه‌ای ساخته نشده است.",
  "index.state.building": "نمایه در حال ساخت است.",
  "index.state.ready": "نمایه آماده است.",
  "index.state.error": "نمایه خطا گزارش کرد.",
  "index.builtAt": "زمان ساخت",
  "index.version": "نسخهٔ طرح‌واره",
  "index.counts.sources": "منابع",
  "index.counts.artifacts": "اقلام",
  "index.counts.entities": "موجودیت‌ها",
  "index.counts.relations": "روابط",
  "index.runs.title": "آخرین پویش",
  "index.runs.discovered": "پوشه‌های اجرای یافت‌شده",
  "index.runs.indexed": "نمایه‌شده",
  "index.runs.skipped": "نادیده‌گرفته‌شده، و دلیلش",
  "index.runs.noneSkipped": "چیزی نادیده گرفته نشد.",
  "index.runs.unreported": "این سرور گزارش نمی‌کند که آخرین پویش چه چیزی را کنار گذاشت.",

  "library.title": "کتابخانه",
  "library.group.mode": "چه چیزی مرور شود",
  "library.group.layout": "چیدمان",
  "library.mode.sources": "منابع",
  "library.mode.units": "واحدهای دانش",
  "library.view.list": "فهرست",
  "library.view.grid": "شبکه",
  "library.filter.sourceType": "نوع منبع",
  "library.filter.status": "وضعیت اعتبارسنجی",
  "library.filter.kind": "گونه",
  "library.filter.sourceClass": "ردهٔ منبع",
  "library.filter.minConfidence": "کمینهٔ اطمینان",
  "library.empty": "نمایه هیچ منبعی مطابق این صافی‌ها ندارد.",
  "library.unitsEmpty": "هیچ واحد دانشی در این دامنه با این صافی‌ها همخوان نیست.",
  "library.unitsScopeNote":
    "قرارداد منجمد، واحدهای دانش را به‌ازای هر منبع صافی می‌کند؛ پس هر منبع جداگانه پرس‌وجو شده و مجموع خودش را گزارش می‌کند.",

  "search.label": "جست‌وجو",
  "search.placeholder": "جست‌وجو در واحدهای دانش و رونویس‌ها",
  "search.submit": "جست‌وجو",
  "search.clear": "پاک‌کردن",
  "search.results": "نتایج برای «{query}»",
  "search.empty": "نتیجه‌ای برای این پرس‌وجو نیست.",
  "search.includeTranscript": "شامل متن رونویس",
  "search.hit.knowledge_unit": "واحد دانش",
  "search.hit.transcript_caption": "زیرنویس رونویس",
  "search.captionNotAddressable":
    "زیرنویس در نسخهٔ ۱ موجودیت نشانی‌پذیر نیست؛ پس این نتیجه به منبع و زمانش پیوند می‌خورد، نه به صفحهٔ موجودیت.",
  "search.openSource": "گشودن منبع",
  "search.openExternal": "گشودن در این زمان در سایت منبع",

  "map.title": "نقشهٔ دانش",
  "map.subtitle":
    "همان گرافی که نمایه در خود دارد: موجودیت‌ها به‌عنوان گره و روابط نمایه‌شده به‌عنوان یال‌های جهت‌دار.",
  "map.stage.label": "گراف دانش، ترسیم‌شده",
  "map.stage.companion":
    "ترسیم تنها یک نما از این گراف است. همان موجودیت‌ها در «آنچه این نقشه در خود دارد» فهرست شده‌اند؛ آنجا می‌توان هر یک را بدون نشانگر پیش‌نمایش، کانونی و باز کرد.",
  "map.controls": "کنترل‌های نمای نقشه",
  "map.zoomIn": "بزرگ‌نمایی",
  "map.zoomOut": "کوچک‌نمایی",
  "map.resetView": "بازنشانی نما",
  "map.loadMore": "بارگذاری صفحهٔ بعد",
  "map.stopLoading": "توقف بارگذاری",
  "map.empty":
    "نمایه هیچ گره گرافی ندارد، پس چیزی برای ترسیم نیست. این یک ترسیمِ ناکام نیست.",
  "map.reading.unasked":
    "هنوز هیچ صفحه‌ای از گراف خوانده نشده است، پس این نقشه چیزی دربارهٔ محتوای کتابخانهٔ شما بیان نمی‌کند.",
  "map.reading.loading": "خواندن یک صفحه از گراف…",
  "map.reading.stale":
    "شمارش‌های زیر از صفحه‌هایی است که رسیده‌اند. آن‌ها پاسخِ درخواستی که ناکام ماند نیستند.",
  "map.canvas.pending": "هنوز چیزی ترسیم نشده است.",
  "map.canvas.nothing": "گرهی برای ترسیم نیست؛ پس صحنه خالی است، نه خراب.",
  "map.state.title": "آنچه ترسیم شده",
  "map.state.summary": "{nodes} گره · {edges} یال",
  "map.state.nodes": "گره‌های بارگذاری‌شده",
  "map.state.edges": "یال‌های ترسیم‌شده",
  "map.state.held": "یال‌های نگه‌داشته",
  "map.state.heldNote":
    "در انتظار سری که در صفحه‌ای بارگذاری‌نشده قرار دارد؛ هرگز کنار گذاشته نمی‌شود",
  "map.state.pages": "صفحه‌های بارگذاری‌شده",
  "map.state.extent": "گستره",
  "map.state.complete": "این تمام گرافی است که این صافی‌ها توصیف می‌کنند.",
  "map.state.partial": "بخشی از گراف. بیش از آنچه ترسیم شده وجود دارد.",
  "map.state.truncated":
    "سرور فهرست گره‌های آخرین صفحه را در حدِ درخواست‌شده کوتاه کرد",
  "map.conflict.title": "دو صفحه با هم اختلاف داشتند، پس صفحه رد شد",
  "map.conflict.detail":
    "یک {kind} دو بار با محتوای متفاوت رسید: {field} برای {id} تفاوت دارد. صفحه به‌جای ادغام، یکجا رد شد؛ چون ادغام رکوردی را ترسیم می‌کرد که هیچ درخواستی آن را برنگردانده است.",
  "map.renderer.failed": "گراف ترسیم نشد",
  "map.renderer.failedNote":
    "شمارش‌های بالا همان چیزی است که نمایه برگرداند؛ فقط ترسیم انجام نشده است. رندرکننده ظرفی بدون اندازه را نمی‌پذیرد، پس صحنه‌ای که هنوز چیدمان نشده علت معمول است و چیدمان بعدی آن را درست می‌کند.",
  "map.renderer.unavailable": "این مرورگر گرافیکِ لازم برای ترسیم را فراهم نکرد",
  "map.renderer.unavailableNote":
    "رندرکننده به WebGL2 نیاز دارد و بارگذاری آن پذیرفته نشد. هیچ بخش دیگری از این نقشه به آن وابسته نیست: شمارش‌ها، فهرستِ آنچه نقشه در خود دارد، جست‌وجو، کانون، دانش مرتبط و خوانش سریع همچنان کار می‌کنند.",

  "map.search.title": "جست‌وجو در این نقشه",
  "map.search.noQuery": "هنوز چیزی جست‌وجو نشده",
  "map.search.matched": "{count} گرهِ بارگذاری‌شده منطبق است",
  "map.search.hint":
    "گره‌های بارگذاری‌شده همین‌جا و در مرورگر تطبیق داده می‌شوند. نمایه از راه API جست‌وجو می‌شود.",
  "map.search.transcriptNote":
    "زیرنویس‌های رونویس در نسخهٔ ۱ موجودیت نیستند؛ پس خواندنی‌اند اما هرگز کانونی نمی‌شوند.",
  "map.search.loaded.title": "روی نقشه",
  "map.search.loaded.count": "{shown} از {matched} گرهِ منطبق، از میان {searched} گرهِ بارگذاری‌شده.",
  "map.search.loaded.empty": "هیچ گرهِ بارگذاری‌شده‌ای روی نقشه با این پرس‌وجو منطبق نیست.",
  "map.search.loaded.none": "نقشه هنوز هیچ گرهی بارگذاری نکرده است، پس چیزی برای تطبیق نیست.",
  "map.search.index.title": "در نمایه",
  "map.search.index.scope": "محدود به منبعی که نقشه با آن صافی شده است: {source}",
  "map.search.result.onMap": "بارگذاری‌شده روی نقشه",
  "map.search.result.notLoaded": "هنوز روی نقشه بارگذاری نشده است.",
  "map.search.result.focus": "کانونی‌کردن",
  "map.search.result.focused": "کانونی‌شده",
  "map.search.result.truncated": "اینجا کوتاه شده؛ متنِ ذخیره‌شده بلندتر است",
  "map.search.result.noGlobalId":
    "اجرای این واحد هیچ شناسهٔ ویدیویی اعلام نمی‌کند، پس نمایه شناسهٔ سراسری به آن نمی‌دهد. موجودیتی نیست که نقشه کانونی‌اش کند.",
  "map.focus.title": "کانون",
  "map.focus.none": "چیزی کانونی نشده است. برای کانونی‌کردن، یک نتیجه را برگزینید.",
  "map.focus.clear": "پاک‌کردن کانون",
  "map.focus.notLoaded":
    "این موجودیت میان گره‌های بارگذاری‌شدهٔ تاکنون نیست، پس هنوز ترسیم نشده است.",
  "map.panel.nothingFocused": "چیزی کانونی نشده",

  "map.peek.title": "نگاه گذرا",
  "map.peek.note": "یک پیش‌نمایش. چیزی برگزیده نمی‌شود و هیچ تاریخچه‌ای نوشته نمی‌شود.",
  "map.peek.close": "بستن نگاه گذرا",

  "map.outline.title": "آنچه این نقشه در خود دارد",
  "map.outline.summary": "{listed} از {loaded} گرهِ بارگذاری‌شده فهرست شده است",
  "map.outline.hint":
    "همهٔ موجودیت‌هایی که نقشه ترسیم کرده است، به همان ترتیبی که سرور برگردانده — هرگز بر پایهٔ اهمیت. برای پیش‌نمایش روی یک ردیف بروید، برای خواندن آن را کانونی کنید، یا منبعش را در خواننده باز کنید. هیچ‌یک از این‌ها به نشانگر یا گرافِ ترسیم‌شده نیاز ندارد.",
  "map.outline.none":
    "هیچ گرهی بارگذاری نشده است، پس چیزی برای فهرست‌کردن نیست. آنچه نقشه خوانده است در بالا بیان شده.",
  "map.outline.edges": "{count} رابطه در این نشانه ترسیم شده است",
  "map.outline.unlisted": "{count} گرهِ بارگذاری‌شدهٔ دیگر در این صفحه از فهرست نیستند.",
  "map.outline.more": "فهرست‌کردن گره‌های بیشتر",

  "map.legend.title": "معنای نشانه‌ها",
  "map.legend.nodesShape": "گره‌ها: خاستگاه دانش، با شکل",
  "map.legend.nodesColour": "گره‌ها: گونهٔ دانش، با رنگ",
  "map.legend.edges": "یال‌ها: واژگان با سرِ یال، خاستگاه با رنگ و نشانِ انتها",
  "map.legend.shape": "شکل",
  "map.legend.head": "سرِ یال",
  "map.legend.tail": "انتهای یال",
  "map.legend.unrecognised": "مقداری که این نسخه نمی‌شناسد",
  "map.legend.unrecognisedNote":
    "همان‌گونه که هست ترسیم می‌شود، نه شبیه نزدیک‌ترین مقدار شناخته‌شده، تا واژگانی که این صفحه از آن قدیمی‌تر است دیده شود و خاموش نماند.",
  "map.legend.noColourOnly":
    "شکل، خاستگاه و واژگان را می‌رساند؛ رنگ به‌تنهایی هیچ‌کدام را نمی‌رساند.",
  "map.legend.kindNote":
    "گونه یک صافی سمت سرور نیست: GET /api/graph چنین پارامتری نمی‌پذیرد، پس اینجا فقط ترسیم و نام‌گذاری می‌شود و هرگز به‌عنوان صافی ارائه نمی‌شود.",
  "map.legend.shape.circle": "دایره",
  "map.legend.shape.diamond": "لوزی",
  "map.legend.shape.square": "مربع",
  "map.legend.shape.triangle": "مثلث",
  "map.legend.family.thesis": "تز اصلی",
  "map.legend.family.evidence": "شواهد",
  "map.legend.family.concept": "مفاهیم و تعریف‌ها",
  "map.legend.family.framework": "چارچوب‌ها و مدل‌های ذهنی",
  "map.legend.family.process": "فرایندها و دستورالعمل‌ها",
  "map.legend.family.example": "مثال‌ها و موردکاوی‌ها",
  "map.legend.family.fact": "واقعیت‌ها و آمار",
  "map.legend.family.recommendation": "توصیه‌ها",
  "map.legend.family.caveat": "هشدارها و محدودیت‌ها",
  "map.legend.family.question": "پرسش‌های باز",
  "map.legend.family.synthesis": "ترکیب استنتاجی",
  "map.legend.family.reference": "ارجاع‌ها و نقل‌قول‌ها",
  "map.legend.family.unstated": "گونه‌ای بیان نشده",
  "map.legend.family.unrecognised": "گونه‌ای که این نسخه نمی‌شناسد",
  "map.filters.group": "صافی‌های گراف",
  "map.filters.source": "منبع",
  "map.filters.vocabulary": "واژگان رابطه",
  "map.filters.note":
    "این سه، صافی‌هایی هستند که نقطهٔ پایانی گراف می‌پذیرد. تغییر هرکدام پرسشی تازه از سرور است و ترسیم را جایگزین می‌کند.",
  "map.filters.summary": "{count} صافی اعمال شده",
  "map.filters.unfiltered": "هیچ صافی اعمال نشده",
  "map.filters.moreSources": "منبع‌های بیشتری از آنچه اینجا فهرست شده وجود دارد.",
  "map.filters.sourcesFailed":
    "فهرست منبع‌ها خوانده نشد، پس تنها دو صافی دیگر ارائه می‌شود.",

  "map.relation.thisEntity": "این هستار",
  "map.relation.theFocus": "کانون",
  "map.relation.self": "رابطه‌ای که خط لوله بر خودِ هستار ثبت کرده است",

  "map.stage.primary": "کانونی",
  "map.stage.neighbour": "مرتبط",
  "map.stage.omitted":
    "{count} هستار مرتبط کارتی بر صحنه ندارند. هر یک از آن‌ها در فهرست زیر آمده است.",
  "map.stage.omitted.noRoom":
    "{count} مورد در این اندازه، در هیچ جایگاهی که مدار اجازه می‌دهد، جا ندارند.",
  "map.stage.omitted.crowded":
    "{count} مورد بر کارتی که پیش‌تر جای گرفته هم‌پوشانی می‌کردند، پس کارتشان ترسیم نشد.",
  "map.stage.omitted.budget":
    "{count} مورد بیش از شمار کارت‌هایی‌اند که ترکیب این میدان در هر سو می‌نشاند.",
  "map.stage.omitted.unanchored":
    "{count} مورد بیش از یک گام دورترند و همسایهٔ نزدیک‌ترشان کارتی ندارد، پس بدون ساختن رابطه‌ای که در رکوردها نیست نمی‌شد پیوندی کشید.",

  "map.orbit.focus": "کانون",
  "map.orbit.incoming": "ورودی",
  "map.orbit.incomingGloss": "به کانون",
  "map.orbit.outgoing": "خروجی",
  "map.orbit.outgoingGloss": "از کانون",
  "map.orbit.ring": "گام {hops}",
  "map.orbit.hopBadge": "گام {hops}",

  "map.quickRead.title": "خوانش سریع",
  "map.quickRead.hint":
    "رکورد ذخیره‌شده، کامل و به ترتیب. هیچ‌چیز اینجا خلاصه یا تکمیل نشده است.",
  "map.quickRead.noFocus": "چیزی کانونی نیست، پس رکوردی برای خواندن وجود ندارد.",
  "map.quickRead.statement": "گزارهٔ ذخیره‌شده",
  "map.quickRead.statementNote":
    "گزارهٔ کامل، همان‌گونه که نمایه ذخیره کرده است — اینجا کوتاه نشده.",
  "map.quickRead.evidence": "شاهد ثبت‌شده",
  "map.quickRead.relations": "رابطه‌های فعال",
  "map.quickRead.noRelations":
    "همسایگی کران‌دار در این عمق هیچ رابطه‌ای برای این هستار بازنگرداند.",
  "map.quickRead.derivation": "استنتاج",
  "map.quickRead.noDerivation": "این هستار هیچ استنتاجی ثبت نکرده است.",
  "map.quickRead.provenance": "خاستگاه و منبع",
  "map.quickRead.provenanceClass": "ردهٔ خاستگاه",
  "map.quickRead.source": "منبع",
  "map.quickRead.technical": "فراداده‌های فنی",
  "map.quickRead.kind": "گونه",
  "map.quickRead.openReader": "گشودن منبع کامل",
  "map.quickRead.readerAt": "خواننده از {time} آغاز می‌شود، همان زمانی که مکان‌یاب ثبت کرده است.",
  "map.quickRead.readerNoTime":
    "این هستار زمانی ثبت نکرده است، پس خواننده از آغاز منبع باز می‌شود.",

  "map.related.title": "دانش مرتبط",
  "map.related.summary": "{count} موجودیت مرتبط",
  "map.related.hint":
    "هر هستاری که همسایگی کران‌دار بازگردانده، به‌طور کامل فهرست شده است. صحنه تنها کارت‌هایی را نگه می‌دارد که جا می‌شوند.",
  "map.related.noFocus": "چیزی کانونی نیست، پس همسایگی‌ای برای فهرست کردن وجود ندارد.",
  "map.related.depth": "عمق",
  "map.related.depthNote": "گام‌ها از کانون. کارساز بیش از سه را نمی‌پذیرد.",
  "map.related.count": "{count} هستار مرتبط تا {depth} گام، بر پایهٔ {edges} رابطهٔ بازگردانده‌شده.",
  "map.related.none": "نمایه در این عمق هیچ رابطه‌ای برای این هستار ثبت نکرده است.",
  "map.related.truncated":
    "کارساز پیمایش را در سقف خودش برید، پس همسایه‌های بیشتری از آنچه بازگردانده شد وجود دارد.",
  "map.related.hops": "{count} گام از کانون",
  "map.related.viaPath":
    "از راه هستار دیگری در {hops} گام رسیده است؛ خودش هیچ رابطه‌ای با کانون بیان نمی‌کند.",
  "map.related.onStage": "کارتش بر صحنه است",
  "map.related.viaParent":
    "رابطه‌ای با کانون ندارد. آنچه پاسخ ثبت کرده این است که چگونه به همسایهٔ یک گام نزدیک‌تر می‌پیوندد:",
  "map.related.unjoinable":
    "{count} رابطهٔ بازگردانده‌شده سرِ یالی را نام می‌برند که پاسخ بازنگرداند، پس شمرده شده‌اند و ترسیم نشده‌اند.",
  "map.related.unreachable":
    "{count} هستارِ بازگردانده‌شده بر پایهٔ رابطه‌های همین پاسخ هیچ مسیری به کانون ندارند.",

  "reader.tablist": "بخش‌های خواننده",
  "reader.tab.overview": "نمای کلی",
  "reader.tab.transcript": "رونویس",
  "reader.tab.report": "گزارش",
  "reader.tab.units": "واحدهای دانش",
  "reader.tab.relations": "روابط",
  "reader.tab.artifacts": "اقلام",

  "reader.meta.title": "عنوان",
  "reader.meta.author": "پدیدآور",
  "reader.meta.language": "زبان",
  "reader.meta.duration": "مدت",
  "reader.meta.url": "نشانی منبع",
  "reader.meta.importedAt": "زمان درون‌ریزی",
  "reader.meta.extractedAt": "زمان استخراج",
  "reader.meta.canonicalDir": "پوشهٔ متعارف",
  "reader.meta.adapter": "مبدل",
  "reader.meta.sourceId": "شناسهٔ منبع",
  "reader.meta.sourceType": "نوع منبع",
  "reader.meta.externalId": "شناسهٔ بیرونی",

  "reader.counts.title": "شمارش‌ها",
  "reader.counts.knowledge_units": "واحدهای دانش",
  "reader.counts.source_units": "واحدهای منبع",
  "reader.counts.derived_units": "واحدهای استنتاجی",
  "reader.counts.relationships": "روابط",
  "reader.counts.captions": "زیرنویس‌ها",
  "reader.counts.segments": "قطعه‌ها",

  "reader.diagnostics.title": "آنچه مبدل نتوانست نگاشت کند",
  "reader.diagnostics.unmappable": "اقلام کنارگذاشته و نام‌برده‌شده",
  "reader.diagnostics.unreadable": "فایل‌های متعارف موجود ولی آسیب‌دیده",
  "reader.diagnostics.note":
    "مبدل این‌ها را گزارش می‌کند تا یک قلم افتاده میان اجرا و این صفحه ناپدید نشود.",

  "reader.transcript.title": "رونویس",
  "reader.transcript.count": "{count} زیرنویس",
  "reader.transcript.unavailable": "این منبع قلم رونویسِ خواندنی ندارد.",
  "reader.transcript.malformed":
    "قلم رونویس ارائه شد و فهرست زیرنویسی که این خواننده بشناسد در آن نیست.",
  "reader.transcript.seek": "پخش از اینجا",
  "reader.transcript.noTime": "این زیرنویس زمان آغاز ندارد.",
  "reader.transcript.noCaptionAt":
    "هیچ زیرنویسی زمانِ پیوند داده‌شده را در بر نمی‌گیرد، پس چیزی برجسته نشده است.",

  "reader.report.unavailable": "این منبع قلم گزارش ندارد.",

  "reader.units.confidence": "اطمینان",
  "reader.units.locator": "مکان‌یاب",
  "reader.units.locatorNone": "برای این واحد مکان‌یابی ثبت نشده است.",
  "reader.units.derivedFrom": "برگرفته از",
  "reader.units.derivationNote": "یادداشت استنتاج",
  "reader.units.libraryId": "شناسهٔ کتابخانه",
  "reader.units.canonicalPath": "فایل متعارف",
  "reader.units.empty": "هیچ واحد دانشی با این صافی‌ها همخوان نیست.",

  "reader.relations.confidence": "اطمینان",
  "reader.relations.vocabulary": "واژگان",
  "reader.relations.empty": "هیچ رابطه‌ای با این صافی همخوان نیست.",

  "reader.artifacts.mediaType": "نوع رسانه",
  "reader.artifacts.path": "مسیر",
  "reader.artifacts.bytes": "بایت",
  "reader.artifacts.available": "موجود هنگام نمایه‌سازی",
  "reader.artifacts.immutable": "شاهد تغییرناپذیر",
  "reader.artifacts.open": "گشودن بایت‌ها",
  "reader.artifacts.externalOnly": "بیرونی — بدون بایت محلی",

  "player.title": "رسانه",
  "player.noLocalMedia":
    "هیچ فایل رسانهٔ محلی برای این منبع نمایه نشده است. خط لوله رونویس را نگه می‌دارد، نه لزوماً خودِ رسانه را.",
  "player.externalOnly": "رسانهٔ این منبع در نشانی دوردستی قرار دارد.",
  "player.load": "بارگذاری پخش‌کنندهٔ توکار",
  "player.privacyNote":
    "تا زمانی که بارگذاری نکنید چیزی از میزبانِ توکار درخواست نمی‌شود. بارگذاری با {host} تماس می‌گیرد.",
  "player.loaded": "پخش‌کننده از {host} بارگذاری شد.",
  "player.unload": "برداشتن پخش‌کننده",
  "player.openExternal": "گشودن در سایت منبع",
  "player.seekPending": "بارگذاری پخش‌کننده از {time} آغاز خواهد شد.",
  "player.noEmbed": "برای این نوع منبع پخش‌کنندهٔ توکاری شناخته نیست.",
  "player.localTitle": "رسانهٔ محلی",

  "time.at": "در {time}",
  "time.range": "{start} – {end}",
};

export const CATALOGS: Record<Locale, Messages> = { en, fa };

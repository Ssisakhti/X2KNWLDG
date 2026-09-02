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
  "nav.skipToContent": "Skip to content",

  "locale.label": "Language",
  "locale.en": "English",
  "locale.fa": "فارسی",

  "common.loading": "Loading…",
  "common.retry": "Retry",
  "common.notStated": "not stated",
  "common.notRecorded": "not recorded",
  "common.none": "none",
  "common.any": "any",
  "common.yes": "yes",
  "common.no": "no",
  "common.back": "Back to the library",
  "common.total": "{count} total",
  "common.showing": "Showing {count}",
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
  "status.readFrom": "Read from {path}",
  "status.note":
    "Copied from validation.json and coverage.json. Never recomputed, never raised toward PASS.",

  "provenance.label": "Provenance",
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
  "library.filter.scope": "Scope",
  "library.scope.all": "All listed sources",
  "library.empty": "The index holds no source matching these filters.",
  "library.unitsEmpty": "No knowledge unit in scope matches these filters.",
  "library.unitsScopeNote":
    "The frozen contract filters knowledge units per source, so each source below was queried separately and reports its own total.",
  "library.openReader": "Open in the reader",

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

  "reader.report.title": "Report",
  "reader.report.unavailable": "This source has no report artifact.",

  "reader.units.title": "Knowledge units",
  "reader.units.kind": "Kind",
  "reader.units.confidence": "Confidence",
  "reader.units.evidence": "Evidence excerpt",
  "reader.units.locator": "Locator",
  "reader.units.locatorNone": "No locator is recorded for this unit.",
  "reader.units.derivedFrom": "Derived from",
  "reader.units.derivationNote": "Derivation note",
  "reader.units.libraryId": "Library id",
  "reader.units.canonicalPath": "Canonical file",
  "reader.units.empty": "No knowledge unit matches these filters.",

  "reader.relations.title": "Relations",
  "reader.relations.from": "From",
  "reader.relations.to": "To",
  "reader.relations.relation": "Relation",
  "reader.relations.confidence": "Confidence",
  "reader.relations.vocabulary": "Vocabulary",
  "reader.relations.empty": "No relation matches this filter.",

  "reader.artifacts.title": "Artifacts",
  "reader.artifacts.kind": "Kind",
  "reader.artifacts.role": "Role",
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
  "nav.skipToContent": "پرش به محتوا",

  "locale.label": "زبان",
  "locale.en": "English",
  "locale.fa": "فارسی",

  "common.loading": "در حال بارگذاری…",
  "common.retry": "تلاش دوباره",
  "common.notStated": "بیان نشده",
  "common.notRecorded": "ثبت نشده",
  "common.none": "هیچ",
  "common.any": "همه",
  "common.yes": "بله",
  "common.no": "خیر",
  "common.back": "بازگشت به کتابخانه",
  "common.total": "در مجموع {count}",
  "common.showing": "نمایش {count}",
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
  "status.readFrom": "خوانده‌شده از {path}",
  "status.note":
    "از validation.json و coverage.json عیناً نقل شده است؛ هرگز بازمحاسبه یا به PASS ارتقا داده نمی‌شود.",

  "provenance.label": "خاستگاه",
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
  "library.filter.scope": "دامنه",
  "library.scope.all": "همهٔ منابع فهرست‌شده",
  "library.empty": "نمایه هیچ منبعی مطابق این صافی‌ها ندارد.",
  "library.unitsEmpty": "هیچ واحد دانشی در این دامنه با این صافی‌ها همخوان نیست.",
  "library.unitsScopeNote":
    "قرارداد منجمد، واحدهای دانش را به‌ازای هر منبع صافی می‌کند؛ پس هر منبع جداگانه پرس‌وجو شده و مجموع خودش را گزارش می‌کند.",
  "library.openReader": "گشودن در خواننده",

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

  "reader.report.title": "گزارش",
  "reader.report.unavailable": "این منبع قلم گزارش ندارد.",

  "reader.units.title": "واحدهای دانش",
  "reader.units.kind": "گونه",
  "reader.units.confidence": "اطمینان",
  "reader.units.evidence": "گزیدهٔ شاهد",
  "reader.units.locator": "مکان‌یاب",
  "reader.units.locatorNone": "برای این واحد مکان‌یابی ثبت نشده است.",
  "reader.units.derivedFrom": "برگرفته از",
  "reader.units.derivationNote": "یادداشت استنتاج",
  "reader.units.libraryId": "شناسهٔ کتابخانه",
  "reader.units.canonicalPath": "فایل متعارف",
  "reader.units.empty": "هیچ واحد دانشی با این صافی‌ها همخوان نیست.",

  "reader.relations.title": "روابط",
  "reader.relations.from": "از",
  "reader.relations.to": "به",
  "reader.relations.relation": "رابطه",
  "reader.relations.confidence": "اطمینان",
  "reader.relations.vocabulary": "واژگان",
  "reader.relations.empty": "هیچ رابطه‌ای با این صافی همخوان نیست.",

  "reader.artifacts.title": "اقلام",
  "reader.artifacts.kind": "گونه",
  "reader.artifacts.role": "نقش",
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

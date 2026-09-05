/*
 * The T-255 mockups' display text, in two piles that have different standing.
 *
 * `SHIPPED` is lifted VERBATIM from `web/src/i18n/catalog.ts`, both locales.
 * These strings already ship, and where a source-map surface can say what the
 * Knowledge Map already says, it says it in the same words -- the no-WebGL
 * notice most of all, because that one is not about sources at all.
 *
 * `PROPOSED` is new. The Source Map has no strings in the catalogue, because
 * nothing renders it yet, so every key below is a proposal `T-256` has to add
 * to `catalog.ts` before it can render anything. They are written here in both
 * locales rather than left English-only, because the Persian half is what makes
 * an RTL capture worth looking at.
 *
 * The project's output-language policy governs the *records*, not this file: a
 * brief's narrative is Persian in the canonical document, so it is Persian in
 * BOTH locales below -- the English UI shows English chrome around a Persian
 * brief. That is not a gap in the mockup; it is the policy, drawn.
 */

/** Verbatim from web/src/i18n/catalog.ts. Do not edit either half here. */
export const SHIPPED = {
  "app.title": { en: "Knowledge Canvas", fa: "بوم دانش" },
  "nav.library": { en: "Library", fa: "کتابخانه" },
  "nav.map": { en: "Map", fa: "نقشه" },
  "map.title": { en: "Knowledge Map", fa: "نقشهٔ دانش" },
  "map.zoomIn": { en: "Zoom in", fa: "بزرگ‌نمایی" },
  "map.zoomOut": { en: "Zoom out", fa: "کوچک‌نمایی" },
  "map.resetView": { en: "Reset the view", fa: "بازنشانی نما" },
  "map.state.nodes": { en: "Nodes loaded", fa: "گره‌های بارگذاری‌شده" },
  "map.state.edges": { en: "Edges drawn", fa: "یال‌های ترسیم‌شده" },
  "map.state.extent": { en: "Extent", fa: "گستره" },
  "map.state.complete": {
    en: "This is the whole graph these filters describe.",
    fa: "این تمام گرافی است که این صافی‌ها توصیف می‌کنند.",
  },
  "map.state.partial": {
    en: "Part of the graph. More of it exists than is drawn.",
    fa: "بخشی از گراف. بیش از آنچه ترسیم شده وجود دارد.",
  },
  "map.state.truncated": {
    en: "the server cut the last page's node list short at the requested limit",
    fa: "سرور فهرست گره‌های آخرین صفحه را در حدِ درخواست‌شده کوتاه کرد",
  },
  "map.canvas.nothing": {
    en: "There is no node to draw, so the stage is empty rather than broken.",
    fa: "گرهی برای ترسیم نیست؛ پس صحنه خالی است، نه خراب.",
  },
  "map.empty": {
    en: "The index holds no graph node, so there is nothing to draw. This is not a drawing that failed.",
    fa: "نمایه هیچ گره گرافی ندارد، پس چیزی برای ترسیم نیست. این یک ترسیمِ ناکام نیست.",
  },
  "map.reading.unasked": {
    en: "No page of the graph has been read yet, so this Map states nothing about what your library holds.",
    fa: "هنوز هیچ صفحه‌ای از گراف خوانده نشده است، پس این نقشه چیزی دربارهٔ محتوای کتابخانهٔ شما بیان نمی‌کند.",
  },
  "map.renderer.unavailable": {
    en: "This browser did not provide the graphics the drawing needs",
    fa: "این مرورگر گرافیکِ لازم برای ترسیم را فراهم نکرد",
  },
  "map.renderer.unavailableNote": {
    en: "The renderer needs WebGL2, and loading it was refused. Nothing else on this Map depends on it: the counts, the list of what the Map holds, search, focus, related knowledge and Quick Read all work as they are.",
    fa: "رندرکننده به WebGL2 نیاز دارد و بارگذاری آن پذیرفته نشد. هیچ بخش دیگری از این نقشه به آن وابسته نیست: شمارش‌ها، فهرستِ آنچه نقشه در خود دارد، جست‌وجو، کانون، دانش مرتبط و خوانش سریع همچنان کار می‌کنند.",
  },
  "map.search.title": { en: "Search this Map", fa: "جست‌وجو در این نقشه" },
  "map.focus.title": { en: "Focus", fa: "کانون" },
  "map.focus.clear": { en: "Clear the focus", fa: "پاک‌کردن کانون" },
  "map.legend.title": { en: "What the marks mean", fa: "معنای نشانه‌ها" },
  "map.legend.shape.circle": { en: "circle", fa: "دایره" },
  "map.quickRead.technical": { en: "Technical metadata", fa: "فراداده‌های فنی" },
  "map.quickRead.provenance": { en: "Provenance and source", fa: "خاستگاه و منبع" },
  "provenance.source": { en: "Source-grounded", fa: "متکی بر منبع" },
  "provenance.derived": { en: "Derived", fa: "استنتاجی" },
  "common.notStated": { en: "not stated", fa: "بیان نشده" },
  "library.mode.sources": { en: "Sources", fa: "منابع" },
};

/**
 * PROPOSED by T-255. None of these exists in `catalog.ts`; `T-256` adds them.
 * The Persian is written here rather than deferred, because the RTL capture is
 * the reason the Persian half of this review exists.
 */
export const PROPOSED = {
  "map.mode.knowledge": { en: "Knowledge", fa: "دانش" },
  "map.mode.sources": { en: "Sources", fa: "منابع" },
  "map.mode.label": { en: "What this Map is of", fa: "این نقشه از چیست" },

  "source.title": { en: "Source Map", fa: "نقشهٔ منابع" },
  "source.one": { en: "Source", fa: "منبع" },
  "source.medium": { en: "Medium", fa: "رسانه" },
  "source.medium.youtube": { en: "YouTube", fa: "یوتیوب" },
  "source.medium.twitter": { en: "X / Twitter", fa: "ایکس / توییتر" },
  "source.status": { en: "Run status", fa: "وضعیت اجرا" },
  "source.units": { en: "Knowledge units", fa: "واحدهای دانش" },

  "source.brief.title": { en: "Source brief", fa: "چکیدهٔ منبع" },
  "source.brief.thesis": { en: "Thesis", fa: "گزارهٔ اصلی" },
  "source.brief.keyPoints": { en: "Key points", fa: "نکته‌های کلیدی" },
  "source.brief.limitations": { en: "Limitations and tensions", fa: "محدودیت‌ها و تنش‌ها" },
  "source.brief.basedOn": { en: "Supported by", fa: "بر پایهٔ" },
  "source.brief.state": { en: "Brief", fa: "چکیده" },
  "source.brief.available": { en: "current", fa: "به‌روز" },
  "source.brief.stale": { en: "stale", fa: "کهنه" },
  "source.brief.unavailable": { en: "none", fa: "ندارد" },
  "source.brief.staleNote": {
    en: "This brief was generated from inputs that have since changed. It is shown as it was written, with its state saying so — it is not withheld and it is not refreshed.",
    fa: "این چکیده از ورودی‌هایی ساخته شده که پس از آن تغییر کرده‌اند. همان‌گونه که نوشته شده نمایش داده می‌شود و وضعیتش همین را می‌گوید — نه پنهان می‌شود و نه از نو ساخته.",
  },
  "source.brief.unavailableNote": {
    en: "This source has no brief. That is a normal and possibly permanent condition, not a shortfall: a run that did not pass cannot have one.",
    fa: "این منبع چکیده ندارد. این وضعیتی عادی و چه‌بسا دائمی است، نه کاستی: اجرایی که نپذیرفته باشد نمی‌تواند چکیده داشته باشد.",
  },
  "source.brief.statusNote": {
    en: "A brief can never claim more than the run it was written from.",
    fa: "چکیده هرگز نمی‌تواند بیش از اجرایی که از آن نوشته شده ادعا کند.",
  },

  "source.relations.title": { en: "Source relationships", fa: "نسبت‌های میان منابع" },
  "source.relations.incoming": { en: "incoming", fa: "ورودی" },
  "source.relations.outgoing": { en: "outgoing", fa: "خروجی" },
  "source.relations.intoFocus": { en: "into this source", fa: "به این منبع" },
  "source.relations.outOfFocus": { en: "out of this source", fa: "از این منبع" },
  "source.relations.none": {
    en: "This source relates to no other source in the library. It is a node with no edges, not a node that failed to load.",
    fa: "این منبع با هیچ منبع دیگری در کتابخانه نسبتی ندارد. گرهی بدون یال است، نه گرهی که بارگذاری‌اش ناکام مانده.",
  },
  "source.relations.scope": { en: "Scope", fa: "گستره" },
  "source.relations.scope.partial": { en: "partial", fa: "جزئی" },
  "source.relations.scope.broad": { en: "broad", fa: "فراگیر" },
  "source.relations.scopeNote": {
    en: "Scope qualifies the claim; it does not measure it. There is no third value and no percentage.",
    fa: "گستره ادعا را مقید می‌کند، نه آنکه آن را بسنجد. مقدار سومی وجود ندارد و درصدی در کار نیست.",
  },

  "source.basis.title": { en: "What this relationship rests on", fa: "این نسبت بر چه تکیه دارد" },
  "source.basis.pairs": { en: "Knowledge-unit pairs", fa: "جفت‌های واحد دانش" },
  "source.basis.count": { en: "{returned} of {total} carried in this response", fa: "{returned} از {total} در این پاسخ" },
  "source.basis.rationale": { en: "Why the pass proposed it", fa: "چرا این نسبت پیشنهاد شده" },
  "source.basis.note": {
    en: "A basis is what keeps a source-level verdict from overclaiming: the relationship means these pairs, and nothing wider.",
    fa: "این پایه همان چیزی است که نمی‌گذارد داوری در سطح منبع بیش از حد ادعا کند: نسبت یعنی همین جفت‌ها، و نه بیش از آن.",
  },

  "source.counts.returned": { en: "Sources returned", fa: "منابع بازگردانده‌شده" },
  "source.counts.relations": { en: "Relationships returned", fa: "نسبت‌های بازگردانده‌شده" },
  "source.counts.omitted": { en: "Relationships omitted", fa: "نسبت‌های کنارگذاشته" },
  "source.counts.total": { en: "Sources in the index", fa: "منابع در نمایه" },
  "source.counts.offPage": {
    en: "One relationship on this page names a source the page does not carry. It is on a later page, not missing — so no mark is drawn for it here.",
    fa: "یکی از نسبت‌های این صفحه منبعی را نام می‌برد که خودِ صفحه ندارد. آن منبع در صفحه‌ای دیگر است، نه گم‌شده — پس هیچ نشانه‌ای برایش در اینجا ترسیم نمی‌شود.",
  },
  "source.counts.omittedNote": {
    en: "An omitted relationship is one the bound cut, or one naming a source the index does not hold. Both are counted; neither is drawn.",
    fa: "نسبتِ کنارگذاشته یا آن است که کران بریده، یا آن که منبعی را نام می‌برد که نمایه ندارد. هر دو شمرده می‌شوند و هیچ‌کدام ترسیم نمی‌شود.",
  },

  "source.bound.title": { en: "What this response did not carry", fa: "آنچه این پاسخ در بر نداشت" },
  "source.bound.bothDirections": {
    en: "The limit binds both directions together in id order, so a bound can never empty one side while the other is short of it.",
    fa: "کران بر هر دو جهت با هم و به ترتیب شناسه اعمال می‌شود، پس هیچ‌گاه یک سو خالی نمی‌شود در حالی که سوی دیگر هنوز جا دارد.",
  },

  "source.unknown.title": { en: "No source in this library has that id", fa: "هیچ منبعی در این کتابخانه چنین شناسه‌ای ندارد" },
  "source.unknown.note": {
    en: "The id is well formed and the index does not hold it. Absence is an answer, not an error in the request.",
    fa: "شناسه درست‌ساخت است و نمایه آن را ندارد. نبود، خودْ پاسخ است، نه خطایی در درخواست.",
  },

  "source.refusals.title": { en: "What this Map will not tell you", fa: "آنچه این نقشه نمی‌گوید" },
  "source.refusals.rank": {
    en: "A relationship carries no confidence, no score and no rank. Every edge is drawn at one weight and every source at one size, because a basis count is a count.",
    fa: "هیچ نسبتی اطمینان، امتیاز یا رتبه ندارد. همهٔ یال‌ها با یک ضخامت و همهٔ منابع با یک اندازه ترسیم می‌شوند، چون شمارِ پایه فقط یک شمار است.",
  },
  "source.refusals.freshness": {
    en: "This response says nothing about whether a relationship is still current, so nothing here shows a freshness mark beside an edge.",
    fa: "این پاسخ چیزی دربارهٔ به‌روز بودنِ یک نسبت نمی‌گوید، پس در اینجا هیچ نشانهٔ تازگی کنار یال‌ها دیده نمی‌شود.",
  },

  "source.synthetic.title": { en: "Synthetic relationships", fa: "نسبت‌های ساختگی" },
  "source.synthetic.note": {
    en: "Every source node here is a real committed fixture run. {n} of the {total} relationships were WRITTEN for this mockup — real ids, real endpoint digests, real knowledge-unit ids, invented judgement. Real discovery over this corpus proposes 3 pairs, all single-medium, so a dense picture cannot be honestly derived. Nothing here reaches output/.",
    fa: "هر گرهِ منبع در اینجا یک اجرای واقعیِ ثبت‌شده است. {n} نسبت از {total} نسبت برای همین ماکاپ نوشته شده‌اند — شناسه‌های واقعی، هاضم‌های واقعی، شناسه‌های واقعیِ واحد دانش، و داوریِ ساختگی. کشفِ واقعی روی این پیکره تنها ۳ جفت پیشنهاد می‌دهد که همگی تک‌رسانه‌اند، پس تصویری پرتراکم را نمی‌توان صادقانه استخراج کرد. هیچ‌چیز از اینجا به output/ نمی‌رسد.",
  },
  "source.synthetic.mark": { en: "written", fa: "نوشته‌شده" },
  "source.gated.mark": { en: "gated", fa: "دروازه‌گذشته" },
};

export const LOCALE =
  new URLSearchParams(location.search).get("lang") === "fa" ? "fa" : "en";
export const RTL = LOCALE === "fa";

const ALL = { ...SHIPPED, ...PROPOSED };

/** `t("key")`, with `{name}` substitution for the two keys that take one. */
export const t = (key, values) => {
  const entry = ALL[key];
  if (entry === undefined) return key;
  const text = entry[LOCALE] ?? entry.en;
  if (values === undefined) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name) =>
    values[name] === undefined ? whole : String(values[name]),
  );
};

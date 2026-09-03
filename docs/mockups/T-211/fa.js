/*
 * MOCKUP-ONLY Persian display text.
 *
 * Two different things live here and they have different standing:
 *
 * 1. `CHROME` is lifted VERBATIM from the `fa` catalogue in
 *    web/src/i18n/catalog.ts. These strings already ship. Nothing is invented.
 *
 * 2. `STATEMENTS` are translations of real knowledge-unit statements, made for
 *    this mockup so that RTL wrapping, truncation and card height are exercised
 *    on realistic Persian body copy instead of on Latin text mirrored.
 *    They are NOT canonical, are NOT written back to output/, and no knowledge
 *    unit gains a translation. The API serves the extracted English; a Persian
 *    UI shows Persian chrome around English content. SPEC.md says so again.
 */

export const CHROME = {
  "app.title": "بوم دانش",
  "nav.library": "کتابخانه",
  "nav.map": "نقشه",
  "map.title": "نقشهٔ دانش",
  "map.stage.label": "گراف دانش، ترسیم‌شده",
  "map.zoomIn": "بزرگ‌نمایی",
  "map.zoomOut": "کوچک‌نمایی",
  "map.resetView": "بازنشانی نما",
  "map.state.nodes": "گره‌های بارگذاری‌شده",
  "map.state.edges": "یال‌های ترسیم‌شده",
  "map.state.extent": "گستره",
  "map.state.complete": "این تمام گرافی است که این صافی‌ها توصیف می‌کنند.",
  "map.search.title": "جست‌وجو در این نقشه",
  "map.focus.title": "کانون",
  "map.focus.clear": "پاک‌کردن کانون",
  "map.quickRead.title": "خوانش سریع",
  "map.quickRead.statement": "گزارهٔ ذخیره‌شده",
  "map.quickRead.technical": "فراداده‌های فنی",
  "map.related.title": "دانش مرتبط",
  "map.legend.title": "معنای نشانه‌ها",
  "map.legend.shape.circle": "دایره",
  "map.legend.shape.diamond": "لوزی",
  "map.legend.shape.square": "مربع",
  "provenance.source": "متکی بر منبع",
  "provenance.derived": "استنتاجی",
  "provenance.user": "نوشتهٔ کاربر",
  "common.notStated": "بیان نشده",
  "reader.units.confidence": "اطمینان",
};

/** Mockup-only. See the header. Keyed by the real `local_id`. */
export const STATEMENTS = {
  "KU-000028": "بهره‌وری عامل به سرمایه‌گذاری پیشین در محیط مهندسیِ سازگار با عامل وابسته است.",
  "KU-000026": "تیم‌ها ممکن است پیش از شتاب‌گرفتن بهره‌وری، به یک دورهٔ سرمایه‌گذاری عامدانه نیاز داشته باشند.",
  "KU-000029": "خطاهای ابزار را برای عامل‌ها خوانا و قابل‌اقدام کنید.",
  "KU-000030": "ابزارهای اختصاصی MCP می‌توانند شکاف‌های توانمندی را در محیط کارِ عامل ببندند.",
  "KU-000031": "ساختار کدپایه را می‌توان برای پیمایش‌پذیری عامل بازطراحی کرد.",
  "KU-000032": "زبان‌های نوع‌دار می‌توانند بازخورد عامل را از راه خطاهای کامپایلر و نوع بهبود دهند.",
  "KU-000033": "تشخیص‌های کامپایلر می‌توانند یک زبان را با عامل سازگارتر کنند.",
  "KU-D-0004": "افت کوتاه‌مدت بهره‌وری می‌تواند مقدمهٔ اهرم پایدار عامل باشد، آن‌گاه که هزینهٔ بازطراحی محیط را تأمین کند.",
  "KU-000021": "توسعهٔ مرزی به‌جای یک فن اسپرینت یک‌باره، در قالب پنج عادت تکرارشونده عملیاتی می‌شود.",
  "KU-000027": "پذیرش توسعهٔ مرزی معمولاً با یک افت بهره‌وری آغاز می‌شود.",
  "KU-000052": "رهبری باید پیش از مطالبهٔ دستاوردهای تحویل در سطح مرزی، یک دورهٔ سرمایه‌گذاریِ پذیرش را صریحاً بودجه‌بندی کند.",
  "KU-D-0003": "حلقهٔ خودگردانی: قصد ← زمینه ← کنش ← بازخورد قطعی ← خودتصحیحی.",
  "KU-D-0006": "خلبانِ نماینده: تیم‌های براون‌فیلد + سنجهٔ استقرار + طراحی صریح کار + ممیزی بهزیستی.",
  "KU-000020": "بازطراحی گردش کار، نه صرفِ دسترسی به ابزار، بیشترین دستاورد بهره‌وری را متمایز کرد.",
  "KU-D-0005": "آمادگی مقیاس = باند سرمایه‌گذاری + یادگیری پیش‌آهنگ + بازطراحی گلوگاه.",
  "KU-000022": "تیم‌ها باید زمینهٔ سازمانی و مهندسیِ مرتبط را برای عامل‌ها بیرونی کنند.",
  "KU-000042": "بازخورد کیفیتِ اجراپذیر را زودتر و نزدیک‌تر به اجرای عامل بیاورید.",
  "KU-000055": "برداشتن محدودیت‌های کدنویسی، گلوگاه سامانه را جای دیگری می‌برد.",
  "KU-D-0007": "هوش مصنوعی پیاده‌سازی را می‌فشرد و تأخیرِ قصد، تصمیم و بازبینی را همچون قید سامانه آشکار می‌کند.",
  "KU-D-0002": "تشخیص تیم مرزی: کدنویسیِ بی‌دخالت + مدت خودگردانی + توان عبور موازی.",
  "KU-000003": "توسعهٔ مرزی، کدِ نوشتهٔ عامل، اجراهای خودگردانِ طولانی و اجرای موازی وظایف را در هم می‌آمیزد.",
  "KU-000006": "اجرای موازی عامل‌ها، زمان بی‌کاری توسعه‌دهنده را به توان عبورِ هم‌زمانِ وظایف بدل می‌کند.",
  "KU-000039": "الزامات صریح و قصد فنی باید بر تولید انبوه کد مقدم باشد.",
  a4abbc1138ec: "بهره‌وری عامل به سرمایه‌گذاری پیشین در محیط مهندسیِ سازگار با عامل وابسته است.",
  c5ff72712947: "تیم‌ها ممکن است پیش از شتاب‌گرفتن بهره‌وری، به یک دورهٔ سرمایه‌گذاری عامدانه نیاز داشته باشند.",
};

/** The evidence excerpt shown in Quick Read, translated for the same reason. */
export const EXCERPTS = {
  "KU-000028": "کار مهندسیِ عامدانه، پیش از آن",
};

/** Relation names. The vocabulary itself stays English in `Mono`; this is the
 *  reading gloss shown beside it on a pill, as RELATION_TYPES is a contract. */
export const RELATIONS = {
  supports: "پشتیبانی می‌کند",
  exemplifies: "نمونه می‌آورد",
  derived_from: "برگرفته از",
  expresses_concept: "بیانگر مفهوم",
  is_part_of: "بخشی است از",
  qualifies: "مقید می‌کند",
};

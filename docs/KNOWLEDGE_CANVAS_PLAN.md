# X2KNWLDG Knowledge Canvas — برنامهٔ محصول و معماری

---

**وضعیت سند:** فعال و مرجع ادامهٔ کار  
**مرحلهٔ فعلی:** تحقیق و تصمیم معماری تکمیل شده؛ پیاده‌سازی آغاز نشده است  
**آخرین به‌روزرسانی:** 2026-08-31  
**دامنهٔ فعلی:** اجرای شخصی و کاملاً محلی روی macOS، با اولویت YouTube  
**مالک داده:** کاربر؛ بدون وابستگی به سرویس پولی یا فضای ابری  

---

## 1. هدف این سند

این فایل مرجع اصلی برای طراحی و ساخت لایهٔ بصری X2KNWLDG در چند سشن است. هر عامل یا توسعه‌دهنده‌ای که کار را ادامه می‌دهد باید پیش از هر تغییر این فایل، `AGENTS.md` و `WORKFLOW.md` را بخواند.

این سند باید همیشه پاسخ این پرسش‌ها را روشن نگه دارد:

- دقیقاً چه محصولی ساخته می‌شود و چه چیزی خارج از دامنه است؟
- کدام تصمیم‌ها قطعی‌اند و کدام موارد هنوز باز هستند؟
- مرز میان شواهد، دانش استخراج‌شده و محتوای شخصی کاربر کجاست؟
- معماری و قرارداد داده چگونه به YouTube محدود نمی‌ماند؟
- هر فاز چه خروجی و چه معیار پذیرشی دارد؟
- سشن بعدی باید از کجا ادامه دهد؟

این یک سند زنده است. در پایان هر سشن اجرایی، بخش‌های «وضعیت اجرا»، «تصمیم‌ها»، «ریسک‌ها» و «گام بعدی» باید به‌روزرسانی شوند.

## 2. خلاصهٔ تصمیم نهایی

برای X2KNWLDG یک لایهٔ اختصاصی، سبک و local-first ساخته می‌شود. محصول‌های کامل مانند AFFiNE و Logseq fork نخواهند شد؛ از آن‌ها صرفاً برای الگوهای UX و درس‌های معماری استفاده می‌شود.

پشتهٔ پیشنهادی:

- **Frontend:** React + TypeScript + Vite
- **بوم تعاملی:** React Flow (`@xyflow/react`)
- **گراف سراسری:** Sigma.js + Graphology
- **قلم و طراحی آزاد:** Pointer Events + `perfect-freehand` + لایهٔ SVG
- **سرویس محلی:** FastAPI روی پکیج Python فعلی
- **جست‌وجو و ایندکس:** SQLite + FTS5
- **اجرای اولیه:** وب‌اپ محلی روی `localhost`
- **بسته‌بندی دسکتاپ:** Tauri فقط در صورت اثبات نیاز در فازهای بعدی

اصل کلیدی معماری:

> Canvas و Knowledge Map دو نمای متفاوت از یک مجموعه داده‌اند و نباید با یک renderer یا یک مدل ذخیره‌سازی پیاده‌سازی شوند.

- Canvas برای تعداد محدودی آیتم انتخاب‌شده، تعامل عمیق، یادداشت، رسانه و قلم است.
- Knowledge Map برای مرور سریع گراف سراسری، خوشه‌ها و همسایگی روابط است.

## 3. نیازهای قطعی کاربر

### 3.1. محیط و مالکیت

- فقط استفادهٔ شخصی روی MacBook.
- همهٔ داده‌ها و پردازش‌ها تا حد ممکن محلی باشند.
- در این بخش از سرویس پولی استفاده نشود.
- سیستم از ابتدا برای رشد حجم منابع طراحی شود، اما over-engineering نشود.
- انتخاب فناوری براساس تناسب مسئله باشد، نه علاقه به وب، Rust یا ابزار خاص.

### 3.2. تجربهٔ محصول

- UI تمیز، مینیمال، حرفه‌ای و کم‌اصطکاک.
- ترکیب کتابخانهٔ محتوا، reader، گراف دانش و canvas.
- بازکردن و خواندن سند، transcript، صوت، ویدئو و منابع داخل برنامه.
- نمایش ارتباط میان منابع، knowledge unitها، conceptها و شواهد.
- امکان قراردادن آیتم‌های انتخاب‌شده روی بوم و اتصال آن‌ها.
- امکان نوشتن و طراحی آزاد با قلم نوری.
- قلم فقط annotation است و قرار نیست به متن یا knowledge unit تبدیل شود.

### 3.3. منابع

- فاز نخست: YouTube.
- آینده: Twitter/X، Medium، صفحات وب، PDF و انواع دیگر محتوا.
- هستهٔ UI و مدل ایندکس نباید `video_id` را مفهوم عمومی همهٔ منابع فرض کنند.

## 4. واقعیت فعلی مخزن

هستهٔ فعلی X2KNWLDG یک pipeline مبتنی بر provenance است و این فایل‌ها را برای هر ویدئو می‌سازد:

```text
output/<video-id>/
  raw/
    source.<ext>
    transcript.json
    transcript.md
  metadata.json
  transcript.json
  segments.json
  knowledge_units.json
  relationships.json
  coverage.json
  validation.json
  report.md
  graph.json
  vault/
```

فایل‌های `raw/` شواهد immutable هستند و UI حق ویرایش آن‌ها را ندارد.

هسته همچنین در `output/library/` گراف میان‌ویدئویی، conceptهای canonical و فهرست ویدئوها را تولید می‌کند. منطق فعلی در `src/x2knwldg/library.py` قرار دارد و باید به‌جای بازنویسی، تدریجاً عمومی شود.

نمونهٔ فعلی `pqlWNihgdjI` هنوز extraction کامل ندارد:

- `coverage.json` برابر `PARTIAL` است.
- `knowledge_units.json` خالی است.
- `relationships.json` خالی است.
- `graph.json` خالی است.

بنابراین در نسخهٔ اولیهٔ UI باید transcript، metadata، report و وضعیت ناقص نمایش داده شود؛ گراف یا محتوای ساختگی نباید تولید شود. برای تست کامل Knowledge Map حداقل یک extraction نهایی و معتبر لازم است.

## 5. اصول تغییرناپذیر

این اصول از `AGENTS.md` و `WORKFLOW.md` به UI نیز تسری پیدا می‌کنند:

1. شواهد قبل از خلاصه‌سازی و نمایش دانش مشتق‌شده قرار می‌گیرند.
2. timestamp، quote، evidence، confidence یا coverage هرگز ساخته یا حدس زده نمی‌شود.
3. وضعیت `PARTIAL` و `FAIL` باید واضح نمایش داده شود و به `PASS` تبدیل نشود.
4. فایل‌های canonical منبع حقیقت‌اند.
5. SQLite فقط index/cache قابل بازسازی است.
6. یادداشت، stroke، موقعیت نود و رابطهٔ دستی کاربر از دانش canonical جدا هستند.
7. هیچ interaction در UI نباید فایل‌های `raw/` را تغییر دهد.
8. منبع‌محور و derived بودن دانش باید هم در data model و هم در UI قابل تشخیص باشد.
9. حذف cache نباید باعث ازدست‌رفتن شواهد، دانش canonical یا محتوای شخصی کاربر شود.
10. افزودن منبع جدید نباید به بازنویسی frontend نیاز داشته باشد؛ فقط adapter و node renderer لازم است.

## 6. مدل محصول

محصول چهار سطح اصلی دارد که selection و navigation مشترک دارند.

### 6.1. Library

کتابخانهٔ قابل جست‌وجو و فیلتر منابع:

- ویدئوها و در آینده مقاله، tweet/thread، PDF، صوت و فایل محلی
- عنوان، منبع، زبان، تاریخ ورود، مدت و وضعیت pipeline
- تعداد knowledge unitها، روابط و وضعیت coverage
- جست‌وجو در transcript، knowledge units، evidence و report
- فیلتر براساس source type، kind، source class، confidence و validation status
- حالت‌های list و compact grid

### 6.2. Reader

نمای مطالعه و مشاهدهٔ یک منبع:

- player ویدئو یا صوت
- PDF/document viewer
- transcript زمان‌دار با پرش به timestamp
- report Markdown
- knowledge units مرتبط
- evidence excerpt و locator دقیق
- روابط ورودی و خروجی
- وضعیت validation و coverage
- افزودن آیتم منتخب به Canvas

برای YouTube دو حالت پخش وجود دارد:

1. embed آنلاین با استفاده از `video_url` و امکان seek به timestamp؛
2. پخش فایل محلی فقط اگر فایل رسانه واقعاً در دسترس باشد.

وجود فایل ویدئوی محلی نباید فرض شود؛ pipeline فعلی transcript را ذخیره می‌کند، نه الزاماً خود ویدئو را.

### 6.3. Knowledge Map

نمای خودکار گراف سراسری:

- render با Sigma.js/WebGL
- نمایش conceptها، knowledge unitها و sourceها
- فیلتر relationshipها و source classها
- جست‌وجو و focus روی node
- نمایش neighborhood به‌جای بارگذاری جزئیات همهٔ nodeها
- cluster و layout قابل تعویض در صورت نیاز
- بازکردن جزئیات node در inspector
- انتقال node یا subgraph انتخاب‌شده به Canvas

Knowledge Map محیط اصلی ویرایش یا پخش رسانه نیست.

### 6.4. Canvas

بوم آزاد و قابل ذخیره برای چیدمان انتخابی کاربر:

- Knowledge Unit node
- Concept node
- Source/Video node
- Transcript Segment node
- Evidence/Quote node
- Markdown/User Note node
- PDF/Document node
- Audio node
- Image node
- Group/Frame
- Ink stroke
- Canonical relation reference
- User-created relation

Canvas نباید کل گراف کتابخانه را یک‌جا render کند. آیتم‌ها صریحاً توسط کاربر یا از یک subgraph محدود به board اضافه می‌شوند.

## 7. طرح کلی UI/UX

چیدمان پایهٔ پیشنهادی:

```text
┌───────────────┬─────────────────────────────────┬──────────────────┐
│ Navigation    │ Main View                       │ Inspector        │
│               │                                 │                  │
│ Library       │ Library / Reader / Map / Canvas │ Details          │
│ Sources       │                                 │ Evidence         │
│ Boards        │                                 │ Relations        │
│ Saved views   │                                 │ Validation       │
└───────────────┴─────────────────────────────────┴──────────────────┘
```

اصول UX:

- تمرکز روی محتوا، نه panelهای دائمی زیاد.
- inspector قابل جمع‌شدن باشد.
- command/search palette برای navigation سریع.
- انتخاب node در Map، Canvas و Reader به یک entity مشترک اشاره کند.
- جزئیات سنگین فقط هنگام selection بارگذاری شوند.
- رنگ تنها نشانگر تفاوت provenance نباشد؛ icon، label یا line style نیز استفاده شود.
- exact visual language بعد از wireframe مشخص می‌شود، اما تمایز این سه دسته اجباری است:
  - source-grounded
  - derived
  - user-authored
- وضعیت coverage و validation همیشه در دسترس باشد، اما مزاحم مطالعه نباشد.
- برای نمایش فارسی و انگلیسی، layout و typography باید متن دوجهته را درست مدیریت کند.

## 8. معماری سیستم

```text
Canonical filesystem
output/<source-id>/...
        │ read-only
        ▼
Source adapters + Indexer
        │
        ▼
SQLite FTS5 index/cache ───── FastAPI local API
        │                           │
        └───────────────────────────┤
                                    ▼
                         React/Vite application
                     ┌──────────┬──────────┬──────────┐
                     │ Library  │ Map      │ Canvas   │
                     │ Reader   │ Sigma.js │ ReactFlow│
                     └──────────┴──────────┴──────────┘
                                    │ writes
                                    ▼
                           workspace/ user data
```

### 8.1. Backend محلی

FastAPI به‌عنوان یک extra اختیاری به پکیج فعلی اضافه می‌شود؛ CLI و pipeline اصلی نباید برای استفادهٔ بدون UI مجبور به نصب dependencyهای frontend/backend شوند.

مسئولیت backend:

- scan و index کردن خروجی‌های canonical
- API جست‌وجو، library، graph و entity detail
- ارائهٔ transcript/report/metadata
- ارائهٔ امن فایل‌های محلی و media با پشتیبانی مناسب از range request در صورت نیاز
- persistence داده‌های workspace
- rebuild index
- ارائهٔ health/status و version اطلاعات schema

backend مسئول استخراج دانش یا تغییر نتیجهٔ validatorها نیست.

### 8.2. Frontend

Frontend به‌صورت یک اپ React/Vite مستقل در پوشهٔ پیشنهادی `web/` قرار می‌گیرد.

مسئولیت frontend:

- navigation و search
- Library و Reader
- Map renderer و interaction
- Canvas renderer و persistence interaction
- قلم و drawing tools
- inspector و نمایش provenance
- optimistic UI فقط برای داده‌های workspace، نه canonical output

### 8.3. اجرای محلی

فرمان نهایی مورد انتظار، پس از پیاده‌سازی:

```text
x2knwldg ui
```

این فرمان باید:

1. project root را resolve کند؛
2. index را در صورت نیاز بررسی یا rebuild کند؛
3. سرویس local-only را روی loopback اجرا کند؛
4. مرورگر پیش‌فرض را باز کند؛
5. مسیرهای خارج از project root را بدون اجازه expose نکند.

پورت دقیق و شیوهٔ انتخاب آن در فاز implementation تعیین می‌شود و نباید hard-code شکننده داشته باشد.

## 9. مرزبندی ذخیره‌سازی

### 9.1. منبع حقیقت موجود

```text
output/<source-id>/...
```

- توسط pipeline ساخته می‌شود.
- UI در حالت عادی فقط آن را می‌خواند.
- validatorها مرجع وضعیت هستند.

### 9.2. دادهٔ canonical کاربر

ساختار پیشنهادی:

```text
workspace/
  boards/
    <board-id>.json
  notes/
    <note-id>.md
  attachments/
```

این داده‌ها قابل backup، version control و انتقال هستند. ایجاد دقیق پوشه‌ها در فاز persistence انجام می‌شود.

### 9.3. cache قابل بازسازی

```text
.x2knwldg/
  index.sqlite
  thumbnails/
  cache/
```

- حذف این پوشه نباید دادهٔ اصلی را از بین ببرد.
- این پوشه به‌صورت پیش‌فرض برای version control مناسب نیست.
- thumbnail و مشتقات رسانه‌ای هرگز جای فایل اصلی را نمی‌گیرند.

### 9.4. قواعد SQLite

- FTS5 برای جست‌وجوی متن استفاده می‌شود.
- graph database جدا در فاز اول استفاده نمی‌شود.
- relationshipها در جدول adjacency معمولی کافی‌اند.
- schema migration صریح و versioned باشد.
- در صورت استفاده از WAL باید SQLite دارای fix مربوط به WAL reset باشد؛ نسخه و runtime واقعی پیش از فعال‌سازی بررسی شود.
- یک writer کنترل‌شده ترجیح دارد؛ concurrency پیچیده برای اپ شخصی لازم نیست.

## 10. مدل دادهٔ عمومی

مدل UI/index باید source-neutral باشد.

### 10.1. Source

نمایندهٔ منبع اصلی:

```json
{
  "id": "youtube:pqlWNihgdjI",
  "source_type": "youtube",
  "external_id": "pqlWNihgdjI",
  "url": "https://www.youtube.com/watch?v=pqlWNihgdjI",
  "title": "...",
  "language": "en",
  "status": "PARTIAL"
}
```

### 10.2. Artifact

یک بازنمایی یا فایل وابسته به Source:

- video
- audio
- transcript
- article
- PDF
- report
- raw evidence
- image

### 10.3. Locator

محل دقیق evidence یا anchor:

```json
{
  "type": "time_range",
  "start_sec": 120.5,
  "end_sec": 138.2
}
```

انواع آینده:

- `time_range`
- `page`
- `page_bbox`
- `text_span`
- `post_id`
- `url_fragment`

Locator نباید بدون دادهٔ canonical ساخته شود.

### 10.4. KnowledgeUnit

فیلدهای فعلی حفظ می‌شوند:

- stable ID
- kind
- source class
- content
- confidence
- source/locator برای source-grounded unit
- derived_from و derivation_note برای derived unit

شناسهٔ global پیشنهادی:

```text
<source-type>:<external-id>:<local-unit-id>
```

مثال:

```text
youtube:pqlWNihgdjI:KU-001
twitter:1840000000000000000:KU-001
medium:article-slug:KU-001
```

### 10.5. Relation

هر relation باید کلاس منشأ مشخص داشته باشد:

- `source`: مستقیماً قابل پشتیبانی از منبع
- `derived`: نتیجهٔ synthesis یا inference ثبت‌شده
- `user`: ارتباط دستی روی workspace

رابطهٔ user نباید به‌صورت خودکار وارد `relationships.json` شود.

### 10.6. Board و BoardItem

Board فقط layout و انتخاب کاربر را نگه می‌دارد:

- board metadata
- entity reference
- position و dimensions
- collapsed/expanded state
- per-node view state مانند timestamp یا page فعلی، در صورت نیاز
- user edgeها
- ink strokeها
- frameها و groupها

محتوای canonical نباید داخل board duplicate شود، مگر snapshot صریح برای دوام لینک؛ تصمیم snapshot در فاز schema گرفته می‌شود.

## 11. قرارداد Source Adapter

هر منبع جدید باید به قرارداد مشترک indexer تبدیل شود.

حداقل خروجی adapter:

- Source record
- Artifact records
- KnowledgeUnit records
- Relation records
- Locator records
- validation/coverage status
- مسیر فایل‌های canonical

adapterهای برنامه‌ریزی‌شده:

1. YouTube adapter از ساختار فعلی `output/<video-id>`
2. Twitter/X adapter پس از طراحی pipeline استخراج مربوطه
3. Medium/article adapter
4. Generic file/PDF adapter

در فاز نخست فقط YouTube adapter پیاده‌سازی می‌شود، ولی interface آن عمومی خواهد بود.

## 12. انتخاب کتابخانه‌ها و محدودیت‌ها

### 12.1. React Flow

کاربرد:

- custom HTML node
- اتصال و جابه‌جایی nodeها
- zoom/pan/selection
- frame و group
- ذخیرهٔ layout

قواعد:

- attribution رایگان React Flow حذف نمی‌شود.
- نمونه‌های Pro کپی نمی‌شوند.
- قابلیت قلم با پیاده‌سازی خود پروژه و کتابخانه‌های MIT ساخته می‌شود.
- componentها و callbackها باید memoized باشند.
- nodeهای خارج از نیاز board render نشوند.

### 12.2. Sigma.js + Graphology

کاربرد:

- گراف سراسری و WebGL
- focus، filtering، neighborhood و cluster visualization
- الگوریتم‌های graph در memory

Map نباید componentهای HTML سنگین در هر node قرار دهد. جزئیات در inspector نمایش داده می‌شوند.

### 12.3. perfect-freehand

کاربرد:

- smoothing stroke
- pressure-sensitive drawing
- تبدیل pointها به SVG path

stroke باید در مختصات world/canvas ذخیره شود، نه مختصات viewport.

### 12.4. Excalidraw

در هستهٔ Canvas استفاده نمی‌شود. اگر بعداً «سند sketch مستقل» لازم شد، embed یا import/export Excalidraw می‌تواند به‌عنوان feature جدا بررسی شود.

### 12.5. BlockSuite

در فاز اول استفاده نمی‌شود. اگر نیاز به document editor و edgeless editor کاملاً یکپارچه از سطح فعلی فراتر رفت، یک spike مستقل برای مقایسهٔ آن با معماری موجود انجام می‌شود.

### 12.6. tldraw

به‌دلیل license production و نیاز به license key از انتخاب فعلی حذف شده است.

### 12.7. Tauri و Electron

- Electron در معماری فعلی توصیه نمی‌شود؛ runtime و packaging اضافه برای یک اپ شخصی محلی توجیه کافی ندارد.
- Tauri فقط وقتی بررسی می‌شود که web app محلی در file access، native integration، launch UX یا performance محدودیت اثبات‌شده داشته باشد.
- مهاجرت احتمالی به Tauri نباید frontend را بازنویسی کند.

## 13. راهبرد کارایی

### 13.1. قواعد عمومی

- metadata و summary ابتدا؛ متن و رسانهٔ سنگین on demand.
- transcript بلند virtualized شود.
- thumbnailها lazy و cacheable باشند.
- فایل رسانه داخل SQLite ذخیره نشود.
- index براساس hash/mtime فقط منابع تغییرکرده را بازخوانی کند.
- index کامل باید قابل rebuild باشد.
- queryهای UI page-based یا cursor-based باشند.
- layout گراف در worker اجرا شود اگر اندازهٔ واقعی داده UI thread را مسدود کرد؛ نه زودتر.

### 13.2. Canvas

- board به‌طور طبیعی curated و محدود است.
- playerهای خارج از viewport متوقف یا سبک شوند.
- فقط node انتخاب‌شده یا بازشده reader کامل render کند.
- shadow، blur و animation سنگین روی تعداد زیاد node ممنوع باشد.
- strokeهای تکمیل‌شده به path بهینه تبدیل شوند؛ raw pointها فقط در صورت نیاز نگه داشته شوند.

### 13.3. Knowledge Map

- WebGL renderer.
- label همهٔ nodeها هم‌زمان نمایش داده نشود.
- edgeها براساس filter و zoom سطح‌بندی شوند.
- ابتدا overview؛ سپس neighborhood و details.
- graph کامل و Canvas layout دو state جدا باشند.

### 13.4. معیارهای performance

عددهای قطعی پیش از ساخت dataset واقعی تعیین نمی‌شوند. در فاز performance باید fixtureهای کوچک، متوسط و بزرگ از دادهٔ واقعی/ساختگی معتبر تهیه و targetها روی MacBook کاربر اندازه‌گیری شوند. هیچ threshold دلخواه در این سند به‌عنوان واقعیت ثبت نمی‌شود.

## 14. امنیت و حریم خصوصی

- server فقط روی loopback گوش دهد.
- هیچ telemetry یا analytics پیش‌فرض وجود نداشته باشد.
- هیچ فایل یا محتوایی بدون action صریح کاربر upload نشود.
- مسیر فایل‌ها validate شود و path traversal ممکن نباشد.
- raw HTML و Markdown untrusted sanitize شوند.
- embedهای خارجی allowlist داشته باشند.
- بازکردن URL خارجی action صریح و قابل مشاهده باشد.
- API نوشتن فقط به `workspace/` و cache مجاز باشد.
- API canonical در فاز اول read-only باشد.

## 15. API پیشنهادی

نام‌ها provisional هستند و در فاز قرارداد API تثبیت می‌شوند.

```text
GET  /api/status
GET  /api/sources
GET  /api/sources/{source_id}
GET  /api/entities/{entity_id}
GET  /api/search?q=...
GET  /api/graph
GET  /api/graph/neighborhood/{entity_id}
GET  /api/artifacts/{artifact_id}
GET  /api/media/{artifact_id}

GET  /api/boards
POST /api/boards
GET  /api/boards/{board_id}
PUT  /api/boards/{board_id}
```

قواعد API:

- IDها opaque و URL-safe شوند.
- responseها schema version داشته باشند.
- canonical status از فایل‌های validator خوانده شود.
- خطای نبودن artifact با placeholder یا دادهٔ جعلی پوشانده نشود.
- mutationها atomic باشند؛ ابتدا temp و سپس replace امن.

## 16. فازهای اجرا

### فاز 0 — قرارداد و scaffolding

**هدف:** تثبیت مرزها پیش از UI سنگین.

خروجی‌ها:

- ADR کوتاه برای انتخاب معماری
- schema نسخهٔ اول Source/Artifact/Locator/EntityRef
- قرارداد YouTube adapter
- ساختار `web/` و backend اختیاری
- فرمان development مشخص
- fixture معتبر برای وضعیت‌های `PASS`، `PARTIAL` و `FAIL`

معیار پذیرش:

- هیچ فایل canonical تغییر نکند.
- schemaها versioned و validate شوند.
- یک source فعلی بدون حدس به مدل عمومی تبدیل شود.
- پروژهٔ Python بدون extra UI همچنان نصب و تست شود.

### فاز 1 — Read-only Library و Reader

**هدف:** ارزش قابل استفاده پیش از Canvas.

خروجی‌ها:

- index SQLite/FTS5
- scan incremental و rebuild
- API منابع و جست‌وجو
- Library UI
- Reader برای metadata، transcript، report و knowledge units
- پرش timestamp به YouTube
- نمایش validation/coverage

معیار پذیرش:

- جست‌وجوی transcript و knowledge unit کار کند.
- وضعیت نمونهٔ فعلی به‌درستی `PARTIAL` دیده شود.
- حذف index و rebuild نتیجهٔ معادل بسازد.
- raw و canonical files بدون تغییر باقی بمانند.

### فاز 2 — Knowledge Map

**هدف:** مرور روابط در سطح منبع و کتابخانه.

خروجی‌ها:

- Sigma.js view
- node/edge styles براساس provenance و kind
- search/focus/filter
- neighborhood view
- inspector integration
- link از Map به Reader

معیار پذیرش:

- empty graph صادقانه نمایش داده شود.
- روابط canonical و derived قابل تمایز باشند.
- انتخاب node جزئیات و evidence واقعی نشان دهد.
- گراف از `output/library/graph.json` یا index معادل تغذیه شود.

### فاز 3 — Canvas و board persistence

**هدف:** ساخت workspace شخصی روی دانش موجود.

خروجی‌ها:

- ایجاد/نام‌گذاری/حذف board با رفتار recoverable
- افزودن entity از Library/Reader/Map
- custom nodeهای اصلی
- connection و user relation
- frame/group
- autosave و undo/redo
- persistence portable در `workspace/boards/`

معیار پذیرش:

- بستن و بازکردن برنامه layout را حفظ کند.
- خراب یا ناقص بودن یک node کل board را غیرقابل بازکردن نکند.
- user relation از canonical relation قابل تشخیص باشد.
- حذف board نیازمند confirmation و ترجیحاً recoverable باشد.

### فاز 4 — قلم و annotation

**هدف:** طراحی روان با قلم نوری روی بوم.

خروجی‌ها:

- pen/eraser/select
- pressure در صورت پشتیبانی سخت‌افزار
- color و width محدود و مینیمال
- stroke persistence
- undo/redo
- hide/show ink layer

معیار پذیرش:

- stroke با zoom/pan جابه‌جا نشود.
- قلم و drag node با هم conflict نداشته باشند.
- طراحی با mouse نیز fallback داشته باشد.
- هیچ stroke به دانش canonical تبدیل نشود.

### فاز 5 — رسانه و اسناد غنی‌تر

**هدف:** مطالعهٔ چندرسانه‌ای کامل‌تر.

خروجی‌های ممکن براساس اولویت واقعی:

- PDF.js viewer و page locator
- audio waveform سبک در صورت نیاز
- image viewer
- local media range streaming
- annotationهای anchorشده به صفحه یا timestamp

این فاز فقط پس از مشخص‌شدن فایل‌های واقعی مورد استفاده scope می‌شود.

### فاز 6 — منابع جدید

**هدف:** افزودن Twitter/X و Medium بدون تغییر هستهٔ UI.

خروجی‌ها:

- canonical ingestion contract هر منبع
- adapter
- locatorهای مناسب
- node renderer فقط در صورت نیاز
- تست coexistence چند source type

### فاز 7 — بسته‌بندی دسکتاپ، مشروط

فقط اگر شواهد واقعی نشان دهد وب‌اپ local کافی نیست:

- spike Tauri
- بررسی sidecar یا launch backend
- file access و signing macOS
- مقایسهٔ startup، memory و نگهداری

## 17. تست و اعتبارسنجی

### 17.1. backend

- unit test برای adapter و IDها
- schema validation
- index rebuild test
- search correctness
- path traversal و file access tests
- atomic workspace writes
- migration tests

### 17.2. frontend

- component tests برای status/provenance
- interaction tests برای Library/Reader/Map/Canvas
- board save/restore
- timestamp navigation
- keyboard accessibility
- RTL/LTR mixed content
- pen coordinate transform tests

### 17.3. end-to-end

سناریوهای ضروری:

1. بازکردن source با `PARTIAL` و دیدن هشدار واقعی.
2. جست‌وجوی عبارت transcript و پرش به timestamp.
3. انتخاب knowledge unit و مشاهدهٔ evidence.
4. انتقال entity از Map به Canvas.
5. ایجاد user relation بدون تغییر canonical file.
6. طراحی با قلم، reload و حفظ stroke.
7. حذف cache و rebuild بدون ازدست‌رفتن board.

### 17.4. validatorهای موجود

پیش از ادعای موفقیت pipeline همچنان validatorهای فعلی اجرا می‌شوند. UI حق ندارد completion را مستقل از `validation.json` و `coverage.json` تعریف کند.

## 18. ریسک‌ها و راه کاهش آن‌ها

### ریسک 1: مخلوط‌شدن حقیقت و annotation

راهکار: سه namespace و storage جدا برای source، derived و user؛ promotion فقط با workflow صریح آینده.

### ریسک 2: کندشدن Canvas با رشد کتابخانه

راهکار: Canvas curated؛ گراف کامل در Sigma؛ lazy details و عدم render همهٔ nodeها.

### ریسک 3: وابستگی frontend به YouTube

راهکار: Source/Artifact/Locator عمومی و adapter مستقل.

### ریسک 4: از دست رفتن board یا stroke

راهکار: فایل portable، write اتمیک، backup/recovery و تست خرابی جزئی.

### ریسک 5: پیچیدگی زودهنگام editor

راهکار: فاز نخست read-only؛ rich text حداقلی؛ BlockSuite/Tiptap فقط پس از نیاز اثبات‌شده.

### ریسک 6: محدودیت قلم در مرورگر

راهکار: Pointer Events spike روی سخت‌افزار واقعی کاربر پیش از تکمیل ابزارها؛ fallback mouse.

### ریسک 7: نبود دادهٔ گراف معتبر برای توسعه

راهکار: تکمیل حداقل یک extraction واقعی یا ساخت fixture schema-valid با برچسب روشن test data؛ هرگز جعل آن به‌عنوان evidence واقعی.

### ریسک 8: تغییرات library و license

راهکار: نسخه‌ها هنگام implementation pin شوند؛ licenseها پیش از هر upgrade عمده بازبینی شوند؛ tldraw در وضعیت فعلی استفاده نشود.

## 19. تصمیم‌های ثبت‌شده

| ID | تصمیم | وضعیت | دلیل |
|---|---|---|---|
| D-001 | ساخت لایهٔ اختصاصی به‌جای fork محصول کامل | پذیرفته | کنترل provenance و کاهش پیچیدگی |
| D-002 | وب‌اپ محلی در فاز نخست | پذیرفته | سازگاری با هستهٔ Python و کمترین overhead |
| D-003 | React Flow برای Canvas | پذیرفته | custom HTML node و interaction مناسب |
| D-004 | Sigma.js برای Knowledge Map | پذیرفته | WebGL و تناسب با گراف بزرگ |
| D-005 | SQLite FTS5 به‌عنوان index قابل بازسازی | پذیرفته | محلی، ساده و کافی برای تک‌کاربر |
| D-006 | جداسازی workspace از output | پذیرفته | حفاظت از canonical evidence |
| D-007 | قلم با Pointer Events و perfect-freehand | پذیرفته برای spike | سبک و بدون license پولی |
| D-008 | عدم استفاده از tldraw | پذیرفته | محدودیت license production |
| D-009 | عدم استفادهٔ اولیه از graph database | پذیرفته | نیاز فعلی با SQLite/Graphology پوشش داده می‌شود |
| D-010 | Tauri فقط پس از اثبات نیاز | پذیرفته | جلوگیری از packaging زودهنگام |

## 20. پرسش‌های باز

این موارد مانع شروع فاز 0 و 1 نیستند و باید در زمان مناسب پاسخ داده شوند:

- زبان پیش‌فرض UI فارسی، انگلیسی یا انتخاب‌پذیر باشد؟
- boardها به‌طور پیش‌فرض وارد Git شوند یا فقط backup محلی داشته باشند؟
- آیا user note به Markdown ساده محدود بماند یا rich text لازم است؟
- آیا ویدئوها فقط از YouTube پخش می‌شوند یا فایل محلی نیز نگهداری خواهد شد؟
- PDF و اسناد در چه فازی واقعاً وارد workflow روزانه می‌شوند؟
- آیا یک entity می‌تواند در چند board view state مستقل داشته باشد؟ احتمالاً بله، ولی schema باید تثبیت شود.
- آیا snapshot خلاصهٔ node داخل board برای مقاومت در برابر حذف source لازم است؟
- سیاست حذف board و attachment چه میزان recovery نیاز دارد؟
- تم بصری نهایی و design tokens پس از wireframe تعیین می‌شود.

عامل نباید پاسخ این موارد را حدس بزند اگر تصمیم باعث تغییر محسوس در محصول یا schema می‌شود.

## 21. پروتکل کار در چند سشن

### آغاز هر سشن

1. `AGENTS.md` را بخوان.
2. برای هر ingestion/extraction، `WORKFLOW.md` را کامل رعایت کن.
3. این سند را بخوان.
4. `git status` و تغییرات موجود را بررسی کن؛ تغییرات کاربر را حفظ کن.
5. بخش «وضعیت اجرا» و «گام بعدی» را بررسی کن.
6. فقط یک فاز یا subtask محدود و قابل اعتبارسنجی را در دست بگیر.

### حین کار

- تصمیم معماری جدید را در جدول تصمیم‌ها ثبت کن.
- اگر تصمیمی فراتر از دامنهٔ پذیرفته‌شده است، از کاربر سؤال کن.
- canonical output و raw evidence را تغییر نده.
- تغییرات cache را به‌عنوان دستاورد داده‌ای گزارش نکن.
- تست متناسب با ریسک بنویس و اجرا کن.

### پایان هر سشن

1. تست‌ها و validatorهای مرتبط را اجرا کن.
2. فایل‌های تغییرکرده را ثبت کن.
3. معیارهای پذیرش انجام‌شده را علامت بزن.
4. تصمیم و ریسک جدید را به این سند اضافه کن.
5. «وضعیت اجرا» و «گام بعدی دقیق» را به‌روزرسانی کن.
6. اگر چیزی ناقص است، صریحاً `PARTIAL` یا pending ثبت کن.

## 22. وضعیت اجرا

### تکمیل‌شده

- [x] بررسی ساختار فعلی X2KNWLDG
- [x] بررسی قراردادهای provenance و canonical output
- [x] جست‌وجوی چندمرحله‌ای گزینه‌های متن‌باز
- [x] مقایسهٔ AFFiNE، BlockSuite، Logseq، TubeNotes، Kanvaz و Excalidraw
- [x] بررسی React Flow، Sigma.js، perfect-freehand، SQLite FTS5 و tldraw license
- [x] انتخاب معماری پایه
- [x] ثبت برنامهٔ چندسشن در این سند

### شروع‌نشده

- [ ] فاز 0: ADR و schema عمومی
- [ ] YouTube adapter
- [ ] SQLite index
- [ ] FastAPI local API
- [ ] React/Vite scaffolding
- [ ] Library/Reader
- [ ] Knowledge Map
- [ ] Canvas
- [ ] Pen annotations
- [ ] adapterهای منابع آینده

## 23. گام بعدی دقیق

سشن اجرایی بعدی باید فقط فاز 0 را آغاز کند:

1. بررسی schemaهای فعلی و IDهای واقعی knowledge unit/source.
2. نوشتن ADR معماری در `docs/adr/`.
3. تعریف schema نسخهٔ اول برای:
   - Source
   - Artifact
   - Locator
   - EntityRef
   - IndexedRelation
4. تعریف قرارداد YouTube adapter بدون تغییر خروجی‌های canonical موجود.
5. ساخت fixtureهای معتبر برای source `PARTIAL` فعلی و یک graph تکمیل‌شدهٔ test-only.
6. اجرای تست‌های موجود و افزودن تست schema/adapter.

تا زمانی که این قراردادها validate نشده‌اند، ساخت Canvas یا طراحی UI production نباید شروع شود.

## 24. منابع تحقیق

- AFFiNE: <https://github.com/toeverything/AFFiNE>
- BlockSuite Edgeless Editor: <https://blocksuite.io/components/editors/edgeless-editor>
- BlockSuite Edgeless Data Structure: <https://blocksuite.io/components/editors/edgeless-data-structure>
- Logseq: <https://github.com/logseq/logseq>
- Logseq tablet/whiteboard issue: <https://github.com/logseq/logseq/issues/12174>
- TubeNotes: <https://github.com/orgofjs/tubenotes-desktop>
- Kanvaz: <https://github.com/p4inz-code/kanvaz>
- Excalidraw: <https://github.com/excalidraw/excalidraw>
- React Flow performance: <https://reactflow.dev/learn/advanced-use/performance>
- React Flow attribution: <https://reactflow.dev/remove-attribution>
- Sigma.js: <https://github.com/jacomyal/sigma.js>
- perfect-freehand: <https://github.com/steveruizok/perfect-freehand>
- PointerEvent pressure: <https://developer.mozilla.org/en-US/docs/Web/API/PointerEvent/pressure>
- tldraw license: <https://tldraw.dev/community/license>
- SQLite FTS5: <https://www.sqlite.org/fts5.html>
- SQLite WAL: <https://sqlite.org/wal.html>
- Vite: <https://vite.dev/guide/>
- FastAPI: <https://fastapi.tiangolo.com/>

## 25. تاریخچهٔ تغییرات سند

### 2026-08-31

- نسخهٔ نخست سند ایجاد شد.
- نیازهای کاربر، نتایج تحقیق، تصمیم معماری، مرز داده‌ها و نقشهٔ راه ثبت شد.
- فاز 0 به‌عنوان گام بعدی تعیین شد.


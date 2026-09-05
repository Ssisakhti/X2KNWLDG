/**
 * What this Map is a map *of* (`T-256`).
 *
 * Two buttons over one addressable parameter. It sits on the Map's own field
 * rather than in the app bar, which is a **departure from the approved mockups**
 * and is recorded as one: the bar is `Shell`'s and belongs to every route, and a
 * control that is meaningless on the Library and the Reader does not belong on a
 * surface those two also render. The mockups drew it in the bar because a
 * mockup has one page.
 *
 * It is a `radiogroup` rather than two toggles, because the two modes are one
 * choice with two values: a reader tabbing into it hears "Sources, 2 of 2"
 * rather than two unrelated pressed states, and the arrow keys move between
 * them, which is what a keyboard user expects of a choice.
 */

import { useI18n } from "../i18n";
import { DEFAULT_MAP_MODE, MAP_MODES, type MapMode } from "../lib/mapLink";
import type { MessageKey } from "../i18n/catalog";

/** Each mode's own key, spelled in full so the catalogue guard can read it. */
const MODE_LABEL: Record<MapMode, MessageKey> = {
  knowledge: "map.mode.knowledge",
  sources: "map.mode.sources",
};

/** What each mode is *of*, for the control's own description. */
const MODE_NOTE: Record<MapMode, MessageKey> = {
  knowledge: "map.mode.knowledgeNote",
  sources: "map.mode.sourcesNote",
};

export function MapModeSwitch({
  mode,
  onChange,
}: {
  mode: MapMode | null;
  onChange: (mode: MapMode) => void;
}) {
  const { t } = useI18n();
  const current = mode ?? DEFAULT_MAP_MODE;
  return (
    <div
      className="modeswitch"
      role="radiogroup"
      aria-label={t("map.mode.switch")}
      data-map-mode={current}
    >
      <span className="modeswitch__label" aria-hidden="true">
        {t("map.mode.label")}
      </span>
      {MAP_MODES.map((value) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={value === current}
          // Only the selected radio is in the tab order, which is what makes a
          // radiogroup one stop rather than two.
          tabIndex={value === current ? 0 : -1}
          className={`button${value === current ? " button--on" : ""}`}
          onClick={() => onChange(value)}
          onKeyDown={(event) => {
            if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
            event.preventDefault();
            const index = MAP_MODES.indexOf(current);
            const step = event.key === "ArrowRight" ? 1 : -1;
            const next = MAP_MODES[(index + step + MAP_MODES.length) % MAP_MODES.length];
            if (next !== undefined) onChange(next);
          }}
          title={t(MODE_NOTE[value])}
          data-map-mode-option={value}
        >
          {t(MODE_LABEL[value])}
        </button>
      ))}
    </div>
  );
}

import {
  SUPPORTED_LANGUAGES,
  buildLocalizedBlueprint,
  buildGeneratedRoundtableDefaultCopy,
  buildGeneratedRoundtableModelCopy,
  buildGeneratedRoundtableSuggestionCopy,
  buildGeneratedThreadCopy,
  buildGeneratedWatchCopy,
  getPreferredLanguage,
  isRtlLanguage,
} from "./platform-i18n.js?v=20260408-1905";

const MOBILE_BREAKPOINT = 760;
const STORAGE_KEYS = {
  viewerId: "platform-viewer-id",
};
const SECTION_COSTS = {
  "model-briefs": 3,
  "entry-window": 5,
  "objective-data": 6,
  "risk-map": 4,
  "scenario-tree": 4,
  "model-notes": 7,
  "decision-sheet": 3,
};
const CODE_WALL_GLYPHS = "01ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓABCDEFGHIJKLMNOPQRSTUVWXYZ$#%&*+-=<>[]{}()/\\\\|:;".split("");

let sparklineId = 0;
let communitySyncTimer = null;
let feedLoadObserver = null;
let revealObserver = null;
let codeWallBuildTimer = null;

const state = {
  baseBlueprint: null,
  blueprint: null,
  performanceSnapshots: new Map(),
  language: "en",
  theme: "dark",
  activeTab: "feed",
  filterKind: "all",
  rankMetric: "total_return",
  followingOnly: false,
  searchQuery: "",
  feedVisibleCount: 0,
  expandedThreadIds: new Set(),
  followingIds: new Set(),
  communityPosts: [],
  followerCounts: {},
  composerMessage: "",
  composerMessageTone: "neutral",
  contributionType: "question",
  aiRoundtableTicker: "",
  aiRoundtableQuestion: "",
  aiRoundtableQuestionAuto: true,
  aiRoundtableHasAsked: false,
  aiPremiumUnlockedSectionIds: new Set(),
  aiPremiumGeneratingSectionIds: new Set(),
  aiPremiumActiveModelId: "gpt",
  isMobile: window.innerWidth <= MOBILE_BREAKPOINT,
  viewerId: "",
  authenticated: false,
  sessionUser: null,
  account: null,
  accountIdentity: null,
  commerceCatalog: null,
  oauthProviders: [],
  accountMenuMode: "login",
  accountSocialProvider: "",
  pendingSocialProfile: null,
  accountMessage: "",
  accountMessageTone: "neutral",
  accountTopUpPackId: "",
  accountTopUpMethod: "",
  adminToken: "",
  cursorHudEnabled: false,
  activeWorldNewsId: "",
  codeWallSignature: "",
  threadDataVersion: 0,
  followDataVersion: 0,
  allThreadsCacheVersion: -1,
  allThreadsCache: [],
  visibleThreadsCacheKey: "",
  visibleThreadsCache: [],
};

const el = {
  brandLabel: document.querySelector("#brand-label"),
  brandKicker: document.querySelector("#brand-kicker"),
  livePill: document.querySelector("#live-pill"),
  topbarCta: document.querySelector("#topbar-cta"),
  languageDropdown: document.querySelector("#language-dropdown"),
  languageToggle: document.querySelector("#language-toggle"),
  languageLabel: document.querySelector("#language-label"),
  languageCurrent: document.querySelector("#language-current"),
  languageMenu: document.querySelector("#language-menu"),
  languageSelect: document.querySelector("#language-select"),
  accountDropdown: document.querySelector("#account-dropdown"),
  accountToggle: document.querySelector("#account-toggle"),
  accountLabel: document.querySelector("#account-label"),
  accountCurrent: document.querySelector("#account-current"),
  accountMenu: document.querySelector("#account-menu"),
  craftCursor: document.querySelector("#craft-cursor"),
  codeWall: document.querySelector("#code-wall"),
  bootScreen: document.querySelector("#boot-screen"),
  bootCopy: document.querySelector("#boot-copy"),
  activeSignalsTitle: document.querySelector("#active-signals-title"),
  trendingSignalsTitle: document.querySelector("#trending-signals-title"),
  trendingSignalsLink: document.querySelector("#trending-signals-link"),
  publicResearchThreadsTitle: document.querySelector("#public-research-threads-title"),
  navFeedLabel: document.querySelector("#nav-feed-label"),
  navSignalsLabel: document.querySelector("#nav-signals-label"),
  navRankLabel: document.querySelector("#nav-rank-label"),
  navAskAiLabel: document.querySelector("#nav-ask-ai-label"),
  subnavCompare: document.querySelector("#subnav-compare"),
  subnavFeed: document.querySelector("#subnav-feed"),
  topbarSubnav: document.querySelector(".topbar-subnav"),
  globalSearchForm: document.querySelector("#global-search-form"),
  globalSearchSubmit: document.querySelector("#global-search-submit"),
  bottomNav: document.querySelector(".bottom-nav"),
  heroFeature: document.querySelector("#hero-feature"),
  signalBoard: document.querySelector("#signal-board"),
  saveCard: document.querySelector("#save-card"),
  proofStrip: document.querySelector("#proof-strip"),
  quickGuideKicker: document.querySelector("#quick-guide-kicker"),
  quickGuideTitle: document.querySelector("#quick-guide-title"),
  quickGuideDescription: document.querySelector("#quick-guide-description"),
  quickGuideGrid: document.querySelector("#quick-guide-grid"),
  browseKicker: document.querySelector("#browse-kicker"),
  browseTitle: document.querySelector("#browse-title"),
  browseDescription: document.querySelector("#browse-description"),
  browseGrid: document.querySelector("#browse-grid"),
  aiRoundtableKicker: document.querySelector("#ai-roundtable-kicker"),
  aiRoundtableTitle: document.querySelector("#ai-roundtable-title"),
  aiRoundtableDescription: document.querySelector("#ai-roundtable-description"),
  researchStageKicker: document.querySelector("#research-stage-kicker"),
  researchStageTitle: document.querySelector("#research-stage-title"),
  researchStageDescription: document.querySelector("#research-stage-description"),
  researchPanel: document.querySelector('.app-tab-panel[data-tab-panel="research"]'),
  researchHeroStrip: document.querySelector("#research-hero-strip"),
  feedStageKicker: document.querySelector("#feed-stage-kicker"),
  feedStageTitle: document.querySelector("#feed-stage-title"),
  feedStageDescription: document.querySelector("#feed-stage-description"),
  aiRoundtableShell: document.querySelector("#ai-roundtable"),
  aiRoundtableForm: document.querySelector("#ai-roundtable-form"),
  aiRoundtableTickerLabel: document.querySelector("#ai-roundtable-ticker-label"),
  aiRoundtableTicker: document.querySelector("#ai-roundtable-ticker"),
  aiRoundtableQuestionLabel: document.querySelector("#ai-roundtable-question-label"),
  aiRoundtableQuestion: document.querySelector("#ai-roundtable-question"),
  aiRoundtableSubmit: document.querySelector("#ai-roundtable-submit"),
  aiRoundtableSuggestions: document.querySelector("#ai-roundtable-suggestions"),
  aiRoundtableSummary: document.querySelector("#ai-roundtable-summary"),
  aiRoundtableGrid: document.querySelector("#ai-roundtable-grid"),
  returnRadarTitle: document.querySelector("#return-radar-title"),
  returnRadar: document.querySelector("#return-radar"),
  communityStageKicker: document.querySelector("#community-stage-kicker"),
  communityStageTitle: document.querySelector("#community-stage-title"),
  communityStageDescription: document.querySelector("#community-stage-description"),
  composerKicker: document.querySelector("#composer-kicker"),
  composerTitle: document.querySelector("#composer-title"),
  composerDescription: document.querySelector("#composer-description"),
  composerToggleChip: document.querySelector("#composer-toggle-chip"),
  contributionTypeRow: document.querySelector("#contribution-type-row"),
  composerForm: document.querySelector("#composer-form"),
  composerAuthorLabel: document.querySelector("#composer-author-label"),
  composerAuthor: document.querySelector("#composer-author"),
  composerKindLabel: document.querySelector("#composer-kind-label"),
  composerKind: document.querySelector("#composer-kind"),
  composerTickerLabel: document.querySelector("#composer-ticker-label"),
  composerTicker: document.querySelector("#composer-ticker"),
  composerCompanyLabel: document.querySelector("#composer-company-label"),
  composerCompany: document.querySelector("#composer-company"),
  composerHeadlineLabel: document.querySelector("#composer-headline-label"),
  composerHeadline: document.querySelector("#composer-headline"),
  composerSummaryLabel: document.querySelector("#composer-summary-label"),
  composerSummary: document.querySelector("#composer-summary"),
  composerTagsLabel: document.querySelector("#composer-tags-label"),
  composerTags: document.querySelector("#composer-tags"),
  composerLevelALabel: document.querySelector("#composer-level-a-label"),
  composerLevelA: document.querySelector("#composer-level-a"),
  composerLevelBLabel: document.querySelector("#composer-level-b-label"),
  composerLevelB: document.querySelector("#composer-level-b"),
  composerLevelCLabel: document.querySelector("#composer-level-c-label"),
  composerLevelC: document.querySelector("#composer-level-c"),
  composerSubmit: document.querySelector("#composer-submit"),
  composerHint: document.querySelector("#composer-hint"),
  followingCard: document.querySelector("#following-card"),
  leaderboardKicker: document.querySelector("#leaderboard-kicker"),
  leaderboardTitle: document.querySelector("#leaderboard-title"),
  leaderboardDescription: document.querySelector("#leaderboard-description"),
  leaderboardMetricRow: document.querySelector("#leaderboard-metric-row"),
  leaderboardList: document.querySelector("#leaderboard-list"),
  authorsKicker: document.querySelector("#authors-kicker"),
  authorsTitle: document.querySelector("#authors-title"),
  authorGrid: document.querySelector("#author-grid"),
  feedKicker: document.querySelector("#feed-kicker"),
  feedTitle: document.querySelector("#feed-title"),
  searchLabel: document.querySelector("#search-label"),
  threadSearch: document.querySelector("#thread-search"),
  filterRow: document.querySelector("#filter-row"),
  scopeRow: document.querySelector("#scope-row"),
  storiesKicker: document.querySelector("#stories-kicker"),
  storiesTitle: document.querySelector("#stories-title"),
  storiesDescription: document.querySelector("#stories-description"),
  storyGrid: document.querySelector("#story-grid"),
  archiveLogKicker: document.querySelector("#archive-log-kicker"),
  archiveLogTitle: document.querySelector("#archive-log-title"),
  threadFeed: document.querySelector("#thread-feed"),
  monetizationCard: document.querySelector("#monetization-card"),
  brandProofCard: document.querySelector("#brand-proof-card"),
  watchKicker: document.querySelector("#watch-kicker"),
  watchTitle: document.querySelector("#watch-title"),
  watchlist: document.querySelector("#watchlist"),
  archiveKicker: document.querySelector("#archive-kicker"),
  archiveTitle: document.querySelector("#archive-title"),
  archiveList: document.querySelector("#archive-list"),
  rulesKicker: document.querySelector("#rules-kicker"),
  rulesTitle: document.querySelector("#rules-title"),
  rulesList: document.querySelector("#rules-list"),
  playbookKicker: document.querySelector("#playbook-kicker"),
  playbookTitle: document.querySelector("#playbook-title"),
  pipelineList: document.querySelector("#pipeline-list"),
  loopsKicker: document.querySelector("#loops-kicker"),
  loopsTitle: document.querySelector("#loops-title"),
  loopsList: document.querySelector("#loops-list"),
};

window.__platformOnGoogleIdentityLoad = () => {
  renderGoogleIdentityButton();
};

function topbarSearchValue() {
  return el.threadSearch?.value?.trim() || "";
}

function ui() {
  return state.blueprint.ui;
}

function uiText(key, replacements = {}) {
  const text = ui()?.[key] || "";
  return Object.entries(replacements).reduce(
    (result, [name, value]) => result.replaceAll(`{${name}}`, String(value ?? "")),
    text,
  );
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildCodeWallGlyph(columnIndex, glyphIndex) {
  const seed = (columnIndex * 37 + glyphIndex * 19 + glyphIndex * columnIndex) % CODE_WALL_GLYPHS.length;
  return CODE_WALL_GLYPHS[seed];
}

function shouldUseReducedEffects() {
  const memory = Number(window.navigator?.deviceMemory || 0);
  const cores = Number(window.navigator?.hardwareConcurrency || 0);
  return state.isMobile || (memory > 0 && memory <= 4) || (cores > 0 && cores <= 4);
}

function codeWallSignature() {
  const widthBucket = Math.max(1, Math.round(window.innerWidth / 140));
  const heightBucket = Math.max(1, Math.round(window.innerHeight / 180));
  return `${widthBucket}:${heightBucket}:${shouldUseReducedEffects() ? "reduced" : "full"}`;
}

function buildCodeWall() {
  if (!el.codeWall) {
    return;
  }
  const reducedEffects = shouldUseReducedEffects();
  const columnCount = reducedEffects
    ? Math.max(14, Math.min(24, Math.floor(window.innerWidth / 54)))
    : Math.max(18, Math.min(32, Math.floor(window.innerWidth / 40)));
  const glyphRows = reducedEffects
    ? Math.max(28, Math.min(52, Math.floor(window.innerHeight / 24)))
    : Math.max(38, Math.min(68, Math.floor(window.innerHeight / 18)));
  const columnWidth = 100 / columnCount;
  const columns = [];
  for (let columnIndex = 0; columnIndex < columnCount; columnIndex += 1) {
    const glyphs = [];
    const lane = 15 + (columnIndex % 7);
    for (let glyphIndex = 0; glyphIndex < glyphRows; glyphIndex += 1) {
      const distance = (glyphIndex + columnIndex * 5) % lane;
      let className = "code-wall-glyph";
      if (distance === 0) {
        className += " is-head";
      } else if (distance === 1) {
        className += " is-tail-1";
      } else if (distance === 2) {
        className += " is-tail-2";
      } else if (distance === 3 || distance === 4) {
        className += " is-tail-3";
      } else if ((glyphIndex + columnIndex * 3) % 9 === 0) {
        className += " is-bright";
      }
      glyphs.push(`<span class="${className}">${escapeHtml(buildCodeWallGlyph(columnIndex, glyphIndex))}</span>`);
    }
    const stream = glyphs.join("") + glyphs.join("");
    columns.push(`
      <div
        class="code-wall-column"
        style="
          left:${(columnIndex * columnWidth).toFixed(3)}%;
          width:${(columnWidth + 0.18).toFixed(3)}%;
          --code-duration:${reducedEffects ? 11.5 : 9.8 + (columnIndex % 8) * 1.2}s;
          --code-delay:-${(columnIndex % 9) * 0.9}s;
          --code-opacity:${(reducedEffects ? 0.1 : 0.12) + (columnIndex % 5) * 0.025};
        "
      >
        <div class="code-wall-stream">${stream}</div>
      </div>
    `);
  }
  el.codeWall.innerHTML = columns.join("");
}

function scheduleCodeWallBuild({ force = false, immediate = false } = {}) {
  if (!el.codeWall) {
    return;
  }
  const nextSignature = codeWallSignature();
  if (!force && nextSignature === state.codeWallSignature) {
    return;
  }
  window.clearTimeout(codeWallBuildTimer);
  const run = () => {
    state.codeWallSignature = nextSignature;
    buildCodeWall();
  };
  if (immediate) {
    run();
    return;
  }
  codeWallBuildTimer = window.setTimeout(run, 120);
}

function setText(node, value) {
  if (node) {
    node.textContent = value;
  }
}

function applyTheme() {
  state.theme = "dark";
  document.body.dataset.theme = "dark";
  document.documentElement.style.colorScheme = "dark";

  const themeColor = "#050705";
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) {
    themeMeta.setAttribute("content", themeColor);
  }
}

function canUseHudCursor() {
  return window.matchMedia && window.matchMedia("(pointer: fine)").matches && !state.isMobile;
}

function setCursorInteractive(isInteractive) {
  if (!state.cursorHudEnabled || !el.craftCursor) {
    return;
  }
  el.craftCursor.classList.toggle("is-interactive", Boolean(isInteractive));
}

function syncHudCursorMode() {
  state.cursorHudEnabled = false;
  document.body.classList.remove("cursor-hud-enabled");
  if (!state.cursorHudEnabled) {
    setCursorInteractive(false);
  }
}

function bindHudCursor() {
  syncHudCursorMode();
  if (!el.craftCursor) {
    return;
  }

  const updateCursorPosition = (event) => {
    if (!state.cursorHudEnabled) {
      return;
    }
    el.craftCursor.style.transform = `translate(${event.clientX - 2}px, ${event.clientY - 1}px)`;
    el.craftCursor.classList.add("is-visible");
  };

  const setInteractiveFromTarget = (target) => {
    if (!state.cursorHudEnabled) {
      return;
    }
    const interactive = target?.closest?.(
      "button, a, input, select, textarea, label, [role='button'], [data-app-tab], [data-hot-ticker], [data-ai-question]",
    );
    setCursorInteractive(Boolean(interactive));
  };

  document.addEventListener("pointermove", (event) => {
    updateCursorPosition(event);
    setInteractiveFromTarget(event.target);
  });

  document.addEventListener("pointerdown", () => {
    if (state.cursorHudEnabled && el.craftCursor) {
      el.craftCursor.classList.add("is-pressed");
    }
  });

  document.addEventListener("pointerup", () => {
    if (el.craftCursor) {
      el.craftCursor.classList.remove("is-pressed");
    }
  });

  document.addEventListener("pointerleave", () => {
    if (el.craftCursor) {
      el.craftCursor.classList.remove("is-visible");
    }
  });
}

function setPlaceholder(node, value) {
  if (node) {
    node.placeholder = value;
  }
}

function setBootMessage(message) {
  if (el.bootCopy) {
    el.bootCopy.textContent = message;
  }
}

function markAppReady() {
  document.body.classList.remove("is-booting", "is-boot-failed");
  document.body.classList.add("is-ready");
  if (el.bootScreen) {
    el.bootScreen.setAttribute("hidden", "");
    el.bootScreen.setAttribute("aria-hidden", "true");
  }
}

function markAppFailed(message) {
  setBootMessage(message);
  document.body.classList.remove("is-ready", "is-booting");
  document.body.classList.add("is-boot-failed");
  if (el.bootScreen) {
    el.bootScreen.removeAttribute("hidden");
    el.bootScreen.setAttribute("aria-hidden", "false");
  }
}

function safeRender(name, renderFn) {
  try {
    renderFn();
  } catch (error) {
    console.error(`Render failed: ${name}`, error);
  }
}

function setActiveTab(nextTab) {
  state.activeTab = nextTab === "feed" ? "feed" : "research";
  document.body.dataset.activeTab = state.activeTab;

  document.querySelectorAll("[data-app-tab]").forEach((node) => {
    const isActive = node.dataset.appTab === state.activeTab;
    node.classList.toggle("is-active", isActive);
    node.setAttribute("aria-pressed", String(isActive));
  });

  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    const isActive = panel.dataset.tabPanel === state.activeTab;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });

  syncTopbarSearchFromState();
}

function initialTabFromLocation() {
  const hash = window.location.hash || "";
  if (hash.includes("ai-roundtable")) {
    return "research";
  }
  return "feed";
}

function likelyCopyLanguage(text) {
  const source = String(text || "");
  if (!source.trim()) {
    return "unknown";
  }

  const hangul = (source.match(/[\uac00-\ud7a3]/g) || []).length;
  const kana = (source.match(/[\u3040-\u30ff]/g) || []).length;
  const han = (source.match(/[\u4e00-\u9fff]/g) || []).length;
  const arabic = (source.match(/[\u0600-\u06ff]/g) || []).length;
  const devanagari = (source.match(/[\u0900-\u097f]/g) || []).length;
  const latin = (source.match(/[A-Za-z]/g) || []).length;

  if (hangul > 0) {
    return "ko";
  }
  if (kana > 0) {
    return "ja";
  }
  if (arabic > 0) {
    return "ar";
  }
  if (devanagari > 0) {
    return "hi";
  }
  if (han > 0) {
    return "zh-CN";
  }
  if (latin > 0) {
    return "en";
  }
  return "unknown";
}

function copyLanguageSignature(copy = {}) {
  return likelyCopyLanguage(
    [
      copy.headline,
      copy.summary,
      copy.note,
      copy.footer,
      copy.question,
      copy.style,
      copy.tagline,
      ...(copy.beats || []),
    ].filter(Boolean).join(" ")
  );
}

function copyLanguageMatchesTarget(signature, targetLanguage) {
  const target = String(targetLanguage || "en");
  const targetBase = target.split("-")[0];
  if (!signature || signature === "unknown") {
    return true;
  }
  if (signature === target || signature === targetBase) {
    return true;
  }
  if (target === "zh-CN" && signature === "zh-CN") {
    return true;
  }
  return false;
}

function firstAvailableCopy(record) {
  const copy = record?.copy || {};
  const candidates = Object.entries(copy)
    .filter(([key, value]) => key !== "source_language" && value && typeof value === "object")
    .map(([, value]) => value);
  return candidates[0] || {};
}

function generatedCopyFor(record) {
  if (!record) {
    return null;
  }

  if (record.kind && Array.isArray(record.price_map)) {
    return buildGeneratedThreadCopy(record, state.language);
  }
  if (record.ticker && record.trigger) {
    return buildGeneratedWatchCopy(record, state.language);
  }
  if (record.id && (record.copy?.en?.question || record.copy?.ko?.question)) {
    return buildGeneratedRoundtableDefaultCopy(record, state.language);
  }
  if (record.id && (record.copy?.en?.label || record.copy?.ko?.label)) {
    return buildGeneratedRoundtableSuggestionCopy(record, state.language);
  }
  if (record.id && (record.copy?.en?.style || record.copy?.ko?.style)) {
    return buildGeneratedRoundtableModelCopy(record, state.language);
  }
  return null;
}

function copyFor(record) {
  const exact = record.copy?.[state.language];
  if (exact && copyLanguageMatchesTarget(copyLanguageSignature(exact), state.language)) {
    return exact;
  }

  const generated = generatedCopyFor(record);
  if (generated) {
    return generated;
  }

  if (exact) {
    return exact;
  }

  const base = state.language.split("-")[0];
  const baseCopy = record.copy?.[base];
  if (baseCopy && copyLanguageMatchesTarget(copyLanguageSignature(baseCopy), state.language)) {
    return baseCopy;
  }

  if (baseCopy) {
    return baseCopy;
  }

  if (record.copy?.en) {
    const english = record.copy.en;
    if (state.language === "en" || state.language.startsWith("en")) {
      return english;
    }
    return generated || english;
  }

  const fallback = firstAvailableCopy(record);
  if (Object.keys(fallback).length) {
    return fallback;
  }

  if (generated) {
    return generated;
  }

  if (record.copy?.[state.language]) {
    return record.copy[state.language];
  }

  if (record.copy?.[base]) {
    return record.copy[base];
  }

  if (record.copy?.en) {
    return record.copy.en;
  }

  return {};
}

function strategyFor(record) {
  const direct = record.strategy?.[state.language];
  if (direct) {
    return direct;
  }

  const base = state.language.split("-")[0];
  return record.strategy?.[base] || record.strategy?.en || {};
}

function roundtableConfig() {
  const source = state.blueprint || state.baseBlueprint || {};
  return source.ai_roundtable || { defaults: {}, models: [], suggestions: [] };
}

function roundtableModels() {
  return roundtableConfig().models || [];
}

function roundtableSuggestions() {
  return roundtableConfig().suggestions || [];
}

function roundtableDefaultQuestion() {
  return copyFor(roundtableConfig().defaults).question || "";
}

function defaultRoundtableQuestionForTicker(ticker) {
  const normalized = normalizeTicker(ticker) || roundtableConfig().defaults?.ticker || featuredThread()?.ticker || "NVDA";
  return uiText("defaultQuestionForTicker", { ticker: normalized });
}

function roundtableModelsWithResponses(context = roundtableContext()) {
  return roundtableModels().map((model) => ({
    ...model,
    response: roundtableModelResponse(model, context),
  }));
}

function setTopbarSearchValue(value) {
  if (el.threadSearch) {
    el.threadSearch.value = value || "";
  }
}

function syncTopbarSearchFromState() {
  if (!el.threadSearch) {
    return;
  }
  setPlaceholder(el.threadSearch, ui().topbarSearchResearchPlaceholder);
  setTopbarSearchValue(state.aiRoundtableQuestion || "");
}

function syncResearchInputsFromState() {
  if (el.aiRoundtableQuestion) {
    el.aiRoundtableQuestion.value = state.aiRoundtableQuestion || "";
  }
}

function openResearchFromQuery(rawQuery) {
  const nextQuestion = String(rawQuery || "").trim();
  if (!nextQuestion) {
    return;
  }

  const inferredTicker = inferRoundtableTicker(nextQuestion);
  state.aiRoundtableTicker = inferredTicker;
  state.aiRoundtableQuestionAuto = isAutoRoundtableQuestion(nextQuestion) || normalizeTicker(nextQuestion) === inferredTicker;
  state.aiRoundtableQuestion = state.aiRoundtableQuestionAuto
    ? defaultRoundtableQuestionForTicker(inferredTicker)
    : nextQuestion;
  state.aiRoundtableHasAsked = true;
  state.aiPremiumUnlockedSectionIds = new Set();
  state.aiPremiumGeneratingSectionIds = new Set();
  syncResearchInputsFromState();
  setActiveTab("research");
  renderAiRoundtable();
}

function isAutoRoundtableQuestion(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    return true;
  }

  if (/^What do the AIs think about [A-Z.\-]+ right now\?$/i.test(trimmed)) {
    return true;
  }

  if (/^지금 [A-Z.\-]+를 (?:주요 AI들이|AI들은) 어떻게 보고 있나요\?$/.test(trimmed)) {
    return true;
  }

  return trimmed === roundtableDefaultQuestion() || trimmed === ui().aiRoundtableQuestionPlaceholder;
}

function normalizeTicker(value) {
  return String(value || "").trim().toUpperCase();
}

function roundtableLookupEntries() {
  const entries = new Map();
  const defaults = roundtableConfig().defaults || {};

  const addEntry = (ticker, company) => {
    const normalizedTicker = normalizeTicker(ticker);
    if (!normalizedTicker) {
      return;
    }
    const current = entries.get(normalizedTicker) || {
      ticker: normalizedTicker,
      names: new Set(),
    };
    if (company) {
      current.names.add(String(company).trim().toLowerCase());
    }
    current.names.add(normalizedTicker.toLowerCase());
    entries.set(normalizedTicker, current);
  };

  addEntry(defaults.ticker, defaults.company);
  state.baseBlueprint?.threads?.forEach((thread) => addEntry(thread.ticker, thread.company));
  state.baseBlueprint?.watchlist?.forEach((item) => addEntry(item.ticker, item.company));

  return [...entries.values()];
}

function inferRoundtableTicker(question) {
  const normalizedQuestion = String(question || "").trim();
  if (!normalizedQuestion) {
    return normalizeTicker(state.aiRoundtableTicker) || roundtableConfig().defaults?.ticker || featuredThread()?.ticker || "NVDA";
  }

  const upperQuestion = normalizedQuestion.toUpperCase();
  const entries = roundtableLookupEntries();

  for (const entry of entries) {
    const tickerPattern = new RegExp(`(^|[^A-Z0-9])${entry.ticker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?=$|[^A-Z0-9])`, "i");
    if (tickerPattern.test(upperQuestion)) {
      return entry.ticker;
    }
  }

  const lowerQuestion = normalizedQuestion.toLowerCase();
  for (const entry of entries) {
    if ([...entry.names].some((name) => name && lowerQuestion.includes(name))) {
      return entry.ticker;
    }
  }

  const fallback = normalizeTicker(normalizedQuestion);
  if (entries.some((entry) => entry.ticker === fallback)) {
    return fallback;
  }

  const tokenMatch = upperQuestion.match(/\b[A-Z][A-Z.\-]{1,9}\b/);
  if (tokenMatch) {
    return normalizeTicker(tokenMatch[0]);
  }

  return normalizeTicker(state.aiRoundtableTicker) || roundtableConfig().defaults?.ticker || featuredThread()?.ticker || "NVDA";
}

function contributionTypes() {
  return [
    {
      id: "question",
      label: ui().contributionQuestionLabel,
      hint: ui().contributionQuestionHint,
    },
    {
      id: "counter",
      label: ui().contributionCounterLabel,
      hint: ui().contributionCounterHint,
    },
    {
      id: "evidence",
      label: ui().contributionEvidenceLabel,
      hint: ui().contributionEvidenceHint,
    },
  ];
}

function createViewerId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `viewer-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function ensureViewerId() {
  const saved = window.localStorage.getItem(STORAGE_KEYS.viewerId);
  if (saved) {
    return saved;
  }
  const next = createViewerId();
  window.localStorage.setItem(STORAGE_KEYS.viewerId, next);
  return next;
}

function clearLegacyAdminTokenStorage() {
  try {
    window.localStorage.removeItem("platform-admin-token");
  } catch {
    // Ignore storage access errors in private browsing or locked-down contexts.
  }
}

function getStoredAdminToken() {
  clearLegacyAdminTokenStorage();
  return "";
}

function setStoredAdminToken(token) {
  const normalized = String(token || "").trim();
  clearLegacyAdminTokenStorage();
  state.adminToken = normalized;
}

function authorFollowerValue(author) {
  const liveCount = state.followerCounts[author.id];
  if (typeof liveCount === "number" && Number.isFinite(liveCount)) {
    return compactNumber(liveCount);
  }
  return author.followers;
}

function rankingOptions() {
  return [
    { id: "total_return", label: ui().leaderboardTotalLabel },
    { id: "recent_return", label: ui().leaderboardRecentLabel },
    { id: "win_rate", label: ui().leaderboardWinRateLabel },
  ];
}

function leaderboardMetricOptions() {
  return [
    { id: "total_return", label: ui().leaderboardTotalLabel, locked: false },
    {
      id: "recent_return",
      label: ui().leaderboardRecentPaidLabel || ui().leaderboardRecentLabel,
      locked: !hasRecentRankAccess(),
      credits: recentRankCost(),
    },
  ];
}

function recentRankCost() {
  return Number(state.commerceCatalog?.product_costs?.["recent-rank"] || 3);
}

function hasRecentRankAccess() {
  return Boolean(state.account?.recent_rank_active || state.account?.membership_active);
}

function followPassCost() {
  return Number(state.commerceCatalog?.product_costs?.["follow-pass"] || 4);
}

function hasFollowAccess() {
  return Boolean(state.account?.follow_pass_active || state.account?.membership_active);
}

function deskPassCost() {
  return Number(state.commerceCatalog?.product_costs?.["desk-pass"] || 7);
}

function hasDeskAccess(authorId) {
  return Boolean(state.account?.membership_active || accountHasDeskPass(authorId));
}

function parsePriceNumber(value) {
  return Number.parseFloat(String(value || "").replace(/[^\d.-]/g, "")) || 0;
}

function rawAuthorPerformance(author) {
  return {
    total_return: Number(author.performance?.total_return || 0),
    recent_return: Number(author.performance?.recent_return || 0),
    win_rate: Number(author.performance?.win_rate || 0),
    closed_trades: Number(author.performance?.closed_trades || 0),
    avg_hold: author.performance?.avg_hold || "--",
    open_positions: 0,
    open_return: 0,
    open_thread_ids: [],
  };
}

function markPriceForThread(thread) {
  return parsePriceNumber(
    metricValue(thread, "Mark")
      || metricValue(thread, "Current")
      || metricValue(thread, "Focus")
      || metricValue(thread, "Trigger")
  );
}

function openReturnForThread(thread) {
  const entry = parsePriceNumber(metricValue(thread, "Entry"));
  const mark = markPriceForThread(thread);
  if (!entry || !mark) {
    return 0;
  }
  return ((mark - entry) / entry) * 100;
}

function openBuyThreadsForAuthor(author) {
  const timeline = allThreads()
    .filter((thread) => thread.author_id === author.id && (thread.kind === "buy" || thread.kind === "sell"))
    .sort((left, right) => threadAgeMinutes(right) - threadAgeMinutes(left));
  const openByTicker = new Map();

  timeline.forEach((thread) => {
    const ticker = normalizeTicker(thread.ticker);
    if (!ticker) {
      return;
    }
    if (thread.kind === "sell") {
      openByTicker.delete(ticker);
      return;
    }
    openByTicker.set(ticker, thread);
  });

  return [...openByTicker.values()];
}

function deriveAuthorPerformance(author) {
  const base = rawAuthorPerformance(author);
  const openThreads = openBuyThreadsForAuthor(author);
  const openReturn = openThreads.reduce((total, thread) => total + openReturnForThread(thread), 0);

  return {
    ...base,
    total_return: Number((base.total_return + openReturn).toFixed(1)),
    recent_return: Number((base.recent_return + openReturn).toFixed(1)),
    open_positions: openThreads.length,
    open_return: Number(openReturn.toFixed(1)),
    open_thread_ids: openThreads.map((thread) => thread.id),
  };
}

function authorPerformance(author) {
  return state.performanceSnapshots.get(author.id) || rawAuthorPerformance(author);
}

function performanceValue(author, metric) {
  return Number(authorPerformance(author)?.[metric] || 0);
}

function signedPercent(value) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

function winRatePercent(value) {
  return `${Number(value || 0).toFixed(0)}%`;
}

function primaryMetricDisplay(author, metric) {
  const value = performanceValue(author, metric);
  if (metric === "win_rate") {
    return winRatePercent(value);
  }
  return signedPercent(value);
}

function authorRanking(metric = state.rankMetric) {
  return [...state.blueprint.authors].sort((left, right) => {
    const metricDelta = performanceValue(right, metric) - performanceValue(left, metric);
    if (metricDelta !== 0) {
      return metricDelta;
    }

    const totalDelta = performanceValue(right, "total_return") - performanceValue(left, "total_return");
    if (totalDelta !== 0) {
      return totalDelta;
    }

    return performanceValue(right, "win_rate") - performanceValue(left, "win_rate");
  });
}

function compactNumber(value) {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return `${value}`;
}

function parseCompactMetric(value) {
  if (!value) {
    return 0;
  }

  const normalized = String(value).trim().toUpperCase();
  const multiplier = normalized.endsWith("M") ? 1_000_000 : normalized.endsWith("K") ? 1_000 : 1;
  return Number.parseFloat(normalized.replace(/[^\d.]/g, "")) * multiplier;
}

function formatKrw(value) {
  return new Intl.NumberFormat(
    state.language === "ko" ? "ko-KR" : undefined,
    {
      style: "currency",
      currency: "KRW",
      maximumFractionDigits: 0,
    },
  ).format(Number(value || 0));
}

function formatApproxKrw(value) {
  const rounded = Math.max(100, Math.round(Number(value || 0) / 100) * 100);
  const plain = new Intl.NumberFormat(state.language === "ko" ? "ko-KR" : undefined, {
    maximumFractionDigits: 0,
  }).format(rounded);
  if (state.language === "ko") {
    return `약 ${plain}원`;
  }
  return `about ${formatKrw(rounded)}`;
}

function creditPacksList() {
  return Array.isArray(catalog().credit_packs) ? catalog().credit_packs : [];
}

function totalCreditsForPack(pack) {
  return Number(pack?.total_credits || (Number(pack?.credits || 0) + Number(pack?.bonus_credits || 0)) || 0);
}

function starterPack() {
  const packs = creditPacksList();
  return packs.find((pack) => pack.id === "starter")
    || [...packs].sort((left, right) => Number(left.price_krw || 0) - Number(right.price_krw || 0))[0]
    || null;
}

function krwPerCredit() {
  const pack = starterPack();
  const totalCredits = totalCreditsForPack(pack);
  if (!pack || !totalCredits) {
    return 0;
  }
  return Number(pack.price_krw || 0) / totalCredits;
}

function approximateKrwForCredits(credits) {
  const unit = krwPerCredit();
  if (!unit || !credits) {
    return 0;
  }
  return unit * Number(credits || 0);
}

function estimatedQuickUnlockCount(credits) {
  return Math.max(1, Math.round(Number(credits || 0) / 4));
}

function creditValueMeta(credits) {
  return uiText("creditsValueMetaLabel", {
    credits: Number(credits || 0),
    amount: formatApproxKrw(approximateKrwForCredits(credits)),
  });
}

function packBenefitLabel(pack) {
  return uiText("accountPackBenefitLabel", {
    count: estimatedQuickUnlockCount(totalCreditsForPack(pack)),
  });
}

function accountTopUpQuickLabel() {
  const pack = starterPack();
  if (!pack) {
    return uiText("accountTopUpQuickActionLabel", { amount: formatKrw(3900) });
  }
  return uiText("accountTopUpQuickActionLabel", { amount: formatKrw(pack.price_krw) });
}

function catalog() {
  return state.commerceCatalog || { credit_packs: [], payment_methods: [] };
}

function ensureCommerceSelections() {
  const creditPacks = creditPacksList();
  const paymentMethods = Array.isArray(catalog().payment_methods) ? catalog().payment_methods : [];

  if (!creditPacks.some((pack) => pack.id === state.accountTopUpPackId)) {
    state.accountTopUpPackId = creditPacks[0]?.id || "";
  }
  if (!paymentMethods.some((method) => method.id === state.accountTopUpMethod)) {
    state.accountTopUpMethod = paymentMethods[0]?.id || "";
  }
}

function paymentMethodLabel(methodId) {
  const labels = {
    "bank-transfer": ui().accountPaymentMethodBankTransferLabel,
    "manual-card-request": ui().accountPaymentMethodManualCardLabel,
  };
  return labels[methodId] || methodId;
}

function paymentMethodDetails(methodId) {
  const methods = Array.isArray(catalog().payment_methods) ? catalog().payment_methods : [];
  return methods.find((method) => method.id === methodId)?.details || null;
}

function paymentRequestStatusLabel(status) {
  const labels = {
    pending: ui().accountPaymentStatusPendingLabel,
    expired: ui().accountPaymentStatusExpiredLabel,
    approved: ui().accountPaymentStatusApprovedLabel,
    rejected: ui().accountPaymentStatusRejectedLabel,
  };
  return labels[status] || status;
}

function creditPackTitle(packId) {
  const labels = {
    starter: ui().accountPackStarterTitle,
    plus: ui().accountPackPlusTitle,
    pro: ui().accountPackProTitle,
  };
  return labels[packId] || packId;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload.detail || "";
    } catch {
      detail = response.statusText;
    }
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

function currentResearchTicker() {
  return normalizeTicker(
    state.aiRoundtableTicker
    || roundtableConfig().defaults?.ticker
    || featuredThread()?.ticker
    || "NVDA"
  );
}

function invalidateThreadCaches() {
  state.threadDataVersion += 1;
  state.allThreadsCacheVersion = -1;
  state.allThreadsCache = [];
  state.visibleThreadsCacheKey = "";
  state.visibleThreadsCache = [];
}

function invalidateVisibleThreadsCache() {
  state.visibleThreadsCacheKey = "";
  state.visibleThreadsCache = [];
}

function syncUnlockedSectionsFromAccount() {
  const ticker = currentResearchTicker();
  const unlocked = state.account?.unlocked_sections?.[ticker] || [];
  state.aiPremiumUnlockedSectionIds = new Set(Array.isArray(unlocked) ? unlocked : []);
}

function applyAccountPayload(payload = {}, { preserveMessage = false } = {}) {
  state.authenticated = Boolean(payload.authenticated);
  state.sessionUser = payload.user || null;
  state.account = payload.account || null;
  state.accountIdentity = payload.identity || null;
  state.commerceCatalog = payload.catalog || state.commerceCatalog;
  state.oauthProviders = Array.isArray(payload.oauth_providers) ? payload.oauth_providers : state.oauthProviders;
  ensureCommerceSelections();
  if (!preserveMessage) {
    state.accountMessage = "";
    state.accountMessageTone = "neutral";
  }
  syncUnlockedSectionsFromAccount();
}

async function syncAccountState({ rerender = false } = {}) {
  const payload = await requestJson("/api/platform/account", {
    method: "GET",
    headers: {},
  });
  applyAccountPayload(payload);
  if (rerender) {
    renderApp();
  }
}

function setAccountMessage(message = "", tone = "neutral") {
  state.accountMessage = message;
  state.accountMessageTone = tone;
}

function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function adminDashboardUrl() {
  return "/platform/admin";
}

function renderAdminAccessPanel() {
  const token = state.adminToken || "";
  return `
    <section class="account-admin-shell">
      <div class="account-admin-head">
        <div>
          <p class="account-section-label">${escapeHtml(ui().accountAdminTitle)}</p>
          <p class="account-inline-note">${escapeHtml(ui().accountAdminBody)}</p>
        </div>
      </div>
      <form class="account-admin-form" data-admin-access-form>
        <label class="field field-compact">
          <span>${escapeHtml(ui().accountAdminTokenLabel)}</span>
          <input
            name="admin_token"
            type="password"
            value="${escapeHtml(token)}"
            placeholder="${escapeHtml(ui().accountAdminTokenPlaceholder)}"
            autocomplete="off"
          />
        </label>
        <div class="account-admin-actions">
          <button type="submit" class="cta cta-compact">${escapeHtml(ui().accountAdminOpenLabel)}</button>
          ${token ? `<button type="button" class="ghost-cta" data-account-admin-clear>${escapeHtml(ui().accountAdminClearLabel)}</button>` : ""}
        </div>
      </form>
    </section>
  `;
}

async function clearPendingSocialState() {
  state.pendingSocialProfile = null;
  state.accountSocialProvider = "";
  try {
    await requestJson("/api/platform/auth/social/pending", {
      method: "DELETE",
      body: JSON.stringify({}),
    });
  } catch (error) {
    console.error("Pending social clear failed", error);
  }
}

async function syncPendingSocialState() {
  try {
    const payload = await requestJson("/api/platform/auth/social/pending", {
      method: "GET",
      headers: {},
    });
    state.pendingSocialProfile = payload.pending || null;
    state.accountSocialProvider = state.pendingSocialProfile?.provider || "";
  } catch (error) {
    console.error("Pending social sync failed", error);
    state.pendingSocialProfile = null;
    state.accountSocialProvider = "";
  }
}

function openAccountMenu(mode = "login", message = "", tone = "neutral") {
  state.accountMenuMode = mode;
  if (message) {
    setAccountMessage(message, tone);
  }
  if (el.accountDropdown) {
    el.accountDropdown.classList.add("is-open");
  }
  if (el.accountToggle) {
    el.accountToggle.setAttribute("aria-expanded", "true");
  }
  renderAccountMenu();
}

function closeAccountMenu() {
  if (el.accountDropdown) {
    el.accountDropdown.classList.remove("is-open");
  }
  if (el.accountToggle) {
    el.accountToggle.setAttribute("aria-expanded", "false");
  }
}

function socialProviderLabel(provider) {
  const normalized = String(provider || "").toLowerCase();
  const keyByProvider = {
    local: "accountIdentityProviderLocalLabel",
    google: "accountIdentityProviderGoogleLabel",
    apple: "accountIdentityProviderAppleLabel",
    x: "accountIdentityProviderXLabel",
    twitter: "accountIdentityProviderXLabel",
  };
  if (keyByProvider[normalized]) {
    return ui()[keyByProvider[normalized]];
  }
  switch (provider) {
    case "google":
      return "Google";
    case "apple":
      return "Apple";
    case "x":
    case "twitter":
      return "Twitter";
    default:
      return "";
  }
}

function oauthProviderMeta(provider) {
  const normalized = String(provider || "").toLowerCase();
  const aliases = normalized === "twitter" ? ["twitter", "x"] : normalized === "x" ? ["x", "twitter"] : [normalized];
  return state.oauthProviders.find((item) => aliases.includes(String(item?.provider || "").toLowerCase())) || null;
}

function oauthProviderEnabled(provider) {
  return Boolean(oauthProviderMeta(provider)?.enabled);
}

function googleProviderClientId() {
  return String(oauthProviderMeta("google")?.client_id || "").trim();
}

function renderGoogleIdentityButton() {
  const slot = el.accountMenu?.querySelector("[data-google-signin-slot]");
  if (!slot) {
    return;
  }
  const enabled = oauthProviderEnabled("google");
  slot.innerHTML = `
    <button
      type="button"
      class="account-social-btn ${enabled ? "" : "is-disabled"}"
      ${enabled ? 'data-account-social-provider="google"' : 'aria-disabled="true" disabled'}
    >
      <span class="account-social-glyph" aria-hidden="true">G</span>
      <span class="account-social-copy">${escapeHtml(ui().accountSocialGoogleLabel)}</span>
    </button>
  `;
}

function accountIdentityDateLabel(value) {
  if (!value) {
    return "";
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return "";
  }
  return new Intl.DateTimeFormat(state.language || "en", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(parsed));
}

function renderAccountIdentityCard() {
  const identity = state.accountIdentity;
  if (!identity) {
    return "";
  }

  const linkedProviders = Array.isArray(identity.linked_providers) ? identity.linked_providers : [];
  const agreementUpdated = accountIdentityDateLabel(identity.agreement_updated_at);
  const languageParam = encodeURIComponent(state.language || "en");

  return `
    <section class="account-identity-card">
      <div class="account-identity-head">
        <div>
          <p class="account-section-label">${escapeHtml(ui().accountIdentityTitle)}</p>
          <p class="account-inline-note">${escapeHtml(ui().accountIdentityLegalCopy)}</p>
        </div>
        <span class="account-identity-status ${identity.required_agreements_completed ? "is-complete" : ""}">
          ${escapeHtml(identity.required_agreements_completed ? ui().accountIdentityAgreementsDoneLabel : ui().accountIdentityAgreementsPendingLabel)}
        </span>
      </div>
      <div class="account-identity-grid">
        <div class="account-identity-item">
          <span class="account-section-label">${escapeHtml(ui().accountIdentityProviderLabel)}</span>
          <strong>${escapeHtml(socialProviderLabel(identity.provider))}</strong>
        </div>
        <div class="account-identity-item">
          <span class="account-section-label">${escapeHtml(ui().accountIdentityLinkedProvidersLabel)}</span>
          <div class="account-provider-chip-row">
            ${linkedProviders.map((provider) => `
              <span class="account-provider-chip">${escapeHtml(socialProviderLabel(provider))}</span>
            `).join("") || `<span class="account-provider-chip">${escapeHtml(socialProviderLabel(identity.provider))}</span>`}
          </div>
        </div>
        <div class="account-identity-item">
          <span class="account-section-label">${escapeHtml(ui().accountIdentityPasswordLabel)}</span>
          <strong>${escapeHtml(identity.has_local_password ? ui().accountIdentityPasswordReadyLabel : ui().accountIdentityPasswordSocialOnlyLabel)}</strong>
        </div>
        <div class="account-identity-item">
          <span class="account-section-label">${escapeHtml(ui().accountIdentityVersionLabel)}</span>
          <strong>${escapeHtml(identity.agreement_version || "-")}</strong>
        </div>
        <div class="account-identity-item">
          <span class="account-section-label">${escapeHtml(ui().accountIdentityUpdatedLabel)}</span>
          <strong>${escapeHtml(agreementUpdated || "-")}</strong>
        </div>
        <div class="account-identity-item">
          <span class="account-section-label">${escapeHtml(ui().accountIdentityLegalTitle)}</span>
          <div class="account-legal-link-row">
            <a class="account-agreement-link" href="/legal/terms?lang=${languageParam}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().accountTermsLinkLabel)}</a>
            <a class="account-agreement-link" href="/legal/privacy?lang=${languageParam}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().accountPrivacyLinkLabel)}</a>
            <a class="account-agreement-link" href="/legal/investment-notice?lang=${languageParam}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().accountInvestmentNoticeLinkLabel)}</a>
          </div>
        </div>
      </div>
    </section>
  `;
}

function accountAgreementPayload(form) {
  return {
    terms_required: Boolean(form.querySelector('[name="terms_required"]')?.checked),
    privacy_required: Boolean(form.querySelector('[name="privacy_required"]')?.checked),
    investment_notice_required: Boolean(form.querySelector('[name="investment_notice_required"]')?.checked),
    marketing_optional: Boolean(form.querySelector('[name="marketing_optional"]')?.checked),
  };
}

function renderAccountAgreements() {
  const languageParam = encodeURIComponent(state.language || "en");
  return `
    <div class="account-agreements-shell">
      <div class="account-agreements-head">
        <span class="account-section-label">${escapeHtml(ui().accountAgreementsTitle)}</span>
        <p class="account-inline-note">${escapeHtml(ui().accountAgreementsRequiredHint)}</p>
      </div>
      <label class="account-check account-check-all">
        <input type="checkbox" data-agreement-all-required />
        <span>${escapeHtml(ui().accountAgreeAllRequiredLabel)}</span>
      </label>
      <div class="account-agreement-list">
        <div class="account-agreement-row">
          <label class="account-check">
            <input type="checkbox" name="terms_required" required />
            <span>${escapeHtml(ui().accountTermsRequiredLabel)}</span>
          </label>
          <a class="account-agreement-link" href="/legal/terms?lang=${languageParam}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().accountTermsLinkLabel)}</a>
        </div>
        <div class="account-agreement-row">
          <label class="account-check">
            <input type="checkbox" name="privacy_required" required />
            <span>${escapeHtml(ui().accountPrivacyRequiredLabel)}</span>
          </label>
          <a class="account-agreement-link" href="/legal/privacy?lang=${languageParam}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().accountPrivacyLinkLabel)}</a>
        </div>
        <div class="account-agreement-row">
          <label class="account-check">
            <input type="checkbox" name="investment_notice_required" required />
            <span>${escapeHtml(ui().accountInvestmentNoticeRequiredLabel)}</span>
          </label>
          <a class="account-agreement-link" href="/legal/investment-notice?lang=${languageParam}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().accountInvestmentNoticeLinkLabel)}</a>
        </div>
        <div class="account-agreement-row">
          <label class="account-check">
            <input type="checkbox" name="marketing_optional" />
            <span>${escapeHtml(ui().accountMarketingOptionalLabel)}</span>
          </label>
        </div>
      </div>
    </div>
  `;
}

function accountHasDeskPass(authorId) {
  return Boolean(authorId && state.account?.desk_passes?.includes(authorId));
}

function accountHasBundle(ticker) {
  const normalizedTicker = normalizeTicker(ticker);
  return Boolean(normalizedTicker && state.account?.bundle_tickers?.includes(normalizedTicker));
}

function accountHasAllPremiumSections(ticker) {
  const normalizedTicker = normalizeTicker(ticker);
  const unlocked = state.account?.unlocked_sections?.[normalizedTicker] || [];
  return Object.keys(SECTION_COSTS).every((sectionId) => unlocked.includes(sectionId));
}

function accountProductState(card) {
  if (!card) {
    return { purchased: false, label: "" };
  }

  if (card.id === "membership" && state.account?.membership_active) {
    return { purchased: true, label: ui().accountMembershipActiveLabel };
  }
  if (card.id === "alerts" && state.account?.alerts_active) {
    return { purchased: true, label: ui().accountAlertsActiveLabel };
  }
  if (card.id === "archive" && state.account?.archive_active) {
    return { purchased: true, label: ui().accountArchiveActiveLabel };
  }
  if (card.id === "follow-pass" && (state.account?.follow_pass_active || state.account?.membership_active)) {
    return { purchased: true, label: ui().accountFollowPassActiveLabel };
  }
  if (card.id === "desk-pass" && accountHasDeskPass(card.authorId)) {
    return { purchased: true, label: ui().accountDeskPassActiveLabel };
  }
  if (card.id === "bundle" && (accountHasBundle(card.ticker) || accountHasAllPremiumSections(card.ticker))) {
    return { purchased: true, label: ui().accountBundleActiveLabel };
  }

  return { purchased: false, label: "" };
}

function formatTransactionCredits(value) {
  const number = Number(value || 0);
  if (number > 0) {
    return `+${number}`;
  }
  return `${number}`;
}

function renderAccountMenu() {
  if (!el.accountMenu) {
    return;
  }

  setText(el.accountLabel, ui().accountLabel);

  if (!state.authenticated || !state.sessionUser || !state.account) {
    const pendingSocial = state.pendingSocialProfile;
    const socialProvider = pendingSocial?.provider || state.accountSocialProvider;
    const socialMode = Boolean(socialProvider && pendingSocial);
    const socialLabel = socialProviderLabel(socialProvider);
    const socialButtons = socialMode
      ? ""
      : `<div class="account-google-button-shell" data-google-signin-slot></div>`;
    setText(el.accountCurrent, ui().accountSignInLabel);
    el.accountMenu.innerHTML = `
      <div class="account-menu-shell">
        <div class="account-auth-hero">
          <div class="account-mode-row">
            <button type="button" class="account-mode-chip ${state.accountMenuMode === "login" ? "is-active" : ""}" data-account-mode="login">${escapeHtml(ui().accountSignInLabel)}</button>
            <button type="button" class="account-mode-chip ${state.accountMenuMode === "register" ? "is-active" : ""}" data-account-mode="register">${escapeHtml(ui().accountRegisterLabel)}</button>
          </div>
        </div>
        <div class="account-social-shell">
          <div class="account-social-grid">
            ${socialButtons}
          </div>
          ${socialMode ? `
            <div class="account-social-selected">
              <strong>${escapeHtml(uiText("accountSocialSelectedLabel", { provider: socialLabel }))}</strong>
              <button type="button" class="account-social-reset" data-account-social-reset>${escapeHtml(ui().accountSocialUseEmailLabel)}</button>
            </div>
          ` : ""}
        </div>
        <div class="account-divider" role="presentation"></div>
        <form class="account-form" data-account-form="${escapeHtml(socialMode ? "social" : state.accountMenuMode)}">
          ${socialMode ? `<input type="hidden" name="provider" value="${escapeHtml(socialProvider)}" />` : ""}
          ${socialMode ? `<input type="hidden" name="subject" value="${escapeHtml(pendingSocial?.subject || "")}" />` : ""}
          ${state.accountMenuMode === "register" || socialMode ? `
            <label class="field field-compact">
              <span>${escapeHtml(ui().accountNameLabel)}</span>
              <input name="name" type="text" maxlength="60" value="${escapeHtml(pendingSocial?.name || "")}" required />
            </label>
          ` : ""}
          <label class="field field-compact">
            <span>${escapeHtml(ui().accountEmailLabel)}</span>
            <input name="email" type="email" maxlength="160" value="${escapeHtml(pendingSocial?.email || "")}" ${socialMode && pendingSocial?.email ? "readonly" : ""} required />
          </label>
          ${socialMode ? "" : `
            <label class="field field-compact">
              <span>${escapeHtml(ui().accountPasswordLabel)}</span>
              <input name="password" type="password" minlength="8" required />
            </label>
          `}
          ${state.accountMenuMode === "register" || socialMode ? renderAccountAgreements() : ""}
          <button type="submit" class="cta cta-compact">${escapeHtml(
            socialMode
              ? uiText("accountSocialContinueLabel", { provider: socialLabel })
              : state.accountMenuMode === "register"
                ? ui().accountRegisterSubmitLabel
                : ui().accountSignInSubmitLabel,
          )}</button>
        </form>
        ${renderAdminAccessPanel()}
        <p class="account-menu-message" data-tone="${escapeHtml(state.accountMessageTone)}">${escapeHtml(state.accountMessage || ui().accountSignedOutHint)}</p>
      </div>
    `;
    window.requestAnimationFrame(() => {
      renderGoogleIdentityButton();
    });
    return;
  }

  ensureCommerceSelections();
  const transactions = Array.isArray(state.account.transactions) ? state.account.transactions.slice(0, 5) : [];
  const paymentRequests = Array.isArray(state.account.payment_requests) ? state.account.payment_requests.slice(0, 4) : [];
  const alertPreferences = state.account.alert_preferences || {};
  const creditPacks = Array.isArray(catalog().credit_packs) ? catalog().credit_packs : [];
  const paymentMethods = Array.isArray(catalog().payment_methods) ? catalog().payment_methods : [];
  const selectedMethodDetails = paymentMethodDetails(state.accountTopUpMethod);
  const membershipMeta = state.account.membership_active
    ? uiText("accountMembershipDaysLeftLabel", { count: state.account.membership_days_left || 0 })
    : ui().accountMembershipInactiveLabel;
  setText(el.accountCurrent, state.sessionUser.name);
  el.accountMenu.innerHTML = `
    <div class="account-menu-shell is-authenticated">
      <div class="account-summary-head">
        <div>
          <p class="account-summary-name">${escapeHtml(state.sessionUser.name)}</p>
          <p class="account-summary-email">${escapeHtml(state.sessionUser.email || "")}</p>
        </div>
        <button type="button" class="account-logout-btn" data-account-logout>${escapeHtml(ui().accountLogoutLabel)}</button>
      </div>
      ${renderAccountIdentityCard()}
      <div class="account-balance-card">
        <div class="account-balance-copy">
          <span class="account-balance-label">${escapeHtml(ui().accountCreditsLabel)}</span>
          <strong class="account-balance-value">${escapeHtml(String(state.account.credits_balance ?? 0))}</strong>
          <span class="account-inline-note">${escapeHtml(membershipMeta)}</span>
        </div>
        <button type="button" class="cta cta-compact account-balance-cta" data-commerce-open="credits">${escapeHtml(accountTopUpQuickLabel())}</button>
      </div>
      <form class="account-topup-form" data-payment-request-form>
        <div class="account-topup-head">
          <div>
            <p class="account-section-label">${escapeHtml(ui().accountTopUpLabel)}</p>
            <p class="account-menu-message">${escapeHtml(ui().accountTopUpDescription)}</p>
          </div>
          <span class="account-inline-note">${escapeHtml(ui().accountTopUpProcessingLabel)}</span>
        </div>
        <div class="account-pack-grid">
          ${creditPacks.map((pack) => `
            <label class="account-pack-option">
              <input type="radio" name="pack_id" value="${escapeHtml(pack.id)}" ${pack.id === state.accountTopUpPackId ? "checked" : ""} />
              <span class="account-pack-card">
                <strong>${escapeHtml(creditPackTitle(pack.id))}</strong>
                <span>${escapeHtml(formatKrw(pack.price_krw))}</span>
                <span>${escapeHtml(uiText("accountPackCreditsLabel", { credits: totalCreditsForPack(pack) }))}</span>
                <span>${escapeHtml(packBenefitLabel(pack))}</span>
              </span>
            </label>
          `).join("")}
        </div>
        <div class="account-method-grid">
          ${paymentMethods.map((method) => `
            <label class="account-method-option">
              <input type="radio" name="method" value="${escapeHtml(method.id)}" ${method.id === state.accountTopUpMethod ? "checked" : ""} />
              <span class="account-method-chip">${escapeHtml(paymentMethodLabel(method.id))}</span>
            </label>
          `).join("")}
        </div>
        ${selectedMethodDetails ? `
          <div class="account-payment-guide">
            <p class="account-section-label">${escapeHtml(ui().accountPaymentGuideLabel)}</p>
            <strong>${escapeHtml(selectedMethodDetails.title || "")}</strong>
            <div class="account-payment-guide-lines">
              ${(Array.isArray(selectedMethodDetails.lines) ? selectedMethodDetails.lines : []).map((line) => `
                <span>${escapeHtml(String(line || ""))}</span>
              `).join("")}
            </div>
            ${selectedMethodDetails.note ? `<p class="account-menu-message">${escapeHtml(selectedMethodDetails.note)}</p>` : ""}
          </div>
        ` : ""}
        <div class="account-topup-fields">
          <label class="field field-compact">
            <span>${escapeHtml(ui().accountDepositorLabel)}</span>
            <input name="depositor_name" type="text" maxlength="80" placeholder="${escapeHtml(ui().accountDepositorPlaceholder)}" />
          </label>
          <label class="field field-compact">
            <span>${escapeHtml(ui().accountPaymentNoteLabel)}</span>
            <input name="note" type="text" maxlength="180" placeholder="${escapeHtml(ui().accountPaymentNotePlaceholder)}" />
          </label>
        </div>
        <button type="submit" class="cta cta-compact">${escapeHtml(ui().accountTopUpSubmitLabel)}</button>
      </form>
      <div class="account-payments">
        <p class="account-section-label">${escapeHtml(ui().accountPaymentRequestsLabel)}</p>
        ${paymentRequests.length ? paymentRequests.map((request) => `
          <div class="account-request-row">
            <div>
              <strong>${escapeHtml(uiText("accountPaymentRequestTitle", { credits: request.credits + request.bonus_credits }))}</strong>
              <span>${escapeHtml([
                paymentMethodLabel(request.method),
                paymentRequestStatusLabel(request.status),
                formatKrw(request.amount_krw),
              ].join(" · "))}</span>
            </div>
            <span class="account-request-ref">${escapeHtml(request.reference)}</span>
          </div>
        `).join("") : `<p class="account-empty">${escapeHtml(ui().accountPaymentRequestsEmptyLabel)}</p>`}
      </div>
      <div class="account-entitlement-grid">
        <span class="account-entitlement-chip ${state.account.membership_active ? "is-active" : ""}">${escapeHtml(ui().accountMembershipLabel)}</span>
        <span class="account-entitlement-chip ${state.account.alerts_active ? "is-active" : ""}">${escapeHtml(ui().accountAlertsLabel)}</span>
        <span class="account-entitlement-chip ${state.account.archive_active ? "is-active" : ""}">${escapeHtml(ui().accountArchiveLabel)}</span>
        <span class="account-entitlement-chip ${state.account.desk_passes?.length ? "is-active" : ""}">${escapeHtml(uiText("accountDeskPassCountLabel", { count: state.account.desk_passes?.length || 0 }))}</span>
      </div>
      <form class="account-alerts-form" data-alert-preferences-form>
        <p class="account-section-label">${escapeHtml(ui().accountAlertPreferencesLabel)}</p>
        <label class="account-check"><input type="checkbox" name="buy" ${alertPreferences.buy ? "checked" : ""} /> <span>${escapeHtml(ui().entryFilterLabel)}</span></label>
        <label class="account-check"><input type="checkbox" name="watch" ${alertPreferences.watch ? "checked" : ""} /> <span>${escapeHtml(ui().watchFilterLabel)}</span></label>
        <label class="account-check"><input type="checkbox" name="sell" ${alertPreferences.sell ? "checked" : ""} /> <span>${escapeHtml(ui().exitFilterLabel)}</span></label>
        <label class="account-check"><input type="checkbox" name="research" ${alertPreferences.research ? "checked" : ""} /> <span>${escapeHtml(ui().accountResearchAlertsLabel)}</span></label>
        <button type="submit" class="cta cta-compact">${escapeHtml(ui().accountSaveAlertsLabel)}</button>
      </form>
      <div class="account-transactions">
        <p class="account-section-label">${escapeHtml(ui().accountTransactionsLabel)}</p>
        ${transactions.length ? transactions.map((transaction) => `
          <div class="account-transaction-row">
            <div>
              <strong>${escapeHtml(transaction.title || ui().accountTransactionFallback)}</strong>
              <span>${escapeHtml(formatAge(threadAgeMinutes({ created_at: transaction.created_at })))}</span>
            </div>
            <span class="account-transaction-delta">${escapeHtml(formatTransactionCredits(transaction.credits_delta))}</span>
          </div>
        `).join("") : `<p class="account-empty">${escapeHtml(ui().accountTransactionsEmptyLabel)}</p>`}
      </div>
      ${renderAdminAccessPanel()}
      <p class="account-menu-message" data-tone="${escapeHtml(state.accountMessageTone)}">${escapeHtml(state.accountMessage || ui().accountSignedInHint)}</p>
    </div>
  `;
}

async function syncCommunityState({ rerender = false } = {}) {
  const payload = await requestJson(`/api/platform/community?viewer_id=${encodeURIComponent(state.viewerId)}`, {
    method: "GET",
    headers: {},
  });
  state.communityPosts = Array.isArray(payload.posts) ? payload.posts : [];
  state.followingIds = new Set(Array.isArray(payload.following_ids) ? payload.following_ids : []);
  state.followerCounts = payload.follower_counts || {};
  state.followDataVersion += 1;
  invalidateThreadCaches();
  if (rerender) {
    renderApp();
  }
}

function authorById(authorId) {
  return state.blueprint.authors.find((author) => author.id === authorId) || null;
}

function authorForThread(thread) {
  return authorById(thread.author_id) || {
    id: thread.author_id || "guest-writer",
    name: thread.author || "Guest Writer",
    handle: thread.handle || "@guest",
    avatar: thread.avatar || "GW",
    followers: "0",
    following: "0",
    posts: "0",
    topics: [],
    copy: {
      en: { headline: "", bio: "" },
      ko: { headline: "", bio: "" },
    },
  };
}

function threadAgeMinutes(thread) {
  if (thread.created_at) {
    const created = Date.parse(thread.created_at);
    if (!Number.isNaN(created)) {
      return Math.max(0, Math.round((Date.now() - created) / 60000));
    }
  }
  return thread.age_minutes ?? 0;
}

function allThreads() {
  if (state.allThreadsCacheVersion === state.threadDataVersion) {
    return state.allThreadsCache;
  }
  state.allThreadsCache = [...state.communityPosts, ...state.blueprint.threads].sort(
    (left, right) => threadAgeMinutes(left) - threadAgeMinutes(right)
  );
  state.allThreadsCacheVersion = state.threadDataVersion;
  return state.allThreadsCache;
}

function latestByKind(kind) {
  return allThreads().find((thread) => thread.kind === kind) || null;
}

function featuredThread() {
  return latestByKind("buy") || allThreads()[0] || null;
}

function latestExitThread() {
  return latestByKind("sell") || null;
}

function topSavedThread() {
  return [...allThreads()].sort(
    (left, right) => parseCompactMetric(right.metrics.saves) - parseCompactMetric(left.metrics.saves)
  )[0] || null;
}

function activeLiveCount() {
  return allThreads().filter((thread) => thread.kind !== "sell").length;
}

function activeWatch() {
  return state.blueprint.watchlist.find((item) => item.stage === "Hot") || state.blueprint.watchlist[0];
}

function documentedExitCount() {
  return allThreads().filter((thread) => thread.kind === "sell").length;
}

function visibleThreads() {
  const query = state.searchQuery.trim().toLowerCase();
  if (state.filterKind === "all" && !state.followingOnly && !query) {
    return allThreads();
  }

  const cacheKey = [
    state.threadDataVersion,
    state.followDataVersion,
    state.filterKind,
    state.followingOnly ? 1 : 0,
    state.language,
    query,
  ].join("|");

  if (state.visibleThreadsCacheKey === cacheKey) {
    return state.visibleThreadsCache;
  }

  const nextVisibleThreads = allThreads().filter((thread) => {
    if (state.filterKind !== "all" && thread.kind !== state.filterKind) {
      return false;
    }

    if (state.followingOnly && !state.followingIds.has(thread.author_id)) {
      return false;
    }

    if (!query) {
      return true;
    }

    const copy = copyFor(thread);
    const author = authorForThread(thread);
    const haystack = [
      thread.ticker,
      thread.company,
      thread.kind,
      author.name,
      author.handle,
      thread.tags.join(" "),
      copy.headline || "",
      copy.summary || "",
      (copy.beats || []).join(" "),
    ].join(" ").toLowerCase();

    return haystack.includes(query);
  });

  state.visibleThreadsCacheKey = cacheKey;
  state.visibleThreadsCache = nextVisibleThreads;
  return nextVisibleThreads;
}

function feedBatchSize() {
  return state.isMobile ? 14 : 20;
}

function resetFeedWindow() {
  state.feedVisibleCount = feedBatchSize();
}

function extendFeedWindow() {
  const total = visibleThreads().length;
  if (!total) {
    state.feedVisibleCount = feedBatchSize();
    return;
  }
  state.feedVisibleCount = Math.min(
    total,
    Math.max(state.feedVisibleCount || 0, feedBatchSize()) + feedBatchSize(),
  );
}

function setupFeedLoadMoreObserver() {
  if (feedLoadObserver) {
    feedLoadObserver.disconnect();
    feedLoadObserver = null;
  }

  const trigger = document.querySelector("[data-feed-load-more]");
  if (!trigger || !("IntersectionObserver" in window)) {
    return;
  }

  feedLoadObserver = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) {
      return;
    }
    feedLoadObserver?.disconnect();
    feedLoadObserver = null;
    window.requestAnimationFrame(() => {
      extendFeedWindow();
      renderThreads();
    });
  }, {
    rootMargin: "220px 0px",
  });

  feedLoadObserver.observe(trigger);
}

function worldNewsItems() {
  return Array.isArray(state.blueprint?.world_news) ? state.blueprint.world_news : [];
}

function ensureActiveWorldNews() {
  const items = worldNewsItems();
  if (!items.length) {
    state.activeWorldNewsId = "";
    return;
  }
  if (!items.some((item) => item.id === state.activeWorldNewsId)) {
    state.activeWorldNewsId = items[0].id;
  }
}

function activeWorldNewsItem() {
  const items = worldNewsItems();
  return items.find((item) => item.id === state.activeWorldNewsId) || items[0] || null;
}

function storyGroups() {
  const groups = new Map();

  visibleThreads().forEach((thread) => {
    const current = groups.get(thread.ticker) || [];
    current.push(thread);
    groups.set(thread.ticker, current);
  });

  return [...groups.values()]
    .filter((group) => group.length > 1)
    .map((group) => group.sort((left, right) => threadAgeMinutes(left) - threadAgeMinutes(right)))
    .sort((left, right) => threadAgeMinutes(left[0]) - threadAgeMinutes(right[0]));
}

function metricValue(thread, label) {
  return thread.price_map.find((item) => item.label === label)?.value || "";
}

function parseReturnValue(thread) {
  return Number.parseFloat(metricValue(thread, "Return").replace(/[^\d.-]/g, "")) || 0;
}

function formatAge(minutes) {
  if (minutes < 1) {
    return ui().timeJustNow;
  }
  if (minutes < 60) {
    return uiText("timeMinutesAgo", { count: minutes });
  }
  if (minutes < 1440) {
    const hours = Math.round(minutes / 60);
    return uiText("timeHoursAgo", { count: hours });
  }
  const days = Math.round(minutes / 1440);
  return uiText("timeDaysAgo", { count: days });
}

function localizeMetricLabel(label) {
  const mapping = {
    Followers: ui().metricFollowersLabel,
    Following: ui().metricFollowingLabel,
    Posts: ui().metricPostsLabel,
    "Documented threads": ui().metricDocumentedThreadsLabel,
    "Exit recaps": ui().metricExitRecapsLabel,
    "Closed trades": ui().metricClosedTradesLabel,
    "Avg hold": ui().metricAvgHoldLabel,
  };
  return mapping[label] || label;
}

function localizeStage(stage) {
  const mapping = {
    Arming: ui().stageArmingLabel,
    Coiling: ui().stageCoilingLabel,
    Hot: ui().stageHotLabel,
  };
  return mapping[stage] || stage;
}

function localizePriceLabel(label) {
  const mapping = {
    Entry: ui().priceLabelEntry,
    Risk: ui().priceLabelRisk,
    Focus: ui().priceLabelFocus,
    Exit: ui().priceLabelExit,
    Return: ui().priceLabelReturn,
    Hold: ui().priceLabelHold,
    Watch: ui().priceLabelWatch,
    Trigger: ui().priceLabelTrigger,
  };
  return mapping[label] || label;
}

function contributionTypeLabel(value) {
  const mapping = {
    question: ui().contributionQuestionLabel,
    counter: ui().contributionCounterLabel,
    evidence: ui().contributionEvidenceLabel,
  };
  return mapping[value] || ui().contributionNoteLabel;
}

function rankingPeriodLabel(metric) {
  if (metric === "recent_return") {
    return ui().rankingPeriodRecentOpen;
  }
  if (metric === "win_rate") {
    return ui().rankingPeriodClosedOnly;
  }
  return ui().rankingPeriodClosedOpen;
}

function leaderboardBasisCopy(author) {
  const performance = authorPerformance(author);
  if (performance.open_positions > 0) {
    return uiText("leaderboardBasisWithOpen", {
      closed: performance.closed_trades,
      avgHold: performance.avg_hold,
      open: performance.open_positions,
      openReturn: signedPercent(performance.open_return),
    });
  }
  return uiText("leaderboardBasisClosedOnly", {
    closed: performance.closed_trades,
    avgHold: performance.avg_hold,
  });
}

function latestUpdateCopy() {
  const recent = featuredThread();
  if (!recent) {
    return ui().latestUpdateLive;
  }
  return uiText("latestUpdateAt", { age: formatAge(threadAgeMinutes(recent)) });
}

function kindLabel(kind) {
  if (kind === "buy") {
    return ui().entryFilterLabel;
  }
  if (kind === "sell") {
    return ui().exitFilterLabel;
  }
  return ui().watchFilterLabel;
}

function kindChipClass(kind) {
  if (kind === "buy") {
    return "chip-live";
  }
  if (kind === "sell") {
    return "chip-exit";
  }
  return "chip-watch";
}

function lineColor(kind) {
  if (kind === "buy") {
    return "#1f7467";
  }
  if (kind === "sell") {
    return "#964b45";
  }
  return "#9f7b1a";
}

function triggerLabel() {
  return ui().nextTriggerLabel;
}

function currentComposerLabels() {
  const kind = el.composerKind.value || "buy";
  if (kind === "sell") {
    return ["Entry", "Exit", "Return"];
  }
  if (kind === "watch") {
    return ["Watch", "Trigger", "Focus"];
  }
  return ["Entry", "Risk", "Focus"];
}

function defaultComposerMessage() {
  return ui().composerHintBody;
}

function updateComposerLevelLabels() {
  const [a, b, c] = currentComposerLabels();
  el.composerLevelALabel.textContent = `${ui().composerLevelPrefix} ${localizePriceLabel(a)}`;
  el.composerLevelBLabel.textContent = `${ui().composerLevelPrefix} ${localizePriceLabel(b)}`;
  el.composerLevelCLabel.textContent = `${ui().composerLevelPrefix} ${localizePriceLabel(c)}`;
  el.composerLevelA.placeholder = kindExample(a);
  el.composerLevelB.placeholder = kindExample(b);
  el.composerLevelC.placeholder = kindExample(c);
}

function kindExample(label) {
  const mapping = {
    Entry: "$876.20",
    Risk: "$842.00",
    Focus: "$924.00",
    Exit: "$948.60",
    Return: "+8.3%",
    Watch: "$412.50",
    Trigger: "$416.10",
  };
  return mapping[label] || "";
}

function sparklineSvg(points, color, height = 84) {
  sparklineId += 1;
  const data = points?.length ? points : [10, 20, 15, 28, 24, 36];
  const width = 240;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = Math.max(max - min, 1);
  const gradientId = `spark-${sparklineId}`;
  const stepX = width / Math.max(data.length - 1, 1);
  const path = data.map((point, index) => {
    const x = index * stepX;
    const y = height - (((point - min) / range) * (height - 14)) - 7;
    return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");
  const area = `${path} L ${width} ${height} L 0 ${height} Z`;

  return `
    <svg class="sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="${gradientId}" x1="0%" x2="0%" y1="0%" y2="100%">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.18"></stop>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"></stop>
        </linearGradient>
      </defs>
      <path d="${area}" fill="url(#${gradientId})"></path>
      <path d="${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
    </svg>
  `;
}

function buildProofPoints() {
  const delayPoint = state.blueprint.proof_points[0];
  const exitPoint = state.blueprint.proof_points[1];
  const returnPoint = state.blueprint.proof_points[2];

  return [
    {
      value: delayPoint?.value || "4m",
      label: ui().proofMedianDelayLabel,
    },
    {
      value: String(activeLiveCount()),
      label: ui().proofActiveLiveSignalsLabel,
    },
    {
      value: exitPoint?.value || "97",
      label: ui().proofClosedExitRecapLabel,
    },
    {
      value: returnPoint?.value || "62%",
      label: ui().proofVisitorsReturnLabel,
    },
  ];
}

function filterOptions() {
  return [
    { id: "all", label: ui().allFilterLabel },
    { id: "buy", label: ui().entryFilterLabel },
    { id: "sell", label: ui().exitFilterLabel },
    { id: "watch", label: ui().watchFilterLabel },
  ];
}

function scopeOptions() {
  return [
    { id: "all", label: ui().allWritersLabel, active: !state.followingOnly, locked: false, badge: "" },
    {
      id: "following",
      label: ui().followingOnlyLabel,
      active: state.followingOnly,
      locked: !hasFollowAccess(),
      badge: !hasFollowAccess() ? uiText("followingOnlyUnlockHint", { credits: followPassCost() }) : "",
    },
  ];
}

function buildRules() {
  return [
    ui().rulesItemOne,
    ui().rulesItemTwo,
    ui().rulesItemThree,
  ];
}

function quickGuideSteps() {
  return [
    {
      step: "01",
      title: ui().quickStepOneTitle,
      body: ui().quickStepOneBody,
      link: "#thread-feed",
      cta: ui().quickStepOneCta,
    },
    {
      step: "02",
      title: ui().quickStepTwoTitle,
      body: ui().quickStepTwoBody,
      link: "#thread-feed",
      cta: ui().quickStepTwoCta,
    },
    {
      step: "03",
      title: ui().quickStepThreeTitle,
      body: ui().quickStepThreeBody,
      link: "#archive-list",
      cta: ui().quickStepThreeCta,
    },
  ];
}

function browseDestinations() {
  const exitCount = allThreads().filter((thread) => thread.kind === "sell").length;

  return [
    {
      value: String(state.blueprint.authors.length),
      label: ui().browseTradersCountLabel,
      title: ui().browseTradersTitle,
      body: ui().browseTradersBody,
      link: "#thread-feed",
      cta: ui().browseTradersCta,
    },
    {
      value: String(activeLiveCount()),
      label: ui().browseLiveCountLabel,
      title: ui().browseLiveTitle,
      body: ui().browseLiveBody,
      link: "#thread-feed",
      cta: ui().browseLiveCta,
    },
    {
      value: String(exitCount),
      label: ui().browseArchiveCountLabel,
      title: ui().browseArchiveTitle,
      body: ui().browseArchiveBody,
      link: "#archive-list",
      cta: ui().browseArchiveCta,
    },
    {
      value: String(state.blueprint.authors.length),
      label: ui().browseWritersCountLabel,
      title: ui().browseWritersTitle,
      body: ui().browseWritersBody,
      link: "#composer-shell",
      cta: ui().browseWritersCta,
    },
  ];
}

function briefText(value, maxLength = 112) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }

  const clipped = normalized.slice(0, maxLength - 1);
  const boundary = clipped.lastIndexOf(" ");
  const safeClip = boundary > 60 ? clipped.slice(0, boundary) : clipped;
  return `${safeClip.trim()}…`;
}

function threadMainPoint(thread, copy) {
  if (thread.kind === "sell") {
    return briefText(copy.beats?.[0] || copy.summary || copy.footer || "");
  }
  if (thread.kind === "watch") {
    return briefText(copy.beats?.[0] || copy.summary || copy.footer || "");
  }
  return briefText(copy.beats?.[0] || copy.summary || copy.footer || "");
}

function threadReasonLabel(kind) {
  if (kind === "sell") {
    return ui().threadSellReasonLabel;
  }
  if (kind === "watch") {
    return ui().threadWatchReasonLabel;
  }
  return ui().threadBuyReasonLabel;
}

function threadActionLabel(kind) {
  if (kind === "sell") {
    return ui().threadExitLineLabel;
  }
  if (kind === "watch") {
    return ui().threadTriggerLineLabel;
  }
  return ui().threadEntryLineLabel;
}

function threadActionValue(thread) {
  if (thread.kind === "sell") {
    return metricValue(thread, "Exit") || metricValue(thread, "Return") || "--";
  }
  if (thread.kind === "watch") {
    return metricValue(thread, "Trigger") || metricValue(thread, "Watch") || "--";
  }
  return metricValue(thread, "Entry") || metricValue(thread, "Focus") || metricValue(thread, "Trigger") || "--";
}

function localizedHoldValue(value) {
  if (!value) {
    return "--";
  }
  if (state.language.startsWith("ko")) {
    return String(value).replace(/(\d+)\s*d\b/i, "$1일");
  }
  return value;
}

function threadActionNote(thread) {
  if (thread.kind === "sell") {
    return uiText("threadSellActionNote", {
      returnValue: metricValue(thread, "Return") || "--",
      hold: localizedHoldValue(metricValue(thread, "Hold") || "--"),
    });
  }
  if (thread.kind === "watch") {
    return uiText("threadWatchActionNote", {
      watch: metricValue(thread, "Watch") || metricValue(thread, "Trigger") || "--",
    });
  }
  return uiText("threadBuyActionNote", {
    risk: metricValue(thread, "Risk") || "--",
  });
}

function storyMarketLabel(thread) {
  return `NASDAQ: ${thread.ticker}`;
}

function storyTopBadge(thread) {
  if (thread.kind === "sell") {
    return `RET ${metricValue(thread, "Return") || "--"}`;
  }
  if (thread.kind === "watch") {
    return `CHK ${metricValue(thread, "Trigger") || metricValue(thread, "Watch") || "--"}`;
  }
  return `RISK ${metricValue(thread, "Risk") || "--"}`;
}

function storyDisplayName(thread) {
  return thread.company || thread.ticker;
}

function storyPriceValue(thread) {
  return threadActionValue(thread) || "--";
}

function storyDeltaValue(thread) {
  if (thread.kind === "sell") {
    return `${metricValue(thread, "Return") || "--"} closed`;
  }
  if (thread.kind === "watch") {
    return ui().watchFilterLabel;
  }

  const author = authorForThread(thread);
  const performance = authorPerformance(author);
  if (performance.open_thread_ids.includes(thread.id)) {
    return `${signedPercent(openReturnForThread(thread))} live`;
  }
  return ui().entryFilterLabel;
}

function storyActionPrimary(thread) {
  if (thread.kind === "sell") {
    return "SELL";
  }
  if (thread.kind === "watch") {
    return "WATCH";
  }
  return "BUY";
}

function storyActionSecondary(thread) {
  if (thread.kind === "sell") {
    return "LOG";
  }
  if (thread.kind === "watch") {
    return "VIEW";
  }
  return "SELL";
}

function threadStrategyReason(thread, author) {
  const strategy = strategyFor(author);
  if (!strategy.trigger && !strategy.focus) {
    return "";
  }

  if (thread.kind === "sell") {
    return briefText(strategy.risk || strategy.trigger || strategy.focus || "");
  }
  if (thread.kind === "watch") {
    return briefText(strategy.focus || strategy.trigger || "");
  }
  return briefText(strategy.trigger || strategy.focus || "");
}

function storyProgress(group) {
  const kinds = new Set(group.map((thread) => thread.kind));
  const hasWatch = kinds.has("watch");
  const hasBuy = kinds.has("buy");
  const hasSell = kinds.has("sell");

  return [
    { label: ui().storyStageSetupLabel, active: hasWatch || hasBuy || hasSell },
    { label: ui().storyStageLiveLabel, active: hasBuy || hasSell },
    { label: ui().storyStageClosedLabel, active: hasSell },
  ];
}

function authorInline(author) {
  const following = state.followingIds.has(author.id);
  return `
    <div class="author-inline">
      <span class="author-inline-avatar">${escapeHtml(author.avatar)}</span>
      <div>
        <strong class="author-inline-name">${escapeHtml(author.name)}</strong>
        <span class="author-inline-handle">${escapeHtml(author.handle)}</span>
      </div>
    </div>
    <button type="button" class="follow-btn ${following ? "is-following" : ""}" data-follow-author="${escapeHtml(author.id)}">
      ${following ? escapeHtml(ui().followingButtonLabel) : escapeHtml(ui().followButtonLabel)}
    </button>
  `;
}

function buildPriceMap(kind, values) {
  const [a, b, c] = values;
  if (kind === "sell") {
    return [
      { label: "Entry", value: a || "$0.00" },
      { label: "Exit", value: b || "$0.00" },
      { label: "Return", value: c || "+0.0%" },
    ];
  }
  if (kind === "watch") {
    return [
      { label: "Watch", value: a || "$0.00" },
      { label: "Trigger", value: b || "$0.00" },
      { label: "Focus", value: c || "Watching" },
    ];
  }
  return [
    { label: "Entry", value: a || "$0.00" },
    { label: "Risk", value: b || "$0.00" },
    { label: "Focus", value: c || "$0.00" },
  ];
}

function buildReturnRadarItems() {
  const latestLive = featuredThread();
  const latestExit = latestExitThread();
  const recentLeader = authorRanking("recent_return")[0];
  const saved = topSavedThread();

  return [
    {
      kicker: ui().returnRadarLiveNowLabel,
      title: latestLive
        ? uiText("returnRadarLiveTitle", { ticker: latestLive.ticker })
        : ui().returnRadarWaitingTitle,
      meta: latestLive
        ? formatAge(threadAgeMinutes(latestLive))
        : ui().returnRadarSoonLabel,
      href: latestLive ? `#thread-${latestLive.id}` : "#thread-feed",
    },
    {
      kicker: ui().returnRadarFreshExitLabel,
      title: latestExit
        ? uiText("returnRadarExitTitle", {
          ticker: latestExit.ticker,
          value: metricValue(latestExit, "Return"),
        })
        : ui().returnRadarNoExitLabel,
      meta: latestExit ? formatAge(threadAgeMinutes(latestExit)) : ui().returnRadarPendingLabel,
      href: latestExit ? `#thread-${latestExit.id}` : "#thread-feed",
    },
    {
      kicker: ui().returnRadarRankMoverLabel,
      title: recentLeader
        ? uiText("returnRadarLeaderTitle", {
          name: recentLeader.name,
          value: signedPercent(performanceValue(recentLeader, "recent_return")),
        })
        : ui().returnRadarNoRankMoverLabel,
      meta: recentLeader ? ui().returnRadarLast30DaysLabel : ui().returnRadarPendingLabel,
      href: "#thread-feed",
    },
    {
      kicker: ui().returnRadarSavedMostLabel,
      title: saved
        ? uiText("returnRadarSavedTitle", { ticker: saved.ticker })
        : ui().returnRadarSavedMostFallback,
      meta: saved ? `${saved.metrics.saves} ${ui().savesLabel}` : ui().returnRadarPendingLabel,
      href: saved ? `#thread-${saved.id}` : "#thread-feed",
    },
  ];
}

function renderResearchHeroStrip() {
  if (!el.researchHeroStrip || !state.blueprint) {
    return;
  }

  if (state.aiRoundtableHasAsked) {
    el.researchHeroStrip.innerHTML = "";
    return;
  }

  const live = featuredThread();
  const watched = (state.blueprint.watchlist || []).slice(0, 3);
  const examples = [];
  const seen = new Set();

  const addExample = (ticker, note) => {
    const normalized = normalizeTicker(ticker);
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    examples.push({
      ticker: normalized,
      note,
      question: defaultRoundtableQuestionForTicker(normalized),
    });
  };

  addExample(live?.ticker, ui().researchHeroExampleLiveLabel);
  watched.forEach((item) => addExample(item.ticker, ui().researchHeroExampleWatchLabel));
  addExample(roundtableConfig().defaults?.ticker, ui().researchHeroExampleCoreLabel);

  el.researchHeroStrip.innerHTML = `
    <section class="research-hero-intro">
      <div class="research-hero-copy">
        <span class="research-hero-kicker">${escapeHtml(ui().researchHeroKicker)}</span>
        <h3>${escapeHtml(ui().researchHeroTitle)}</h3>
        <p>${escapeHtml(ui().researchHeroBody)}</p>
      </div>
      <div class="research-hero-proof">
        <span class="metric-pill"><strong>${escapeHtml(ui().researchHeroProofFreeValue)}</strong>${escapeHtml(ui().researchHeroProofFreeLabel)}</span>
        <span class="metric-pill"><strong>${escapeHtml(ui().researchHeroProofPaidValue)}</strong>${escapeHtml(ui().researchHeroProofPaidLabel)}</span>
        <span class="metric-pill"><strong>${escapeHtml(activeLiveCount())}</strong>${escapeHtml(ui().researchHeroProofLiveLabel)}</span>
      </div>
      <div class="research-hero-examples">
        ${examples.slice(0, 4).map((item) => `
          <button
            type="button"
            class="research-hero-chip"
            data-ai-question="${escapeHtml(item.question)}"
            data-hot-ticker="${escapeHtml(item.ticker)}"
          >
            <span class="research-hero-chip-kicker">${escapeHtml(item.note)}</span>
            <strong>${escapeHtml(item.ticker)}</strong>
          </button>
        `).join("")}
      </div>
    </section>
  `;
}

function roundtableSplitMarkup(stanceBreakdown) {
  const total = stanceBreakdown.reduce((sum, item) => sum + item.count, 0) || 1;
  return `
    <div class="research-split-meter">
      ${stanceBreakdown.map((item) => `
        <div
          class="research-split-segment ${roundtableToneClass(item.tone)}"
          style="width:${((item.count / total) * 100).toFixed(1)}%"
          title="${escapeHtml(`${item.label} ${item.count}`)}"
        ></div>
      `).join("")}
    </div>
    <div class="research-split-legend">
      ${stanceBreakdown.map((item) => `
        <span class="status-chip ${roundtableToneClass(item.tone)}">${escapeHtml(String(item.count))} ${escapeHtml(item.label)}</span>
      `).join("")}
    </div>
  `;
}

function applyStaticTranslations() {
  document.documentElement.lang = state.language;
  document.documentElement.dir = isRtlLanguage(state.language) ? "rtl" : "ltr";
  document.title = state.blueprint.meta.title;

  setText(el.brandLabel, ui().brand);
  setText(el.brandKicker, ui().brandKicker);
  setText(el.topbarCta, ui().topbarCta);
  setText(el.languageLabel, ui().languageLabel);
  if (el.languageMenu) {
    el.languageMenu.setAttribute("aria-label", ui().languageMenuAriaLabel);
  }
  if (el.languageToggle) {
    el.languageToggle.setAttribute("aria-label", ui().languageLabel);
  }
  setText(el.activeSignalsTitle, ui().activeSignalsTitle);
  setText(el.trendingSignalsTitle, ui().trendingSignalsTitle);
  setText(el.trendingSignalsLink, ui().viewAllLabel);
  setText(el.publicResearchThreadsTitle, ui().publicResearchThreadsTitle);
  setText(el.navFeedLabel, ui().tabFeedLabel);
  setText(el.navSignalsLabel, ui().navSignalsLabel);
  setText(el.navRankLabel, ui().navRankLabel);
  setText(el.navAskAiLabel, ui().tabResearchLabel);
  setText(el.subnavCompare, ui().tabResearchLabel);
  setText(el.subnavFeed, ui().tabFeedLabel);
  setText(el.communityStageKicker, ui().communityStageKicker);
  setText(el.quickGuideKicker, ui().quickGuideKicker);
  setText(el.quickGuideTitle, ui().quickGuideTitle);
  setText(el.quickGuideDescription, ui().quickGuideDescription);
  setText(el.browseKicker, ui().browseKicker);
  setText(el.browseTitle, ui().browseTitle);
  setText(el.browseDescription, ui().browseDescription);
  setText(el.aiRoundtableKicker, ui().aiRoundtableKicker);
  setText(el.aiRoundtableTitle, ui().aiRoundtableTitle);
  setText(el.aiRoundtableDescription, ui().aiRoundtableDescription);
  setText(el.researchStageKicker, ui().researchStageKicker);
  setText(el.researchStageTitle, ui().researchStageTitle);
  setText(el.researchStageDescription, ui().researchStageDescription);
  setText(el.feedStageKicker, ui().feedStageKicker);
  setText(el.feedStageTitle, ui().feedStageTitle);
  setText(el.feedStageDescription, ui().feedStageDescription);
  setText(el.aiRoundtableTickerLabel, ui().aiRoundtableTickerLabel);
  setText(el.aiRoundtableQuestionLabel, ui().aiRoundtableQuestionLabel);
  setText(el.aiRoundtableSubmit, ui().aiRoundtableSubmitLabel);
  setText(el.returnRadarTitle, ui().returnRadarTitle);
  setText(el.communityStageTitle, ui().communityStageTitle);
  setText(el.communityStageDescription, ui().communityStageDescription);
  setText(el.composerKicker, ui().composerKicker);
  setText(el.composerTitle, ui().composerTitle);
  setText(el.composerDescription, ui().composerDescription);
  setText(el.composerToggleChip, ui().composerToggleLabel);
  setText(el.composerAuthorLabel, ui().composerAuthorLabel);
  setText(el.composerKindLabel, ui().composerKindLabel);
  setText(el.composerTickerLabel, ui().composerTickerLabel);
  setText(el.composerCompanyLabel, ui().composerCompanyLabel);
  setText(el.composerHeadlineLabel, ui().composerHeadlineLabel);
  setText(el.composerSummaryLabel, ui().composerSummaryLabel);
  setText(el.composerTagsLabel, ui().composerTagsLabel);
  setText(el.composerSubmit, ui().composerSubmitLabel);
  setText(el.leaderboardKicker, ui().leaderboardKicker);
  setText(el.leaderboardTitle, ui().leaderboardTitle);
  setText(el.leaderboardDescription, ui().leaderboardDescription);
  setText(el.authorsKicker, ui().authorsKicker);
  setText(el.authorsTitle, ui().authorsTitle);
  setText(el.feedKicker, ui().feedKicker);
  setText(el.feedTitle, ui().feedTitle);
  setText(el.searchLabel, ui().searchLabel);
  setText(el.globalSearchSubmit, ui().globalSearchSubmitLabel);
  setPlaceholder(el.threadSearch, ui().topbarSearchResearchPlaceholder);
  setText(el.storiesKicker, ui().storiesKicker);
  setText(el.storiesTitle, ui().storiesTitle);
  setText(el.storiesDescription, ui().storiesDescription);
  setText(el.archiveLogKicker, ui().archiveLogKicker);
  setText(el.archiveLogTitle, ui().archiveLogTitle);
  setText(el.watchKicker, ui().watchKicker);
  setText(el.watchTitle, ui().watchTitle);
  setText(el.archiveKicker, ui().archiveKicker);
  setText(el.archiveTitle, ui().archiveTitle);
  setText(el.rulesKicker, ui().rulesKicker);
  setText(el.rulesTitle, ui().rulesTitle);
  setText(el.playbookKicker, ui().playbookKicker);
  setText(el.playbookTitle, ui().playbookTitle);
  setText(el.loopsKicker, ui().loopsKicker);
  setText(el.loopsTitle, ui().loopsTitle);
  applyTheme();
}

function renderLanguageOptions() {
  el.languageSelect.innerHTML = "";
  el.languageMenu.innerHTML = "";
  const currentLanguage = SUPPORTED_LANGUAGES.find((language) => language.code === state.language) || SUPPORTED_LANGUAGES[0];
  if (el.languageMenu) {
    el.languageMenu.setAttribute("aria-label", ui().languageMenuAriaLabel);
  }

  SUPPORTED_LANGUAGES.forEach((language) => {
    const option = document.createElement("option");
    option.value = language.code;
    option.textContent = language.label;
    el.languageSelect.append(option);

    const button = document.createElement("button");
    button.type = "button";
    button.className = `language-option ${state.language === language.code ? "is-active" : ""}`;
    button.dataset.languageCode = language.code;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(state.language === language.code));
    button.textContent = language.label;
    el.languageMenu.append(button);
  });
  el.languageSelect.value = state.language;
  if (el.languageCurrent) {
    el.languageCurrent.textContent = currentLanguage.label;
  }
  if (el.languageToggle) {
    el.languageToggle.setAttribute("aria-expanded", "false");
  }
  if (el.languageDropdown) {
    el.languageDropdown.classList.remove("is-open");
  }
}

function renderContributionTypeRow() {
  el.contributionTypeRow.innerHTML = contributionTypes().map((item) => `
    <button
      type="button"
      class="contribution-chip ${state.contributionType === item.id ? "is-active" : ""}"
      data-contribution-type="${escapeHtml(item.id)}"
      aria-pressed="${state.contributionType === item.id}"
      title="${escapeHtml(item.hint)}"
    >
      ${escapeHtml(item.label)}
    </button>
  `).join("");
}

function renderComposerControls() {
  const selectedAuthor = el.composerAuthor.value || state.blueprint.authors[0]?.id || "";
  const selectedKind = el.composerKind.value || "buy";

  el.composerAuthor.innerHTML = state.blueprint.authors.map((author) => `
    <option value="${escapeHtml(author.id)}">${escapeHtml(author.name)} ${escapeHtml(author.handle)}</option>
  `).join("");

  el.composerKind.innerHTML = [
    { id: "buy", label: ui().entryFilterLabel },
    { id: "sell", label: ui().exitFilterLabel },
    { id: "watch", label: ui().watchFilterLabel },
  ].map((option) => `<option value="${option.id}">${escapeHtml(option.label)}</option>`).join("");

  el.composerAuthor.value = selectedAuthor;
  el.composerKind.value = selectedKind;
  updateComposerLevelLabels();

  el.composerTicker.placeholder = "NVDA";
  el.composerCompany.placeholder = "NVIDIA";
  el.composerHeadline.placeholder = ui().composerHeadlinePlaceholder;
  el.composerSummary.placeholder = ui().composerSummaryPlaceholder;
  el.composerTags.placeholder = ui().composerTagsPlaceholder;
  el.composerHint.textContent = state.composerMessage || defaultComposerMessage();
  el.composerHint.dataset.tone = state.composerMessageTone;
  renderContributionTypeRow();
}

function renderLivePill() {
  if (!el.livePill) {
    return;
  }
  const recent = featuredThread();
  const suffix = recent ? `${activeLiveCount()} ${ui().liveLabel} · ${formatAge(threadAgeMinutes(recent))}` : ui().liveLabel;
  el.livePill.textContent = suffix;
}

function renderHeroFeature() {
  const thread = featuredThread();
  const copy = copyFor(thread);
  const headline = briefText(copy.headline || copy.summary || "", 54);
  const note = briefText(copy.summary || copy.footer || "", 68);
  const metric = metricValue(thread, "Focus") || metricValue(thread, "Entry") || "--";

  el.heroFeature.innerHTML = `
    <article class="active-signal-card active-signal-card-primary">
      <div class="active-signal-top">
        <span class="mono-label">${escapeHtml(thread.ticker)} / ${escapeHtml(thread.company)}</span>
        <span class="signal-delta positive">${escapeHtml(metric)}</span>
      </div>
      <div class="active-signal-chart">
        ${sparklineSvg(thread.sparkline, lineColor(thread.kind), 56)}
      </div>
      <strong class="active-signal-title">${escapeHtml(headline)}</strong>
      <p class="active-signal-note">${escapeHtml(note)}</p>
      <div class="active-signal-mini-metrics">
        <span class="reaction-pill">${escapeHtml(thread.metrics.reads)} ${escapeHtml(ui().readsLabel)}</span>
        <span class="reaction-pill">${escapeHtml(thread.metrics.saves)} ${escapeHtml(ui().savesLabel)}</span>
      </div>
      <a class="active-signal-link" href="#thread-${escapeHtml(thread.id)}">${escapeHtml(ui().openThreadCta)}</a>
    </article>
  `;
}

function renderSignalBoard() {
  const exit = latestExitThread();
  const watch = activeWatch();
  const watchCopy = copyFor(watch);
  const source = exit || watch;
  const sourceCopy = exit ? copyFor(exit) : watchCopy;
  const sourceMetric = exit ? metricValue(exit, "Return") : watch.trigger;
  const toneClass = exit ? "negative" : "watching";

  el.signalBoard.innerHTML = `
    <article class="active-signal-card">
      <div class="active-signal-top">
        <span class="mono-label">${escapeHtml(source.ticker)}</span>
        <span class="signal-delta ${escapeHtml(toneClass)}">${escapeHtml(sourceMetric)}</span>
      </div>
      <div class="active-signal-chart">
        ${sparklineSvg(source.sparkline, lineColor(exit ? exit.kind : "watch"), 56)}
      </div>
      <strong class="active-signal-title">${escapeHtml(briefText(sourceCopy.headline || sourceCopy.note || "", 54))}</strong>
      <p class="active-signal-note">${escapeHtml(exit ? uiText("closedAgeLabel", { age: formatAge(threadAgeMinutes(exit)) }) : `${triggerLabel()} · ${watch.trigger}`)}</p>
    </article>
  `;
}

function buildFeedSignalItems() {
  const live = featuredThread();
  const exit = latestExitThread() || live;

  return [
    {
      toneClass: "active-signal-card-primary",
      kicker: `${live.ticker} / ${live.company}`,
      delta: metricValue(live, "Focus") || metricValue(live, "Entry") || "--",
      deltaClass: "positive",
      chart: sparklineSvg(live.sparkline, lineColor(live.kind), 52),
      title: briefText(copyFor(live).headline || copyFor(live).summary || "", 62),
      note: briefText(copyFor(live).summary || copyFor(live).footer || "", 92),
      metrics: [
        `${live.metrics.reads} ${ui().readsLabel}`,
        `${live.metrics.saves} ${ui().savesLabel}`,
      ],
      href: `#thread-${live.id}`,
      cta: ui().openThreadCta,
    },
    {
      toneClass: "",
      kicker: exit.ticker,
      delta: metricValue(exit, "Return") || "--",
      deltaClass: "negative",
      chart: sparklineSvg(exit.sparkline, lineColor(exit.kind), 52),
      title: briefText(copyFor(exit).headline || "", 62),
      note: uiText("closedAgeLabel", { age: formatAge(threadAgeMinutes(exit)) }),
      metrics: [],
      href: `#thread-${exit.id}`,
      cta: ui().openArchiveCta,
    },
  ];
}

function feedSignalModule() {
  const items = buildFeedSignalItems();

  return `
    <section class="feed-insert feed-insert-signals reveal" aria-label="${escapeHtml(ui().activeSignalsTitle)}">
      <div class="feed-insert-bar">
        <span class="feed-insert-kicker">${escapeHtml(ui().activeSignalsTitle)}</span>
        <a class="feed-insert-link" href="#hero-feature">${escapeHtml(ui().viewAllLabel)}</a>
      </div>
      <div class="feed-signal-grid">
        ${items.map((item) => `
          <a class="feed-signal-card active-signal-card ${escapeHtml(item.toneClass)}" href="${escapeHtml(item.href)}">
            <div class="active-signal-top">
              <span class="mono-label">${escapeHtml(item.kicker)}</span>
              <span class="signal-delta ${escapeHtml(item.deltaClass)}">${escapeHtml(item.delta)}</span>
            </div>
            <div class="active-signal-chart">
              ${item.chart}
            </div>
            <strong class="active-signal-title">${escapeHtml(item.title)}</strong>
            <p class="active-signal-note">${escapeHtml(item.note)}</p>
            ${item.metrics.length ? `
              <div class="active-signal-mini-metrics">
                ${item.metrics.map((metric) => `<span class="reaction-pill">${escapeHtml(metric)}</span>`).join("")}
              </div>
            ` : ""}
            <span class="feed-signal-cta">${escapeHtml(item.cta)}</span>
          </a>
        `).join("")}
      </div>
    </section>
  `;
}

function worldNewsModule() {
  const items = worldNewsItems();
  const activeItem = activeWorldNewsItem();

  if (!items.length || !activeItem) {
    return "";
  }

  const activeCopy = copyFor(activeItem);
  const activeAge = formatAge(activeItem.published_minutes_ago || 0);
  const newsDescription = (ui().worldNewsDescription || "").trim();

  return `
    <section class="feed-insert feed-insert-news reveal" aria-label="${escapeHtml(ui().worldNewsTitle)}">
      <div class="feed-insert-bar">
        <div>
          <span class="feed-insert-kicker">${escapeHtml(ui().worldNewsKicker)}</span>
          ${newsDescription ? `<p class="feed-insert-copy">${escapeHtml(newsDescription)}</p>` : ""}
        </div>
      </div>
      <div class="macro-news-grid">
        ${items.map((item) => {
          const copy = copyFor(item);
          const isActive = item.id === activeItem.id;
          return `
            <button
              type="button"
              class="macro-news-card ${isActive ? "is-active" : ""}"
              data-news-select="${escapeHtml(item.id)}"
              aria-pressed="${isActive ? "true" : "false"}"
            >
              <span class="macro-news-meta">${escapeHtml(item.region)} · ${escapeHtml(formatAge(item.published_minutes_ago || 0))}</span>
              <strong class="macro-news-headline">${escapeHtml(copy.headline || "")}</strong>
              <span class="macro-news-open">${escapeHtml(ui().worldNewsReadLabel)}</span>
            </button>
          `;
        }).join("")}
      </div>
      <div class="macro-news-focus">
        <div class="macro-news-focus-head">
          <div>
            <span class="feed-insert-kicker">${escapeHtml(ui().worldNewsImpactLabel)}</span>
            <h3 class="macro-news-focus-title">${escapeHtml(activeCopy.headline || "")}</h3>
          </div>
          <div class="macro-news-focus-meta">
            <span>${escapeHtml(ui().worldNewsSourceLabel)} · ${escapeHtml(activeItem.source || "")}</span>
            <span>${escapeHtml(uiText("worldNewsTimeLabel", { age: activeAge }))}</span>
            ${activeItem.source_url ? `<a class="macro-news-source-link" href="${escapeHtml(activeItem.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(ui().worldNewsOriginalLink || "Read original")}</a>` : ""}
          </div>
        </div>
        <p class="macro-news-focus-summary">${escapeHtml(activeCopy.summary || "")}</p>
        <div class="macro-news-impact-card">
          <span class="level-label">${escapeHtml(ui().worldNewsImpactLabel)}</span>
          <strong>${escapeHtml(activeCopy.impact || activeCopy.summary || "")}</strong>
        </div>
        <div class="macro-news-comments">
          <div class="macro-news-comments-head">
            <span class="feed-insert-kicker">${escapeHtml(ui().worldNewsAiViewLabel)}</span>
            <span class="macro-news-comments-lead">${escapeHtml(ui().worldNewsCommentLead)}</span>
          </div>
          <div class="macro-news-comment-list">
            ${(activeItem.views || []).map((view) => {
              const author = authorById(view.author_id) || {
                name: view.author_id,
                handle: "@signal",
                avatar: "AI",
              };
              const authorMetricValue = primaryMetricDisplay(author, state.rankMetric);
              const authorMetricLabel = rankingOptions().find((option) => option.id === state.rankMetric)?.label || "";
              const viewCopy = copyFor(view);
              return `
                <article class="macro-news-comment" data-author-focus="${escapeHtml(view.author_id)}" tabindex="0" role="button" aria-label="${escapeHtml(author.name)}">
                  <span class="macro-news-comment-avatar">${escapeHtml(author.avatar || author.name.slice(0, 2).toUpperCase())}</span>
                  <div class="macro-news-comment-body">
                    <div class="macro-news-comment-meta">
                      <strong>${escapeHtml(author.name)}</strong>
                      <span>${escapeHtml(author.handle)}</span>
                      <span class="macro-news-comment-performance">
                        <strong>${escapeHtml(authorMetricValue)}</strong>
                        ${authorMetricLabel ? `<span>${escapeHtml(authorMetricLabel)}</span>` : ""}
                      </span>
                      <span class="status-chip ${kindChipClass(view.kind)}">${escapeHtml(kindLabel(view.kind))}</span>
                    </div>
                    <p class="macro-news-comment-headline">${escapeHtml(viewCopy.headline || author.name)}</p>
                    <p class="macro-news-comment-copy">${escapeHtml(viewCopy.summary || "")}</p>
                  </div>
                </article>
              `;
            }).join("")}
          </div>
        </div>
      </div>
    </section>
  `;
}

function renderSaveCard() {
  const thread = topSavedThread();
  const copy = copyFor(thread);
  const author = authorForThread(thread);

  el.saveCard.innerHTML = `
    <div class="section-headline">
      <p class="section-kicker">${escapeHtml(ui().socialProofKicker)}</p>
      <h2>${escapeHtml(ui().socialProofTitle)}</h2>
    </div>
    <p class="save-card-value">${escapeHtml(thread.metrics.saves)}</p>
    <p class="brand-proof-copy">${escapeHtml(ui().socialProofBody)}</p>
    <div class="archive-card">
      <div class="archive-topline">
        <span class="status-chip ${kindChipClass(thread.kind)}">${escapeHtml(kindLabel(thread.kind))}</span>
        <span class="ticker-chip">${escapeHtml(thread.ticker)}</span>
      </div>
      <strong>${escapeHtml(copy.headline || "")}</strong>
      <p>${escapeHtml(author.name)} · ${escapeHtml(compactNumber(parseCompactMetric(thread.metrics.reads)))} ${escapeHtml(ui().readsLabel)}</p>
    </div>
  `;
}

function renderProofStrip() {
  const items = buildProofItems();

  el.proofStrip.innerHTML = items.map((item) => `
    <article class="proof-card proof-card-${escapeHtml(item.tone)} reveal">
      <span class="proof-kicker">${escapeHtml(item.kicker)}</span>
      <strong class="proof-title">${escapeHtml(briefText(item.title, 68))}</strong>
      <span class="proof-meta">${escapeHtml(item.meta)}</span>
    </article>
  `).join("");
}

function buildProofItems() {
  const saved = topSavedThread();
  const live = featuredThread();
  const watch = activeWatch();
  const leader = authorRanking()[0];
  const leaderStrategy = strategyFor(leader);

  return [
    {
      tone: "dark",
      kicker: live.ticker,
      title: copyFor(live).headline || "",
      meta: `${compactNumber(parseCompactMetric(live.metrics.reads))} ${ui().readsLabel}`,
      href: `#thread-${live.id}`,
    },
    {
      tone: "light",
      kicker: watch.ticker,
      title: copyFor(watch).headline || copyFor(watch).note || "",
      meta: `${triggerLabel()} · ${watch.trigger}`,
      href: "#thread-feed",
    },
    {
      tone: "light",
      kicker: leader.handle,
      title: leaderStrategy.label || leader.name,
      meta: `${primaryMetricDisplay(leader, state.rankMetric)} ${rankingOptions().find((option) => option.id === state.rankMetric)?.label || ""}`,
      href: "#thread-feed",
    },
    {
      tone: "light",
      kicker: saved.ticker,
      title: copyFor(saved).headline || "",
      meta: `${saved.metrics.saves} ${ui().savesLabel}`,
      href: `#thread-${saved.id}`,
    },
  ];
}

function feedProofModule(moduleIndex) {
  const items = buildProofItems();
  const start = (moduleIndex * 2) % items.length;
  const windowed = [items[start], items[(start + 1) % items.length]];

  return `
    <section class="feed-insert feed-insert-proof reveal" aria-label="${escapeHtml(ui().trendingSignalsTitle)}">
      <div class="feed-insert-bar">
        <span class="feed-insert-kicker">${escapeHtml(ui().trendingSignalsTitle)}</span>
        <a class="feed-insert-link" href="#proof-strip">${escapeHtml(ui().viewAllLabel)}</a>
      </div>
      <div class="feed-proof-grid">
        ${windowed.map((item) => `
          <a class="feed-proof-card proof-card proof-card-${escapeHtml(item.tone)}" href="${escapeHtml(item.href)}">
            <span class="proof-kicker">${escapeHtml(item.kicker)}</span>
            <strong class="proof-title">${escapeHtml(briefText(item.title, 72))}</strong>
            <span class="proof-meta">${escapeHtml(item.meta)}</span>
          </a>
        `).join("")}
      </div>
    </section>
  `;
}

function feedReturnRadarModule(moduleIndex) {
  const items = buildReturnRadarItems();
  const start = (moduleIndex * 2) % items.length;
  const windowed = [items[start], items[(start + 1) % items.length]];

  return `
    <section class="feed-insert feed-insert-return reveal" aria-label="${escapeHtml(ui().whyComeBackLabel)}">
      <div class="feed-insert-bar">
        <span class="feed-insert-kicker">${escapeHtml(ui().whyComeBackLabel)}</span>
      </div>
      <div class="feed-radar-grid">
        ${windowed.map((item) => `
          <a class="feed-radar-card return-radar-card" href="${escapeHtml(item.href)}">
            <span class="proof-kicker">${escapeHtml(item.kicker)}</span>
            <strong class="proof-title">${escapeHtml(item.title)}</strong>
            <span class="proof-meta">${escapeHtml(item.meta)}</span>
          </a>
        `).join("")}
      </div>
    </section>
  `;
}

function feedLeaderboardModule() {
  const leaders = authorRanking().slice(0, 3);

  return `
    <section class="feed-insert feed-insert-rank reveal" aria-label="${escapeHtml(ui().leaderboardTitle)}">
      <div class="feed-insert-bar">
        <span class="feed-insert-kicker">${escapeHtml(ui().leaderboardKicker)}</span>
        <a class="feed-insert-link" href="#thread-feed">${escapeHtml(ui().viewAllLabel)}</a>
      </div>
      <div class="feed-rank-shell">
        <div class="feed-rank-head">
          <strong>${escapeHtml(ui().communityStageTitle)}</strong>
          <span>${escapeHtml(rankingPeriodLabel(state.rankMetric))}</span>
        </div>
        <div class="feed-rank-list">
          ${leaders.map((author, index) => {
            const unlocked = hasDeskAccess(author.id);
            return `
            <a class="feed-rank-row" href="#thread-feed" data-author-rank-focus="${escapeHtml(author.id)}" data-author-rank-locked="${unlocked ? "false" : "true"}" aria-label="${escapeHtml(author.name)}">
              <span class="feed-rank-order">#${escapeHtml(String(index + 1))}</span>
              <div class="feed-rank-main">
                <strong>${escapeHtml(author.name)}</strong>
                <span>${escapeHtml(leaderboardBasisCopy(author))}</span>
              </div>
              <div class="feed-rank-value">
                <strong>${escapeHtml(primaryMetricDisplay(author, state.rankMetric))}</strong>
                <span>${escapeHtml(rankingOptions().find((option) => option.id === state.rankMetric)?.label || "")}</span>
                <em class="feed-rank-access ${unlocked ? "is-open" : "is-locked"}">${escapeHtml(unlocked ? ui().leaderboardDeskOpenLabel : uiText("leaderboardDeskUnlockHint", { credits: deskPassCost() }))}</em>
              </div>
            </a>
          `;
          }).join("")}
        </div>
      </div>
    </section>
  `;
}

function renderReturnRadar() {
  if (!el.returnRadar) {
    return;
  }
  el.returnRadar.innerHTML = buildReturnRadarItems().slice(0, 2).map((item) => `
    <article class="return-radar-card">
      <span class="proof-kicker">${escapeHtml(item.kicker)}</span>
      <strong class="proof-title">${escapeHtml(item.title)}</strong>
      <span class="proof-meta">${escapeHtml(item.meta)}</span>
    </article>
  `).join("");
}

function renderQuickGuide() {
  el.quickGuideGrid.innerHTML = quickGuideSteps().map((item) => `
    <article class="quick-guide-card">
      <span class="quick-guide-step">${escapeHtml(item.step)}</span>
      <strong class="quick-guide-card-title">${escapeHtml(item.title)}</strong>
      <a class="quick-guide-link" href="${escapeHtml(item.link)}">${escapeHtml(item.cta)}</a>
    </article>
  `).join("");
}

function renderBrowseGrid() {
  el.browseGrid.innerHTML = browseDestinations().map((item) => `
    <article class="browse-card">
      <div class="browse-card-top">
        <span class="browse-card-value">${escapeHtml(item.value)}</span>
        <span class="browse-card-label">${escapeHtml(item.label)}</span>
      </div>
      <strong class="browse-card-title">${escapeHtml(item.title)}</strong>
      <a class="browse-card-link" href="${escapeHtml(item.link)}">${escapeHtml(item.cta)}</a>
    </article>
  `).join("");
}

function roundtableContext() {
  const defaults = roundtableConfig().defaults || {};
  const ticker = normalizeTicker(state.aiRoundtableTicker) || defaults.ticker || featuredThread()?.ticker || "NVDA";
  const matchingThreads = allThreads().filter((thread) => normalizeTicker(thread.ticker) === ticker);
  const latestThread = matchingThreads[0] || null;
  const matchingWatch = state.blueprint.watchlist.find((item) => normalizeTicker(item.ticker) === ticker) || null;
  const company = latestThread?.company || matchingWatch?.company || ticker;
  const author = latestThread ? authorForThread(latestThread) : null;

  return {
    ticker,
    company,
    latestThread,
    matchingWatch,
    author,
    strategy: author ? strategyFor(author) : null,
    threadCopy: latestThread ? copyFor(latestThread) : null,
    watchCopy: matchingWatch ? copyFor(matchingWatch) : null,
  };
}

function roundtableStance(modelId, context) {
  const kind = context.latestThread?.kind || (context.matchingWatch ? "watch" : "unknown");

  if (kind === "sell") {
    if (modelId === "grok") {
      return "watch";
    }
    return "cautious";
  }

  if (kind === "watch") {
    if (modelId === "grok") {
      return "constructive";
    }
    if (modelId === "claude") {
      return "cautious";
    }
    return "watch";
  }

  if (kind === "buy") {
    if (modelId === "claude") {
      return "watch";
    }
    return "constructive";
  }

  return "watch";
}

function roundtableStanceLabel(stance) {
  if (stance === "constructive") {
    return ui().aiRoundtableConstructiveLabel;
  }
  if (stance === "cautious") {
    return ui().aiRoundtableCautiousLabel;
  }
  return ui().aiRoundtableWatchLabel;
}

function roundtableToneClass(stance) {
  if (stance === "constructive") {
    return "tone-positive";
  }
  if (stance === "cautious") {
    return "tone-negative";
  }
  return "tone-watch";
}

function roundtableModelResponse(model, context) {
  const stance = roundtableStance(model.id, context);
  const modelCopy = copyFor(model);
  const latestThread = context.latestThread;
  const strategy = context.strategy;
  const modelAngle = {
    gpt: ui().roundtableAngleStructureLabel,
    gemini: ui().roundtableAngleContextLabel,
    claude: ui().roundtableAngleRiskLabel,
    grok: ui().roundtableAngleSpeedLabel,
  }[model.id] || ui().roundtableAngleViewLabel;

  if (!latestThread && !context.matchingWatch) {
    return {
      stance,
      angle: modelAngle,
      summary: uiText("roundtableNoFreshSummary", { ticker: context.ticker }),
      bullets: [
        ui().roundtableNoFreshBulletWhy,
        ui().roundtableNoFreshBulletNext,
      ],
    };
  }

  const trigger = latestThread?.price_map?.[0]?.value || context.matchingWatch?.trigger || "--";
  const risk = latestThread?.price_map?.[1]?.value || latestThread?.price_map?.[0]?.value || "--";
  const threadAge = latestThread ? formatAge(threadAgeMinutes(latestThread)) : ui().watchFilterLabel;
  const simpleThreadSummary = briefText(context.threadCopy?.summary || context.watchCopy?.note || strategy?.focus || "", 52);
  const simpleHeadline = briefText(context.threadCopy?.headline || context.watchCopy?.headline || "", 44);

  const structuredSummary = {
    constructive: uiText("roundtableStructuredPositive", { ticker: context.ticker }),
    watch: uiText("roundtableStructuredWatch", { ticker: context.ticker }),
    cautious: uiText("roundtableStructuredNegative", { ticker: context.ticker }),
  }[stance];

  const firstBullet = {
    gpt: ui().roundtableFirstBulletGpt,
    gemini: uiText("roundtableFirstBulletGemini", {
      reason: simpleThreadSummary || ui().roundtableGeminiReasonFallback,
    }),
    claude: uiText("roundtableFirstBulletClaude", { risk }),
    grok: uiText("roundtableFirstBulletGrok", {
      reason: simpleHeadline || uiText("roundtableGrokReasonFallback", { ticker: context.ticker }),
    }),
  }[model.id];

  const secondBullet = {
    gpt: uiText("roundtableSecondBulletGpt", { trigger, risk }),
    gemini: uiText("roundtableSecondBulletGemini", { age: threadAge }),
    claude: latestThread?.kind === "sell"
      ? ui().roundtableSecondBulletClaudeSell
      : uiText("roundtableSecondBulletClaude", { risk }),
    grok: latestThread?.kind === "buy"
      ? ui().roundtableSecondBulletGrokBuy
      : latestThread?.kind === "sell"
        ? ui().roundtableSecondBulletGrokSell
        : ui().roundtableSecondBulletGrokWatch,
  }[model.id];

  return {
    stance,
    angle: modelAngle,
    summary: structuredSummary,
    bullets: [firstBullet, secondBullet].filter(Boolean),
  };
}

function premiumResearchSections(context, models) {
  const latestThread = context.latestThread;
  const watch = context.matchingWatch;
  const trigger = latestThread?.price_map?.[0]?.value || watch?.trigger || "--";
  const risk = latestThread?.price_map?.[1]?.value || latestThread?.price_map?.[0]?.value || "--";
  const focus = latestThread?.price_map?.[2]?.value || watch?.focus || ui().premiumFocusFallback;
  const reads = latestThread?.metrics?.reads || ui().premiumNoReadsFallback;
  const saves = latestThread?.metrics?.saves || ui().premiumNoSavesFallback;
  const hasFreshThread = Boolean(latestThread);
  const previewOpenCount = 2;
  const topBull = models.filter((model) => model.response.stance === "constructive").map((model) => model.name);
  const topWatch = models.filter((model) => model.response.stance === "watch").map((model) => model.name);
  const bullLabel = topBull.length ? topBull.join(", ") : ui().premiumSnapshotBullFallback;
  const watchLabel = topWatch.length ? topWatch.join(", ") : ui().premiumSnapshotWatchFallback;

  const sections = [
    {
      id: "snapshot",
      locked: false,
      title: ui().premiumSnapshotTitle,
      body: uiText("premiumSnapshotBody", {
        ticker: context.ticker,
        trigger,
        bullish: bullLabel,
        watch: watchLabel,
      }),
      bullets: [
        uiText("premiumSnapshotBulletReads", { reads, saves }),
        uiText("premiumSnapshotBulletFocus", { focus }),
      ],
    },
    {
      id: "consensus",
      locked: false,
      title: ui().premiumConsensusTitle,
      body: hasFreshThread
        ? ui().premiumConsensusBodyLive
        : ui().premiumConsensusBodyNoLive,
      bullets: [
        uiText("premiumConsensusBulletLine", { risk }),
        ui().premiumConsensusBulletCaution,
      ],
    },
    {
      id: "model-briefs",
      locked: true,
      credits: 3,
      title: ui().premiumModelBriefsTitle,
      body: ui().premiumModelBriefsBody,
      bullets: [
        ui().premiumModelBriefsBulletOne,
        ui().premiumModelBriefsBulletTwo,
      ],
    },
    {
      id: "entry-window",
      locked: true,
      credits: 5,
      title: ui().premiumEntryWindowTitle,
      body: ui().premiumEntryWindowBody,
      bullets: [
        ui().premiumEntryWindowBulletOne,
        ui().premiumEntryWindowBulletTwo,
      ],
    },
    {
      id: "objective-data",
      locked: true,
      credits: 6,
      title: ui().premiumObjectiveDataTitle,
      body: ui().premiumObjectiveDataBody,
      bullets: [
        ui().premiumObjectiveDataBulletOne,
        ui().premiumObjectiveDataBulletTwo,
      ],
    },
    {
      id: "risk-map",
      locked: true,
      credits: 4,
      title: ui().premiumRiskMapTitle,
      body: ui().premiumRiskMapBody,
      bullets: [
        ui().premiumRiskMapBulletOne,
        ui().premiumRiskMapBulletTwo,
      ],
    },
    {
      id: "scenario-tree",
      locked: true,
      credits: 4,
      title: ui().premiumScenarioTreeTitle,
      body: ui().premiumScenarioTreeBody,
      bullets: [
        ui().premiumScenarioTreeBulletOne,
        ui().premiumScenarioTreeBulletTwo,
      ],
    },
    {
      id: "model-notes",
      locked: true,
      credits: 7,
      title: ui().premiumModelNotesTitle,
      body: ui().premiumModelNotesBody,
      bullets: models.map((model) => uiText("premiumModelNotesBullet", { model: model.name })),
    },
    {
      id: "decision-sheet",
      locked: true,
      credits: 3,
      title: ui().premiumDecisionSheetTitle,
      body: ui().premiumDecisionSheetBody,
      bullets: [
        ui().premiumDecisionSheetBulletOne,
        ui().premiumDecisionSheetBulletTwo,
      ],
    },
  ];

  return {
    previewOpenCount,
    sections,
    openRatio: Math.round((previewOpenCount / sections.length) * 100),
    lockedCount: sections.filter((section) => section.locked).length,
    totalCredits: sections
      .filter((section) => section.locked)
      .reduce((sum, section) => sum + Number(section.credits || 0), 0),
  };
}

function buildCommerceCatalog(context = roundtableContext(), premiumSummary = null) {
  const effectiveContext = context || roundtableContext();
  const models = roundtableModelsWithResponses(effectiveContext);
  const premium = premiumSummary || premiumResearchSections(effectiveContext, models);
  const leadDesk = authorRanking()[0] || state.blueprint.authors?.[0] || null;
  const currentTicker = effectiveContext.ticker || featuredThread()?.ticker || "NVDA";
  const monthlyCredits = Number(catalog().membership_credit_topup || 30);
  const bundleCredits = Number(catalog().product_costs?.bundle || Math.max(9, Math.round(Number(premium.totalCredits || 0) * 0.4)));
  const archiveCount = documentedExitCount();
  const bundleSavings = Math.max(0, Number(premium.totalCredits || 0) - bundleCredits);

  return {
    cards: [
      {
        id: "credits",
        type: ui().commerceCreditsType,
        title: uiText("commerceCreditsTitle", { ticker: currentTicker }),
        body: ui().commerceCreditsBody,
        meta: uiText("commerceCreditsMeta", {
          credits: premium.totalCredits,
          count: premium.lockedCount,
          amount: formatApproxKrw(approximateKrwForCredits(premium.totalCredits)),
        }),
        cta: ui().commerceCreditsCta,
        ticker: currentTicker,
      },
      {
        id: "membership",
        type: ui().commerceMembershipType,
        title: ui().commerceMembershipTitle,
        body: ui().commerceMembershipBody,
        meta: uiText("commerceMembershipMeta", {
          credits: monthlyCredits,
          count: estimatedQuickUnlockCount(monthlyCredits),
        }),
        cta: ui().commerceMembershipCta,
        ticker: currentTicker,
      },
      {
        id: "follow-pass",
        type: ui().commerceFollowType,
        title: ui().commerceFollowTitle,
        body: ui().commerceFollowBody,
        meta: uiText("commerceFollowMeta", {
          credits: followPassCost(),
          amount: formatApproxKrw(approximateKrwForCredits(followPassCost())),
        }),
        cta: ui().commerceFollowCta,
      },
      {
        id: "desk-pass",
        type: ui().commerceDeskPassType,
        title: uiText("commerceDeskPassTitle", { desk: leadDesk?.name || "Loom Core" }),
        body: ui().commerceDeskPassBody,
        meta: uiText("commerceDeskPassMeta", {
          credits: deskPassCost(),
          amount: formatApproxKrw(approximateKrwForCredits(deskPassCost())),
        }),
        cta: ui().commerceDeskPassCta,
        authorId: leadDesk?.id || "signal-loom",
      },
      {
        id: "alerts",
        type: ui().commerceAlertsType,
        title: ui().commerceAlertsTitle,
        body: ui().commerceAlertsBody,
        meta: uiText("commerceAlertsMeta", {
          credits: Number(catalog().product_costs?.alerts || 4),
          amount: formatApproxKrw(approximateKrwForCredits(Number(catalog().product_costs?.alerts || 4))),
        }),
        cta: ui().commerceAlertsCta,
        ticker: currentTicker,
      },
      {
        id: "bundle",
        type: ui().commerceBundleType,
        title: uiText("commerceBundleTitle", { ticker: currentTicker }),
        body: ui().commerceBundleBody,
        meta: uiText("commerceBundleMeta", {
          credits: bundleCredits,
          full: premium.totalCredits,
          saved: bundleSavings,
        }),
        cta: ui().commerceBundleCta,
        ticker: currentTicker,
      },
      {
        id: "archive",
        type: ui().commerceArchiveType,
        title: ui().commerceArchiveTitle,
        body: ui().commerceArchiveBody,
        meta: uiText("commerceArchiveMeta", {
          credits: Number(catalog().product_costs?.archive || 6),
          count: archiveCount,
        }),
        cta: ui().commerceArchiveCta,
      },
    ],
    sponsor: {
      label: ui().commerceSponsorLabel,
      title: ui().commerceSponsorTitle,
      body: ui().commerceSponsorBody,
      tag: ui().commerceSponsorTag,
      metaLabel: ui().commerceSponsorPartnerLabel,
      metaValue: ui().commerceSponsorPartnerValue,
    },
  };
}

function commerceCardMap(cards = []) {
  return new Map(cards.map((card) => [card.id, card]));
}

function premiumSectionPriority(context, premium) {
  const kind = context?.latestThread?.kind || (context?.matchingWatch ? "watch" : "watch");
  const unlocked = state.aiPremiumUnlockedSectionIds || new Set();
  const preference = {
    buy: ["entry-window", "model-briefs", "risk-map", "objective-data", "decision-sheet", "scenario-tree", "model-notes"],
    watch: ["model-briefs", "entry-window", "objective-data", "risk-map", "scenario-tree", "decision-sheet", "model-notes"],
    sell: ["objective-data", "model-briefs", "archive", "scenario-tree", "decision-sheet", "risk-map", "model-notes"],
  }[kind] || ["model-briefs", "entry-window", "objective-data", "risk-map", "decision-sheet", "scenario-tree", "model-notes"];

  return preference
    .map((sectionId) => premium.sections.find((section) => section.id === sectionId))
    .filter((section) => section && section.locked && !unlocked.has(section.id));
}

function primaryResearchOffer(context, premium, catalog) {
  const nextSection = premiumSectionPriority(context, premium)[0];
  const starter = starterPack();
  const starterCredits = totalCreditsForPack(starter);
  const needsCredits = Boolean(nextSection && (!state.authenticated || Number(state.account?.credits_balance || 0) < Number(nextSection.credits || 0)));
  if (needsCredits && starter && starterCredits) {
    return {
      kind: "product",
      card: {
        id: "credits",
        title: ui().accountPackStarterTitle,
        cta: uiText("researchTopUpCta", { credits: starterCredits }),
      },
      title: ui().researchTopUpTitle,
      body: uiText("researchTopUpBody", { section: nextSection.title }),
      meta: uiText("researchTopUpMeta", {
        amount: formatKrw(starter.price_krw),
        credits: starterCredits,
        count: estimatedQuickUnlockCount(starterCredits),
      }),
      bullets: [],
      cta: uiText("researchTopUpCta", { credits: starterCredits }),
    };
  }

  if (nextSection) {
    return {
      kind: "section",
      section: nextSection,
      title: uiText("researchNextUnlockTitle", { section: nextSection.title }),
      body: uiText("researchNextUnlockBody", { ticker: context.ticker, section: nextSection.title }),
      meta: uiText("researchNextUnlockMeta", {
        credits: nextSection.credits || 0,
        amount: formatApproxKrw(approximateKrwForCredits(nextSection.credits || 0)),
      }),
      bullets: (nextSection.bullets || []).slice(0, 2),
      cta: uiText("researchNextUnlockCta", { credits: nextSection.credits || 0 }),
    };
  }

  const cards = commerceCardMap(catalog.cards);
  const fallbackOrder = [
    cards.get("alerts"),
    cards.get("follow-pass"),
    cards.get("membership"),
    cards.get("desk-pass"),
    cards.get("archive"),
    cards.get("bundle"),
  ].filter(Boolean);
  const card = fallbackOrder.find((candidate) => !accountProductState(candidate).purchased);

  if (!card) {
    return null;
  }

  return {
    kind: "product",
    card,
    title: uiText("researchNextProductTitle", { title: card.title }),
    body: uiText("researchNextProductBody", { title: card.title }),
    meta: card.meta,
    bullets: [],
    cta: card.cta,
  };
}

function secondaryResearchOffers(context, premium, catalog, primaryOffer) {
  const cards = commerceCardMap(catalog.cards);
  const currentTicker = context.ticker;
  const currentAuthorId = catalog.cards.find((card) => card.id === "desk-pass")?.authorId || context.author?.id || "signal-loom";
  const candidateOrder = [
    cards.get("follow-pass"),
    cards.get("membership"),
    cards.get("bundle"),
    cards.get("alerts"),
    cards.get("desk-pass"),
    cards.get("archive"),
    cards.get("credits"),
  ].filter(Boolean);

  return candidateOrder
    .filter((card) => {
      if (primaryOffer?.kind === "product" && primaryOffer.card?.id === card.id) {
        return false;
      }
      return !accountProductState(card).purchased;
    })
    .slice(0, 2)
    .map((card) => ({
      ...card,
      ticker: card.ticker || currentTicker,
      authorId: card.authorId || currentAuthorId,
    }));
}

function primaryFeedOffer(context, catalog) {
  const cards = commerceCardMap(catalog.cards);
  const topDesk = catalog.cards.find((card) => card.id === "desk-pass");

  if (!state.authenticated) {
    return {
      card: cards.get("alerts"),
      title: ui().feedUpgradeGuestTitle,
      body: uiText("feedUpgradeGuestBody", { ticker: context.ticker }),
      cta: ui().feedUpgradeGuestCta,
    };
  }

  if (!hasFollowAccess()) {
    return {
      card: cards.get("follow-pass"),
      title: ui().feedUpgradeFollowTitle,
      body: ui().feedUpgradeFollowBody,
      cta: ui().feedUpgradeFollowCta,
    };
  }

  if (!state.account?.alerts_active) {
    return {
      card: cards.get("alerts"),
      title: ui().feedUpgradeAlertsTitle,
      body: uiText("feedUpgradeAlertsBody", { ticker: context.ticker }),
      cta: ui().feedUpgradeAlertsCta,
    };
  }

  if (!state.account?.membership_active) {
    return {
      card: cards.get("membership"),
      title: ui().feedUpgradeMembershipTitle,
      body: uiText("feedUpgradeMembershipBody", { ticker: context.ticker }),
      cta: ui().feedUpgradeMembershipCta,
    };
  }

  if (topDesk && !accountHasDeskPass(topDesk.authorId)) {
    return {
      card: topDesk,
      title: uiText("feedUpgradeDeskPassTitle", { desk: topDesk.title }),
      body: uiText("feedUpgradeDeskPassBody", { desk: topDesk.title }),
      cta: ui().feedUpgradeDeskPassCta,
    };
  }

  if (!state.account?.archive_active) {
    return {
      card: cards.get("archive"),
      title: ui().feedUpgradeArchiveTitle,
      body: ui().feedUpgradeArchiveBody,
      cta: ui().feedUpgradeArchiveCta,
    };
  }

  return {
    card: cards.get("bundle") || cards.get("credits"),
    title: uiText("feedUpgradeBundleTitle", { ticker: context.ticker }),
    body: uiText("feedUpgradeBundleBody", { ticker: context.ticker }),
    cta: ui().feedUpgradeBundleCta,
  };
}

function renderResearchPrimaryOffer(offer) {
  if (!offer) {
    return "";
  }

  const meta = offer.meta ? `<span class="research-next-meta">${escapeHtml(offer.meta)}</span>` : "";
  const action = offer.kind === "section"
    ? `<button type="button" class="cta research-next-cta" data-premium-unlock="${escapeHtml(offer.section.id)}">${escapeHtml(offer.cta)}</button>`
    : `
      <button
        type="button"
        class="cta research-next-cta"
        data-commerce-open="${escapeHtml(offer.card.id)}"
        ${offer.card.ticker ? `data-commerce-ticker="${escapeHtml(offer.card.ticker)}"` : ""}
        ${offer.card.authorId ? `data-commerce-author="${escapeHtml(offer.card.authorId)}"` : ""}
      >
        ${escapeHtml(offer.cta)}
      </button>
    `;

  return `
    <section class="research-next-card">
      <div class="research-next-copy">
        <p class="section-kicker">${escapeHtml(ui().researchNextStepKicker)}</p>
        <h4>${escapeHtml(offer.title)}</h4>
        <p class="research-next-body">${escapeHtml(offer.body)}</p>
      </div>
      <div class="research-next-actions">
        ${meta}
        ${action}
      </div>
    </section>
  `;
}

function renderResearchSecondaryOffers(cards = []) {
  if (!cards.length) {
    return "";
  }

  return `
    <section class="research-secondary-shell">
      <div class="research-secondary-head">
        <p class="section-kicker">${escapeHtml(ui().researchSecondaryKicker)}</p>
      </div>
      <div class="research-secondary-list">
        ${cards.map((card) => `
          <article class="research-secondary-row">
            <div class="research-secondary-copyline">
              <strong>${escapeHtml(card.title)}</strong>
              <p>${escapeHtml(card.meta)}</p>
            </div>
            <button
              type="button"
              class="research-secondary-cta"
              data-commerce-open="${escapeHtml(card.id)}"
              ${card.ticker ? `data-commerce-ticker="${escapeHtml(card.ticker)}"` : ""}
              ${card.authorId ? `data-commerce-author="${escapeHtml(card.authorId)}"` : ""}
            >
              ${escapeHtml(card.cta)}
            </button>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}

function renderFeedUpgradeInline(offer) {
  if (!offer?.card) {
    return "";
  }

  return `
    <section class="feed-insert feed-insert-premium reveal" aria-label="${escapeHtml(ui().commerceFeedKicker)}">
      <div class="feed-upgrade-inline">
        <div class="feed-upgrade-copy">
          <span class="feed-insert-kicker">${escapeHtml(ui().commerceFeedKicker)}</span>
          <strong class="feed-upgrade-title">${escapeHtml(offer.title)}</strong>
          <p class="feed-upgrade-body">${escapeHtml(briefText(offer.body || "", 72))}</p>
        </div>
        <button
          type="button"
          class="feed-upgrade-cta"
          data-commerce-open="${escapeHtml(offer.card.id)}"
          ${offer.card.ticker ? `data-commerce-ticker="${escapeHtml(offer.card.ticker)}"` : ""}
          ${offer.card.authorId ? `data-commerce-author="${escapeHtml(offer.card.authorId)}"` : ""}
        >
          ${escapeHtml(offer.cta)}
        </button>
      </div>
    </section>
  `;
}

function renderCommerceCard(card, surface = "research") {
  const productState = accountProductState(card);
  return `
    <article class="commerce-card commerce-card-${escapeHtml(surface)} ${productState.purchased ? "is-purchased" : ""}">
      <div class="commerce-card-head">
        <span class="commerce-card-type">${escapeHtml(card.type)}</span>
        <span class="commerce-card-meta">${escapeHtml(productState.purchased ? productState.label : card.meta)}</span>
      </div>
      <strong class="commerce-card-title">${escapeHtml(card.title)}</strong>
      <p class="commerce-card-copy">${escapeHtml(card.body)}</p>
      <button
        type="button"
        class="commerce-card-cta"
        data-commerce-open="${escapeHtml(card.id)}"
        ${card.ticker ? `data-commerce-ticker="${escapeHtml(card.ticker)}"` : ""}
        ${card.authorId ? `data-commerce-author="${escapeHtml(card.authorId)}"` : ""}
        ${productState.purchased ? "disabled" : ""}
      >
        ${escapeHtml(productState.purchased ? ui().accountPurchasedLabel : card.cta)}
      </button>
    </article>
  `;
}

function renderCommerceSponsor(sponsor, surface = "research") {
  return `
    <aside class="commerce-sponsor commerce-sponsor-${escapeHtml(surface)}" aria-label="${escapeHtml(sponsor.label)}">
      <div class="commerce-sponsor-copy">
        <span class="commerce-sponsor-tag">${escapeHtml(sponsor.tag)}</span>
        <strong class="commerce-sponsor-title">${escapeHtml(sponsor.title)}</strong>
        <p class="commerce-sponsor-body">${escapeHtml(sponsor.body)}</p>
      </div>
      <div class="commerce-sponsor-meta">
        <span class="commerce-sponsor-meta-label">${escapeHtml(sponsor.metaLabel)}</span>
        <strong class="commerce-sponsor-meta-value">${escapeHtml(sponsor.metaValue)}</strong>
      </div>
    </aside>
  `;
}

function openResearchCommerce(ticker = "") {
  const nextTicker = normalizeTicker(ticker) || roundtableContext().ticker || featuredThread()?.ticker || "NVDA";
  openResearchFromQuery(defaultRoundtableQuestionForTicker(nextTicker));
  window.setTimeout(() => {
    document.querySelector(".premium-map-shell")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, 80);
}

function openArchiveCommerce() {
  state.filterKind = "sell";
  state.followingOnly = false;
  state.searchQuery = "";
  setActiveTab("feed");
  renderFilters();
  renderScopeRow();
  renderStoryGrid();
  renderThreads();
  renderFollowingCard();
  document.querySelector("#thread-feed")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function openAlertsCommerce() {
  state.filterKind = "all";
  state.followingOnly = false;
  state.searchQuery = "";
  setActiveTab("feed");
  renderFilters();
  renderScopeRow();
  renderStoryGrid();
  renderThreads();
  document.querySelector("#thread-feed")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function handleCommerceAction(action, payload = {}) {
  if (!action) {
    return false;
  }

  if (action === "credits") {
    if (!state.authenticated) {
      openAccountMenu("login", ui().accountPurchaseRequiresSignInLabel, "error");
      return false;
    }
    openAccountMenu("login", ui().accountTopUpPromptLabel, "neutral");
    return false;
  }

  if (!state.authenticated) {
    openAccountMenu("login", ui().accountPurchaseRequiresSignInLabel, "error");
    return false;
  }

  try {
    const response = await requestJson("/api/platform/commerce/products/purchase", {
      method: "POST",
      body: JSON.stringify({
        product_id: action,
        ticker: payload.ticker || "",
        author_id: payload.authorId || "",
      }),
    });
    applyAccountPayload(response, { preserveMessage: true });
    setAccountMessage(ui().accountPurchaseSuccessLabel, "success");
  } catch (error) {
    const message = error.message || ui().accountPurchaseFailedLabel;
    openAccountMenu(
      "login",
      message === "Not enough credits." ? ui().accountTopUpRequiredLabel : message,
      "error",
    );
    return false;
  }

  if (action === "desk-pass") {
    renderAccountMenu();
    focusAuthorPosts(payload.authorId);
    return true;
  }

  if (action === "archive") {
    renderAccountMenu();
    openArchiveCommerce();
    return true;
  }

  if (action === "alerts") {
    openAccountMenu("login", ui().accountAlertsUnlockedLabel, "success");
    openAlertsCommerce();
    return true;
  }

  if (action === "follow-pass") {
    renderAccountMenu();
    renderScopeRow();
    renderFollowingCard();
    return true;
  }

  if (action === "recent-rank") {
    renderAccountMenu();
    return true;
  }

  renderAccountMenu();
  openResearchCommerce(payload.ticker);
  return true;
}

function premiumGeneratedSection(section, context, models) {
  const latestThread = context.latestThread;
  const watch = context.matchingWatch;
  const trigger = latestThread?.price_map?.[0]?.value || watch?.trigger || "--";
  const risk = latestThread?.price_map?.[1]?.value || latestThread?.price_map?.[0]?.value || "--";
  const focus = latestThread?.price_map?.[2]?.value || watch?.focus || ui().premiumFocusFallback;
  const supportiveModels = models.filter((model) => model.response.stance === "constructive").map((model) => model.name);
  const cautiousModels = models.filter((model) => model.response.stance !== "constructive").map((model) => model.name);

  const generated = {
    "entry-window": {
      body: uiText("premiumGeneratedEntryWindowBody", { ticker: context.ticker, trigger, risk }),
      bullets: [
        uiText("premiumGeneratedEntryWindowBulletOne", { trigger }),
        uiText("premiumGeneratedEntryWindowBulletTwo", { risk }),
        ui().premiumGeneratedEntryWindowBulletThree,
      ],
    },
    "objective-data": {
      body: ui().premiumGeneratedObjectiveDataBody,
      bullets: [
        ui().premiumGeneratedObjectiveDataBulletOne,
        uiText("premiumGeneratedObjectiveDataBulletTwo", { focus }),
        uiText("premiumGeneratedObjectiveDataBulletThree", {
          models: supportiveModels.join(", ") || ui().premiumGeneratedObjectiveDataBullFallback,
        }),
      ],
    },
    "risk-map": {
      body: uiText("premiumGeneratedRiskMapBody", { risk }),
      bullets: [
        uiText("premiumGeneratedRiskMapBulletOne", { risk }),
        ui().premiumGeneratedRiskMapBulletTwo,
        uiText("premiumGeneratedRiskMapBulletThree", {
          models: cautiousModels.join(", ") || ui().premiumGeneratedRiskMapCautiousFallback,
        }),
      ],
    },
    "scenario-tree": {
      body: ui().premiumGeneratedScenarioTreeBody,
      bullets: [
        ui().premiumGeneratedScenarioTreeBulletOne,
        ui().premiumGeneratedScenarioTreeBulletTwo,
        ui().premiumGeneratedScenarioTreeBulletThree,
      ],
    },
    "model-notes": {
      body: ui().premiumGeneratedModelNotesBody,
      bullets: models.map((model) => uiText("premiumGeneratedModelNotesBullet", { model: model.name })),
    },
    "decision-sheet": {
      body: ui().premiumGeneratedDecisionSheetBody,
      bullets: [
        ui().premiumGeneratedDecisionSheetBulletOne,
        uiText("premiumGeneratedDecisionSheetBulletTwo", { trigger, risk }),
        uiText("premiumGeneratedDecisionSheetBulletThree", { focus }),
      ],
    },
  };

  return generated[section.id] || {
    body: section.body,
    bullets: section.bullets,
  };
}

function renderPremiumSection(section, context, models) {
  const isUnlocked = state.aiPremiumUnlockedSectionIds.has(section.id);
  const isGenerating = state.aiPremiumGeneratingSectionIds.has(section.id);
  const isModelBriefs = section.id === "model-briefs";
  const activeModel = models.find((model) => model.id === state.aiPremiumActiveModelId) || models[0];
  const content = isUnlocked ? premiumGeneratedSection(section, context, models) : section;
  const stateLabel = section.locked
    ? (isUnlocked
      ? ui().premiumPurchasedLabel
      : uiText("premiumCreditsShort", { credits: section.credits || 0 }))
    : ui().premiumFreeLabel;
  const teaser = briefText(section.body, 108);
  const pointList = (isUnlocked ? content.bullets : section.bullets || []).slice(0, isUnlocked ? 3 : 2);
  const lockedAction = section.locked && !isUnlocked ? `
    <button type="button" class="cta premium-inline-unlock" data-premium-unlock="${escapeHtml(section.id)}" ${isGenerating ? "disabled" : ""}>
      ${escapeHtml(isGenerating
        ? ui().premiumGeneratingLabel
        : uiText("premiumUseCreditsLabel", { credits: section.credits || 0 }))}
    </button>
  ` : "";

  return `
    <article class="premium-accordion-card ${isUnlocked ? "is-open" : "is-locked"} ${section.locked ? "is-paid" : "is-free"}" id="premium-section-${escapeHtml(section.id)}">
      <div class="premium-accordion-head">
        <div class="premium-accordion-titleblock">
          <h4>${escapeHtml(section.title)}</h4>
          <p class="premium-accordion-body">${escapeHtml(isUnlocked && !isModelBriefs ? content.body : teaser)}</p>
        </div>
        <div class="premium-accordion-side">
          <span class="premium-accordion-price">${escapeHtml(stateLabel)}</span>
          ${lockedAction}
        </div>
      </div>
      ${pointList.length ? `
        <div class="premium-accordion-points premium-accordion-points-compact">
          ${pointList.map((bullet) => `<p>${escapeHtml(bullet)}</p>`).join("")}
        </div>
      ` : ""}
      ${isUnlocked ? (
        isModelBriefs ? `
          <div class="premium-model-tabs">
            ${models.map((model) => `
              <button type="button" class="premium-model-tab ${model.id === activeModel.id ? "is-active" : ""}" data-premium-model="${escapeHtml(model.id)}">
                ${escapeHtml(model.name)}
              </button>
            `).join("")}
          </div>
          <article class="opinion-detail-card">
            <div class="opinion-card-top">
              <div>
                <p class="ai-opinion-name">${escapeHtml(activeModel.name)}</p>
                <p class="ai-opinion-style">${escapeHtml(activeModel.response.angle || copyFor(activeModel).style || "")}</p>
              </div>
              <span class="status-chip ${roundtableToneClass(activeModel.response.stance)}">${escapeHtml(roundtableStanceLabel(activeModel.response.stance))}</span>
            </div>
            <p class="ai-opinion-summary">${escapeHtml(activeModel.response.summary)}</p>
            <div class="ai-opinion-points">
              ${activeModel.response.bullets.map((bullet) => `<p>${escapeHtml(bullet)}</p>`).join("")}
            </div>
          </article>
        ` : `
          <div class="premium-accordion-footnote">${escapeHtml(ui().premiumDetailedUnlockedLabel)}</div>
        `
      ) : ""}
    </article>
  `;
}

function renderPremiumAccordionGroups(sections, context, models) {
  const initiallyVisible = sections.slice(0, 3);
  const deferred = sections.slice(3);

  return `
    <div class="premium-accordion-group premium-accordion-group-flat">
      ${initiallyVisible.map((section) => renderPremiumSection(section, context, models)).join("")}
      ${deferred.length ? `
        <details class="premium-more-shell">
          <summary class="premium-more-summary">
            <span>${escapeHtml(ui().premiumMoreSectionsLabel)}</span>
            <span class="premium-more-count">${escapeHtml(uiText("premiumMoreSectionsCount", { count: deferred.length }))}</span>
          </summary>
          <div class="premium-more-list">
            ${deferred.map((section) => renderPremiumSection(section, context, models)).join("")}
          </div>
        </details>
      ` : ""}
    </div>
  `;
}

function renderAiRoundtable() {
  const defaults = roundtableConfig().defaults || {};
  if (!state.aiRoundtableTicker) {
    state.aiRoundtableTicker = defaults.ticker || featuredThread()?.ticker || "NVDA";
  }
  if (state.aiRoundtableHasAsked && (!state.aiRoundtableQuestion || state.aiRoundtableQuestionAuto)) {
    state.aiRoundtableQuestion = defaultRoundtableQuestionForTicker(state.aiRoundtableTicker);
  }

  const isIdle = !state.aiRoundtableHasAsked;
  el.researchPanel?.classList.toggle("is-idle", isIdle);
  el.researchPanel?.classList.toggle("has-results", !isIdle);
  el.aiRoundtableShell?.classList.toggle("is-idle", isIdle);

  const context = roundtableContext();
  const models = roundtableModelsWithResponses(context);

  const constructiveCount = models.filter((model) => model.response.stance === "constructive").length;
  const cautiousCount = models.filter((model) => model.response.stance === "cautious").length;
  const watchCount = models.length - constructiveCount - cautiousCount;
  const summaryTone = constructiveCount >= 2
    ? ui().aiRoundtableConstructiveLabel
    : cautiousCount >= 2
      ? ui().aiRoundtableCautiousLabel
      : ui().aiRoundtableWatchLabel;
  const leadSummary = constructiveCount >= 2
    ? uiText("researchLeadSummaryPositive", { ticker: context.ticker })
    : cautiousCount >= 2
      ? uiText("researchLeadSummaryNegative", { ticker: context.ticker })
      : uiText("researchLeadSummaryWatch", { ticker: context.ticker });

  el.aiRoundtableTicker.value = context.ticker;
  el.aiRoundtableQuestion.value = state.aiRoundtableQuestion;
  el.aiRoundtableQuestion.placeholder = ui().aiRoundtableQuestionPlaceholder;
  el.aiRoundtableTicker.placeholder = defaults.ticker || "NVDA";

  el.aiRoundtableSuggestions.innerHTML = "";

  if (isIdle) {
    el.aiRoundtableSummary.innerHTML = "";
    el.aiRoundtableGrid.innerHTML = "";
    el.aiRoundtableSummary.hidden = true;
    el.aiRoundtableGrid.hidden = true;
    return;
  }

  el.aiRoundtableSummary.hidden = false;
  el.aiRoundtableGrid.hidden = true;

  const premium = premiumResearchSections(context, models);
  const commerce = buildCommerceCatalog(context, premium);
  const primaryOffer = primaryResearchOffer(context, premium, commerce);
  const secondaryOffers = secondaryResearchOffers(context, premium, commerce, primaryOffer);
  const dominantStance = constructiveCount >= 2 ? "constructive" : cautiousCount >= 2 ? "cautious" : "watch";
  const dominantToneClass = roundtableToneClass(dominantStance);
  const latestThread = context.latestThread;
  const currentPrice = latestThread?.price_map?.[0]?.value || latestThread?.price_map?.[1]?.value || "--";
  const riskPrice = latestThread?.price_map?.[1]?.value || latestThread?.price_map?.[0]?.value || "--";
  const momentumLabel = latestThread?.engagement?.reads
    ? uiText("researchReadsCount", { reads: latestThread.engagement.reads })
    : ui().researchContextValueFallback;
  const freeSummaryMeta = ui().researchFreeAnswerMeta;
  const stanceBreakdown = [
    { label: ui().aiRoundtableConstructiveLabel, count: constructiveCount, tone: "constructive" },
    { label: ui().aiRoundtableWatchLabel, count: watchCount, tone: "watch" },
    { label: ui().aiRoundtableCautiousLabel, count: cautiousCount, tone: "cautious" },
  ];

  el.aiRoundtableSummary.innerHTML = `
    <div class="research-results-shell">
      <section class="research-dossier-shell">
        <header class="research-dossier-head">
          <div class="research-dossier-title">
            <span class="section-kicker">${escapeHtml(ui().researchDossierKicker)}</span>
            <h3>${escapeHtml(context.ticker)} <span>${escapeHtml(uiText("researchCompanyInline", { company: context.company }))}</span></h3>
            <p class="research-answer-meta">${escapeHtml(state.aiRoundtableQuestion)}</p>
          </div>
          <span class="meta-chip ${dominantToneClass}">${escapeHtml(summaryTone)}</span>
        </header>
        <div class="research-answer-shell">
          <div class="research-answer-copy">
            <p class="section-kicker">${escapeHtml(ui().researchFreeAnswerKicker)}</p>
            <p class="research-answer-lead">${escapeHtml(leadSummary)}</p>
            <p class="research-answer-meta">${escapeHtml(freeSummaryMeta)}</p>
            ${roundtableSplitMarkup(stanceBreakdown)}
          </div>
          <div class="research-answer-strip">
            <span class="research-answer-pill">
              <span class="research-pill-label">${escapeHtml(ui().researchCurrentLabel)}</span>
              <strong class="research-pill-value">${escapeHtml(currentPrice)}</strong>
            </span>
            <span class="research-answer-pill">
              <span class="research-pill-label">${escapeHtml(ui().researchRiskLineLabel)}</span>
              <strong class="research-pill-value">${escapeHtml(riskPrice)}</strong>
            </span>
            <span class="research-answer-pill">
              <span class="research-pill-label">${escapeHtml(ui().researchContextLabel)}</span>
              <strong class="research-pill-value">${escapeHtml(momentumLabel)}</strong>
            </span>
          </div>
        </div>
        <section class="premium-map-shell">
          <div class="premium-map-head">
            <p class="section-kicker">${escapeHtml(ui().researchDeepResearchKicker)}</p>
            <div class="premium-map-meta">
              <span class="premium-map-total">${escapeHtml(uiText("researchPaidSectionsCount", { count: premium.lockedCount }))}</span>
              <span class="premium-map-total">${escapeHtml(uiText("researchTotalCredits", { credits: premium.totalCredits }))}</span>
            </div>
          </div>
          ${renderResearchPrimaryOffer(primaryOffer)}
          ${renderResearchSecondaryOffers(secondaryOffers)}
          <div class="premium-map-list">
            ${renderPremiumAccordionGroups(premium.sections, context, models)}
          </div>
        </section>
      </section>
    </div>
  `;
  el.aiRoundtableGrid.innerHTML = "";
}

function renderMonetizationCard() {
  const context = roundtableContext();
  const premium = premiumResearchSections(context, roundtableModelsWithResponses(context));
  const commerce = buildCommerceCatalog(context, premium);
  const primaryOffer = primaryResearchOffer(context, premium, commerce);
  const secondaryOffers = secondaryResearchOffers(context, premium, commerce, primaryOffer);

  el.monetizationCard.innerHTML = `
    <div class="section-stack">
      <p class="section-kicker">${escapeHtml(ui().commerceSectionKicker)}</p>
      <h2>${escapeHtml(ui().commerceSectionTitle)}</h2>
      <p class="section-description">${escapeHtml(ui().premiumPromoBody ? uiText("premiumPromoBody", { ticker: context.ticker || "NVDA" }) : "")}</p>
    </div>
    ${renderResearchPrimaryOffer(primaryOffer)}
    ${renderResearchSecondaryOffers(secondaryOffers)}
  `;
}

function buildPremiumPromo() {
  const context = roundtableContext();
  const premium = premiumResearchSections(context, roundtableModelsWithResponses(context));
  const commerce = buildCommerceCatalog(context, premium);
  const offer = primaryFeedOffer(context, commerce);

  return {
    kicker: ui().commerceFeedKicker,
    title: offer?.title || ui().commerceFeedTitle,
    body: offer?.body || uiText("premiumPromoBody", { ticker: context.ticker || "NVDA" }),
    offer,
  };
}

function feedPremiumModule() {
  const promo = buildPremiumPromo();
  return renderFeedUpgradeInline(promo.offer);
}

function renderFollowingCard() {
  const followedAuthors = state.blueprint.authors.filter((author) => state.followingIds.has(author.id));
  const unlocked = hasFollowAccess();
  const chips = followedAuthors.length
    ? followedAuthors.map((author) => `<span class="following-chip">${escapeHtml(author.handle)}</span>`).join("")
    : `<span class="following-chip">${escapeHtml(ui().noFollowingLabel)}</span>`;

  el.followingCard.innerHTML = `
    <div class="following-card ${unlocked ? "" : "is-locked"}">
      <p class="section-kicker">${escapeHtml(ui().followingKicker)}</p>
      <h2>${escapeHtml(ui().followingTitle)}</h2>
      <span class="following-count">${escapeHtml(String(followedAuthors.length))}</span>
      <p class="brand-proof-copy">${escapeHtml(unlocked ? ui().followingBody : ui().followingLockedBody)}</p>
      <div class="following-list">${chips}</div>
      <button
        type="button"
        class="scope-chip following-card-cta ${state.followingOnly ? "is-active" : ""} ${unlocked ? "" : "is-locked"}"
        data-scope="${unlocked ? (state.followingOnly ? "all" : "following") : "following"}"
        data-scope-locked="${unlocked ? "false" : "true"}"
      >
        <span class="scope-chip-label">${escapeHtml(unlocked ? (state.followingOnly ? ui().showAllWritersLabel : ui().followingOnlyLabel) : ui().followingUnlockCta)}</span>
        ${unlocked ? "" : `<span class="scope-chip-badge">${escapeHtml(uiText("followingOnlyUnlockHint", { credits: followPassCost() }))}</span>`}
      </button>
    </div>
  `;
}

function renderLeaderboard() {
  if (!el.leaderboardMetricRow || !el.leaderboardList) {
    return;
  }

  if (state.rankMetric === "recent_return" && !hasRecentRankAccess()) {
    state.rankMetric = "total_return";
  }

  const authors = authorRanking().slice(0, 3);
  const metricOption = rankingOptions().find((option) => option.id === state.rankMetric);

  el.leaderboardMetricRow.innerHTML = leaderboardMetricOptions().map((option) => `
    <button
      type="button"
      class="leaderboard-metric-btn ${state.rankMetric === option.id ? "is-active" : ""} ${option.locked ? "is-locked" : ""}"
      data-rank-metric="${escapeHtml(option.id)}"
      data-rank-locked="${option.locked ? "true" : "false"}"
      aria-pressed="${state.rankMetric === option.id}"
    >
      <span class="leaderboard-metric-btn-label">${escapeHtml(option.label)}</span>
      ${option.locked ? `<span class="leaderboard-metric-btn-badge">${escapeHtml(uiText("leaderboardRecentUnlockHint", { credits: option.credits }))}</span>` : ""}
    </button>
  `).join("");

  el.leaderboardList.innerHTML = `
    <div class="leaderboard-list-simple">
      ${authors.map((author, index) => {
        const performance = authorPerformance(author);
        const unlocked = hasDeskAccess(author.id);
        return `
          <article class="leaderboard-row leaderboard-row-simple" data-author-rank-focus="${escapeHtml(author.id)}" data-author-rank-locked="${unlocked ? "false" : "true"}" role="button" tabindex="0" aria-label="${escapeHtml(author.name)}">
            <span class="leaderboard-row-rank">#${index + 1}</span>
            <div class="leaderboard-row-main">
              <div>
                <p class="leaderboard-row-name">${escapeHtml(author.name)}</p>
                <span class="leaderboard-row-handle">${escapeHtml(author.handle)}</span>
              </div>
              <p class="leaderboard-row-basis">${escapeHtml(String(performance.closed_trades))} ${escapeHtml(ui().leaderboardClosedShortLabel)} · ${escapeHtml(performance.avg_hold)}</p>
            </div>
            <div class="leaderboard-row-value">
              <strong>${escapeHtml(primaryMetricDisplay(author, state.rankMetric))}</strong>
              <span>${escapeHtml(metricOption?.label || "")}</span>
              <em class="leaderboard-row-access ${unlocked ? "is-open" : "is-locked"}">${escapeHtml(unlocked ? ui().leaderboardDeskOpenLabel : uiText("leaderboardDeskUnlockHint", { credits: deskPassCost() }))}</em>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderAuthorGrid() {
  if (el.authorGrid) {
    el.authorGrid.innerHTML = "";
  }
}

function renderFilters() {
  el.filterRow.innerHTML = filterOptions().map((option) => `
    <button
      type="button"
      class="filter-chip ${state.filterKind === option.id ? "is-active" : ""}"
      data-filter="${escapeHtml(option.id)}"
      aria-pressed="${state.filterKind === option.id}"
    >
      ${escapeHtml(option.label)}
    </button>
  `).join("");
}

function renderScopeRow() {
  el.scopeRow.innerHTML = scopeOptions().map((option) => `
    <button
      type="button"
      class="scope-chip ${option.active ? "is-active" : ""} ${option.locked ? "is-locked" : ""}"
      data-scope="${escapeHtml(option.id)}"
      data-scope-locked="${option.locked ? "true" : "false"}"
      aria-pressed="${option.active}"
    >
      <span class="scope-chip-label">${escapeHtml(option.label)}</span>
      ${option.badge ? `<span class="scope-chip-badge">${escapeHtml(option.badge)}</span>` : ""}
    </button>
  `).join("");
}

function renderStoryGrid() {
  if (!el.storyGrid) {
    return;
  }
  const groups = storyGroups().slice(0, 2);

  if (!groups.length) {
    el.storyGrid.innerHTML = `
      <article class="empty-card">
        <h3>${escapeHtml(ui().emptyStateTitle)}</h3>
        <p class="empty-copy">${escapeHtml(ui().emptyStateBody)}</p>
      </article>
    `;
    return;
  }

  el.storyGrid.innerHTML = groups.map((group) => {
    const latest = group[0];
    const latestCopy = copyFor(latest);
    const statusClass = latest.kind === "sell" ? "story-card-closed" : "story-card-live";
    const summary = briefText(latestCopy.headline || latestCopy.summary || threadMainPoint(latest, latestCopy), 94);

    return `
      <article class="story-card story-card-compact ${statusClass}">
        <div class="story-market-top">
          <p class="story-market-source">${escapeHtml(storyMarketLabel(latest))}</p>
          <span class="story-market-badge">${escapeHtml(storyTopBadge(latest))}</span>
        </div>
        <div class="story-market-main">
          <div class="story-market-copy">
            <h3 class="story-company">${escapeHtml(storyDisplayName(latest))}</h3>
            <div class="story-market-price-row">
              <strong class="story-market-price">${escapeHtml(storyPriceValue(latest))}</strong>
              <span class="story-market-delta">${escapeHtml(storyDeltaValue(latest))}</span>
            </div>
            <p class="story-market-summary">${escapeHtml(summary)}</p>
          </div>
          <div class="story-market-actions">
            <a class="story-command-btn is-active" href="#thread-${escapeHtml(latest.id)}">${escapeHtml(storyActionPrimary(latest))}</a>
            <a class="story-command-btn" href="#thread-${escapeHtml(latest.id)}">${escapeHtml(storyActionSecondary(latest))}</a>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

function threadCard(thread, index) {
  const copy = copyFor(thread);
  const author = authorForThread(thread);
  const expanded = state.expandedThreadIds.has(thread.id);
  const summary = briefText(copy.summary || copy.footer || "", 96);
  const mainPoint = briefText(threadMainPoint(thread, copy), 82);
  const actionValue = threadActionValue(thread);
  const actionNote = threadActionNote(thread);
  const contribution = thread.contribution_type ? contributionTypeLabel(thread.contribution_type) : "";
  const beats = (copy.beats || []).slice(0, 2);
  const showFollowCta = thread.kind === "buy";
  const following = state.followingIds.has(author.id);
  const followLocked = !hasFollowAccess();
  const followButtonLabel = following
    ? ui().followingButtonLabel
    : (followLocked
      ? uiText("threadFollowUnlockLabel", { credits: followPassCost() })
      : ui().followButtonLabel);
  const followBody = following
    ? ui().threadFollowActiveBody
    : (followLocked
      ? uiText("threadFollowLockedBody", { credits: followPassCost() })
      : ui().threadFollowBody);
  const followMarkup = showFollowCta
    ? `
        <div class="thread-follow-row">
          <div class="thread-follow-copy">
            <strong>${escapeHtml(ui().threadFollowTitle)}</strong>
            <span>${escapeHtml(followBody)}</span>
          </div>
          <button
            type="button"
            class="follow-btn ${following ? "is-following" : ""}"
            data-follow-author="${escapeHtml(author.id)}"
          >
            ${escapeHtml(followButtonLabel)}
          </button>
        </div>
      `
    : "";
  const detailsMarkup = beats.length
    ? `
          <div class="thread-details">
            <ul class="thread-list">
              ${beats.map((beat) => `<li>${escapeHtml(beat)}</li>`).join("")}
            </ul>
          </div>
        `
    : "";

  return `
    <article id="thread-${escapeHtml(thread.id)}" class="thread-card thread-card-${escapeHtml(thread.kind)} ${expanded ? "" : "is-collapsed"}">
      <div class="thread-rail">
        <span class="thread-avatar">${escapeHtml(author.avatar || author.name.slice(0, 2).toUpperCase())}</span>
        <span class="thread-rail-line"></span>
      </div>
      <div class="thread-body">
        <div class="thread-topline">
          <div class="thread-authorline">
            <strong class="thread-author-name">${escapeHtml(author.name)}</strong>
            <span class="thread-author-handle">${escapeHtml(author.handle)}</span>
            <span class="thread-author-age">${escapeHtml(formatAge(threadAgeMinutes(thread)))}</span>
          </div>
          <div class="thread-meta">
            <span class="status-chip ${kindChipClass(thread.kind)}">${escapeHtml(kindLabel(thread.kind))}</span>
            ${contribution ? `<span class="meta-chip">${escapeHtml(contribution)}</span>` : ""}
          </div>
        </div>
        <h3 class="thread-title">${escapeHtml(copy.headline || "")}</h3>
        <p class="thread-summary">${escapeHtml(summary)}</p>
        <div class="thread-brief-row">
          <div class="thread-brief-pill">
            <span class="level-label">${escapeHtml(threadReasonLabel(thread.kind))}</span>
            <strong>${escapeHtml(mainPoint || summary)}</strong>
          </div>
          <div class="thread-brief-pill">
            <span class="level-label">${escapeHtml(threadActionLabel(thread.kind))}</span>
            <strong>${escapeHtml(actionValue)}</strong>
            <span class="thread-brief-note">${escapeHtml(actionNote)}</span>
          </div>
        </div>
        ${followMarkup}
        ${detailsMarkup}
        <button type="button" class="thread-toggle" data-thread-id="${escapeHtml(thread.id)}">
          ${escapeHtml(expanded ? ui().showLessLabel : ui().showMoreLabel)}
        </button>
      </div>
    </article>
  `;
}

function renderThreads() {
  const allVisibleThreads = visibleThreads();
  const batchSize = feedBatchSize();
  if (!state.feedVisibleCount || state.feedVisibleCount < batchSize) {
    state.feedVisibleCount = batchSize;
  }

  if (!allVisibleThreads.length) {
    el.threadFeed.innerHTML = `
      <article class="empty-card">
        <h3>${escapeHtml(ui().emptyStateTitle)}</h3>
        <p class="empty-copy">${escapeHtml(ui().emptyStateBody)}</p>
      </article>
    `;
    setupFeedLoadMoreObserver();
    return;
  }

  const threads = allVisibleThreads.slice(0, state.feedVisibleCount);
  const insertEvery = state.isMobile ? 8 : 10;
  const content = [];
  const modules = [feedSignalModule, feedReturnRadarModule, feedLeaderboardModule];
  const worldNewsIndex = threads.length > 6 ? 2 : -1;
  const premiumIndex = threads.length > 7 ? 5 : threads.length > 4 ? 3 : -1;

  threads.forEach((thread, index) => {
    content.push(threadCard(thread, index));

    if (index === worldNewsIndex) {
      content.push(worldNewsModule());
    }

    if (index === premiumIndex) {
      content.push(feedPremiumModule());
    }

    if ((index + 1) % insertEvery === 0 && index < threads.length - 1) {
      const moduleIndex = Math.floor(index / insertEvery);
      const renderModule = modules[moduleIndex % modules.length];
      if (renderModule === feedReturnRadarModule) {
        content.push(renderModule(moduleIndex));
      } else {
        content.push(renderModule());
      }
    }
  });

  if (allVisibleThreads.length > threads.length) {
    const remainingCount = allVisibleThreads.length - threads.length;
    content.push(`
      <button class="feed-load-more" type="button" data-feed-load-more="true">
        ${escapeHtml(uiText("feedLoadMoreLabel", { count: remainingCount }))}
      </button>
    `);
  }

  el.threadFeed.innerHTML = content.join("");
  setupFeedLoadMoreObserver();
}

function renderBrandProofCard() {
  const creatorCopy = copyFor(state.blueprint.creator);
  const primaryStat = state.blueprint.creator.stats[1];
  const secondaryStat = state.blueprint.creator.stats[2];

  el.brandProofCard.innerHTML = `
    <div class="brand-proof-card">
      <div class="section-headline">
        <p class="section-kicker">${escapeHtml(ui().brandProofKicker)}</p>
        <h2 class="brand-proof-title">${escapeHtml(ui().brandProofTitle)}</h2>
      </div>
      <div class="brand-proof-metric">
        <span>${escapeHtml(localizeMetricLabel(primaryStat.label))}</span>
        <strong>${escapeHtml(primaryStat.value)}</strong>
      </div>
      <div class="brand-proof-secondary">
        <span class="metric-pill"><strong>${escapeHtml(secondaryStat.value)}</strong>${escapeHtml(localizeMetricLabel(secondaryStat.label))}</span>
      </div>
      <div class="brand-proof-secondary">
        <span class="metric-pill"><strong>${escapeHtml(String(state.blueprint.authors.length))}</strong>${escapeHtml(ui().brandProofAiDesksLabel)}</span>
      </div>
      <p class="brand-proof-copy">${escapeHtml(creatorCopy.headline || "")}</p>
      <p class="brand-proof-copy">${escapeHtml(creatorCopy.bio || "")}</p>
    </div>
  `;
}

function renderWatchlist() {
  el.watchlist.innerHTML = state.blueprint.watchlist.map((item) => {
    const copy = copyFor(item);
    return `
      <article class="watch-card-item">
        <div class="watch-top">
          <strong>${escapeHtml(item.ticker)}</strong>
          <span class="watch-stage">${escapeHtml(localizeStage(item.stage))}</span>
        </div>
        <span class="watch-trigger">${escapeHtml(triggerLabel())} · ${escapeHtml(item.trigger)}</span>
        <p class="watch-note">${escapeHtml(copy.note || "")}</p>
        <div class="watch-sparkline">
          ${sparklineSvg(item.sparkline, lineColor("watch"), 58)}
        </div>
      </article>
    `;
  }).join("");
}

function renderArchiveList() {
  const exits = allThreads()
    .filter((thread) => thread.kind === "sell")
    .sort((left, right) => parseReturnValue(right) - parseReturnValue(left));

  el.archiveList.innerHTML = exits.map((thread) => {
    const copy = copyFor(thread);
    const author = authorForThread(thread);
    return `
      <article class="archive-card">
        <div class="archive-topline">
          <span class="status-chip chip-exit">${escapeHtml(ui().latestExitLabel)}</span>
          <span class="ticker-chip">${escapeHtml(thread.ticker)}</span>
        </div>
        <strong>${escapeHtml(copy.headline || "")}</strong>
        <span class="archive-return">${escapeHtml(metricValue(thread, "Return"))}</span>
        <p>${escapeHtml(author.handle)} · ${escapeHtml(thread.metrics.saves)} ${escapeHtml(ui().savesLabel)}</p>
      </article>
    `;
  }).join("");
}

function renderRules() {
  el.rulesList.innerHTML = buildRules().map((rule) => `<li>${escapeHtml(rule)}</li>`).join("");
}

function renderPipeline() {
  el.pipelineList.innerHTML = state.blueprint.pipeline.map((item) => {
    const copy = copyFor(item);
    return `
      <article class="pipeline-step">
        <span class="step-index">${escapeHtml(item.step)}</span>
        <strong>${escapeHtml(copy.title || "")}</strong>
        <p class="step-detail">${escapeHtml(copy.detail || "")}</p>
      </article>
    `;
  }).join("");
}

function renderLoops() {
  el.loopsList.innerHTML = state.blueprint.loops.map((item, index) => {
    const copy = copyFor(item);
    return `
      <article class="loop-card">
        <span class="step-index">${index + 1}</span>
        <strong>${escapeHtml(copy.title || "")}</strong>
        <p class="loop-detail">${escapeHtml(copy.detail || "")}</p>
      </article>
    `;
  }).join("");
}

function setupRevealObservers() {
  const nodes = document.querySelectorAll(".reveal");
  if (revealObserver) {
    revealObserver.disconnect();
    revealObserver = null;
  }
  revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver?.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  nodes.forEach((node) => revealObserver?.observe(node));
}

function renderApp() {
  state.blueprint = buildLocalizedBlueprint(state.baseBlueprint, state.language);
  invalidateThreadCaches();
  ensureActiveWorldNews();
  state.performanceSnapshots = new Map(
    state.blueprint.authors.map((author) => [author.id, deriveAuthorPerformance(author)])
  );
  safeRender("applyStaticTranslations", applyStaticTranslations);
  safeRender("renderLanguageOptions", renderLanguageOptions);
  safeRender("renderAccountMenu", renderAccountMenu);
  safeRender("renderResearchHeroStrip", renderResearchHeroStrip);
  safeRender("renderComposerControls", renderComposerControls);
  safeRender("renderLivePill", renderLivePill);
  safeRender("renderHeroFeature", renderHeroFeature);
  safeRender("renderSignalBoard", renderSignalBoard);
  safeRender("renderSaveCard", renderSaveCard);
  safeRender("renderProofStrip", renderProofStrip);
  safeRender("renderReturnRadar", renderReturnRadar);
  safeRender("renderQuickGuide", renderQuickGuide);
  safeRender("renderBrowseGrid", renderBrowseGrid);
  safeRender("renderAiRoundtable", renderAiRoundtable);
  safeRender("renderFollowingCard", renderFollowingCard);
  safeRender("renderLeaderboard", renderLeaderboard);
  safeRender("renderAuthorGrid", renderAuthorGrid);
  safeRender("renderMonetizationCard", renderMonetizationCard);
  safeRender("renderFilters", renderFilters);
  safeRender("renderScopeRow", renderScopeRow);
  safeRender("renderStoryGrid", renderStoryGrid);
  safeRender("renderThreads", renderThreads);
  safeRender("renderBrandProofCard", renderBrandProofCard);
  safeRender("renderWatchlist", renderWatchlist);
  safeRender("renderArchiveList", renderArchiveList);
  safeRender("renderRules", renderRules);
  safeRender("renderPipeline", renderPipeline);
  safeRender("renderLoops", renderLoops);
  safeRender("setupRevealObservers", setupRevealObservers);
}

function focusAuthorPosts(authorId) {
  const author = authorById(authorId);
  if (!author) {
    return;
  }

  state.filterKind = "all";
  state.followingOnly = false;
  state.searchQuery = author.handle;
  resetFeedWindow();

  setActiveTab("feed");
  renderFilters();
  renderScopeRow();
  renderStoryGrid();
  renderThreads();
  renderFollowingCard();

  document.querySelector("#thread-feed")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function openRankAuthorFeed(authorId) {
  const author = authorById(authorId);
  if (!author) {
    return false;
  }

  if (!hasDeskAccess(authorId)) {
    const unlocked = await handleCommerceAction("desk-pass", { authorId });
    return Boolean(unlocked);
  }

  focusAuthorPosts(authorId);
  return true;
}

function buildCommunityPostPayload() {
  const author = authorById(el.composerAuthor.value);
  const kind = el.composerKind.value;
  const ticker = el.composerTicker.value.trim().toUpperCase();
  const company = el.composerCompany.value.trim() || ticker;
  const headline = el.composerHeadline.value.trim();
  const summary = el.composerSummary.value.trim();
  const tags = el.composerTags.value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .slice(0, 4);

  if (!author || !ticker || !headline || !summary) {
    return null;
  }

  const levels = [
    el.composerLevelA.value.trim(),
    el.composerLevelB.value.trim(),
    el.composerLevelC.value.trim(),
  ];

  return {
    author_id: author.id,
    kind,
    contribution_type: state.contributionType,
    ticker,
    company,
    headline,
    summary,
    tags: tags.length ? tags : [kindLabel(kind)],
    levels,
  };
}

function resetComposerForm() {
  const authorValue = el.composerAuthor.value;
  const kindValue = el.composerKind.value;
  el.composerForm.reset();
  el.composerAuthor.value = authorValue;
  el.composerKind.value = kindValue;
  updateComposerLevelLabels();
}

async function unlockPremiumSections(sectionIds) {
  const targets = sectionIds.filter((sectionId) => sectionId && !state.aiPremiumUnlockedSectionIds.has(sectionId));
  if (!targets.length) {
    return;
  }

  if (!state.authenticated) {
    openAccountMenu("login", ui().accountUnlockRequiresSignInLabel, "error");
    return;
  }

  targets.forEach((sectionId) => state.aiPremiumGeneratingSectionIds.add(sectionId));
  renderAiRoundtable();

  try {
    const payload = await requestJson("/api/platform/commerce/sections/unlock", {
      method: "POST",
      body: JSON.stringify({
        ticker: currentResearchTicker(),
        section_ids: targets,
      }),
    });
    applyAccountPayload(payload, { preserveMessage: true });
    setAccountMessage(ui().accountUnlockSuccessLabel, "success");
    if (targets.includes("model-briefs")) {
      state.aiPremiumActiveModelId = roundtableModels()[0]?.id || "gpt";
    }
  } catch (error) {
    setAccountMessage(error.message || ui().accountPurchaseFailedLabel, "error");
  } finally {
    targets.forEach((sectionId) => {
      state.aiPremiumGeneratingSectionIds.delete(sectionId);
    });
    renderAiRoundtable();
    renderAccountMenu();
  }
}

async function toggleFollow(authorId) {
  if (!hasFollowAccess()) {
    const unlocked = await handleCommerceAction("follow-pass");
    if (!unlocked || !hasFollowAccess()) {
      return;
    }
  }

  const nextFollowing = !state.followingIds.has(authorId);
  try {
    const payload = await requestJson("/api/platform/follows", {
      method: "POST",
      body: JSON.stringify({
        viewer_id: state.viewerId,
        author_id: authorId,
        following: nextFollowing,
      }),
    });
    state.followingIds = new Set(Array.isArray(payload.following_ids) ? payload.following_ids : []);
    state.followerCounts = payload.follower_counts || {};
    state.followDataVersion += 1;
    invalidateVisibleThreadsCache();
    renderApp();
  } catch (error) {
    openAccountMenu("login", error?.message || ui().accountPurchaseRequiresSignInLabel, "error");
  }
}

async function init() {
  state.viewerId = ensureViewerId();
  state.adminToken = getStoredAdminToken();
  applyTheme();
  setBootMessage("Loading live feed…");
  bindHudCursor();
  state.baseBlueprint = await requestJson("/api/platform/blueprint", { method: "GET", headers: {} });
  state.language = getPreferredLanguage();
  state.aiRoundtableTicker = state.baseBlueprint.ai_roundtable?.defaults?.ticker || state.baseBlueprint.threads?.[0]?.ticker || "NVDA";
  state.aiRoundtableQuestion = "";
  state.aiRoundtableQuestionAuto = false;
  state.aiRoundtableHasAsked = false;
  try {
    await syncCommunityState();
  } catch (error) {
    console.error("Initial community sync failed", error);
    state.communityPosts = [];
    state.followingIds = new Set();
    state.followerCounts = {};
  }
  try {
    await syncAccountState();
  } catch (error) {
    console.error("Initial account sync failed", error);
    applyAccountPayload({
      authenticated: false,
      user: null,
      account: null,
      identity: null,
      catalog: state.commerceCatalog,
    });
  }
  await syncPendingSocialState();
  resetFeedWindow();
  renderApp();
  setActiveTab(initialTabFromLocation());
  markAppReady();
  window.requestAnimationFrame(() => {
    scheduleCodeWallBuild({ force: true });
  });

  const authMode = queryParam("auth");
  const authError = queryParam("auth_error");
  const accountMode = queryParam("account");
  if (!state.authenticated && state.pendingSocialProfile && authMode === "complete-social") {
    openAccountMenu("register");
  } else if (accountMode === "login") {
    openAccountMenu("login");
  } else if (accountMode === "register") {
    openAccountMenu("register");
  } else if (!state.authenticated && authError) {
    openAccountMenu("login", authError, "error");
  }

  if (!communitySyncTimer) {
    communitySyncTimer = window.setInterval(() => {
      if (document.hidden) {
        return;
      }
      syncCommunityState({ rerender: true }).catch((error) => {
        console.error("Community sync failed", error);
      });
    }, 60000);
  }
}

function applyLanguageChange(nextLanguage) {
  state.language = nextLanguage;
  window.localStorage.setItem("platform-language", state.language);
  if (state.aiRoundtableHasAsked && state.aiRoundtableQuestionAuto) {
    state.aiRoundtableQuestion = defaultRoundtableQuestionForTicker(state.aiRoundtableTicker);
  }
  renderApp();
  setActiveTab(state.activeTab);
}

el.languageSelect.addEventListener("change", (event) => {
  applyLanguageChange(event.target.value);
});

document.addEventListener("click", async (event) => {
  if (el.languageDropdown && !event.target.closest("#language-dropdown")) {
    el.languageDropdown.classList.remove("is-open");
    if (el.languageToggle) {
      el.languageToggle.setAttribute("aria-expanded", "false");
    }
  }
  if (el.accountDropdown && !event.target.closest("#account-dropdown")) {
    closeAccountMenu();
  }

  const tabTrigger = event.target.closest("[data-app-tab]");
  if (tabTrigger) {
    setActiveTab(tabTrigger.dataset.appTab);
    return;
  }

  const languageToggle = event.target.closest("#language-toggle");
  if (languageToggle) {
    const nextOpen = !el.languageDropdown.classList.contains("is-open");
    el.languageDropdown.classList.toggle("is-open", nextOpen);
    el.languageToggle.setAttribute("aria-expanded", String(nextOpen));
    return;
  }

  const languageOption = event.target.closest("[data-language-code]");
  if (languageOption) {
    const nextLanguage = languageOption.dataset.languageCode;
    el.languageSelect.value = nextLanguage;
    applyLanguageChange(nextLanguage);
    return;
  }

  const accountToggle = event.target.closest("#account-toggle");
  if (accountToggle) {
    const nextOpen = !el.accountDropdown.classList.contains("is-open");
    if (nextOpen) {
      openAccountMenu(state.accountMenuMode);
    } else {
      closeAccountMenu();
    }
    return;
  }

  const accountMode = event.target.closest("[data-account-mode]");
  if (accountMode) {
    state.accountMenuMode = accountMode.dataset.accountMode || "login";
    renderAccountMenu();
    return;
  }

  const accountAdminClear = event.target.closest("[data-account-admin-clear]");
  if (accountAdminClear) {
    setStoredAdminToken("");
    openAccountMenu(state.accountMenuMode, ui().accountAdminClearedLabel, "success");
    return;
  }

  const accountSocialProvider = event.target.closest("[data-account-social-provider]");
  if (accountSocialProvider) {
    const provider = accountSocialProvider.dataset.accountSocialProvider || "";
    if (!oauthProviderEnabled(provider)) {
      openAccountMenu("login", uiText("accountSocialUnavailableLabel", { provider: socialProviderLabel(provider) }), "error");
      return;
    }
    const lang = encodeURIComponent(state.language || "en");
    window.location.assign(`/api/platform/auth/oauth/${encodeURIComponent(provider)}/start?lang=${lang}`);
    return;
  }

  const accountSocialReset = event.target.closest("[data-account-social-reset]");
  if (accountSocialReset) {
    await clearPendingSocialState();
    renderAccountMenu();
    return;
  }

  const agreementAllRequired = event.target.closest("[data-agreement-all-required]");
  if (agreementAllRequired) {
    const shell = agreementAllRequired.closest(".account-menu-shell");
    if (shell) {
      const nextChecked = agreementAllRequired.checked;
      shell.querySelectorAll(
        'input[name="terms_required"], input[name="privacy_required"], input[name="investment_notice_required"]',
      ).forEach((input) => {
        input.checked = nextChecked;
      });
    }
    return;
  }

  const accountLogout = event.target.closest("[data-account-logout]");
  if (accountLogout) {
    try {
      const payload = await requestJson("/api/platform/auth/logout", {
        method: "POST",
        body: JSON.stringify({}),
      });
      applyAccountPayload(payload, { preserveMessage: true });
      await syncCommunityState();
      renderApp();
      openAccountMenu("login", ui().accountSignedOutSuccessLabel, "success");
    } catch (error) {
      openAccountMenu("login", error.message || ui().accountPurchaseFailedLabel, "error");
    }
  }
});

el.composerKind.addEventListener("change", () => {
  updateComposerLevelLabels();
});

el.composerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = buildCommunityPostPayload();
  if (!payload) {
    state.composerMessage = ui().composerValidationMessage;
    state.composerMessageTone = "error";
    renderComposerControls();
    return;
  }

  try {
    const response = await requestJson("/api/platform/posts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.communityPosts.unshift(response.thread);
    state.composerMessage = ui().composerSuccessMessage;
    state.composerMessageTone = "success";
    resetComposerForm();
    await syncCommunityState();
    renderApp();
  } catch (error) {
    state.composerMessage = error.message || ui().composerValidationMessage;
    state.composerMessageTone = "error";
    renderComposerControls();
  }
});

el.aiRoundtableForm.addEventListener("submit", (event) => {
  event.preventDefault();
  openResearchFromQuery(el.aiRoundtableQuestion.value);
});

el.aiRoundtableTicker.addEventListener("input", (event) => {
  const nextTicker = normalizeTicker(event.target.value);
  if (!nextTicker) {
    return;
  }
  state.aiRoundtableTicker = nextTicker;
  if (state.aiRoundtableQuestionAuto) {
    state.aiRoundtableQuestion = defaultRoundtableQuestionForTicker(nextTicker);
    el.aiRoundtableQuestion.value = state.aiRoundtableQuestion;
  }
});

el.aiRoundtableQuestion.addEventListener("input", (event) => {
  state.aiRoundtableQuestionAuto = isAutoRoundtableQuestion(event.target.value);
  state.aiRoundtableQuestion = event.target.value;
  if (state.activeTab === "research") {
    setTopbarSearchValue(state.aiRoundtableQuestion);
  }
});

el.filterRow.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter]");
  if (!button) {
    return;
  }
  state.filterKind = button.dataset.filter;
  resetFeedWindow();
  renderFilters();
  renderStoryGrid();
  renderThreads();
});

el.scopeRow.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-scope]");
  if (!button) {
    return;
  }
  if (button.dataset.scope === "following" && button.dataset.scopeLocked === "true") {
    const unlocked = await handleCommerceAction("follow-pass");
    if (!unlocked || !hasFollowAccess()) {
      return;
    }
  }
  state.followingOnly = button.dataset.scope === "following";
  resetFeedWindow();
  renderScopeRow();
  renderStoryGrid();
  renderThreads();
  renderFollowingCard();
});

if (el.leaderboardMetricRow) {
  el.leaderboardMetricRow.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-rank-metric]");
    if (!button) {
      return;
    }

    const metric = button.dataset.rankMetric;
    const locked = button.dataset.rankLocked === "true";

    if (metric === "recent_return" && locked) {
      const unlocked = await handleCommerceAction("recent-rank");
      if (!unlocked || !hasRecentRankAccess()) {
        return;
      }
    }

    state.rankMetric = metric;
    renderLeaderboard();
    renderAuthorGrid();
    renderThreads();
  });
}

el.threadSearch.addEventListener("input", (event) => {
  const nextValue = event.target.value;
  state.aiRoundtableQuestion = nextValue;
  state.aiRoundtableQuestionAuto = isAutoRoundtableQuestion(nextValue);

  if (state.searchQuery) {
    state.searchQuery = "";
    resetFeedWindow();
    renderStoryGrid();
    renderThreads();
  }

  syncResearchInputsFromState();
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  if (target.name === "pack_id") {
    state.accountTopUpPackId = target.value;
    return;
  }
  if (target.name === "method") {
    state.accountTopUpMethod = target.value;
  }
});

el.globalSearchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = topbarSearchValue();
  if (!query) {
    return;
  }
  openResearchFromQuery(query);
});

document.addEventListener("submit", async (event) => {
  const adminAccessForm = event.target.closest?.("[data-admin-access-form]");
  if (adminAccessForm) {
    event.preventDefault();
    const formData = new FormData(adminAccessForm);
    const token = String(formData.get("admin_token") || "").trim();
    if (!token) {
      openAccountMenu(state.accountMenuMode, ui().accountAdminTokenRequiredLabel, "error");
      return;
    }
    try {
      const payload = await requestJson("/api/platform/admin/session", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      setStoredAdminToken("");
      window.location.assign(payload.redirect || adminDashboardUrl());
    } catch (error) {
      setStoredAdminToken("");
      openAccountMenu(state.accountMenuMode, error.message || ui().accountAdminTokenRequiredLabel, "error");
    }
    return;
  }

  const form = event.target.closest?.("[data-account-form]");
  if (form) {
    event.preventDefault();
    const formData = new FormData(form);
    const mode = form.dataset.accountForm || "login";
    const agreements = accountAgreementPayload(form);
    const endpoint = mode === "register"
      ? "/api/platform/auth/register"
      : mode === "social"
        ? "/api/platform/auth/social/complete"
        : "/api/platform/auth/login";
    const body = {
      email: String(formData.get("email") || "").trim(),
      password: String(formData.get("password") || ""),
    };
    if (mode === "register") {
      body.name = String(formData.get("name") || "").trim();
      body.agreements = agreements;
    }
    if (mode === "social") {
      body.provider = String(formData.get("provider") || "").trim();
      body.subject = String(formData.get("subject") || "").trim();
      body.name = String(formData.get("name") || "").trim();
      body.agreements = agreements;
      delete body.password;
    }

    try {
      const payload = await requestJson(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
      });
      applyAccountPayload(payload, { preserveMessage: true });
      if (mode === "social") {
        state.pendingSocialProfile = null;
        state.accountSocialProvider = "";
      }
      await syncCommunityState();
      renderApp();
      openAccountMenu(
        "login",
        mode === "register" || mode === "social" ? ui().accountRegisterSuccessLabel : ui().accountSignInSuccessLabel,
        "success",
      );
    } catch (error) {
      if (mode === "register" || mode === "social") {
        openAccountMenu("register", error.message || ui().accountAgreementRequiredError, "error");
      } else {
        openAccountMenu(mode, error.message || ui().accountPurchaseFailedLabel, "error");
      }
    }
    return;
  }

  const paymentRequestForm = event.target.closest?.("[data-payment-request-form]");
  if (paymentRequestForm) {
    event.preventDefault();
    const formData = new FormData(paymentRequestForm);
    try {
      const payload = await requestJson("/api/platform/commerce/payment-requests", {
        method: "POST",
        body: JSON.stringify({
          pack_id: String(formData.get("pack_id") || "").trim(),
          method: String(formData.get("method") || "").trim(),
          depositor_name: String(formData.get("depositor_name") || "").trim(),
          note: String(formData.get("note") || "").trim(),
        }),
      });
      state.accountTopUpPackId = String(formData.get("pack_id") || "").trim();
      state.accountTopUpMethod = String(formData.get("method") || "").trim();
      applyAccountPayload(payload, { preserveMessage: true });
      const latestRequest = payload.account?.payment_requests?.[0];
      const successMessage = latestRequest?.reference
        ? `${ui().accountTopUpRequestSuccessLabel} · ${latestRequest.reference}`
        : ui().accountTopUpRequestSuccessLabel;
      setAccountMessage(successMessage, "success");
      renderAccountMenu();
    } catch (error) {
      setAccountMessage(error.message || ui().accountTopUpRequestFailedLabel, "error");
      renderAccountMenu();
    }
    return;
  }

  const alertsForm = event.target.closest?.("[data-alert-preferences-form]");
  if (alertsForm) {
    event.preventDefault();
    const formData = new FormData(alertsForm);
    try {
      const payload = await requestJson("/api/platform/alerts/preferences", {
        method: "POST",
        body: JSON.stringify({
          preferences: {
            buy: formData.get("buy") === "on",
            watch: formData.get("watch") === "on",
            sell: formData.get("sell") === "on",
            research: formData.get("research") === "on",
          },
        }),
      });
      applyAccountPayload(payload, { preserveMessage: true });
      setAccountMessage(ui().accountAlertPreferencesSavedLabel, "success");
      renderAccountMenu();
    } catch (error) {
      setAccountMessage(error.message || ui().accountPurchaseFailedLabel, "error");
      renderAccountMenu();
    }
  }
});

document.addEventListener("click", async (event) => {
  const rankAuthorTarget = event.target.closest("[data-author-rank-focus]");
  if (rankAuthorTarget) {
    event.preventDefault();
    await openRankAuthorFeed(rankAuthorTarget.dataset.authorRankFocus);
    return;
  }

  const authorFocusTarget = event.target.closest("[data-author-focus]");
  if (authorFocusTarget) {
    event.preventDefault();
    focusAuthorPosts(authorFocusTarget.dataset.authorFocus);
    return;
  }

  const newsSelectTarget = event.target.closest("[data-news-select]");
  if (newsSelectTarget) {
    event.preventDefault();
    state.activeWorldNewsId = newsSelectTarget.dataset.newsSelect || "";
    renderThreads();
    return;
  }

  const premiumUnlockOne = event.target.closest("[data-premium-unlock]");
  if (premiumUnlockOne) {
    unlockPremiumSections([premiumUnlockOne.dataset.premiumUnlock]).catch((error) => {
      console.error("Premium unlock failed", error);
    });
    return;
  }

  const premiumModelTarget = event.target.closest("[data-premium-model]");
  if (premiumModelTarget) {
    state.aiPremiumActiveModelId = premiumModelTarget.dataset.premiumModel || state.aiPremiumActiveModelId;
    renderAiRoundtable();
    return;
  }

  const premiumUnlockAll = event.target.closest("[data-premium-unlock-all]");
  if (premiumUnlockAll) {
    const context = roundtableContext();
    const sections = premiumResearchSections(context, roundtableModelsWithResponses(context)).sections;
    unlockPremiumSections(sections.filter((section) => section.locked).map((section) => section.id)).catch((error) => {
      console.error("Premium unlock failed", error);
    });
    return;
  }

  const commerceTarget = event.target.closest("[data-commerce-open]");
  if (commerceTarget) {
    handleCommerceAction(commerceTarget.dataset.commerceOpen, {
      ticker: commerceTarget.dataset.commerceTicker,
      authorId: commerceTarget.dataset.commerceAuthor,
    }).catch((error) => {
      console.error("Commerce action failed", error);
    });
    return;
  }

  const contributionTarget = event.target.closest("[data-contribution-type]");
  if (contributionTarget) {
    state.contributionType = contributionTarget.dataset.contributionType || "question";
    renderContributionTypeRow();
    return;
  }

  const followTarget = event.target.closest("[data-follow-author]");
  if (followTarget) {
    toggleFollow(followTarget.dataset.followAuthor).catch((error) => {
      console.error("Follow update failed", error);
    });
    return;
  }

  const scopeTarget = event.target.closest("#following-card [data-scope]");
  if (scopeTarget) {
    if (scopeTarget.dataset.scope === "following" && scopeTarget.dataset.scopeLocked === "true") {
      const unlocked = await handleCommerceAction("follow-pass");
      if (!unlocked || !hasFollowAccess()) {
        return;
      }
    }
    state.followingOnly = scopeTarget.dataset.scope === "following";
    resetFeedWindow();
    renderScopeRow();
    renderStoryGrid();
    renderThreads();
    renderFollowingCard();
    return;
  }

  const feedLoadMoreTarget = event.target.closest("[data-feed-load-more]");
  if (feedLoadMoreTarget) {
    extendFeedWindow();
    renderThreads();
    return;
  }

  const threadTarget = event.target.closest("[data-thread-id]");
  if (threadTarget) {
    const threadId = threadTarget.dataset.threadId;
    if (state.expandedThreadIds.has(threadId)) {
      state.expandedThreadIds.delete(threadId);
    } else {
      state.expandedThreadIds.add(threadId);
    }
    renderThreads();
    return;
  }

  const aiQuestionTarget = event.target.closest("[data-ai-question]");
  if (aiQuestionTarget) {
    if (aiQuestionTarget.dataset.hotTicker) {
      state.aiRoundtableTicker = aiQuestionTarget.dataset.hotTicker;
      el.aiRoundtableTicker.value = state.aiRoundtableTicker;
    }
    state.aiRoundtableQuestion = aiQuestionTarget.dataset.aiQuestion || roundtableDefaultQuestion();
    state.aiRoundtableQuestionAuto = isAutoRoundtableQuestion(state.aiRoundtableQuestion);
    el.aiRoundtableQuestion.value = state.aiRoundtableQuestion;
    setActiveTab("research");
    setTopbarSearchValue(state.aiRoundtableQuestion);
    renderAiRoundtable();
    return;
  }

  const hotTickerTarget = event.target.closest("[data-hot-ticker]");
  if (hotTickerTarget) {
    state.aiRoundtableTicker = hotTickerTarget.dataset.hotTicker || state.aiRoundtableTicker;
    if (state.aiRoundtableQuestionAuto) {
      state.aiRoundtableQuestion = defaultRoundtableQuestionForTicker(state.aiRoundtableTicker);
    }
    el.aiRoundtableTicker.value = state.aiRoundtableTicker;
    syncResearchInputsFromState();
    setTopbarSearchValue(state.aiRoundtableQuestion);
    setActiveTab("research");
    renderAiRoundtable();
  }
});

document.addEventListener("keydown", (event) => {
  const rankAuthorTarget = event.target.closest?.("[data-author-rank-focus]");
  if (rankAuthorTarget && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    openRankAuthorFeed(rankAuthorTarget.dataset.authorRankFocus).catch((error) => {
      console.error("Rank author focus failed", error);
    });
    return;
  }

  const authorFocusTarget = event.target.closest?.("[data-author-focus]");
  if (!authorFocusTarget) {
    return;
  }

  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    focusAuthorPosts(authorFocusTarget.dataset.authorFocus);
  }
});

window.addEventListener("resize", () => {
  const nextMobile = window.innerWidth <= MOBILE_BREAKPOINT;
  if (nextMobile !== state.isMobile) {
    state.isMobile = nextMobile;
    if (state.feedVisibleCount < feedBatchSize()) {
      state.feedVisibleCount = feedBatchSize();
    }
    renderThreads();
  }
  scheduleCodeWallBuild();
  syncHudCursorMode();
});

init().catch((error) => {
  console.error("Platform init failed", error);
  markAppFailed("Could not load Signal Loom. Refresh and try again.");
});

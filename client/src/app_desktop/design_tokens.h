#pragma once

// M125 + M135: design system tokens for the Qt Widgets desktop client.
//
// M125 introduced a flat constexpr palette for the light theme. M135 wraps
// every color/spacing token into a `Theme` struct, ships both `kLightTheme`
// and `kDarkTheme` constants, and exposes `active_theme()` so the stylesheet
// builder can switch by reading `TELEGRAM_LIKE_THEME=light|dark` (env var).
// The previous flat `k*` constants are kept as aliases pointing at the
// active theme's fields so existing call sites compile unchanged.

#include <QColor>
#include <QString>
#include <cstdlib>
#include <cstring>

namespace telegram_like::client::app_desktop::design {

struct Theme {
    // App + container surfaces
    const char* app_background;
    const char* surface;
    const char* surface_muted;
    const char* chat_area;
    const char* border;
    const char* border_subtle;
    const char* border_input;
    const char* splitter;
    const char* selection_tint;
    const char* hover;

    // Brand + accents
    const char* primary;
    const char* primary_hover;
    const char* primary_disabled;
    const char* primary_ghost_hover;
    const char* secondary_header_tint;
    const char* in_chat_search_bg;

    // Text
    const char* text_primary;
    const char* text_secondary;
    const char* text_muted;
    const char* text_disabled;

    // Message bubbles (M137 will start using these for Telegram-style polish).
    // own_bubble_top + own_bubble_bottom drive the right-side gradient;
    // peer_bubble is the flat fill on the left.
    const char* own_bubble_top;
    const char* own_bubble_bottom;
    const char* own_bubble_text;
    const char* peer_bubble;
    const char* peer_bubble_text;
    const char* tick_unread;
    const char* tick_read;
};

// ---- light theme — the existing Telegram-Web-Z baseline ----
inline constexpr Theme kLightTheme = {
    /* app_background        */ "#f4f5f7",
    /* surface               */ "#ffffff",
    /* surface_muted         */ "#fafbfc",
    /* chat_area             */ "#e6ebee",
    /* border                */ "#e6e8eb",
    /* border_subtle         */ "#eef0f2",
    /* border_input          */ "#d8dde2",
    /* splitter              */ "#e1e4e8",
    /* selection_tint        */ "#e7f0fb",
    /* hover                 */ "#f0f3f6",
    /* primary               */ "#3390ec",
    /* primary_hover         */ "#2079d2",
    /* primary_disabled      */ "#a8c8ec",
    /* primary_ghost_hover   */ "#eaf3fc",
    /* secondary_header_tint */ "#f7f8fa",
    /* in_chat_search_bg     */ "#f4f6f8",
    /* text_primary          */ "#0f1419",
    /* text_secondary        */ "#3a4853",
    /* text_muted            */ "#7c8a96",
    /* text_disabled         */ "#9aa3ab",
    /* own_bubble_top        */ "#5eb5f7",
    /* own_bubble_bottom     */ "#3390ec",
    /* own_bubble_text       */ "#ffffff",
    /* peer_bubble           */ "#ffffff",
    /* peer_bubble_text      */ "#0f1419",
    /* tick_unread           */ "#a8c8ec",
    /* tick_read             */ "#3390ec",
};

// ---- dark theme — Telegram desktop "Night" inspired ----
//
// Anchors:
// - app shell: very dark slate (#17212b → #0e1621 sidebar)
// - chat area: #0e1621 (deep) so own gradient pops on top of it
// - own bubble: same brand blue gradient as light, since brand carries across themes
// - peer bubble: #182533 (slightly lighter than chat area for contrast)
// - text: near-white primary, mid-grey secondary
inline constexpr Theme kDarkTheme = {
    /* app_background        */ "#0e1621",
    /* surface               */ "#17212b",
    /* surface_muted         */ "#1c2734",
    /* chat_area             */ "#0e1621",
    /* border                */ "#243240",
    /* border_subtle         */ "#1f2c39",
    /* border_input          */ "#2a3a4b",
    /* splitter              */ "#243240",
    /* selection_tint        */ "#2b5278",
    /* hover                 */ "#202b38",
    /* primary               */ "#3390ec",
    /* primary_hover         */ "#5eb5f7",
    /* primary_disabled      */ "#1f3b58",
    /* primary_ghost_hover   */ "#1c2c3e",
    /* secondary_header_tint */ "#17212b",
    /* in_chat_search_bg     */ "#1c2734",
    /* text_primary          */ "#e9edef",
    /* text_secondary        */ "#aebac1",
    /* text_muted            */ "#7c8a96",
    /* text_disabled         */ "#5d6b78",
    /* own_bubble_top        */ "#5eb5f7",
    /* own_bubble_bottom     */ "#3390ec",
    /* own_bubble_text       */ "#ffffff",
    /* peer_bubble           */ "#182533",
    /* peer_bubble_text      */ "#e9edef",
    /* tick_unread           */ "#7c8a96",
    /* tick_read             */ "#5eb5f7",
};

// Resolve the active theme. M135 originally cached lazily and was set in
// stone for the process lifetime; M139 makes the cache mutable so the
// Appearance settings page can flip between light + dark at runtime by
// calling `set_active_theme(...)` then re-applying the QApplication
// stylesheet + rendering the bubble view. The env-var seed only fires the
// first time `active_theme()` runs.
namespace detail {
    inline const Theme*& theme_cache_ref() {
        static const Theme* cached = nullptr;
        return cached;
    }
}

inline const Theme& active_theme() {
    auto& cached = detail::theme_cache_ref();
    if (cached != nullptr) return *cached;
    const char* raw = std::getenv("TELEGRAM_LIKE_THEME");
    bool is_dark = false;
    if (raw != nullptr) {
        // Tiny case-insensitive match to "dark" — avoid pulling <string>.
        is_dark =
            (raw[0] == 'd' || raw[0] == 'D') &&
            (raw[1] == 'a' || raw[1] == 'A') &&
            (raw[2] == 'r' || raw[2] == 'R') &&
            (raw[3] == 'k' || raw[3] == 'K') &&
            raw[4] == '\0';
    }
    cached = is_dark ? &kDarkTheme : &kLightTheme;
    return *cached;
}

// Runtime override called from the Appearance settings page. Caller must
// re-invoke whatever stylesheet/render path consumes `active_theme()`.
inline void set_active_theme(bool dark) {
    detail::theme_cache_ref() = dark ? &kDarkTheme : &kLightTheme;
}

inline bool is_dark_theme() {
    return &active_theme() == &kDarkTheme;
}

// ---- backwards-compat aliases for M125 callers ----
//
// Existing code uses `dt::kAppBackground` etc. as constexpr `const char*`.
// Implementation note: `active_theme()` is per-process-cached and never
// changes after the first read, so these aliases are stable references for
// the lifetime of the process. They cannot be `constexpr` anymore (the
// theme is selected at runtime), but they remain trivially cheap.
#define TELEGRAM_LIKE_THEME_ALIAS(name) \
    inline const char* k##name = active_theme().name;

TELEGRAM_LIKE_THEME_ALIAS(app_background)
TELEGRAM_LIKE_THEME_ALIAS(surface)
TELEGRAM_LIKE_THEME_ALIAS(surface_muted)
TELEGRAM_LIKE_THEME_ALIAS(chat_area)
TELEGRAM_LIKE_THEME_ALIAS(border)
TELEGRAM_LIKE_THEME_ALIAS(border_subtle)
TELEGRAM_LIKE_THEME_ALIAS(border_input)
TELEGRAM_LIKE_THEME_ALIAS(splitter)
TELEGRAM_LIKE_THEME_ALIAS(selection_tint)
TELEGRAM_LIKE_THEME_ALIAS(hover)
TELEGRAM_LIKE_THEME_ALIAS(primary)
TELEGRAM_LIKE_THEME_ALIAS(primary_hover)
TELEGRAM_LIKE_THEME_ALIAS(primary_disabled)
TELEGRAM_LIKE_THEME_ALIAS(primary_ghost_hover)
TELEGRAM_LIKE_THEME_ALIAS(secondary_header_tint)
TELEGRAM_LIKE_THEME_ALIAS(in_chat_search_bg)
TELEGRAM_LIKE_THEME_ALIAS(text_primary)
TELEGRAM_LIKE_THEME_ALIAS(text_secondary)
TELEGRAM_LIKE_THEME_ALIAS(text_muted)
TELEGRAM_LIKE_THEME_ALIAS(text_disabled)

// Pre-existing names in PascalCase (kAppBackground -> app_background) are
// what the existing call sites use; the alias macro above gives us
// `kapp_background` instead. Provide explicit camelCase aliases too so we
// don't have to rewrite every call site in this milestone. M137 (bubble
// polish) and later milestones can migrate gradually.
inline const char* kAppBackground       = active_theme().app_background;
inline const char* kSurface             = active_theme().surface;
inline const char* kSurfaceMuted        = active_theme().surface_muted;
inline const char* kChatArea            = active_theme().chat_area;
inline const char* kBorder              = active_theme().border;
inline const char* kBorderSubtle        = active_theme().border_subtle;
inline const char* kBorderInput         = active_theme().border_input;
inline const char* kSplitter            = active_theme().splitter;
inline const char* kSelectionTint       = active_theme().selection_tint;
inline const char* kHover               = active_theme().hover;
inline const char* kPrimary             = active_theme().primary;
inline const char* kPrimaryHover        = active_theme().primary_hover;
inline const char* kPrimaryDisabled     = active_theme().primary_disabled;
inline const char* kPrimaryGhostHover   = active_theme().primary_ghost_hover;
inline const char* kSecondaryHeaderTint = active_theme().secondary_header_tint;
inline const char* kInChatSearchBg      = active_theme().in_chat_search_bg;
inline const char* kTextPrimary         = active_theme().text_primary;
inline const char* kTextSecondary       = active_theme().text_secondary;
inline const char* kTextMuted           = active_theme().text_muted;
inline const char* kTextDisabled        = active_theme().text_disabled;

// Bubble tokens (M135 introduces; M137 starts using).
inline const char* kOwnBubbleTop        = active_theme().own_bubble_top;
inline const char* kOwnBubbleBottom     = active_theme().own_bubble_bottom;
inline const char* kOwnBubbleText       = active_theme().own_bubble_text;
inline const char* kPeerBubble          = active_theme().peer_bubble;
inline const char* kPeerBubbleText      = active_theme().peer_bubble_text;
inline const char* kTickUnread          = active_theme().tick_unread;
inline const char* kTickRead            = active_theme().tick_read;

// ---- avatar palette (deterministic per-seed selection) ----
inline const QColor kAvatarPalette[] = {
    QColor("#e17076"), QColor("#7bc862"), QColor("#65aadd"),
    QColor("#a695e7"), QColor("#ee7aae"), QColor("#6ec9cb"),
    QColor("#faa774"), QColor("#7d8ea0"),
};

// ---- typography ----
constexpr const char* kFontStack = "'Segoe UI','Helvetica Neue',sans-serif";
constexpr int kFontPxBase     = 13;
constexpr int kFontPxHeading  = 18;
constexpr int kFontPxLabel    = 11;
constexpr int kFontPxSubtitle = 11;

// ---- spacing / radius ----
constexpr int kRadiusSmall  = 6;
constexpr int kRadiusMedium = 8;
constexpr int kRadiusLarge  = 10;

}  // namespace telegram_like::client::app_desktop::design

#pragma once

// M125: design system tokens for the Qt Widgets desktop client.
//
// Centralizes the colors + spacing the QSS stylesheet was previously
// inlining as hex literals. Adding a token here and referencing it from
// telegram_stylesheet() lets a UI tweak land in one place instead of N
// scattered string concatenations. Kept as constexpr so the optimizer can
// fold the strings into the QStringLiteral concatenation site.

#include <QColor>
#include <QString>

namespace telegram_like::client::app_desktop::design {

// ---- palette (light theme — matches the Telegram-style baseline) ----
constexpr const char* kAppBackground       = "#f4f5f7";
constexpr const char* kSurface             = "#ffffff";
constexpr const char* kSurfaceMuted        = "#fafbfc";
constexpr const char* kChatArea            = "#e6ebee";
constexpr const char* kBorder              = "#e6e8eb";
constexpr const char* kBorderSubtle        = "#eef0f2";
constexpr const char* kBorderInput         = "#d8dde2";
constexpr const char* kSplitter            = "#e1e4e8";
constexpr const char* kSelectionTint       = "#e7f0fb";
constexpr const char* kHover               = "#f0f3f6";
constexpr const char* kPrimary             = "#3390ec";
constexpr const char* kPrimaryHover        = "#2079d2";
constexpr const char* kPrimaryDisabled     = "#a8c8ec";
constexpr const char* kPrimaryGhostHover   = "#eaf3fc";
constexpr const char* kSecondaryHeaderTint = "#f7f8fa";
constexpr const char* kInChatSearchBg      = "#f4f6f8";
constexpr const char* kTextPrimary         = "#0f1419";
constexpr const char* kTextSecondary       = "#3a4853";
constexpr const char* kTextMuted           = "#7c8a96";
constexpr const char* kTextDisabled        = "#9aa3ab";

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

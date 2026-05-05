// M136: shared theme tokens for the mobile QML UI.
//
// Mirrors client/src/app_desktop/design_tokens.h so a single visual change
// can be made in two trivially-diffable files. Each page accesses tokens
// via `theme.<name>` where `theme` is the Theme instance hung off the root
// ApplicationWindow in Main.qml.
//
// Dark mode is gated by `darkMode` — set true to flip every token below
// to its dark counterpart in one place. Main.qml reads the same
// `TELEGRAM_LIKE_THEME=dark` env var the desktop app uses, and toggles
// `darkMode` accordingly so the desktop preview and the Android APK pick
// up the same theme without the QML files knowing how the choice was made.

import QtQuick

QtObject {
    id: root

    // ---- toggle ----
    property bool darkMode: false

    // ---- light palette (Telegram-like baseline; matches desktop kLightTheme) ----
    readonly property color lightAppBackground:      "#f2f3f5"
    readonly property color lightSurface:            "#ffffff"
    readonly property color lightSurfaceMuted:       "#fafbfc"
    readonly property color lightChatArea:           "#d9e7bd"
    readonly property color lightBorder:             "#e6e8eb"
    readonly property color lightBorderSubtle:       "#eef0f2"
    readonly property color lightSelectionTint:      "#e7f0fb"
    readonly property color lightHover:              "#f0f3f6"
    readonly property color lightTextPrimary:        "#0f1419"
    readonly property color lightTextSecondary:      "#3a4853"
    readonly property color lightTextMuted:          "#7c8a96"
    readonly property color lightOwnBubbleTop:       "#5eb5f7"
    readonly property color lightOwnBubbleBottom:    "#3390ec"
    readonly property color lightOwnBubbleText:      "#ffffff"
    readonly property color lightPeerBubble:         "#ffffff"
    readonly property color lightPeerBubbleText:     "#0f1419"
    readonly property color lightTickUnread:         "#a8c8ec"
    readonly property color lightTickRead:           "#3390ec"

    // ---- dark palette (matches desktop kDarkTheme) ----
    readonly property color darkAppBackground:       "#0e1621"
    readonly property color darkSurface:             "#17212b"
    readonly property color darkSurfaceMuted:        "#1c2734"
    readonly property color darkChatArea:            "#0e1621"
    readonly property color darkBorder:              "#243240"
    readonly property color darkBorderSubtle:        "#1f2c39"
    readonly property color darkSelectionTint:       "#2b5278"
    readonly property color darkHover:               "#202b38"
    readonly property color darkTextPrimary:         "#e9edef"
    readonly property color darkTextSecondary:       "#aebac1"
    readonly property color darkTextMuted:           "#7c8a96"
    readonly property color darkOwnBubbleTop:        "#5eb5f7"
    readonly property color darkOwnBubbleBottom:     "#3390ec"
    readonly property color darkOwnBubbleText:       "#ffffff"
    readonly property color darkPeerBubble:          "#182533"
    readonly property color darkPeerBubbleText:      "#e9edef"
    readonly property color darkTickUnread:          "#7c8a96"
    readonly property color darkTickRead:            "#5eb5f7"

    // ---- brand (stable across themes — Telegram keeps the accent constant) ----
    readonly property color primary:                 "#3390ec"
    readonly property color primaryHover:            "#2079d2"

    // ---- active palette (resolved from darkMode so consumers stay simple) ----
    readonly property color appBackground:    darkMode ? darkAppBackground   : lightAppBackground
    readonly property color surface:          darkMode ? darkSurface         : lightSurface
    readonly property color surfaceMuted:     darkMode ? darkSurfaceMuted    : lightSurfaceMuted
    readonly property color chatArea:         darkMode ? darkChatArea        : lightChatArea
    readonly property color border:           darkMode ? darkBorder          : lightBorder
    readonly property color borderSubtle:     darkMode ? darkBorderSubtle    : lightBorderSubtle
    readonly property color selectionTint:    darkMode ? darkSelectionTint   : lightSelectionTint
    readonly property color hover:            darkMode ? darkHover           : lightHover
    readonly property color textPrimary:      darkMode ? darkTextPrimary     : lightTextPrimary
    readonly property color textSecondary:    darkMode ? darkTextSecondary   : lightTextSecondary
    readonly property color textMuted:        darkMode ? darkTextMuted       : lightTextMuted
    readonly property color ownBubbleTop:     darkMode ? darkOwnBubbleTop    : lightOwnBubbleTop
    readonly property color ownBubbleBottom:  darkMode ? darkOwnBubbleBottom : lightOwnBubbleBottom
    readonly property color ownBubbleText:    darkMode ? darkOwnBubbleText   : lightOwnBubbleText
    readonly property color peerBubble:       darkMode ? darkPeerBubble      : lightPeerBubble
    readonly property color peerBubbleText:   darkMode ? darkPeerBubbleText  : lightPeerBubbleText
    readonly property color tickUnread:       darkMode ? darkTickUnread      : lightTickUnread
    readonly property color tickRead:         darkMode ? darkTickRead        : lightTickRead
}

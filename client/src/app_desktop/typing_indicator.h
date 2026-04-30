#pragma once

// M140: animated three-dot "typing..." indicator for the chat header.
//
// Pure UI primitive — paints three pulsing dots beside an optional label
// ("X is typing"). Activated via setActive(...) and stays visible until
// setActive() is called with active=false. The animation runs on a
// QTimer; widget hides itself when inactive so the chat header layout
// reclaims space.
//
// Real protocol integration (TYPING_START / TYPING_STOP fanout) is a
// separate milestone — this primitive is the UI half, designed so the
// fanout can hook in by simply calling setActive(peer, true|false) when
// the next backend pulse arrives. For visual development the env var
// TELEGRAM_LIKE_DEMO_TYPING=1 activates a self-cycling demo at startup.

#include <QString>
#include <QWidget>

class QTimer;

namespace telegram_like::client::app_desktop {

class TypingIndicator : public QWidget {
    Q_OBJECT
public:
    explicit TypingIndicator(QWidget* parent = nullptr);

    // Show "X is typing" with the pulsing dots. Pass an empty QString
    // to drop the label and just paint the dots (e.g. group chat
    // "Several people typing" without naming them).
    void setActive(const QString& peer_name, bool active);
    [[nodiscard]] bool active() const { return active_; }
    [[nodiscard]] QString peerName() const { return peer_name_; }

    // Color overrides driven by the theme; called from render_store()
    // on every repaint pass so dark/light flips immediately.
    void setDotColor(const QColor& color);
    void setLabelColor(const QColor& color);

protected:
    void paintEvent(QPaintEvent* event) override;
    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

private:
    void onTick();

    bool active_ {false};
    QString peer_name_;
    int phase_ {0};               // 0..2 — which dot peaks this frame
    QTimer* timer_ {nullptr};
    QColor dot_color_;
    QColor label_color_;
};

}  // namespace telegram_like::client::app_desktop

#include "app_desktop/typing_indicator.h"

#include <QFont>
#include <QFontMetrics>
#include <QPainter>
#include <QTimer>

namespace telegram_like::client::app_desktop {

namespace {
constexpr int kDotRadius = 3;     // px
constexpr int kDotGap    = 4;     // px between dots
constexpr int kLabelGap  = 8;     // px between label and dots
constexpr int kFrameMs   = 220;   // animation step
constexpr int kPhases    = 3;     // 3 dots
}  // namespace

TypingIndicator::TypingIndicator(QWidget* parent)
    : QWidget(parent),
      timer_(new QTimer(this)),
      dot_color_(QStringLiteral("#7c8a96")),
      label_color_(QStringLiteral("#7c8a96")) {
    timer_->setInterval(kFrameMs);
    QObject::connect(timer_, &QTimer::timeout, this, &TypingIndicator::onTick);
    setAttribute(Qt::WA_TranslucentBackground);
    setVisible(false);
}

void TypingIndicator::setActive(const QString& peer_name, bool active) {
    if (peer_name_ != peer_name) peer_name_ = peer_name;
    if (active_ == active) {
        update();
        return;
    }
    active_ = active;
    if (active_) {
        phase_ = 0;
        timer_->start();
    } else {
        timer_->stop();
    }
    setVisible(active_);
    updateGeometry();
    update();
}

void TypingIndicator::setDotColor(const QColor& color) {
    if (dot_color_ != color) {
        dot_color_ = color;
        update();
    }
}

void TypingIndicator::setLabelColor(const QColor& color) {
    if (label_color_ != color) {
        label_color_ = color;
        update();
    }
}

void TypingIndicator::onTick() {
    phase_ = (phase_ + 1) % kPhases;
    update();
}

QSize TypingIndicator::sizeHint() const {
    QFont f(QStringLiteral("Segoe UI"));
    f.setPixelSize(11);
    QFontMetrics fm(f);
    const int label_w = peer_name_.isEmpty()
        ? 0
        : fm.horizontalAdvance(QStringLiteral("%1 is typing").arg(peer_name_)) + kLabelGap;
    const int dots_w = kPhases * (kDotRadius * 2) + (kPhases - 1) * kDotGap;
    const int h = std::max(static_cast<int>(fm.height()), kDotRadius * 2 + 2);
    return QSize(label_w + dots_w + 4, h);
}

QSize TypingIndicator::minimumSizeHint() const {
    return sizeHint();
}

void TypingIndicator::paintEvent(QPaintEvent*) {
    if (!active_) return;
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    int x = 0;
    if (!peer_name_.isEmpty()) {
        QFont f(QStringLiteral("Segoe UI"));
        f.setPixelSize(11);
        p.setFont(f);
        p.setPen(label_color_);
        const QString text = QStringLiteral("%1 is typing").arg(peer_name_);
        QFontMetrics fm(f);
        p.drawText(0, fm.ascent(), text);
        x = fm.horizontalAdvance(text) + kLabelGap;
    }

    const int cy = height() / 2;
    p.setPen(Qt::NoPen);
    for (int i = 0; i < kPhases; ++i) {
        // Dot at index `phase_` peaks (full opacity); the others fade.
        const int dist = std::abs(i - phase_);
        const int alpha = dist == 0 ? 230 : (dist == 1 ? 140 : 80);
        QColor c = dot_color_;
        c.setAlpha(alpha);
        p.setBrush(c);
        const int cx = x + kDotRadius + i * (kDotRadius * 2 + kDotGap);
        p.drawEllipse(QPoint(cx, cy), kDotRadius, kDotRadius);
    }
}

}  // namespace telegram_like::client::app_desktop

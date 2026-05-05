#include "app_desktop/bubble_list_view.h"

#include <QContextMenuEvent>
#include <QDateTime>
#include <QFont>
#include <QFontMetrics>
#include <QLinearGradient>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>

#include <algorithm>
#include <cstddef>

namespace telegram_like::client::app_desktop {

namespace {

constexpr int kRowMargin       = 8;     // vertical padding above + below the bubble row
constexpr int kSideMargin      = 12;    // left/right edge of the row
constexpr int kAvatarSize      = 32;
constexpr int kAvatarBubbleGap = 8;
constexpr int kBubblePaddingX  = 12;
constexpr int kBubblePaddingY  = 8;
constexpr int kBubbleRadius    = 12;
constexpr int kMinBubbleWidth  = 96;
constexpr double kMaxBubbleRatio = 0.72;

// Stable 8-color avatar palette (matches the existing design::kAvatarPalette).
QColor avatar_color_for(const QString& seed) {
    static const QColor palette[] = {
        QColor("#e17076"), QColor("#7bc862"), QColor("#65aadd"),
        QColor("#a695e7"), QColor("#ee7aae"), QColor("#6ec9cb"),
        QColor("#faa774"), QColor("#7d8ea0"),
    };
    if (seed.isEmpty()) return palette[0];
    unsigned hash = 0;
    for (QChar ch : seed) hash = hash * 31u + static_cast<unsigned>(ch.unicode());
    return palette[hash % (sizeof(palette) / sizeof(palette[0]))];
}

QString initials_for(const QString& seed) {
    if (seed.isEmpty()) return QStringLiteral("?");
    QString out;
    out += seed.at(0).toUpper();
    int sp = seed.indexOf(QLatin1Char(' '));
    if (sp < 0) sp = seed.indexOf(QLatin1Char('_'));
    if (sp >= 0 && sp + 1 < seed.size()) out += seed.at(sp + 1).toUpper();
    return out;
}

QFont base_font(int px = 11, bool bold = false, bool italic = false) {
    QFont f(QStringLiteral("Segoe UI"));
    f.setPixelSize(px);
    f.setBold(bold);
    f.setItalic(italic);
    return f;
}

}  // namespace

// ============================================================
// BubbleMessageModel
// ============================================================

BubbleMessageModel::BubbleMessageModel(QObject* parent)
    : QAbstractListModel(parent) {}

void BubbleMessageModel::setData(const DesktopChatStore* store,
                                 const std::string& current_user_id) {
    beginResetModel();
    store_ = store;
    current_user_id_ = current_user_id;
    messages_.clear();
    conversation_id_.clear();
    if (store_ != nullptr) {
        if (const auto* conv = store_->selected_conversation()) {
            conversation_id_ = conv->conversation_id;
            // Cap to the last 200 to keep the view responsive without
            // constraining real-world chat history. The previous HTML
            // renderer capped at 100; bumped because the new delegate
            // handles thousands of items via virtual scrolling cheaply.
            const std::size_t total = conv->messages.size();
            const std::size_t tail = total > 200 ? total - 200 : 0;
            messages_.assign(conv->messages.begin() + static_cast<std::ptrdiff_t>(tail),
                             conv->messages.end());
        }
    }
    endResetModel();
}

void BubbleMessageModel::setThumbnailCache(const QHash<QString, QPixmap>& thumbnails) {
    thumbnails_ = thumbnails;
    if (!messages_.empty()) {
        emit dataChanged(index(0), index(static_cast<int>(messages_.size()) - 1),
                         {ThumbnailRole});
    }
}

void BubbleMessageModel::setSearchHighlight(const QString& search_query,
                                            const QString& focused_message_id) {
    if (search_query == search_query_ && focused_message_id == focused_message_id_) return;
    search_query_ = search_query;
    focused_message_id_ = focused_message_id;
    if (!messages_.empty()) {
        emit dataChanged(index(0), index(static_cast<int>(messages_.size()) - 1),
                         {MatchRole, FocusedRole});
    }
}

int BubbleMessageModel::rowCount(const QModelIndex& parent) const {
    if (parent.isValid()) return 0;
    return static_cast<int>(messages_.size());
}

QVariant BubbleMessageModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid()) return {};
    const auto row = index.row();
    if (row < 0 || row >= static_cast<int>(messages_.size())) return {};
    const auto& m = messages_[static_cast<std::size_t>(row)];
    switch (role) {
        case MessageIdRole:    return QString::fromStdString(m.message_id);
        case OutgoingRole:     return (m.sender_user_id == current_user_id_);
        case SenderRole:       return QString::fromStdString(m.sender_user_id);
        case TextRole:         return QString::fromStdString(m.text);
        case CreatedAtMsRole:  return static_cast<qlonglong>(m.created_at_ms);
        case TickRole: {
            if (store_ == nullptr) return QString();
            return QString::fromStdString(store_->delivery_tick(conversation_id_, m.message_id));
        }
        case EditedRole:       return m.edited;
        case DeletedRole:      return m.deleted;
        case ReplyToRole:      return QString::fromStdString(m.reply_to_message_id);
        case ReplyToTextRole: {
            // Look up the replied message's text in our local snapshot. If
            // it's older than the cap or in another conversation we just
            // display the message id — better than blanking the quote.
            const auto target = m.reply_to_message_id;
            if (target.empty()) return QString();
            for (const auto& other : messages_) {
                if (other.message_id == target) {
                    return QString::fromStdString(other.text);
                }
            }
            return QString::fromStdString(std::string("(") + target + ")");
        }
        case ForwardedFromRole: {
            if (m.forwarded_from_message_id.empty()) return QString();
            std::string s = m.forwarded_from_sender_user_id.empty()
                ? m.forwarded_from_conversation_id
                : m.forwarded_from_sender_user_id;
            return QString::fromStdString(s);
        }
        case ReactionsRole:    return QString::fromStdString(m.reaction_summary);
        case PinnedRole:       return m.pinned;
        case FailedRole:       return (m.delivery_state == "failed");
        case PendingRole:      return (m.delivery_state == "pending");
        case AvatarSeedRole:   return QString::fromStdString(m.sender_user_id);
        case FocusedRole:
            return !focused_message_id_.isEmpty()
                && focused_message_id_ == QString::fromStdString(m.message_id);
        case MatchRole: {
            if (search_query_.isEmpty()) return false;
            return QString::fromStdString(m.text).contains(search_query_, Qt::CaseInsensitive);
        }
        case AttachmentIdRole: return QString::fromStdString(m.attachment_id);
        case AttachmentMimeRole: return QString::fromStdString(m.mime_type);
        case FilenameRole: return QString::fromStdString(m.filename);
        case SizeBytesRole: return QVariant::fromValue<qlonglong>(m.size_bytes);
        case ThumbnailRole: {
            if (m.attachment_id.empty()) return QVariant::fromValue(QPixmap());
            const QString key = QString::fromStdString(m.attachment_id);
            auto it = thumbnails_.find(key);
            if (it == thumbnails_.end()) return QVariant::fromValue(QPixmap());
            return QVariant::fromValue(it.value());
        }
        default:               return {};
    }
}

QHash<int, QByteArray> BubbleMessageModel::roleNames() const {
    return {
        {MessageIdRole,     "messageId"},
        {OutgoingRole,      "outgoing"},
        {SenderRole,        "sender"},
        {TextRole,          "text"},
        {CreatedAtMsRole,   "createdAtMs"},
        {TickRole,          "tick"},
        {EditedRole,        "edited"},
        {DeletedRole,       "deleted"},
        {ReplyToRole,       "replyTo"},
        {ReplyToTextRole,   "replyToText"},
        {ForwardedFromRole, "forwardedFrom"},
        {ReactionsRole,     "reactions"},
        {PinnedRole,        "pinned"},
        {FailedRole,        "failed"},
        {PendingRole,       "pending"},
        {AvatarSeedRole,    "avatarSeed"},
        {FocusedRole,       "focused"},
        {MatchRole,         "match"},
        {AttachmentIdRole,  "attachmentId"},
        {AttachmentMimeRole,"attachmentMime"},
        {FilenameRole,      "filename"},
        {SizeBytesRole,     "sizeBytes"},
        {ThumbnailRole,     "thumbnail"},
    };
}

QString BubbleMessageModel::messageIdAt(int row) const {
    if (row < 0 || row >= static_cast<int>(messages_.size())) return {};
    return QString::fromStdString(messages_[static_cast<std::size_t>(row)].message_id);
}


// ============================================================
// BubbleDelegate
// ============================================================

BubbleDelegate::BubbleDelegate(QObject* parent) : QStyledItemDelegate(parent) {}

void BubbleDelegate::setPalette(const DesktopBubblePalette& palette) {
    palette_ = palette;
}

int BubbleDelegate::maxBubbleContentWidth(int viewportWidth) const {
    int w = static_cast<int>(viewportWidth * kMaxBubbleRatio) - 2 * kSideMargin
            - kAvatarSize - kAvatarBubbleGap;
    return std::max(kMinBubbleWidth, w);
}

QString BubbleDelegate::tickGlyph(const QString& tick) const {
    if (tick == QLatin1String("pending")) return QString::fromUtf8("\xe2\x8c\x9b");        // ⌛
    if (tick == QLatin1String("failed"))  return QString::fromUtf8("\xe2\x9c\x95");        // ✕
    if (tick == QLatin1String("read"))    return QString::fromUtf8("\xe2\x9c\x93\xe2\x9c\x93"); // ✓✓
    if (tick == QLatin1String("sent"))    return QString::fromUtf8("\xe2\x9c\x93");        // ✓
    return QString();
}

QString BubbleDelegate::formatTime(qint64 ms) const {
    if (ms <= 0) return QStringLiteral("legacy");
    return QDateTime::fromMSecsSinceEpoch(ms).toString(QStringLiteral("HH:mm"));
}

BubbleDelegate::LayoutMetrics BubbleDelegate::measure(const QModelIndex& index,
                                                      int viewportWidth) const {
    LayoutMetrics m;
    const int contentMax = maxBubbleContentWidth(viewportWidth);

    const bool outgoing = index.data(BubbleMessageModel::OutgoingRole).toBool();
    const QString text = index.data(BubbleMessageModel::TextRole).toString();
    const QString sender = index.data(BubbleMessageModel::SenderRole).toString();
    const QString replyTo = index.data(BubbleMessageModel::ReplyToRole).toString();
    const QString replyToText = index.data(BubbleMessageModel::ReplyToTextRole).toString();
    const QString forwarded = index.data(BubbleMessageModel::ForwardedFromRole).toString();
    const QString reactions = index.data(BubbleMessageModel::ReactionsRole).toString();
    const QString filename = index.data(BubbleMessageModel::FilenameRole).toString();
    const QString mimeType = index.data(BubbleMessageModel::AttachmentMimeRole).toString();
    const bool deleted = index.data(BubbleMessageModel::DeletedRole).toBool();
    const bool edited = index.data(BubbleMessageModel::EditedRole).toBool();
    const bool pinned = index.data(BubbleMessageModel::PinnedRole).toBool();
    const bool systemMessage = text.startsWith(QStringLiteral("[system]"));
    const bool pollMessage = text.startsWith(QStringLiteral("[poll]"));

    // Section heights — rough but consistent with paint().
    if (!outgoing && !sender.isEmpty()) m.senderHeight = 14;
    if (!forwarded.isEmpty())           m.forwardedHeight = 14;
    if (!replyTo.isEmpty())             m.replyHeight = 30;
    if (pinned)                         m.pinnedHeight = 12;
    if (systemMessage)                  m.systemHeight = 30;

    // M148: image thumbnail occupies the top of the bubble content area.
    // Cap at 240 wide × 240 tall, scaled with KeepAspectRatio so the
    // shape mirrors Telegram desktop (square-ish for landscape, taller
    // for portrait).
    const QPixmap thumb = index.data(BubbleMessageModel::ThumbnailRole).value<QPixmap>();
    if (!thumb.isNull()) {
        const int maxW = std::min(240, contentMax);
        const int maxH = 240;
        const QSize scaled = thumb.size().scaled(QSize(maxW, maxH),
                                                  Qt::KeepAspectRatio);
        m.thumbnailWidth  = scaled.width();
        m.thumbnailHeight = scaled.height() + 6;  // 6px gap below image
    }
    if (!filename.isEmpty() && !mimeType.startsWith(QStringLiteral("image/"))) {
        m.fileCardHeight = 48;
    }
    if (pollMessage) {
        m.pollCardHeight = 76;
    }

    QString shownText = deleted ? QStringLiteral("<deleted>") : text;
    if (edited) shownText += QStringLiteral(" (edited)");
    QFontMetrics fm(base_font(13));
    QRect textRect = fm.boundingRect(QRect(0, 0, contentMax, 1),
                                     Qt::TextWordWrap, shownText);
    m.textHeight = std::max(textRect.height(), fm.lineSpacing());
    int textWidth = std::min(contentMax, std::max(kMinBubbleWidth, textRect.width()));

    if (!reactions.isEmpty()) m.reactionsHeight = 22;

    int contentHeight = m.senderHeight + m.forwardedHeight + m.replyHeight
                        + m.pinnedHeight + m.thumbnailHeight
                        + m.fileCardHeight + m.pollCardHeight + m.systemHeight
                        + m.textHeight + m.reactionsHeight
                        + m.footerHeight;
    int contentWidth = std::max({textWidth, m.thumbnailWidth,
                                 m.fileCardHeight > 0 ? 230 : 0,
                                 m.pollCardHeight > 0 ? 250 : 0,
                                 m.systemHeight > 0 ? 230 : 0});
    // Reply quote needs at least ~60% of max width to look right.
    if (!replyTo.isEmpty()) {
        contentWidth = std::max(contentWidth,
                                static_cast<int>(contentMax * 0.6));
    }
    if (!forwarded.isEmpty() || (!outgoing && !sender.isEmpty())) {
        contentWidth = std::max(contentWidth, fm.horizontalAdvance(forwarded.isEmpty() ? sender : forwarded) + 16);
    }
    contentWidth = std::min(contentWidth, contentMax);

    m.bubbleSize = QSize(contentWidth + 2 * kBubblePaddingX,
                          contentHeight + 2 * kBubblePaddingY);
    return m;
}

QSize BubbleDelegate::sizeHint(const QStyleOptionViewItem& option,
                               const QModelIndex& index) const {
    const int width = option.rect.width() > 0
        ? option.rect.width()
        : (option.widget ? option.widget->width() : 600);
    const auto m = measure(index, width);
    const int rowHeight = std::max(kAvatarSize, m.bubbleSize.height()) + 2 * kRowMargin;
    return QSize(width, rowHeight);
}

void BubbleDelegate::paint(QPainter* painter,
                           const QStyleOptionViewItem& option,
                           const QModelIndex& index) const {
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setRenderHint(QPainter::TextAntialiasing, true);

    const bool outgoing  = index.data(BubbleMessageModel::OutgoingRole).toBool();
    const QString text   = index.data(BubbleMessageModel::TextRole).toString();
    const QString sender = index.data(BubbleMessageModel::SenderRole).toString();
    const QString tick   = index.data(BubbleMessageModel::TickRole).toString();
    const bool failed    = index.data(BubbleMessageModel::FailedRole).toBool();
    const bool pending   = index.data(BubbleMessageModel::PendingRole).toBool();
    const bool deleted   = index.data(BubbleMessageModel::DeletedRole).toBool();
    const bool edited    = index.data(BubbleMessageModel::EditedRole).toBool();
    const QString replyTo     = index.data(BubbleMessageModel::ReplyToRole).toString();
    const QString replyToText = index.data(BubbleMessageModel::ReplyToTextRole).toString();
    const QString forwarded   = index.data(BubbleMessageModel::ForwardedFromRole).toString();
    const QString reactions   = index.data(BubbleMessageModel::ReactionsRole).toString();
    const QString filename    = index.data(BubbleMessageModel::FilenameRole).toString();
    const QString mimeType    = index.data(BubbleMessageModel::AttachmentMimeRole).toString();
    const qint64 sizeBytes    = index.data(BubbleMessageModel::SizeBytesRole).toLongLong();
    const bool pinned    = index.data(BubbleMessageModel::PinnedRole).toBool();
    const qint64 createdMs = index.data(BubbleMessageModel::CreatedAtMsRole).toLongLong();
    const QString avatarSeed = index.data(BubbleMessageModel::AvatarSeedRole).toString();
    const bool focused = index.data(BubbleMessageModel::FocusedRole).toBool();
    const bool match = index.data(BubbleMessageModel::MatchRole).toBool();
    const bool systemMessage = text.startsWith(QStringLiteral("[system]"));
    const bool pollMessage = text.startsWith(QStringLiteral("[poll]"));

    const auto layout = measure(index, option.rect.width());
    const QSize bubbleSize = layout.bubbleSize;

    QRect avatarRect;
    QRect bubbleRect;
    if (outgoing) {
        bubbleRect = QRect(option.rect.right() - kSideMargin - bubbleSize.width(),
                           option.rect.top() + kRowMargin,
                           bubbleSize.width(), bubbleSize.height());
    } else {
        avatarRect = QRect(option.rect.left() + kSideMargin,
                           option.rect.top() + kRowMargin,
                           kAvatarSize, kAvatarSize);
        bubbleRect = QRect(avatarRect.right() + kAvatarBubbleGap,
                           option.rect.top() + kRowMargin,
                           bubbleSize.width(), bubbleSize.height());
    }

    // ---- avatar (peer side only) ----
    if (!outgoing) {
        painter->setPen(Qt::NoPen);
        painter->setBrush(avatar_color_for(avatarSeed));
        painter->drawEllipse(avatarRect);
        painter->setPen(Qt::white);
        painter->setFont(base_font(13, true));
        painter->drawText(avatarRect, Qt::AlignCenter, initials_for(avatarSeed));
    }

    // ---- bubble background ----
    if (failed) {
        painter->setPen(Qt::NoPen);
        painter->setBrush(QColor(palette_.failed_bubble));
    } else if (outgoing) {
        // Brand-blue gradient (top-light -> bottom-darker), the Telegram
        // contract for outgoing bubbles. The two stops live in the
        // palette as `primary` (single brand color) and a slightly
        // lighter manual top — derived from primary by lightening it.
        QLinearGradient grad(bubbleRect.topLeft(), bubbleRect.bottomLeft());
        QColor bottom(palette_.own_bubble);
        QColor top = bottom.lighter(125);  // ~25% lighter
        grad.setColorAt(0.0, top);
        grad.setColorAt(1.0, bottom);
        painter->setPen(Qt::NoPen);
        painter->setBrush(grad);
    } else {
        painter->setPen(Qt::NoPen);
        painter->setBrush(QColor(palette_.peer_bubble));
    }
    painter->drawRoundedRect(bubbleRect, kBubbleRadius, kBubbleRadius);

    // Pending state border (subtle dashed yellow, peer side only useful).
    if (pending && !failed) {
        painter->setPen(QPen(QColor("#b88a16"), 1, Qt::DashLine));
        painter->setBrush(Qt::NoBrush);
        painter->drawRoundedRect(bubbleRect, kBubbleRadius, kBubbleRadius);
    }
    // Match / focused outline.
    if (focused) {
        painter->setPen(QPen(QColor(palette_.primary), 2));
        painter->setBrush(Qt::NoBrush);
        painter->drawRoundedRect(bubbleRect, kBubbleRadius, kBubbleRadius);
    } else if (match) {
        painter->setPen(QPen(QColor("#f6c344"), 2));
        painter->setBrush(Qt::NoBrush);
        painter->drawRoundedRect(bubbleRect, kBubbleRadius, kBubbleRadius);
    }

    // ---- inner content ----
    QRect content = bubbleRect.adjusted(kBubblePaddingX, kBubblePaddingY,
                                        -kBubblePaddingX, -kBubblePaddingY);
    int y = content.top();

    const QColor primaryText(outgoing && !failed ? QColor(palette_.own_bubble_text)
                                                  : QColor(palette_.peer_bubble_text));
    const QColor metaText(outgoing && !failed ? QColor("#e6f1ff")
                                               : QColor(palette_.text_muted));
    const QColor accentText(outgoing && !failed ? QColor("#cee9ff")
                                                 : QColor(palette_.primary));

    // Sender name (peer side, useful in groups; harmless in 1:1).
    if (layout.senderHeight > 0) {
        painter->setPen(accentText);
        painter->setFont(base_font(11, true));
        QRect r(content.left(), y, content.width(), layout.senderHeight);
        painter->drawText(r, Qt::AlignLeft | Qt::AlignTop, sender);
        y += layout.senderHeight;
    }

    // Forwarded header.
    if (layout.forwardedHeight > 0) {
        painter->setPen(metaText);
        painter->setFont(base_font(10, false, true));
        QRect r(content.left(), y, content.width(), layout.forwardedHeight);
        painter->drawText(r, Qt::AlignLeft | Qt::AlignTop,
                          QStringLiteral("Forwarded from %1").arg(forwarded));
        y += layout.forwardedHeight;
    }

    // Reply quote — accent bar + sender id + 1-line snippet.
    if (layout.replyHeight > 0) {
        painter->fillRect(QRect(content.left(), y, 3, layout.replyHeight - 4), accentText);
        painter->setPen(accentText);
        painter->setFont(base_font(10, true));
        QRect r1(content.left() + 8, y, content.width() - 8, 12);
        painter->drawText(r1, Qt::AlignLeft | Qt::AlignTop,
                          QStringLiteral("Reply: %1").arg(replyTo));
        painter->setPen(metaText);
        painter->setFont(base_font(10));
        QRect r2(content.left() + 8, y + 12, content.width() - 8, 14);
        painter->drawText(r2, Qt::AlignLeft | Qt::AlignTop,
                          replyToText.left(80));
        y += layout.replyHeight;
    }

    // M148: image thumbnail (positioned above text, below reply/forward).
    if (layout.thumbnailHeight > 0) {
        const QPixmap thumb = index.data(BubbleMessageModel::ThumbnailRole).value<QPixmap>();
        if (!thumb.isNull()) {
            const QPixmap scaled = thumb.scaled(QSize(layout.thumbnailWidth,
                                                       layout.thumbnailHeight - 6),
                                                Qt::KeepAspectRatio,
                                                Qt::SmoothTransformation);
            painter->drawPixmap(content.left(), y, scaled);
            y += layout.thumbnailHeight;
        }
    }

    // Pinned tag.
    if (pinned && layout.pinnedHeight > 0) {
        painter->setPen(metaText);
        painter->setFont(base_font(10));
        QRect r(content.left(), y, content.width(), layout.pinnedHeight);
        painter->drawText(r, Qt::AlignLeft | Qt::AlignTop,
                          QString::fromUtf8("\xf0\x9f\x93\x8c pinned"));  // 📌 pinned
        y += layout.pinnedHeight;
    }

    // System service message — compact centered pill inside the timeline.
    if (systemMessage && layout.systemHeight > 0) {
        QRect sysRect(content.left(), y, content.width(), layout.systemHeight - 6);
        painter->setPen(Qt::NoPen);
        painter->setBrush(outgoing && !failed ? QColor(255, 255, 255, 46)
                                              : QColor(palette_.text_muted).lighter(185));
        painter->drawRoundedRect(sysRect, 12, 12);
        painter->setPen(metaText);
        painter->setFont(base_font(10));
        painter->drawText(sysRect.adjusted(8, 0, -8, 0), Qt::AlignCenter,
                          text.mid(QStringLiteral("[system]").size()).trimmed());
        y += layout.systemHeight;
    }

    // File attachment card — filename, type and size in a Telegram-like row.
    if (layout.fileCardHeight > 0) {
        QRect card(content.left(), y, content.width(), layout.fileCardHeight - 6);
        painter->setPen(Qt::NoPen);
        painter->setBrush(outgoing && !failed ? QColor(255, 255, 255, 42)
                                              : QColor(palette_.text_muted).lighter(190));
        painter->drawRoundedRect(card, 10, 10);
        QRect icon(card.left() + 8, card.top() + 7, 32, 32);
        painter->setBrush(QColor(palette_.primary));
        painter->drawEllipse(icon);
        painter->setPen(Qt::white);
        painter->setFont(base_font(11, true));
        painter->drawText(icon, Qt::AlignCenter, QStringLiteral("F"));
        painter->setPen(primaryText);
        painter->setFont(base_font(11, true));
        painter->drawText(QRect(icon.right() + 8, card.top() + 6, card.width() - 54, 16),
                          Qt::AlignLeft | Qt::AlignVCenter,
                          filename.isEmpty() ? QStringLiteral("Attachment") : filename);
        painter->setPen(metaText);
        painter->setFont(base_font(10));
        const QString sizeText = sizeBytes > 0
            ? QStringLiteral("%1 KB").arg(std::max<qint64>(1, sizeBytes / 1024))
            : QStringLiteral("file");
        painter->drawText(QRect(icon.right() + 8, card.top() + 24, card.width() - 54, 14),
                          Qt::AlignLeft | Qt::AlignVCenter,
                          mimeType.isEmpty() ? sizeText : mimeType + QStringLiteral(" · ") + sizeText);
        y += layout.fileCardHeight;
    }

    // Poll card — visual surface for poll messages while the server RPCs
    // continue to own vote/close behavior.
    if (pollMessage && layout.pollCardHeight > 0) {
        QRect poll(content.left(), y, content.width(), layout.pollCardHeight - 6);
        painter->setPen(QPen(QColor(palette_.primary), 1));
        painter->setBrush(outgoing && !failed ? QColor(255, 255, 255, 36)
                                              : QColor("#f6fbff"));
        painter->drawRoundedRect(poll, 10, 10);
        painter->setPen(primaryText);
        painter->setFont(base_font(11, true));
        painter->drawText(QRect(poll.left() + 10, poll.top() + 8, poll.width() - 20, 16),
                          Qt::AlignLeft | Qt::AlignVCenter,
                          text.mid(QStringLiteral("[poll]").size()).trimmed());
        painter->setPen(QPen(QColor(palette_.primary), 1));
        painter->setBrush(Qt::NoBrush);
        painter->drawRoundedRect(QRect(poll.left() + 10, poll.top() + 32, poll.width() - 20, 14), 7, 7);
        painter->drawRoundedRect(QRect(poll.left() + 10, poll.top() + 52, poll.width() - 20, 14), 7, 7);
        y += layout.pollCardHeight;
    }

    // Body text (with edit suffix).
    {
        QString shownText = deleted ? QStringLiteral("<deleted>") : text;
        if (systemMessage || pollMessage) shownText.clear();
        if (edited) shownText += QStringLiteral(" (edited)");
        painter->setPen(failed ? QColor("#0f1419") : primaryText);
        painter->setFont(base_font(13));
        QRect r(content.left(), y, content.width(), layout.textHeight);
        painter->drawText(r, Qt::TextWordWrap, shownText);
        y += layout.textHeight;
    }

    // Reaction chips.
    if (layout.reactionsHeight > 0) {
        painter->setFont(base_font(10));
        QFontMetrics fm = painter->fontMetrics();
        int chipX = content.left();
        for (const QString& chip : reactions.split(QLatin1Char(','), Qt::SkipEmptyParts)) {
            const int colon = chip.indexOf(QLatin1Char(':'));
            QString chipText = colon > 0 ? chip.left(colon) + QLatin1Char(' ') + chip.mid(colon + 1)
                                          : chip;
            int chipW = fm.horizontalAdvance(chipText) + 14;
            QRect chipRect(chipX, y, chipW, 18);
            painter->setPen(Qt::NoPen);
            painter->setBrush(outgoing && !failed
                                ? QColor(255, 255, 255, 56)
                                : QColor(palette_.text_muted).lighter(180));
            painter->drawRoundedRect(chipRect, 9, 9);
            painter->setPen(outgoing && !failed
                              ? QColor("#ffffff")
                              : QColor(palette_.peer_bubble_text));
            painter->drawText(chipRect, Qt::AlignCenter, chipText);
            chipX += chipW + 4;
            if (chipX > content.right()) break;
        }
    }

    // Footer: time + tick aligned to the bubble's bottom-right edge.
    {
        const QString glyph = tickGlyph(tick);
        const QString footer = formatTime(createdMs)
            + (glyph.isEmpty() ? QString() : QStringLiteral(" ") + glyph);
        painter->setPen(metaText);
        painter->setFont(base_font(10));
        QRect r(content.left(),
                bubbleRect.bottom() - kBubblePaddingY - 12,
                content.width(),
                12);
        painter->drawText(r, Qt::AlignRight | Qt::AlignBottom, footer);
    }

    painter->restore();
}


// ============================================================
// BubbleListView
// ============================================================

BubbleListView::BubbleListView(QWidget* parent)
    : QListView(parent),
      model_(new BubbleMessageModel(this)),
      delegate_(new BubbleDelegate(this)) {
    setModel(model_);
    setItemDelegate(delegate_);
    setSelectionMode(QAbstractItemView::SingleSelection);
    setSelectionBehavior(QAbstractItemView::SelectRows);
    setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    setUniformItemSizes(false);
    setMouseTracking(true);
    // Smooth scroll feel + no item highlighting (the bubble paints its own).
    setStyleSheet(QStringLiteral("BubbleListView { border: none; } "
                                  "BubbleListView::item:selected { background: transparent; }"));
}

void BubbleListView::setStore(const DesktopChatStore* store,
                              const std::string& current_user_id) {
    model_->setData(store, current_user_id);
}

void BubbleListView::setBubblePalette(const DesktopBubblePalette& palette) {
    palette_ = palette;
    delegate_->setPalette(palette);
    QPalette pal = this->palette();
    pal.setColor(QPalette::Base, QColor(palette.chat_area_bg));
    pal.setColor(QPalette::Text, QColor(palette.peer_bubble_text));
    setPalette(pal);
    // Force a repaint after the delegate's palette flips.
    viewport()->update();
}

void BubbleListView::setEmptyStateText(const QString& text) {
    empty_state_text_ = text;
    viewport()->update();
}

void BubbleListView::refresh() {
    // Re-pull from the same store — model::setData re-snapshots.
    // Caller resets the model + scrolls to bottom.
    if (model_->rowCount() > 0) {
        scrollToBottom();
    }
    viewport()->update();
}

void BubbleListView::setSearchHighlight(const QString& query,
                                        const QString& focused_message_id) {
    model_->setSearchHighlight(query, focused_message_id);
    if (!focused_message_id.isEmpty()) {
        for (int row = 0; row < model_->rowCount(); ++row) {
            if (model_->messageIdAt(row) == focused_message_id) {
                scrollTo(model_->index(row), QAbstractItemView::PositionAtCenter);
                break;
            }
        }
    }
}

void BubbleListView::setThumbnailCache(const QHash<QString, QPixmap>& thumbnails) {
    model_->setThumbnailCache(thumbnails);
    viewport()->update();
}

void BubbleListView::paintTelegramDoodleWallpaper(QPainter& painter, const QRect& rect) const {
    painter.save();
    painter.setRenderHint(QPainter::Antialiasing, true);
    QLinearGradient bg(rect.topLeft(), rect.bottomRight());
    bg.setColorAt(0.0, QColor("#dfe79d"));
    bg.setColorAt(0.52, QColor(palette_.chat_area_bg));
    bg.setColorAt(1.0, QColor("#8ac5b0"));
    painter.fillRect(rect, bg);

    QColor ink("#5f8f68");
    ink.setAlpha(42);
    QPen pen(ink, 1.4);
    painter.setPen(pen);
    painter.setBrush(Qt::NoBrush);

    const int step = 92;
    for (int y = rect.top() - step; y < rect.bottom() + step; y += step) {
        for (int x = rect.left() - step; x < rect.right() + step; x += step) {
            const int variant = ((x / step) + (y / step)) & 3;
            const QPoint c(x + 46, y + 42);
            if (variant == 0) {
                painter.drawEllipse(QRect(c.x() - 14, c.y() - 12, 28, 24));
                painter.drawLine(c.x() - 5, c.y() + 12, c.x() - 12, c.y() + 22);
                painter.drawLine(c.x() + 5, c.y() + 12, c.x() + 12, c.y() + 22);
            } else if (variant == 1) {
                painter.drawRoundedRect(QRect(c.x() - 16, c.y() - 12, 32, 24), 6, 6);
                painter.drawLine(c.x() - 8, c.y() - 18, c.x(), c.y() - 12);
                painter.drawLine(c.x() + 8, c.y() - 18, c.x(), c.y() - 12);
            } else if (variant == 2) {
                QPainterPath path;
                path.moveTo(c.x() - 16, c.y() + 10);
                path.cubicTo(c.x() - 10, c.y() - 18, c.x() + 12, c.y() - 18, c.x() + 16, c.y() + 10);
                path.cubicTo(c.x() + 5, c.y() + 2, c.x() - 5, c.y() + 2, c.x() - 16, c.y() + 10);
                painter.drawPath(path);
            } else {
                painter.drawEllipse(QRect(c.x() - 11, c.y() - 11, 22, 22));
                painter.drawLine(c.x() - 20, c.y(), c.x() - 14, c.y());
                painter.drawLine(c.x() + 14, c.y(), c.x() + 20, c.y());
                painter.drawLine(c.x(), c.y() - 20, c.x(), c.y() - 14);
                painter.drawLine(c.x(), c.y() + 14, c.x(), c.y() + 20);
            }
        }
    }
    painter.restore();
}

void BubbleListView::paintEvent(QPaintEvent* event) {
    QPainter painter(viewport());
    paintTelegramDoodleWallpaper(painter, event->rect());
    QListView::paintEvent(event);
    if (model_ != nullptr && model_->rowCount() == 0 && !empty_state_text_.isEmpty()) {
        painter.save();
        painter.setRenderHint(QPainter::Antialiasing, true);
        QFont font(QStringLiteral("Segoe UI"));
        font.setPixelSize(26);
        font.setBold(true);
        painter.setFont(font);
        const QFontMetrics fm(font);
        const int w = fm.horizontalAdvance(empty_state_text_) + 42;
        const int h = 52;
        const QRect bubble((viewport()->width() - w) / 2,
                           (viewport()->height() - h) / 2,
                           w,
                           h);
        QColor bg("#3f7f5b");
        bg.setAlpha(130);
        painter.setPen(Qt::NoPen);
        painter.setBrush(bg);
        painter.drawRoundedRect(bubble, 22, 22);
        painter.setPen(Qt::white);
        painter.drawText(bubble, Qt::AlignCenter, empty_state_text_);
        painter.restore();
    }
}

QString BubbleListView::messageIdAtRow(int row) const {
    return model_->messageIdAt(row);
}

void BubbleListView::contextMenuEvent(QContextMenuEvent* event) {
    const auto idx = indexAt(event->pos());
    if (!idx.isValid()) return;
    const auto id = model_->messageIdAt(idx.row());
    if (id.isEmpty()) return;
    setCurrentIndex(idx);
    emit messageContextMenuRequested(id, event->globalPos());
}

void BubbleListView::mouseDoubleClickEvent(QMouseEvent* event) {
    const auto idx = indexAt(event->pos());
    if (idx.isValid()) {
        const auto id = model_->messageIdAt(idx.row());
        if (!id.isEmpty()) emit messageActivated(id);
    }
    QListView::mouseDoubleClickEvent(event);
}

}  // namespace telegram_like::client::app_desktop

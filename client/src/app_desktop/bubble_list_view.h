#pragma once

// M138: Telegram-style message rendering for the Qt Widgets desktop app.
//
// Replaces the previous QTextBrowser + HTML+CSS approach. Qt's rich-text
// engine doesn't support `float`, `max-width`, `border-radius`, or
// gradients; bubbles painted via QPainter on a QListView delegate get all
// of those for free, plus avatars, reply quotes, forwarded headers,
// reaction chips, pinned markers, and a right-click context menu.
//
// Three classes live in one header so the model/delegate/view stay close:
//
//   BubbleMessageModel — wraps the desktop store's selected conversation;
//                        exposes per-message roles to the delegate.
//   BubbleDelegate     — paints each row as a Telegram bubble with
//                        avatar (peer only) + content sections + footer.
//   BubbleListView     — QListView with the model + delegate already
//                        wired; the host (main.cpp) just calls
//                        setStore(...) + refresh() + setPalette(...) and
//                        listens for messageContextMenuRequested().

#include "app_desktop/desktop_chat_store.h"
#include "transport/control_plane_client.h"

#include <QAbstractListModel>
#include <QHash>
#include <QListView>
#include <QPixmap>
#include <QStyledItemDelegate>
#include <QString>

#include <string>
#include <vector>

namespace telegram_like::client::app_desktop {

class BubbleMessageModel : public QAbstractListModel {
    Q_OBJECT
public:
    enum Roles {
        MessageIdRole = Qt::UserRole + 1,
        OutgoingRole,
        SenderRole,
        TextRole,
        CreatedAtMsRole,
        TickRole,            // "pending" | "sent" | "read" | "failed" | "received"
        EditedRole,
        DeletedRole,
        ReplyToRole,         // message_id this is a reply to (empty if none)
        ReplyToTextRole,     // resolved snippet of the replied message
        ForwardedFromRole,   // "<conv>/<msg>" or "<sender>" string for header
        ReactionsRole,       // reaction_summary string ("+1:2,heart:1")
        PinnedRole,
        FailedRole,
        PendingRole,
        AvatarSeedRole,      // sender_user_id used to pick avatar color
        FocusedRole,         // current search-focused message
        MatchRole,           // matches the active in-chat search query
        AttachmentIdRole,    // attachment_id (if any) — drives M148 lookup
        AttachmentMimeRole,  // mime_type so the delegate can detect images
        ThumbnailRole,       // QPixmap from M148 cache (null when missing)
    };

    explicit BubbleMessageModel(QObject* parent = nullptr);

    // Pull a fresh snapshot from the store. Re-runs delivery_tick() on
    // every row so the ✓/✓✓ promotion lands without an external nudge.
    void setData(const DesktopChatStore* store,
                 const std::string& current_user_id);
    void setSearchHighlight(const QString& search_query,
                            const QString& focused_message_id);
    // M148: cache of decoded image thumbnails keyed by attachment_id.
    // Replacing the cache emits dataChanged for every row whose attachment
    // appears in the new map so the delegate repaints with the new image.
    void setThumbnailCache(const QHash<QString, QPixmap>& thumbnails);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    QString messageIdAt(int row) const;

private:
    const DesktopChatStore* store_ {nullptr};
    std::string current_user_id_;
    std::string conversation_id_;
    std::vector<DesktopMessage> messages_;
    QString search_query_;
    QString focused_message_id_;
    QHash<QString, QPixmap> thumbnails_;  // M148
};


class BubbleDelegate : public QStyledItemDelegate {
    Q_OBJECT
public:
    explicit BubbleDelegate(QObject* parent = nullptr);
    void setPalette(const DesktopBubblePalette& palette);

    void paint(QPainter* painter,
               const QStyleOptionViewItem& option,
               const QModelIndex& index) const override;
    QSize sizeHint(const QStyleOptionViewItem& option,
                   const QModelIndex& index) const override;

private:
    struct LayoutMetrics {
        QSize bubbleSize;
        int senderHeight = 0;
        int forwardedHeight = 0;
        int replyHeight = 0;
        int pinnedHeight = 0;
        int thumbnailHeight = 0;
        int thumbnailWidth = 0;
        int textHeight = 0;
        int reactionsHeight = 0;
        int footerHeight = 14;
    };
    LayoutMetrics measure(const QModelIndex& index, int viewportWidth) const;
    int maxBubbleContentWidth(int viewportWidth) const;
    QString tickGlyph(const QString& tick) const;
    QString formatTime(qint64 ms) const;

    DesktopBubblePalette palette_;
};


class BubbleListView : public QListView {
    Q_OBJECT
public:
    explicit BubbleListView(QWidget* parent = nullptr);

    void setStore(const DesktopChatStore* store, const std::string& current_user_id);
    void setBubblePalette(const DesktopBubblePalette& palette);
    void refresh();
    void setSearchHighlight(const QString& query,
                            const QString& focused_message_id);
    void setThumbnailCache(const QHash<QString, QPixmap>& thumbnails);  // M148
    QString messageIdAtRow(int row) const;

signals:
    void messageContextMenuRequested(const QString& message_id, const QPoint& globalPos);
    void messageActivated(const QString& message_id);

protected:
    void contextMenuEvent(QContextMenuEvent* event) override;
    void mouseDoubleClickEvent(QMouseEvent* event) override;

private:
    BubbleMessageModel* model_ {nullptr};
    BubbleDelegate* delegate_ {nullptr};
};

}  // namespace telegram_like::client::app_desktop

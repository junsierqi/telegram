#include "app_desktop/bubble_list_view.h"
#include "app_desktop/design_tokens.h"
#include "app_desktop/desktop_chat_store.h"
#include "app_desktop/typing_indicator.h"
#include "transport/control_plane_client.h"

#include <QDateTime>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPropertyAnimation>
#include <QResizeEvent>
#include <QSet>
#include <QTimer>

#include <QAction>
#include <QApplication>
#include <QAbstractItemView>
#include <QCheckBox>
#include <QFile>
#include <QComboBox>
#include <QDialog>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFont>
#include <QFrame>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QIcon>
#include <QInputDialog>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMainWindow>
#include <QMenu>
#include <QMetaObject>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>
#include <QPointer>
#include <QRadioButton>
#include <QScrollArea>
#include <QSettings>
#include <QSizePolicy>
#include <QSlider>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QStatusBar>
#include <QString>
#include <QStringList>
#include <QTabWidget>
#include <QStyledItemDelegate>
#include <QStyleOptionViewItem>
#include <QToolButton>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>
#include <QMoveEvent>

#include <atomic>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

using telegram_like::client::transport::ControlPlaneClient;
namespace transport = telegram_like::client::transport;

struct Args {
    std::string user;
    std::string password;
    std::string display_name;
    std::string device = "desktop";
    std::string host = "127.0.0.1";
    unsigned short port = 8787;
    bool tls = false;
    bool tls_insecure = false;
    std::string tls_server_name;
    std::string conversation;
    std::string cache_file = ".tmp_app_desktop_cache.json";
    std::string smoke_save_dir;
    bool smoke = false;
    bool smoke_attachment = false;
    bool smoke_register = false;
    bool smoke_two_client_flow = false;
    bool gui_smoke = false;
};

bool parse_args(int argc, char** argv, Args& out) {
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto next = [&](const char* name) -> const char* {
            if (i + 1 >= argc) {
                std::cerr << "missing value for " << name << "\n";
                return nullptr;
            }
            return argv[++i];
        };
        if (arg == "--smoke") {
            out.smoke = true;
        } else if (arg == "--gui-smoke") {
            out.gui_smoke = true;
        } else if (arg == "--smoke-attachment") {
            out.smoke = true;
            out.smoke_attachment = true;
        } else if (arg == "--user") {
            const char* v = next("--user");
            if (!v) return false;
            out.user = v;
        } else if (arg == "--password") {
            const char* v = next("--password");
            if (!v) return false;
            out.password = v;
        } else if (arg == "--display-name") {
            const char* v = next("--display-name");
            if (!v) return false;
            out.display_name = v;
        } else if (arg == "--device") {
            const char* v = next("--device");
            if (!v) return false;
            out.device = v;
        } else if (arg == "--host") {
            const char* v = next("--host");
            if (!v) return false;
            out.host = v;
        } else if (arg == "--port") {
            const char* v = next("--port");
            if (!v) return false;
            out.port = static_cast<unsigned short>(std::atoi(v));
        } else if (arg == "--tls") {
            out.tls = true;
        } else if (arg == "--tls-insecure") {
            out.tls = true;
            out.tls_insecure = true;
        } else if (arg == "--tls-server-name") {
            const char* v = next("--tls-server-name");
            if (!v) return false;
            out.tls_server_name = v;
        } else if (arg == "--conversation") {
            const char* v = next("--conversation");
            if (!v) return false;
            out.conversation = v;
        } else if (arg == "--cache-file") {
            const char* v = next("--cache-file");
            if (!v) return false;
            out.cache_file = v;
        } else if (arg == "--smoke-save-dir") {
            const char* v = next("--smoke-save-dir");
            if (!v) return false;
            out.smoke_save_dir = v;
        } else if (arg == "--smoke-register") {
            out.smoke = true;
            out.smoke_register = true;
        } else if (arg == "--smoke-two-client-flow") {
            out.smoke = true;
            out.smoke_two_client_flow = true;
        } else {
            std::cerr << "unknown arg: " << arg << "\n";
            return false;
        }
    }
    return true;
}

QString qstr(const std::string& value) {
    return QString::fromStdString(value);
}

std::string str(const QString& value) {
    return value.toStdString();
}

enum ChatListRole {
    ChatTitleRole = Qt::UserRole + 10,
    ChatSnippetRole,
    ChatTimeRole,
    ChatUnreadRole,
    ChatAvatarSeedRole,
};

QColor chat_avatar_color_for(const QString& seed) {
    static const QColor palette[] = {
        QColor("#e17076"), QColor("#7bc862"), QColor("#65aadd"),
        QColor("#a695e7"), QColor("#ee7aae"), QColor("#6ec9cb"),
        QColor("#faa774"), QColor("#7d8ea0")
    };
    if (seed.isEmpty()) return palette[0];
    unsigned hash = 0;
    for (QChar c : seed) hash = hash * 31u + static_cast<unsigned>(c.unicode());
    return palette[hash % (sizeof(palette) / sizeof(palette[0]))];
}

QString chat_initials_for(const QString& seed) {
    const QString trimmed = seed.trimmed();
    if (trimmed.isEmpty()) return QStringLiteral("?");
    QString out = trimmed.left(1).toUpper();
    const int sp = trimmed.indexOf(QLatin1Char(' '));
    if (sp >= 0 && sp + 1 < trimmed.size()) out += trimmed.mid(sp + 1, 1).toUpper();
    return out.left(2);
}

class ChatListDelegate final : public QStyledItemDelegate {
public:
    explicit ChatListDelegate(QObject* parent = nullptr) : QStyledItemDelegate(parent) {}

    QSize sizeHint(const QStyleOptionViewItem&, const QModelIndex&) const override {
        return QSize(360, 82);
    }

    void paint(QPainter* painter, const QStyleOptionViewItem& option,
               const QModelIndex& index) const override {
        namespace dt = telegram_like::client::app_desktop::design;
        const auto& t = dt::active_theme();
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);

        const bool selected = option.state.testFlag(QStyle::State_Selected);
        const bool hovered = option.state.testFlag(QStyle::State_MouseOver);
        QRect row = option.rect.adjusted(0, 0, 0, 0);
        painter->setPen(Qt::NoPen);
        if (selected) {
            painter->setBrush(QColor(t.primary));
            painter->drawRect(row);
        } else if (hovered) {
            painter->setBrush(QColor(t.hover));
            painter->drawRoundedRect(row, 8, 8);
        }

        const QString title = index.data(ChatTitleRole).toString();
        const QString snippet = index.data(ChatSnippetRole).toString();
        const QString time = index.data(ChatTimeRole).toString();
        const int unread = index.data(ChatUnreadRole).toInt();
        const QString seed = index.data(ChatAvatarSeedRole).toString();

        const QRect avatar(row.left() + 12, row.top() + 12, 58, 58);
        painter->setBrush(chat_avatar_color_for(seed));
        painter->drawEllipse(avatar);
        painter->setPen(Qt::white);
        QFont avatarFont(QStringLiteral("Segoe UI"));
        avatarFont.setPixelSize(22);
        avatarFont.setBold(true);
        painter->setFont(avatarFont);
        painter->drawText(avatar, Qt::AlignCenter, chat_initials_for(title.isEmpty() ? seed : title));

        const QColor titleColor = selected ? QColor("#ffffff") : QColor(t.text_primary);
        const QColor metaColor = selected ? QColor(230, 245, 255) : QColor(t.text_muted);
        const int textLeft = avatar.right() + 16;
        const int textRight = row.right() - 14;
        QFont titleFont(QStringLiteral("Segoe UI"));
        titleFont.setPixelSize(15);
        titleFont.setBold(true);
        painter->setFont(titleFont);
        painter->setPen(titleColor);
        painter->drawText(QRect(textLeft, row.top() + 13, textRight - textLeft - 70, 22),
                          Qt::AlignLeft | Qt::AlignVCenter,
                          painter->fontMetrics().elidedText(title, Qt::ElideRight, textRight - textLeft - 70));

        QFont metaFont(QStringLiteral("Segoe UI"));
        metaFont.setPixelSize(14);
        painter->setFont(metaFont);
        painter->setPen(metaColor);
        painter->drawText(QRect(textRight - 70, row.top() + 14, 70, 20),
                          Qt::AlignRight | Qt::AlignVCenter, time);
        painter->drawText(QRect(textLeft, row.top() + 43, textRight - textLeft - (unread > 0 ? 58 : 0), 24),
                          Qt::AlignLeft | Qt::AlignVCenter,
                          painter->fontMetrics().elidedText(snippet, Qt::ElideRight,
                                                            textRight - textLeft - (unread > 0 ? 56 : 0)));
        if (unread > 0) {
            const QString badge = unread > 999 ? QStringLiteral("999+") : QString::number(unread);
            const int badgeW = std::max(28, painter->fontMetrics().horizontalAdvance(badge) + 14);
            QRect badgeRect(textRight - badgeW, row.top() + 42, badgeW, 24);
            painter->setPen(Qt::NoPen);
            painter->setBrush(selected ? QColor(255, 255, 255, 70) : QColor("#b9bec4"));
            painter->drawRoundedRect(badgeRect, 11, 11);
            painter->setPen(Qt::white);
            painter->drawText(badgeRect, Qt::AlignCenter, badge);
        }

        painter->restore();
    }
};

std::string guess_mime_type(const QFileInfo& info) {
    const auto suffix = info.suffix().toLower();
    if (suffix == "txt" || suffix == "md" || suffix == "log" || suffix == "csv") return "text/plain";
    if (suffix == "png") return "image/png";
    if (suffix == "jpg" || suffix == "jpeg") return "image/jpeg";
    if (suffix == "gif") return "image/gif";
    if (suffix == "webp") return "image/webp";
    return "application/octet-stream";
}

QString reference_title_for(const std::string& conversation_id, const std::string& title = {}) {
    if (!title.empty()) return qstr(title);
    return qstr(conversation_id);
}

QString reference_subtitle_for(
    const telegram_like::client::app_desktop::DesktopConversation& conversation) {
    const QString title = reference_title_for(conversation.conversation_id, conversation.title);
    const std::size_t members = conversation.participant_user_ids.size();
    const bool is_group = members > 2
        || title.contains(QString::fromUtf8("三叉戟"))
        || conversation.conversation_id.find("group") != std::string::npos;
    const bool is_channel = !is_group && (
        title.contains("M-Team", Qt::CaseInsensitive)
        || title.contains("channel", Qt::CaseInsensitive)
        || title.contains("proxy", Qt::CaseInsensitive));
    if (is_group) return QString("%1 members").arg(std::max<std::size_t>(members, 3));
    if (is_channel) return QString("%1 subscribers").arg(members);
    if (title == QStringLiteral("Telegram")) return QStringLiteral("service notifications");
    return members > 0 ? QString("%1 participants").arg(members) : QString();
}

QIcon line_icon(const QString& key, int side = 28, QColor color = QColor("#202124")) {
    QPixmap pixmap(side, side);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    QPen pen(color, std::max(2, side / 12), Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);
    painter.setPen(pen);
    painter.setBrush(Qt::NoBrush);
    const QRectF r(side * 0.18, side * 0.18, side * 0.64, side * 0.64);
    const qreal cx = side / 2.0;
    const qreal cy = side / 2.0;

    if (key == "profile" || key == "account" || key == "contact") {
        painter.drawEllipse(QPointF(cx, side * 0.36), side * 0.16, side * 0.16);
        painter.drawArc(QRectF(side * 0.25, side * 0.50, side * 0.50, side * 0.34), 20 * 16, 140 * 16);
    } else if (key == "search") {
        painter.drawEllipse(QPointF(side * 0.43, side * 0.42), side * 0.20, side * 0.20);
        painter.drawLine(QPointF(side * 0.58, side * 0.58), QPointF(side * 0.78, side * 0.78));
    } else if (key == "smile") {
        painter.drawEllipse(QPointF(cx, cy), side * 0.30, side * 0.30);
        painter.drawEllipse(QPointF(side * 0.40, side * 0.42), side * 0.025, side * 0.025);
        painter.drawEllipse(QPointF(side * 0.60, side * 0.42), side * 0.025, side * 0.025);
        painter.drawArc(QRectF(side * 0.36, side * 0.42, side * 0.28, side * 0.22), 200 * 16, 140 * 16);
    } else if (key == "wallet") {
        painter.drawRoundedRect(QRectF(side * 0.18, side * 0.30, side * 0.64, side * 0.42), side * 0.06, side * 0.06);
        painter.drawLine(QPointF(side * 0.28, side * 0.30), QPointF(side * 0.60, side * 0.20));
        painter.drawEllipse(QPointF(side * 0.66, side * 0.51), side * 0.035, side * 0.035);
    } else if (key == "group" || key == "members") {
        painter.drawEllipse(QPointF(side * 0.38, side * 0.36), side * 0.11, side * 0.11);
        painter.drawEllipse(QPointF(side * 0.62, side * 0.36), side * 0.11, side * 0.11);
        painter.drawArc(QRectF(side * 0.22, side * 0.52, side * 0.32, side * 0.25), 20 * 16, 140 * 16);
        painter.drawArc(QRectF(side * 0.46, side * 0.52, side * 0.32, side * 0.25), 20 * 16, 140 * 16);
    } else if (key == "channel") {
        QPolygonF horn;
        horn << QPointF(side * 0.20, side * 0.54)
             << QPointF(side * 0.64, side * 0.34)
             << QPointF(side * 0.64, side * 0.74)
             << QPointF(side * 0.20, side * 0.58);
        painter.drawPolygon(horn);
        painter.drawLine(QPointF(side * 0.20, side * 0.58), QPointF(side * 0.12, side * 0.70));
    } else if (key == "call") {
        painter.drawArc(QRectF(side * 0.22, side * 0.20, side * 0.56, side * 0.56), 215 * 16, 110 * 16);
        painter.drawLine(QPointF(side * 0.31, side * 0.69), QPointF(side * 0.22, side * 0.78));
        painter.drawLine(QPointF(side * 0.69, side * 0.31), QPointF(side * 0.78, side * 0.22));
    } else if (key == "bookmark" || key == "saved") {
        painter.drawPath([&] {
            QPainterPath path;
            path.moveTo(side * 0.28, side * 0.18);
            path.lineTo(side * 0.72, side * 0.18);
            path.lineTo(side * 0.72, side * 0.80);
            path.lineTo(side * 0.50, side * 0.64);
            path.lineTo(side * 0.28, side * 0.80);
            path.closeSubpath();
            return path;
        }());
    } else if (key == "settings" || key == "advanced") {
        painter.drawEllipse(QPointF(cx, cy), side * 0.15, side * 0.15);
        for (int i = 0; i < 8; ++i) {
            const double a = (3.14159265358979323846 * 2.0 * i) / 8.0;
            painter.drawLine(QPointF(cx + std::cos(a) * side * 0.25, cy + std::sin(a) * side * 0.25),
                             QPointF(cx + std::cos(a) * side * 0.36, cy + std::sin(a) * side * 0.36));
        }
    } else if (key == "bell" || key == "mute") {
        painter.drawArc(QRectF(side * 0.30, side * 0.24, side * 0.40, side * 0.42), 20 * 16, 140 * 16);
        painter.drawLine(QPointF(side * 0.30, side * 0.58), QPointF(side * 0.70, side * 0.58));
        painter.drawLine(QPointF(side * 0.42, side * 0.72), QPointF(side * 0.58, side * 0.72));
    } else if (key == "lock") {
        painter.drawRoundedRect(QRectF(side * 0.28, side * 0.44, side * 0.44, side * 0.34), side * 0.06, side * 0.06);
        painter.drawArc(QRectF(side * 0.34, side * 0.22, side * 0.32, side * 0.36), 0, 180 * 16);
    } else if (key == "chat" || key == "message" || key == "discuss") {
        painter.drawRoundedRect(QRectF(side * 0.20, side * 0.24, side * 0.60, side * 0.44), side * 0.08, side * 0.08);
        painter.drawLine(QPointF(side * 0.38, side * 0.68), QPointF(side * 0.28, side * 0.80));
    } else if (key == "folder") {
        painter.drawRoundedRect(QRectF(side * 0.18, side * 0.34, side * 0.64, side * 0.40), side * 0.06, side * 0.06);
        painter.drawLine(QPointF(side * 0.20, side * 0.34), QPointF(side * 0.40, side * 0.24));
        painter.drawLine(QPointF(side * 0.40, side * 0.24), QPointF(side * 0.56, side * 0.34));
    } else if (key == "speaker") {
        painter.drawPolyline(QPolygonF{QPointF(side * 0.20, side * 0.56), QPointF(side * 0.36, side * 0.56),
                                      QPointF(side * 0.56, side * 0.36), QPointF(side * 0.56, side * 0.72),
                                      QPointF(side * 0.36, side * 0.56)});
        painter.drawArc(QRectF(side * 0.54, side * 0.34, side * 0.28, side * 0.36), -45 * 16, 90 * 16);
    } else if (key == "battery") {
        painter.drawRoundedRect(QRectF(side * 0.20, side * 0.36, side * 0.54, side * 0.30), side * 0.04, side * 0.04);
        painter.drawLine(QPointF(side * 0.78, side * 0.45), QPointF(side * 0.78, side * 0.57));
    } else if (key == "language") {
        painter.drawEllipse(r);
        painter.drawLine(QPointF(side * 0.18, cy), QPointF(side * 0.82, cy));
        painter.drawArc(QRectF(side * 0.36, side * 0.18, side * 0.28, side * 0.64), 90 * 16, 180 * 16);
        painter.drawArc(QRectF(side * 0.36, side * 0.18, side * 0.28, side * 0.64), -90 * 16, 180 * 16);
    } else if (key == "gift" || key == "premium" || key == "stars") {
        painter.drawRect(QRectF(side * 0.24, side * 0.42, side * 0.52, side * 0.36));
        painter.drawLine(QPointF(cx, side * 0.42), QPointF(cx, side * 0.78));
        painter.drawLine(QPointF(side * 0.24, side * 0.54), QPointF(side * 0.76, side * 0.54));
        painter.drawEllipse(QPointF(side * 0.42, side * 0.34), side * 0.08, side * 0.08);
        painter.drawEllipse(QPointF(side * 0.58, side * 0.34), side * 0.08, side * 0.08);
    } else if (key == "link") {
        painter.drawRoundedRect(QRectF(side * 0.20, side * 0.38, side * 0.32, side * 0.22), side * 0.10, side * 0.10);
        painter.drawRoundedRect(QRectF(side * 0.48, side * 0.38, side * 0.32, side * 0.22), side * 0.10, side * 0.10);
    } else if (key == "attach") {
        painter.drawArc(QRectF(side * 0.28, side * 0.16, side * 0.38, side * 0.62), 230 * 16, 260 * 16);
        painter.drawArc(QRectF(side * 0.40, side * 0.28, side * 0.24, side * 0.42), 230 * 16, 250 * 16);
    } else if (key == "pin") {
        painter.drawLine(QPointF(side * 0.36, side * 0.22), QPointF(side * 0.64, side * 0.50));
        painter.drawLine(QPointF(side * 0.52, side * 0.62), QPointF(side * 0.76, side * 0.38));
        painter.drawLine(QPointF(cx, side * 0.58), QPointF(side * 0.28, side * 0.80));
    } else if (key == "device" || key == "remote") {
        painter.drawRoundedRect(QRectF(side * 0.18, side * 0.24, side * 0.64, side * 0.42), side * 0.04, side * 0.04);
        painter.drawLine(QPointF(side * 0.40, side * 0.76), QPointF(side * 0.60, side * 0.76));
        painter.drawLine(QPointF(cx, side * 0.66), QPointF(cx, side * 0.76));
    } else if (key == "leave") {
        painter.drawRect(QRectF(side * 0.24, side * 0.24, side * 0.32, side * 0.52));
        painter.drawLine(QPointF(side * 0.54, cy), QPointF(side * 0.82, cy));
        painter.drawLine(QPointF(side * 0.70, side * 0.38), QPointF(side * 0.82, cy));
        painter.drawLine(QPointF(side * 0.70, side * 0.62), QPointF(side * 0.82, cy));
    } else if (key == "moon") {
        painter.drawArc(QRectF(side * 0.26, side * 0.20, side * 0.52, side * 0.58), 70 * 16, 250 * 16);
    } else if (key == "scale") {
        painter.drawEllipse(QPointF(cx, cy), side * 0.26, side * 0.18);
        painter.drawEllipse(QPointF(cx, cy), side * 0.07, side * 0.07);
    } else if (key == "photo" || key == "files") {
        painter.drawRect(QRectF(side * 0.22, side * 0.24, side * 0.56, side * 0.48));
        painter.drawPolyline(QPolygonF{QPointF(side * 0.28, side * 0.64), QPointF(side * 0.42, side * 0.50),
                                      QPointF(side * 0.54, side * 0.60), QPointF(side * 0.66, side * 0.44)});
    } else if (key == "timer") {
        painter.drawEllipse(QPointF(cx, cy), side * 0.28, side * 0.28);
        painter.drawLine(QPointF(cx, cy), QPointF(cx, side * 0.34));
        painter.drawLine(QPointF(cx, cy), QPointF(side * 0.62, side * 0.56));
    } else if (key == "poll") {
        painter.drawLine(QPointF(side * 0.30, side * 0.66), QPointF(side * 0.30, side * 0.46));
        painter.drawLine(QPointF(side * 0.50, side * 0.66), QPointF(side * 0.50, side * 0.34));
        painter.drawLine(QPointF(side * 0.70, side * 0.66), QPointF(side * 0.70, side * 0.54));
    } else if (key == "voice") {
        painter.drawRoundedRect(QRectF(side * 0.38, side * 0.18, side * 0.24, side * 0.42), side * 0.10, side * 0.10);
        painter.drawArc(QRectF(side * 0.28, side * 0.34, side * 0.44, side * 0.30), 200 * 16, 140 * 16);
        painter.drawLine(QPointF(cx, side * 0.66), QPointF(cx, side * 0.80));
    } else {
        painter.drawEllipse(r);
    }
    return QIcon(pixmap);
}

int run_two_client_flow_smoke(const Args& args) {
    ControlPlaneClient alice;
    ControlPlaneClient bob;
    const bool alice_connected = args.tls
        ? alice.connect_tls(args.host, args.port, args.tls_insecure, args.tls_server_name)
        : alice.connect(args.host, args.port);
    if (!alice_connected) {
        std::cerr << "desktop two-client flow smoke: alice connect failed\n";
        return 1;
    }
    const bool bob_connected = args.tls
        ? bob.connect_tls(args.host, args.port, args.tls_insecure, args.tls_server_name)
        : bob.connect(args.host, args.port);
    if (!bob_connected) {
        std::cerr << "desktop two-client flow smoke: bob connect failed\n";
        return 1;
    }

    const auto alice_login = alice.login("alice", "alice_pw", "dev_alice_two_client_ui");
    if (!alice_login.ok) {
        std::cerr << "desktop two-client flow smoke: alice login failed "
                  << alice_login.error_code << " " << alice_login.error_message << "\n";
        return 1;
    }
    const auto bob_login = bob.login("bob", "bob_pw", "dev_bob_two_client_ui");
    if (!bob_login.ok) {
        std::cerr << "desktop two-client flow smoke: bob login failed "
                  << bob_login.error_code << " " << bob_login.error_message << "\n";
        return 1;
    }

    const auto alice_add = alice.add_contact("u_bob");
    if (!alice_add.ok) {
        std::cerr << "desktop two-client flow smoke: alice add contact failed "
                  << alice_add.error_code << " " << alice_add.error_message << "\n";
        return 1;
    }
    const auto bob_add = bob.add_contact("u_alice");
    if (!bob_add.ok) {
        std::cerr << "desktop two-client flow smoke: bob add contact failed "
                  << bob_add.error_code << " " << bob_add.error_message << "\n";
        return 1;
    }

    auto alice_sync = alice.conversation_sync();
    auto bob_sync = bob.conversation_sync();
    if (!alice_sync.ok || !bob_sync.ok) {
        std::cerr << "desktop two-client flow smoke: initial sync failed\n";
        return 1;
    }
    const std::string conversation = args.conversation;
    const std::string alice_text = "hello bob from desktop two-client flow";
    const auto alice_sent = alice.send_message(conversation, alice_text);
    if (!alice_sent.ok) {
        std::cerr << "desktop two-client flow smoke: alice send failed "
                  << alice_sent.error_code << " " << alice_sent.error_message << "\n";
        return 1;
    }
    bob_sync = bob.conversation_sync();
    bool bob_saw_alice_message = false;
    for (const auto& conv : bob_sync.conversations) {
        if (conv.conversation_id != conversation) continue;
        for (const auto& msg : conv.messages) {
            if (msg.message_id == alice_sent.message_id && msg.text == alice_text
                && msg.sender_user_id == "u_alice") {
                bob_saw_alice_message = true;
            }
        }
    }
    if (!bob_sync.ok || !bob_saw_alice_message) {
        std::cerr << "desktop two-client flow smoke: bob did not receive alice message\n";
        return 1;
    }

    const std::string bob_text = "hi alice from desktop two-client flow";
    const auto bob_sent = bob.send_message(conversation, bob_text);
    if (!bob_sent.ok) {
        std::cerr << "desktop two-client flow smoke: bob send failed "
                  << bob_sent.error_code << " " << bob_sent.error_message << "\n";
        return 1;
    }
    alice_sync = alice.conversation_sync();
    bool alice_saw_bob_message = false;
    for (const auto& conv : alice_sync.conversations) {
        if (conv.conversation_id != conversation) continue;
        for (const auto& msg : conv.messages) {
            if (msg.message_id == bob_sent.message_id && msg.text == bob_text
                && msg.sender_user_id == "u_bob") {
                alice_saw_bob_message = true;
            }
        }
    }
    if (!alice_sync.ok || !alice_saw_bob_message) {
        std::cerr << "desktop two-client flow smoke: alice did not receive bob message\n";
        return 1;
    }

    std::cout << "desktop two-client flow smoke ok: alice="
              << alice_login.user_id << " bob=" << bob_login.user_id
              << " contacts=mutual conversation=" << conversation
              << " alice_message=" << alice_sent.message_id
              << " bob_message=" << bob_sent.message_id << "\n";
    alice.disconnect();
    bob.disconnect();
    return 0;
}

int run_smoke(const Args& args) {
    if (args.smoke_two_client_flow) {
        return run_two_client_flow_smoke(args);
    }
    const std::string smoke_conversation = args.conversation.empty()
        ? std::string("conv_alice_bob")
        : args.conversation;
    const std::string smoke_user = args.user.empty() ? std::string("alice") : args.user;
    const std::string smoke_password = args.password.empty() ? std::string("alice_pw") : args.password;
    const std::string smoke_device = args.device.empty() ? std::string("dev_alice_qt_smoke") : args.device;
    ControlPlaneClient client;
    const bool connected = args.tls
        ? client.connect_tls(args.host, args.port, args.tls_insecure, args.tls_server_name)
        : client.connect(args.host, args.port);
    if (!connected) {
        std::cerr << "desktop smoke: connect failed\n";
        return 1;
    }
    if (args.smoke_register) {
        const auto reg = client.register_user(
            smoke_user,
            smoke_password,
            args.display_name.empty() ? smoke_user : args.display_name,
            smoke_device
        );
        if (!reg.ok) {
            std::cerr << "desktop register smoke: register failed " << reg.error_code << " "
                      << reg.error_message << "\n";
            return 1;
        }
        std::cout << "desktop register smoke ok: user=" << reg.user_id
                  << " device=" << reg.device_id << "\n";
        client.disconnect();
        return 0;
    }
    const auto login = client.login(smoke_user, smoke_password, smoke_device);
    if (!login.ok) {
        std::cerr << "desktop smoke: login failed " << login.error_code << " "
                  << login.error_message << "\n";
        return 1;
    }
    const auto sync = client.conversation_sync();
    if (!sync.ok) {
        std::cerr << "desktop smoke: sync failed " << sync.error_code << " "
                  << sync.error_message << "\n";
        return 1;
    }
    telegram_like::client::app_desktop::DesktopChatStore smoke_store;
    smoke_store.set_current_user(login.user_id);
    smoke_store.set_selected_conversation(smoke_conversation);
    smoke_store.apply_sync(sync);
    const auto filtered_chats = smoke_store.filtered_conversations("alice");
    const auto message_matches = smoke_store.search_selected_messages("hello");
    const auto highlighted = smoke_store.render_selected_timeline_html("hello",
        message_matches.empty() ? std::string {} : message_matches.front().message_id);
    if (filtered_chats.empty() || message_matches.empty()
        || highlighted.find("match") == std::string::npos
        || highlighted.find("focused") == std::string::npos) {
        std::cerr << "desktop smoke: navigation search failed\n";
        return 1;
    }
    std::cout << "desktop navigation search smoke ok: chats=" << filtered_chats.size()
              << " matches=" << message_matches.size()
              << " first=" << message_matches.front().message_id << "\n";
    std::vector<telegram_like::client::transport::SyncCursor> cursors;
    for (const auto& conversation : sync.conversations) {
        if (conversation.conversation_id == smoke_conversation && !conversation.messages.empty()) {
            cursors.push_back(telegram_like::client::transport::SyncCursor {
                .conversation_id = conversation.conversation_id,
                .last_message_id = conversation.messages.back().message_id,
                .version = conversation.version,
            });
        }
    }
    const auto sent = client.send_message(smoke_conversation, "hello from Qt desktop smoke");
    if (!sent.ok) {
        std::cerr << "desktop smoke: send failed " << sent.error_code << " "
                  << sent.error_message << "\n";
        return 1;
    }
    std::cout << "desktop smoke ok: user=" << login.user_id
              << " conversations=" << sync.conversations.size()
              << " message_id=" << sent.message_id << "\n";
    smoke_store.apply_sent_message(smoke_conversation, sent);
    const auto reply = client.reply_message(smoke_conversation, sent.message_id, "reply from Qt desktop smoke");
    if (!reply.ok || reply.reply_to_message_id != sent.message_id) {
        std::cerr << "desktop smoke: reply failed " << reply.error_code << " "
                  << reply.error_message << "\n";
        return 1;
    }
    smoke_store.apply_sent_message(smoke_conversation, reply);
    const auto reaction = client.toggle_reaction(smoke_conversation, sent.message_id, "+1");
    if (!reaction.ok || reaction.reaction_summary.find("+1:1") == std::string::npos) {
        std::cerr << "desktop smoke: reaction failed " << reaction.error_code << " "
                  << reaction.error_message << "\n";
        return 1;
    }
    smoke_store.apply_reaction_summary(smoke_conversation, sent.message_id, reaction.reaction_summary);
    const auto pinned = client.set_message_pin(smoke_conversation, sent.message_id, true);
    if (!pinned.ok || !pinned.pinned) {
        std::cerr << "desktop smoke: pin failed " << pinned.error_code << " "
                  << pinned.error_message << "\n";
        return 1;
    }
    smoke_store.apply_pin_state(smoke_conversation, sent.message_id, true);
    const auto forwarded = client.forward_message(smoke_conversation, sent.message_id, smoke_conversation);
    if (!forwarded.ok || forwarded.forwarded_from_message_id != sent.message_id) {
        std::cerr << "desktop smoke: forward failed " << forwarded.error_code << " "
                  << forwarded.error_message << "\n";
        return 1;
    }
    smoke_store.apply_sent_message(smoke_conversation, forwarded);
    const auto actions_transcript = smoke_store.render_selected_transcript();
    if (actions_transcript.find("[reply_to=" + sent.message_id + "]") == std::string::npos
        || actions_transcript.find("[reactions=+1:1]") == std::string::npos
        || actions_transcript.find("[pinned]") == std::string::npos
        || actions_transcript.find("[forwarded_from=" + smoke_conversation + "/" + sent.message_id) == std::string::npos) {
        std::cerr << "desktop smoke: message actions store rendering failed\n";
        return 1;
    }
    std::cout << "desktop message actions smoke ok: reply=" << reply.message_id
              << " forward=" << forwarded.message_id
              << " reactions=" << reaction.reaction_summary << "\n";
    const auto server_search = client.search_messages("reply from Qt desktop smoke", "", 10);
    bool saw_server_search_result = false;
    for (const auto& result : server_search.results) {
        if (result.message_id == reply.message_id && result.conversation_id == smoke_conversation) {
            saw_server_search_result = true;
        }
    }
    if (!server_search.ok || !saw_server_search_result) {
        std::cerr << "desktop smoke: server message search failed "
                  << server_search.error_code << " " << server_search.error_message << "\n";
        return 1;
    }
    std::cout << "desktop server message search smoke ok: results="
              << server_search.results.size() << " hit=" << reply.message_id << "\n";
    const auto history_page = client.conversation_history_page(smoke_conversation, "", 2);
    if (!history_page.ok || history_page.conversations.empty()
        || history_page.conversations.front().messages.size() != 2
        || !history_page.conversations.front().has_more
        || history_page.conversations.front().next_before_message_id.empty()) {
        std::cerr << "desktop smoke: history page failed\n";
        return 1;
    }
    std::cout << "desktop history page smoke ok: messages="
              << history_page.conversations.front().messages.size()
              << " next_before=" << history_page.conversations.front().next_before_message_id << "\n";
    const auto incremental = client.conversation_sync_since(cursors);
    bool saw_sent_incremental = false;
    for (const auto& conversation : incremental.conversations) {
        for (const auto& message : conversation.messages) {
            if (message.message_id == sent.message_id) saw_sent_incremental = true;
        }
    }
    if (!incremental.ok || !saw_sent_incremental) {
        std::cerr << "desktop smoke: incremental sync missed " << sent.message_id << "\n";
        return 1;
    }
    std::cout << "desktop incremental smoke ok: message_id=" << sent.message_id << "\n";
    const auto devices = client.list_devices();
    if (!devices.ok || devices.devices.empty()) {
        std::cerr << "desktop smoke: device list failed " << devices.error_code << " "
                  << devices.error_message << "\n";
        return 1;
    }
    std::cout << "desktop devices smoke ok: devices=" << devices.devices.size()
              << " first=" << devices.devices.front().device_id << "\n";
    const auto profile = client.profile_get();
    if (!profile.ok || profile.user_id != login.user_id) {
        std::cerr << "desktop smoke: profile get failed " << profile.error_code << " "
                  << profile.error_message << "\n";
        return 1;
    }
    const auto updated_profile = client.profile_update("Alice Smoke");
    if (!updated_profile.ok || updated_profile.display_name != "Alice Smoke") {
        std::cerr << "desktop smoke: profile update failed " << updated_profile.error_code << " "
                  << updated_profile.error_message << "\n";
        return 1;
    }
    std::cout << "desktop profile smoke ok: user=" << updated_profile.user_id
              << " display=" << updated_profile.display_name << "\n";
    const auto search_before_contact = client.search_users("bob", 5);
    if (!search_before_contact.ok || search_before_contact.results.empty()
        || search_before_contact.results.front().user_id != "u_bob") {
        std::cerr << "desktop smoke: user search failed " << search_before_contact.error_code << " "
                  << search_before_contact.error_message << "\n";
        return 1;
    }
    std::cout << "desktop user search smoke ok: results="
              << search_before_contact.results.size()
              << " first=" << search_before_contact.results.front().user_id << "\n";
    const auto contacts_added = client.add_contact("u_bob");
    if (!contacts_added.ok || contacts_added.contacts.empty()) {
        std::cerr << "desktop smoke: contact add failed " << contacts_added.error_code << " "
                  << contacts_added.error_message << "\n";
        return 1;
    }
    const auto search_after_contact = client.search_users("bob", 5);
    if (!search_after_contact.ok || search_after_contact.results.empty()
        || !search_after_contact.results.front().is_contact) {
        std::cerr << "desktop smoke: user search contact flag failed\n";
        return 1;
    }
    const auto contacts_removed = client.remove_contact("u_bob");
    if (!contacts_removed.ok) {
        std::cerr << "desktop smoke: contact remove failed " << contacts_removed.error_code << " "
                  << contacts_removed.error_message << "\n";
        return 1;
    }
    std::cout << "desktop contacts smoke ok: added=u_bob remaining="
              << contacts_removed.contacts.size() << "\n";
    const auto group = client.create_conversation({"u_bob"}, "Qt Smoke Group");
    if (!group.ok || group.conversation.conversation_id.empty()
        || group.conversation.participant_user_ids.size() < 2) {
        std::cerr << "desktop smoke: group create failed " << group.error_code << " "
                  << group.error_message << "\n";
        return 1;
    }
    std::cout << "desktop group smoke ok: conversation_id="
              << group.conversation.conversation_id
              << " participants=" << group.conversation.participant_user_ids.size() << "\n";
    auto require_ack = [](const char* label, const telegram_like::client::transport::AckResult& ack) {
        if (!ack.ok) {
            std::cerr << "desktop smoke: " << label << " failed "
                      << ack.error_code << " " << ack.error_message << "\n";
            return false;
        }
        return true;
    };
    if (!require_ack("draft save", client.save_draft(smoke_conversation, "desktop smoke draft"))
        || !require_ack("draft clear", client.clear_draft(smoke_conversation))
        || !require_ack("conversation pin", client.set_conversation_pinned(smoke_conversation, true))
        || !require_ack("conversation unpin", client.set_conversation_pinned(smoke_conversation, false))
        || !require_ack("conversation archive", client.set_conversation_archived(smoke_conversation, true))
        || !require_ack("conversation unarchive", client.set_conversation_archived(smoke_conversation, false))
        || !require_ack("conversation mute", client.set_conversation_mute(smoke_conversation, -1))
        || !require_ack("conversation unmute", client.set_conversation_mute(smoke_conversation, 0))
        || !require_ack("profile avatar clear", client.update_profile_avatar(""))
        || !require_ack("conversation avatar clear", client.update_conversation_avatar(smoke_conversation, ""))
        || !require_ack("block user", client.block_user("u_bob"))
        || !require_ack("unblock user", client.unblock_user("u_bob"))) {
        return 1;
    }
    const auto account_export = client.account_export();
    if (!account_export.ok || account_export.user_id != login.user_id) {
        std::cerr << "desktop smoke: account export failed "
                  << account_export.error_code << " " << account_export.error_message << "\n";
        return 1;
    }
    const auto poll = client.create_poll(smoke_conversation, "Desktop smoke poll", {"Yes", "No"}, false);
    if (!poll.ok || poll.message_id.empty()) {
        std::cerr << "desktop smoke: poll create failed "
                  << poll.error_code << " " << poll.error_message << "\n";
        return 1;
    }
    const auto poll_vote = client.vote_poll(smoke_conversation, poll.message_id, {0});
    if (!poll_vote.ok) {
        std::cerr << "desktop smoke: poll vote failed "
                  << poll_vote.error_code << " " << poll_vote.error_message << "\n";
        return 1;
    }
    const auto poll_close = client.close_poll(smoke_conversation, poll.message_id);
    if (!poll_close.ok || !poll_close.closed) {
        std::cerr << "desktop smoke: poll close failed "
                  << poll_close.error_code << " " << poll_close.error_message << "\n";
        return 1;
    }
    std::cout << "desktop advanced RC-005 smoke ok: export_user=" << account_export.user_id
              << " poll=" << poll.message_id
              << " devices=" << account_export.devices << "\n";
    if (args.smoke_attachment) {
        const std::string attachment_body = "desktop attachment smoke bytes";
        std::vector<std::string> upload_stages;
        upload_stages.push_back("queued");
        upload_stages.push_back("uploading");
        const auto attached = client.send_attachment(
            smoke_conversation,
            "desktop attachment smoke",
            "desktop-smoke.txt",
            "text/plain",
            attachment_body
        );
        if (!attached.ok) {
            std::cerr << "desktop smoke: attachment send failed " << attached.error_code << " "
                      << attached.error_message << "\n";
            return 1;
        }
        upload_stages.push_back("uploaded");
        std::cout << "desktop attachment upload progress smoke ok: stages="
                  << upload_stages.front() << "," << upload_stages[1] << ","
                  << upload_stages.back() << " bytes=" << attachment_body.size() << "\n";
        std::vector<std::string> download_stages;
        download_stages.push_back("downloading");
        const auto fetched = client.fetch_attachment(attached.attachment_id);
        if (!fetched.ok || fetched.content != attachment_body) {
            std::cerr << "desktop smoke: attachment fetch mismatch\n";
            return 1;
        }
        download_stages.push_back("downloaded");
        if (!args.smoke_save_dir.empty()) {
            const std::string save_path = args.smoke_save_dir + "/desktop-smoke.txt";
            download_stages.push_back("saving");
            std::ofstream out(save_path, std::ios::binary | std::ios::trunc);
            out.write(fetched.content.data(), static_cast<std::streamsize>(fetched.content.size()));
            out.close();
            if (!out) {
                std::cerr << "desktop smoke: attachment save failed\n";
                return 1;
            }
            download_stages.push_back("saved");
            std::cout << "desktop attachment save smoke ok: path=" << save_path
                      << " bytes=" << fetched.content.size() << "\n";
        }
        std::cout << "desktop attachment download progress smoke ok: stages=";
        for (std::size_t i = 0; i < download_stages.size(); ++i) {
            if (i > 0) std::cout << ",";
            std::cout << download_stages[i];
        }
        std::cout << " bytes=" << fetched.content.size() << "\n";
        std::cout << "desktop attachment smoke ok: attachment_id="
                  << attached.attachment_id << " bytes=" << fetched.content.size() << "\n";
    }
    client.disconnect();
    return 0;
}

class DesktopWindow final : public QMainWindow {
    enum class DeviceAction { Revoke, Trust, Untrust };

public:
    explicit DesktopWindow(const Args& args, QWidget* parent = nullptr)
        : QMainWindow(parent), args_(args) {
        // ---- create every widget first; layout is assembled below ----
        QSettings remembered;
        const bool has_remembered_login = !args.gui_smoke
            && remembered.value(QStringLiteral("auth/remembered"), false).toBool();
        const QString remembered_host = args.gui_smoke
            ? qstr(args.host)
            : remembered.value(QStringLiteral("auth/host"), qstr(args.host)).toString();
        const int remembered_port = args.gui_smoke
            ? args.port
            : remembered.value(QStringLiteral("auth/port"), args.port).toInt();
        const QString remembered_user = args.gui_smoke
            ? qstr(args.user)
            : remembered.value(QStringLiteral("auth/user"), qstr(args.user)).toString();
        const QString remembered_password = args.gui_smoke
            ? qstr(args.password)
            : remembered.value(QStringLiteral("auth/password"), qstr(args.password)).toString();
        const QString remembered_display = args.gui_smoke
            ? qstr(args.display_name)
            : remembered.value(QStringLiteral("auth/display_name"), qstr(args.display_name)).toString();
        const QString remembered_device = args.gui_smoke
            ? qstr(args.device)
            : remembered.value(QStringLiteral("auth/device"), qstr(args.device)).toString();

        host_ = new QLineEdit(remembered_host);
        port_ = new QSpinBox();
        port_->setRange(1, 65535);
        port_->setValue(remembered_port);
        conversation_ = new QLineEdit(qstr(args.conversation));
        tls_ = new QCheckBox("TLS");
        tls_->setChecked(args.tls);
        tls_insecure_ = new QCheckBox("Dev insecure");
        tls_insecure_->setChecked(args.tls_insecure);

        user_ = new QLineEdit(remembered_user);
        password_ = new QLineEdit(remembered_password);
        password_->setEchoMode(QLineEdit::Password);
        display_name_ = new QLineEdit(remembered_display.isEmpty() ? remembered_user : remembered_display);
        device_ = new QLineEdit(remembered_device);
        connect_ = new QPushButton("Connect");
        connect_->setObjectName("primary");
        register_ = new QPushButton("Register");

        profile_display_name_ = new QLineEdit();
        profile_display_name_->setPlaceholderText("profile display name");
        refresh_profile_ = new QPushButton("Refresh");
        save_profile_ = new QPushButton("Save");
        profile_ = new QPlainTextEdit();
        profile_->setReadOnly(true);
        profile_->setMaximumHeight(72);
        profile_->setPlaceholderText("Profile appears here after connect.");
        set_profile_action_enabled(false);

        // M138: BubbleListView replaces the QTextBrowser-based timeline.
        // Bubbles, ticks, gradients, avatars, reply quotes, forwarded
        // headers, reaction chips, pinned markers + the right-click
        // context menu are all painted by BubbleDelegate, so we no longer
        // depend on Qt rich text supporting things it doesn't.
        messages_ = new telegram_like::client::app_desktop::BubbleListView();

        chat_filter_ = new QLineEdit();
        chat_filter_->setObjectName("sidebarSearchInput");
        chat_filter_->setPlaceholderText("Search");
        chat_filter_->setClearButtonEnabled(true);

        message_search_ = new QLineEdit();
        message_search_->setPlaceholderText("Search in this chat");
        message_search_->setClearButtonEnabled(true);
        prev_match_ = new QPushButton("‹");
        next_match_ = new QPushButton("›");
        prev_match_->setMaximumWidth(28);
        next_match_->setMaximumWidth(28);
        load_older_ = new QPushButton("Older");
        server_search_ = new QPushButton("Server");
        load_older_->setEnabled(false);
        server_search_->setEnabled(false);
        search_status_ = new QLabel("No search");
        search_status_->setObjectName("searchStatus");
        message_search_results_ = new QPlainTextEdit();
        message_search_results_->setReadOnly(true);
        message_search_results_->setMaximumHeight(96);
        message_search_results_->setPlaceholderText("Server search results appear here.");

        conversations_ = new QListWidget();
        conversations_->setObjectName("chatList");
        conversations_->setMinimumWidth(360);
        conversations_->setSpacing(0);
        conversations_->setItemDelegate(new ChatListDelegate(conversations_));
        conversations_->setMouseTracking(true);

        composer_ = new QLineEdit();
        composer_->setObjectName("composerInput");
        composer_->setPlaceholderText("Write a message...");
        send_ = new QPushButton(QString::fromUtf8("\xe2\x9e\xa4"));  // ➤
        send_->setObjectName("primary");
        send_->setToolTip("Send");
        attach_ = new QPushButton();
        attach_->setObjectName("ghost");
        attach_->setIcon(line_icon("attach", 28, QColor("#8a9299")));
        attach_->setIconSize(QSize(28, 28));
        attach_->setToolTip("Attach file");
        emoji_panel_ = new QPushButton();
        emoji_panel_->setObjectName("ghost");
        emoji_panel_->setIcon(line_icon("smile", 26, QColor("#8a9299")));
        emoji_panel_->setIconSize(QSize(26, 26));
        emoji_panel_->setToolTip("Emoji and stickers");
        send_->setEnabled(false);
        attach_->setEnabled(false);
        emoji_panel_->setEnabled(true);

        message_action_id_ = new QLineEdit();
        message_action_id_->setPlaceholderText("message_id");
        reaction_emoji_ = new QLineEdit("+1");
        reaction_emoji_->setMaximumWidth(80);
        reply_ = new QPushButton("Reply");
        forward_ = new QPushButton("Forward");
        react_ = new QPushButton("React");
        pin_ = new QPushButton("Pin");
        unpin_ = new QPushButton("Unpin");
        edit_ = new QPushButton("Edit");
        delete_ = new QPushButton("Delete");
        use_match_ = new QPushButton("Use Match");
        use_latest_ = new QPushButton("Use Latest");
        set_message_action_enabled(false);

        attachment_id_ = new QLineEdit();
        attachment_id_->setPlaceholderText("attachment_id to save");
        save_attachment_ = new QPushButton("Save Attachment");
        save_attachment_->setEnabled(false);

        transfer_status_ = new QLabel("Transfer idle");
        transfer_progress_ = new QProgressBar();
        transfer_progress_->setRange(0, 100);
        transfer_progress_->setValue(0);
        transfer_progress_->setTextVisible(true);

        refresh_devices_ = new QPushButton("Refresh Devices");
        refresh_devices_->setEnabled(false);
        devices_ = new QPlainTextEdit();
        devices_->setReadOnly(true);
        devices_->setMaximumHeight(110);
        devices_->setPlaceholderText("Connected devices appear here.");

        device_action_id_ = new QLineEdit();
        device_action_id_->setPlaceholderText("device_id to manage");
        revoke_device_ = new QPushButton("Revoke");
        trust_device_ = new QPushButton("Trust");
        untrust_device_ = new QPushButton("Untrust");
        set_device_action_enabled(false);

        refresh_contacts_ = new QPushButton("Refresh Contacts");
        refresh_contacts_->setEnabled(false);
        contact_user_id_ = new QLineEdit();
        contact_user_id_->setPlaceholderText("user_id");
        add_contact_ = new QPushButton("Add");
        remove_contact_ = new QPushButton("Remove");
        contacts_ = new QPlainTextEdit();
        contacts_->setReadOnly(true);
        contacts_->setMaximumHeight(100);
        contacts_->setPlaceholderText("Contacts appear here.");
        set_contact_action_enabled(false);

        user_search_query_ = new QLineEdit();
        user_search_query_->setPlaceholderText("search username/display/user_id");
        search_users_ = new QPushButton("Search Users");
        user_search_results_ = new QPlainTextEdit();
        user_search_results_->setReadOnly(true);
        user_search_results_->setMaximumHeight(100);
        user_search_results_->setPlaceholderText("User search results appear here.");
        set_user_search_enabled(false);

        group_title_ = new QLineEdit();
        group_title_->setPlaceholderText("new group title");
        group_participants_ = new QLineEdit();
        group_participants_->setPlaceholderText("participant user_ids comma-separated");
        create_group_ = new QPushButton("Create Group");
        create_group_->setEnabled(false);

        member_user_id_ = new QLineEdit();
        member_user_id_->setPlaceholderText("member user_id");
        add_member_ = new QPushButton("Add Member");
        remove_member_ = new QPushButton("Remove Member");
        set_group_action_enabled(false);

        // ---- M128: voice/video call panel ----
        call_callee_user_ = new QLineEdit();
        call_callee_user_->setPlaceholderText("callee user_id (e.g. u_bob)");
        call_callee_device_ = new QLineEdit();
        call_callee_device_->setPlaceholderText("callee device_id (e.g. dev_bob_win)");
        call_kind_ = new QComboBox();
        call_kind_->addItem("audio");
        call_kind_->addItem("video");
        call_id_input_ = new QLineEdit();
        call_id_input_->setPlaceholderText("call_id (auto-filled after invite)");
        call_invite_ = new QPushButton("Invite");
        call_accept_ = new QPushButton("Accept");
        call_decline_ = new QPushButton("Decline");
        call_end_ = new QPushButton("End");
        call_log_ = new QPlainTextEdit();
        call_log_->setReadOnly(true);
        call_log_->setMaximumHeight(140);
        call_log_->setPlaceholderText("Call FSM transitions appear here.");
        set_call_action_enabled(false);

        // ---- M108: remote-control panel ----
        remote_target_device_ = new QLineEdit();
        remote_target_device_->setPlaceholderText("target device_id (e.g. dev_bob_win)");
        remote_invite_ = new QPushButton("Invite");
        remote_session_id_input_ = new QLineEdit();
        remote_session_id_input_->setPlaceholderText("remote_session_id (from invite or push)");
        remote_approve_ = new QPushButton("Approve");
        remote_reject_ = new QPushButton("Reject");
        remote_cancel_ = new QPushButton("Cancel");
        remote_terminate_ = new QPushButton("Terminate");
        remote_rendezvous_ = new QPushButton("Rendezvous");
        remote_log_ = new QPlainTextEdit();
        remote_log_->setReadOnly(true);
        remote_log_->setMaximumHeight(140);
        remote_log_->setPlaceholderText("Remote-control RPC results and rendezvous info appear here.");
        set_remote_action_enabled(false);

        // ---- RC-005: server-backed advanced account/chat primitives ----
        advanced_target_user_ = new QLineEdit();
        advanced_target_user_->setPlaceholderText("target user_id or phone number");
        advanced_code_ = new QLineEdit();
        advanced_code_->setPlaceholderText("OTP / 2FA code");
        advanced_password_ = new QLineEdit();
        advanced_password_->setPlaceholderText("current password for delete confirmation");
        advanced_password_->setEchoMode(QLineEdit::Password);
        advanced_draft_ = new QLineEdit();
        advanced_draft_->setPlaceholderText("draft text for selected chat");
        advanced_avatar_id_ = new QLineEdit();
        advanced_avatar_id_->setPlaceholderText("avatar attachment_id (blank clears)");
        advanced_poll_question_ = new QLineEdit();
        advanced_poll_question_->setPlaceholderText("poll question");
        advanced_poll_options_ = new QLineEdit();
        advanced_poll_options_->setPlaceholderText("poll options comma-separated");
        advanced_poll_message_id_ = new QLineEdit();
        advanced_poll_message_id_->setPlaceholderText("poll message_id");
        advanced_poll_multi_ = new QCheckBox("Multiple choice");
        advanced_phone_request_ = new QPushButton("Request OTP");
        advanced_phone_verify_ = new QPushButton("Verify OTP");
        advanced_twofa_begin_ = new QPushButton("Begin 2FA");
        advanced_twofa_confirm_ = new QPushButton("Confirm 2FA");
        advanced_twofa_disable_ = new QPushButton("Disable 2FA");
        advanced_export_ = new QPushButton("Export Account");
        advanced_delete_ = new QPushButton("Delete Account");
        advanced_block_ = new QPushButton("Block");
        advanced_unblock_ = new QPushButton("Unblock");
        advanced_mute_ = new QPushButton("Mute");
        advanced_unmute_ = new QPushButton("Unmute");
        advanced_save_draft_ = new QPushButton("Save Draft");
        advanced_clear_draft_ = new QPushButton("Clear Draft");
        advanced_pin_chat_ = new QPushButton("Pin Chat");
        advanced_unpin_chat_ = new QPushButton("Unpin Chat");
        advanced_archive_chat_ = new QPushButton("Archive");
        advanced_unarchive_chat_ = new QPushButton("Unarchive");
        advanced_profile_avatar_ = new QPushButton("Set Profile Avatar");
        advanced_chat_avatar_ = new QPushButton("Set Chat Avatar");
        advanced_poll_create_ = new QPushButton("Create Poll");
        advanced_poll_vote_ = new QPushButton("Vote 0");
        advanced_poll_close_ = new QPushButton("Close Poll");
        advanced_log_ = new QPlainTextEdit();
        advanced_log_->setReadOnly(true);
        advanced_log_->setMaximumHeight(150);
        advanced_log_->setPlaceholderText("Advanced RPC results appear here.");
        set_advanced_action_enabled(false);

        chat_header_title_ = new QLabel("No chat selected");
        chat_header_title_->setObjectName("chatHeaderTitle");
        chat_header_subtitle_ = new QLabel("");
        chat_header_subtitle_->setObjectName("chatHeaderSubtitle");

        // ---- sidebar (left) ----
        auto* sidebar = new QWidget();
        sidebar_panel_ = sidebar;
        sidebar->setObjectName("sidebar");
        auto* sidebar_layout = new QVBoxLayout(sidebar);
        sidebar_layout->setContentsMargins(0, 0, 0, 0);
        sidebar_layout->setSpacing(0);
        auto* sidebar_search_wrap = new QWidget();
        sidebar_search_wrap->setObjectName("sidebarSearch");
        auto* sidebar_search_layout = new QHBoxLayout(sidebar_search_wrap);
        sidebar_search_layout->setContentsMargins(18, 12, 18, 12);
        sidebar_search_layout->setSpacing(10);
        auto* menu_btn = new QToolButton();
        hamburger_button_ = menu_btn;
        menu_btn->setObjectName("hamburgerButton");
        menu_btn->setText(QString::fromUtf8("\xe2\x98\xb0"));
        menu_btn->setToolTip("Menu");
        menu_btn->setCursor(Qt::PointingHandCursor);
        sidebar_search_layout->addWidget(menu_btn);
        sidebar_search_layout->addWidget(chat_filter_);
        sidebar_layout->addWidget(sidebar_search_wrap);
        auto* birthday_banner = new QWidget();
        birthday_banner->setObjectName("birthdayBanner");
        auto* birthday_layout = new QHBoxLayout(birthday_banner);
        birthday_layout->setContentsMargins(16, 10, 12, 10);
        auto* birthday_text = new QLabel(
            QStringLiteral("<b>Add your birthday!</b><br><span>Let your contacts know when you're celebrating.</span>"));
        birthday_text->setObjectName("birthdayText");
        birthday_text->setTextFormat(Qt::RichText);
        birthday_layout->addWidget(birthday_text, 1);
        auto* birthday_close = new QToolButton();
        birthday_close->setObjectName("settingsClose");
        birthday_close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        birthday_layout->addWidget(birthday_close);
        sidebar_layout->addWidget(birthday_banner);
        sidebar_layout->addWidget(conversations_, 1);
        reconnect_indicator_ = new QWidget();
        reconnect_indicator_->setObjectName("reconnectIndicator");
        auto* reconnect_layout = new QHBoxLayout(reconnect_indicator_);
        reconnect_layout->setContentsMargins(14, 10, 14, 12);
        reconnect_layout->setSpacing(10);
        auto* reconnect_icon = new QLabel();
        reconnect_icon->setObjectName("reconnectIcon");
        reconnect_icon->setPixmap(line_icon("timer", 28, QColor("#8a98a5")).pixmap(28, 28));
        reconnect_indicator_text_ = new QLabel("Loading...");
        reconnect_indicator_text_->setObjectName("reconnectIndicatorText");
        reconnect_layout->addWidget(reconnect_icon);
        reconnect_layout->addWidget(reconnect_indicator_text_, 1);
        reconnect_indicator_->setVisible(false);
        sidebar_layout->addWidget(reconnect_indicator_);
        toggle_details_ = new QPushButton("Settings ▸");
        toggle_details_->setObjectName("ghost");
        auto* sidebar_footer_wrap = new QWidget();
        sidebar_footer_wrap->setObjectName("sidebarFooter");
        auto* sidebar_footer_layout = new QHBoxLayout(sidebar_footer_wrap);
        sidebar_footer_layout->setContentsMargins(10, 8, 10, 8);
        sidebar_footer_layout->addWidget(toggle_details_, 1);
        sidebar_layout->addWidget(sidebar_footer_wrap);
        sidebar_footer_wrap->setVisible(false);

        // ---- center pane ----
        auto* center = new QWidget();
        center->setObjectName("centerPane");
        auto* center_layout = new QVBoxLayout(center);
        center_layout->setContentsMargins(0, 0, 0, 0);
        center_layout->setSpacing(0);
        // chat header
        auto* chat_header = new QWidget();
        chat_header->setObjectName("chatHeader");
        auto* chat_header_layout = new QHBoxLayout(chat_header);
        chat_header_layout->setContentsMargins(16, 10, 16, 10);
        auto* header_titles = new QVBoxLayout();
        header_titles->setSpacing(0);
        header_titles->addWidget(chat_header_title_);
        // M140: subtitle row carries the static "online · participants"
        // text + the animated typing indicator. The indicator hides itself
        // when inactive so the subtitle reflows seamlessly.
        auto* subtitle_row = new QHBoxLayout();
        subtitle_row->setSpacing(8);
        subtitle_row->setContentsMargins(0, 0, 0, 0);
        subtitle_row->addWidget(chat_header_subtitle_);
        typing_indicator_ = new telegram_like::client::app_desktop::TypingIndicator();
        subtitle_row->addWidget(typing_indicator_);
        subtitle_row->addStretch(1);
        header_titles->addLayout(subtitle_row);
        chat_header_layout->addLayout(header_titles, 1);
        // M145: chat info button — opens a non-modal dialog with the
        // conversation summary (title, participants, pinned messages,
        // attachment count). Sits next to load_older / server_search so
        // the header reads left-to-right as identity → load → search → info.
        auto* header_search = new QToolButton();
        header_search->setObjectName("chatInfoBtn");
        header_search->setText(QString::fromUtf8("\xe2\x8c\x95"));  // U+2315 search glyph
        header_search->setToolTip("Search");
        header_search->setCursor(Qt::PointingHandCursor);
        details_toggle_btn_ = new QToolButton();
        details_toggle_btn_->setObjectName("chatInfoBtn");
        details_toggle_btn_->setText(QString::fromUtf8("\xe2\x97\xa7"));  // split-panel outline
        details_toggle_btn_->setToolTip(QStringLiteral("Show or hide info panel"));
        details_toggle_btn_->setCursor(Qt::PointingHandCursor);
        chat_info_btn_ = new QToolButton();
        chat_info_btn_->setObjectName("chatInfoBtn");
        chat_info_btn_->setText(QString::fromUtf8("\xe2\x8b\xae"));  // vertical ellipsis
        chat_info_btn_->setToolTip(QStringLiteral("More"));
        chat_info_btn_->setCursor(Qt::PointingHandCursor);
        chat_header_layout->addWidget(header_search);
        chat_header_layout->addWidget(details_toggle_btn_);
        chat_header_layout->addWidget(chat_info_btn_);
        chat_header_layout->addWidget(load_older_);
        chat_header_layout->addWidget(server_search_);
        load_older_->setVisible(false);
        server_search_->setVisible(false);
        center_layout->addWidget(chat_header);
        // in-chat search row (under header)
        search_row_wrap_ = new QWidget();
        search_row_wrap_->setObjectName("inChatSearch");
        auto* search_row = new QHBoxLayout(search_row_wrap_);
        search_row->setContentsMargins(16, 6, 16, 6);
        search_row->addWidget(message_search_, 1);
        search_row->addWidget(prev_match_);
        search_row->addWidget(next_match_);
        search_row->addWidget(search_status_);
        search_row_wrap_->setVisible(false);
        center_layout->addWidget(search_row_wrap_);
        connection_notice_ = new QWidget();
        connection_notice_->setObjectName("connectionNotice");
        auto* connection_notice_layout = new QHBoxLayout(connection_notice_);
        connection_notice_layout->setContentsMargins(16, 8, 16, 8);
        connection_notice_layout->setSpacing(10);
        auto* connection_notice_icon = new QLabel();
        connection_notice_icon->setPixmap(line_icon("timer", 22, QColor("#e07a2f")).pixmap(22, 22));
        connection_notice_text_ = new QLabel("Connecting...");
        connection_notice_text_->setObjectName("connectionNoticeText");
        connection_notice_text_->setWordWrap(true);
        connection_notice_layout->addWidget(connection_notice_icon);
        connection_notice_layout->addWidget(connection_notice_text_, 1);
        connection_notice_->setVisible(false);
        center_layout->addWidget(connection_notice_);
        // M144: Pin message top strip — sits above the bubble list and
        // surfaces the most-recent pinned message snippet. Click jumps to
        // the message in-line. Hidden entirely when nothing is pinned so
        // the chat area gets the full vertical space.
        pin_bar_ = new QPushButton();
        pin_bar_->setObjectName("pinBar");
        pin_bar_->setVisible(false);
        pin_bar_->setCursor(Qt::PointingHandCursor);
        pin_bar_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        pin_bar_->setMinimumHeight(36);
        pin_bar_->setStyleSheet(
            "QPushButton#pinBar { text-align:left; padding:6px 12px;"
            " border:none; background:transparent; }");
        center_layout->addWidget(pin_bar_);
        // timeline
        center_layout->addWidget(messages_, 1);
        // server search result panel (collapsible feel)
        message_search_results_->setVisible(false);
        center_layout->addWidget(message_search_results_);
        // transfer status
        auto* transfer_wrap = new QWidget();
        auto* transfer_row = new QHBoxLayout(transfer_wrap);
        transfer_row->setContentsMargins(16, 4, 16, 4);
        transfer_row->addWidget(transfer_status_);
        transfer_row->addWidget(transfer_progress_, 1);
        transfer_wrap->setVisible(false);
        center_layout->addWidget(transfer_wrap);
        // composer
        auto* composer_wrap = new QWidget();
        composer_wrap->setObjectName("composer");
        auto* send_row = new QHBoxLayout(composer_wrap);
        send_row->setContentsMargins(16, 10, 16, 12);
        send_row->setSpacing(8);
        send_row->addWidget(attach_);
        send_row->addWidget(emoji_panel_);
        send_row->addWidget(composer_, 1);
        send_row->addWidget(send_);
        center_layout->addWidget(composer_wrap);
        // message-action row (advanced; stays visible under composer because smoke + power users use it)
        auto* message_action_wrap = new QWidget();
        message_action_wrap->setObjectName("messageActions");
        auto* message_action_row = new QHBoxLayout(message_action_wrap);
        message_action_row->setContentsMargins(16, 6, 16, 8);
        message_action_row->addWidget(new QLabel("Action"));
        message_action_row->addWidget(message_action_id_, 1);
        message_action_row->addWidget(reaction_emoji_);
        message_action_row->addWidget(use_match_);
        message_action_row->addWidget(use_latest_);
        message_action_row->addWidget(reply_);
        message_action_row->addWidget(forward_);
        message_action_row->addWidget(react_);
        message_action_row->addWidget(pin_);
        message_action_row->addWidget(unpin_);
        message_action_row->addWidget(edit_);
        message_action_row->addWidget(delete_);
        message_action_wrap->setVisible(false);
        center_layout->addWidget(message_action_wrap);

        // ---- details panel (right, collapsible) ----
        details_panel_ = new QScrollArea();
        details_panel_->setObjectName("detailsPanel");
        details_panel_->setWidgetResizable(true);
        details_panel_->setFrameShape(QFrame::NoFrame);
        details_panel_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        details_stack_ = new QStackedWidget();
        details_stack_->setObjectName("detailsStack");
        details_stack_->setMinimumWidth(0);
        details_stack_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Expanding);

        auto* info_page = new QWidget();
        info_page->setObjectName("profileDetailsPage");
        info_page->setMinimumWidth(0);
        info_page->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Expanding);
        auto* info_layout = new QVBoxLayout(info_page);
        info_layout->setContentsMargins(0, 0, 0, 0);
        info_layout->setSpacing(0);

        auto* detail_header = new QWidget();
        detail_header->setObjectName("profileDetailsHeader");
        auto* detail_header_layout = new QVBoxLayout(detail_header);
        detail_header_layout->setContentsMargins(24, 22, 24, 24);
        detail_header_layout->setSpacing(10);
        auto* detail_close_row = new QHBoxLayout();
        detail_close_row->addStretch(1);
        auto* detail_close = new QToolButton();
        detail_close->setObjectName("settingsClose");
        detail_close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        detail_close->setToolTip("Hide info");
        detail_close_row->addWidget(detail_close);
        detail_header_layout->addLayout(detail_close_row);

        detail_avatar_label_ = new QLabel();
        detail_avatar_label_->setObjectName("detailAvatar");
        detail_avatar_label_->setFixedSize(112, 112);
        detail_avatar_label_->setMinimumSize(112, 112);
        detail_avatar_label_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        detail_avatar_label_->setScaledContents(false);
        detail_avatar_label_->setAlignment(Qt::AlignCenter);
        detail_header_layout->addWidget(detail_avatar_label_, 0, Qt::AlignHCenter);
        detail_title_label_ = new QLabel("No chat selected");
        detail_title_label_->setObjectName("detailTitle");
        detail_title_label_->setAlignment(Qt::AlignCenter);
        detail_header_layout->addWidget(detail_title_label_);
        detail_subtitle_label_ = new QLabel("Pick a chat");
        detail_subtitle_label_->setObjectName("detailSubtitle");
        detail_subtitle_label_->setAlignment(Qt::AlignCenter);
        detail_header_layout->addWidget(detail_subtitle_label_);
        auto* detail_actions = new QHBoxLayout();
        detail_actions->setSpacing(6);
        for (const char* text : {"Mute", "Manage", "Leave"}) {
            auto* action = new QToolButton();
            action->setObjectName("detailAction");
            action->setText(QString::fromUtf8(text));
            action->setToolButtonStyle(Qt::ToolButtonTextUnderIcon);
            action->setIconSize(QSize(28, 28));
            action->setCursor(Qt::PointingHandCursor);
            action->setFixedSize(96, 68);
            action->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
            detail_actions->addWidget(action);
            detail_action_buttons_.push_back(action);
        }
        detail_header_layout->addLayout(detail_actions);
        info_layout->addWidget(detail_header);

        auto* detail_identity = new QWidget();
        detail_identity_section_ = detail_identity;
        detail_identity->setObjectName("detailSection");
        auto* identity_layout = new QVBoxLayout(detail_identity);
        identity_layout->setContentsMargins(22, 18, 22, 18);
        identity_layout->setSpacing(8);
        detail_link_label_ = new QLabel();
        detail_link_label_->setObjectName("detailLink");
        detail_link_label_->setTextInteractionFlags(Qt::TextSelectableByMouse);
        identity_layout->addWidget(detail_link_label_);
        detail_description_label_ = new QLabel();
        detail_description_label_->setObjectName("detailDescription");
        detail_description_label_->setWordWrap(true);
        identity_layout->addWidget(detail_description_label_);
        info_layout->addWidget(detail_identity);

        auto* detail_media = new QWidget();
        detail_media_section_ = detail_media;
        detail_media->setObjectName("detailSection");
        auto* detail_media_layout = new QVBoxLayout(detail_media);
        detail_media_layout->setContentsMargins(22, 18, 22, 18);
        detail_media_layout->setSpacing(0);
        detail_media_tabs_ = new QTabWidget();
        detail_media_tabs_->setObjectName("detailMediaTabs");
        detail_media_list_ = new QListWidget();
        detail_media_list_->setObjectName("detailMediaRows");
        detail_media_list_->setFrameShape(QFrame::NoFrame);
        detail_media_list_->setFocusPolicy(Qt::NoFocus);
        detail_media_list_->setSelectionMode(QAbstractItemView::NoSelection);
        detail_media_list_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        detail_media_list_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        detail_media_tabs_->addTab(detail_media_list_, "Media");
        auto* detail_files_list = new QListWidget();
        detail_files_list->setObjectName("detailFilesRows");
        detail_files_list->addItem(new QListWidgetItem(line_icon("files", 24, QColor("#7d8790")), "Files"));
        detail_media_tabs_->addTab(detail_files_list, "Files");
        auto* detail_links_list = new QListWidget();
        detail_links_list->setObjectName("detailLinksRows");
        detail_links_list->addItem(new QListWidgetItem(line_icon("link", 24, QColor("#7d8790")), "Links"));
        detail_media_tabs_->addTab(detail_links_list, "Links");
        auto* detail_voice_list = new QListWidget();
        detail_voice_list->setObjectName("detailVoiceRows");
        detail_voice_list->addItem(new QListWidgetItem(line_icon("voice", 24, QColor("#7d8790")), "Voice"));
        detail_media_tabs_->addTab(detail_voice_list, "Voice");
        detail_media_layout->addWidget(detail_media_tabs_);
        info_layout->addWidget(detail_media);

        auto* members_section = new QWidget();
        detail_members_section_ = members_section;
        members_section->setObjectName("detailSection");
        auto* members_layout = new QVBoxLayout(members_section);
        members_layout->setContentsMargins(22, 16, 22, 18);
        members_layout->setSpacing(10);
        detail_members_title_ = new QLabel("MEMBERS");
        detail_members_title_->setObjectName("fieldLabel");
        members_layout->addWidget(detail_members_title_);
        auto* member_search = new QLineEdit();
        member_search->setObjectName("detailMemberSearch");
        member_search->setPlaceholderText("Search members");
        members_layout->addWidget(member_search);
        detail_members_list_ = new QListWidget();
        detail_members_list_->setObjectName("detailMembers");
        detail_members_list_->setFrameShape(QFrame::NoFrame);
        detail_members_list_->setMaximumHeight(190);
        detail_members_list_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        members_layout->addWidget(detail_members_list_);
        info_layout->addWidget(members_section);

        auto* detail_danger = new QWidget();
        detail_danger_section_ = detail_danger;
        detail_danger->setObjectName("detailSection");
        auto* danger_layout = new QVBoxLayout(detail_danger);
        danger_layout->setContentsMargins(22, 16, 22, 18);
        auto* leave_btn = new QPushButton("Leave channel");
        leave_btn->setObjectName("detailFlatAction");
        auto* report_btn = new QPushButton("Report");
        report_btn->setObjectName("dangerAction");
        danger_layout->addWidget(leave_btn);
        danger_layout->addWidget(report_btn);
        info_layout->addWidget(detail_danger);
        info_layout->addStretch(1);
        details_stack_->addWidget(info_page);

        auto* details_inner = new QWidget();
        auto* details_root_layout = new QVBoxLayout(details_inner);
        details_root_layout->setContentsMargins(0, 0, 0, 0);
        details_root_layout->setSpacing(0);

        // Settings header bar
        auto* settings_header = new QWidget();
        settings_header->setObjectName("settingsHeader");
        auto* settings_header_layout = new QHBoxLayout(settings_header);
        settings_header_layout->setContentsMargins(16, 12, 12, 12);
        auto* settings_title = new QLabel("Settings");
        settings_title->setObjectName("settingsTitle");
        settings_header_layout->addWidget(settings_title, 1);
        auto* settings_close = new QToolButton();
        settings_close->setObjectName("settingsClose");
        settings_close->setText("✕");
        settings_close->setToolTip("Close settings");
        settings_header_layout->addWidget(settings_close);
        details_root_layout->addWidget(settings_header);

        // body: nav (left) + stacked pages (right)
        auto* body_wrap = new QWidget();
        auto* body_layout = new QHBoxLayout(body_wrap);
        body_layout->setContentsMargins(0, 0, 0, 0);
        body_layout->setSpacing(0);

        settings_nav_ = new QListWidget();
        settings_nav_->setObjectName("settingsNav");
        settings_nav_->setMinimumWidth(150);
        settings_nav_->setMaximumWidth(170);
        settings_nav_->setFrameShape(QFrame::NoFrame);
        settings_nav_->setSpacing(2);
        // M139: Telegram-style nav — each item gets a leading unicode glyph
        // so the column reads as an icon list rather than a plain text
        // list. Glyphs come from common Unicode planes; no external icon
        // assets needed. New "Appearance" entry hosts the light/dark
        // toggle below.
        struct NavEntry { const char* icon; const char* label; };
        constexpr NavEntry nav_entries[] = {
            {"profile", "Profile"},
            {"lock", "Account"},
            {"lock", "Privacy"},
            {"scale", "Appearance"},
            {"link", "Connection"},
            {"device", "Devices"},
            {"contact", "Contacts"},
            {"search", "Find Users"},
            {"group", "Groups"},
            {"chat", "Chat Tools"},
            {"attach", "Attachments"},
            {"remote", "Remote"},
            {"call", "Call"},
            {"settings", "Advanced"},
        };
        for (const auto& entry : nav_entries) {
            auto* item = new QListWidgetItem(line_icon(QString::fromUtf8(entry.icon), 22),
                                             QString::fromUtf8(entry.label));
            settings_nav_->addItem(item);
        }
        body_layout->addWidget(settings_nav_);

        settings_pages_ = new QStackedWidget();
        settings_pages_->setObjectName("settingsPages");

        auto make_page = [](const char* title, const char* subtitle, QLayout* body) -> QWidget* {
            auto* page = new QWidget();
            auto* layout = new QVBoxLayout(page);
            layout->setContentsMargins(20, 18, 20, 18);
            layout->setSpacing(12);
            auto* heading = new QLabel(title);
            heading->setObjectName("pageHeading");
            layout->addWidget(heading);
            if (subtitle && *subtitle) {
                auto* sub = new QLabel(subtitle);
                sub->setObjectName("pageSubtitle");
                sub->setWordWrap(true);
                layout->addWidget(sub);
            }
            auto* container = new QWidget();
            container->setLayout(body);
            layout->addWidget(container);
            layout->addStretch(1);
            return page;
        };

        // === Profile page (with avatar) ===
        avatar_label_ = new QLabel();
        avatar_label_->setObjectName("profileAvatar");
        avatar_label_->setFixedSize(96, 96);
        avatar_label_->setAlignment(Qt::AlignCenter);
        update_avatar_pixmap(args.user, args.display_name.empty() ? args.user : args.display_name);

        profile_identity_label_ = new QLabel("Not connected");
        profile_identity_label_->setObjectName("profileIdentity");
        profile_identity_label_->setWordWrap(true);

        auto* profile_body = new QVBoxLayout();
        profile_body->setSpacing(10);
        auto* profile_top = new QHBoxLayout();
        profile_top->setSpacing(14);
        profile_top->addWidget(avatar_label_);
        auto* profile_top_text = new QVBoxLayout();
        profile_top_text->addWidget(profile_identity_label_);
        profile_top_text->addStretch(1);
        profile_top->addLayout(profile_top_text, 1);
        profile_body->addLayout(profile_top);
        profile_body->addWidget(new QLabel("Display name"));
        auto* prof_form = new QHBoxLayout();
        prof_form->addWidget(profile_display_name_, 1);
        prof_form->addWidget(refresh_profile_);
        prof_form->addWidget(save_profile_);
        profile_body->addLayout(prof_form);
        profile_body->addWidget(new QLabel("Server profile snapshot"));
        profile_body->addWidget(profile_);
        settings_pages_->addWidget(
            make_page("Profile", "Edit how others see you on this server.", profile_body));

        // === Account page ===
        auto* account_body = new QVBoxLayout();
        account_body->setSpacing(10);
        auto* acc_user_lab = new QLabel("Username");
        acc_user_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_user_lab);
        account_body->addWidget(user_);
        auto* acc_pwd_lab = new QLabel("Password");
        acc_pwd_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_pwd_lab);
        account_body->addWidget(password_);
        auto* acc_disp_lab = new QLabel("Display name (used at register)");
        acc_disp_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_disp_lab);
        account_body->addWidget(display_name_);
        auto* acc_dev_lab = new QLabel("Device id");
        acc_dev_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_dev_lab);
        account_body->addWidget(device_);
        auto* acc_btns = new QHBoxLayout();
        acc_btns->addWidget(connect_);
        acc_btns->addWidget(register_);
        acc_btns->addStretch(1);
        account_body->addLayout(acc_btns);
        auto* account_product_lab = new QLabel("Security and data");
        account_product_lab->setObjectName("fieldLabel");
        account_body->addWidget(account_product_lab);
        auto* account_product_row = new QHBoxLayout();
        auto* account_export_shortcut = new QPushButton("Export Data");
        account_export_shortcut->setObjectName("accountExportShortcut");
        auto* account_twofa_shortcut = new QPushButton("Set Up 2FA");
        account_twofa_shortcut->setObjectName("accountTwoFaShortcut");
        auto* account_delete_shortcut = new QPushButton("Delete Account");
        account_delete_shortcut->setObjectName("dangerActionButton");
        account_product_row->addWidget(account_export_shortcut);
        account_product_row->addWidget(account_twofa_shortcut);
        account_product_row->addWidget(account_delete_shortcut);
        account_product_row->addStretch(1);
        account_body->addLayout(account_product_row);
        QObject::connect(account_export_shortcut, &QPushButton::clicked,
                         [this] { advanced_export_action(); });
        QObject::connect(account_twofa_shortcut, &QPushButton::clicked,
                         [this] { advanced_twofa_begin_action(); });
        QObject::connect(account_delete_shortcut, &QPushButton::clicked, [this] {
            if (advanced_password_ != nullptr && password_ != nullptr) {
                advanced_password_->setText(password_->text());
            }
            advanced_delete_action();
        });
        settings_pages_->addWidget(
            make_page("Account", "Sign in or create a new account on this server.", account_body));

        // === Privacy page ===
        auto* privacy_body = new QVBoxLayout();
        privacy_body->setSpacing(10);
        auto* privacy_target = new QLineEdit();
        privacy_target->setObjectName("privacyTargetUser");
        privacy_target->setPlaceholderText("user_id to block or unblock");
        privacy_body->addWidget(privacy_target);
        auto* privacy_user_row = new QHBoxLayout();
        auto* privacy_block = new QPushButton("Block User");
        privacy_block->setObjectName("privacyBlockButton");
        auto* privacy_unblock = new QPushButton("Unblock User");
        privacy_unblock->setObjectName("privacyUnblockButton");
        privacy_user_row->addWidget(privacy_block);
        privacy_user_row->addWidget(privacy_unblock);
        privacy_user_row->addStretch(1);
        privacy_body->addLayout(privacy_user_row);
        auto* privacy_chat_row = new QHBoxLayout();
        auto* privacy_mute = new QPushButton("Mute Selected Chat");
        privacy_mute->setObjectName("privacyMuteButton");
        auto* privacy_unmute = new QPushButton("Unmute Selected Chat");
        privacy_unmute->setObjectName("privacyUnmuteButton");
        privacy_chat_row->addWidget(privacy_mute);
        privacy_chat_row->addWidget(privacy_unmute);
        privacy_chat_row->addStretch(1);
        privacy_body->addLayout(privacy_chat_row);
        QObject::connect(privacy_block, &QPushButton::clicked, [this, privacy_target] {
            if (advanced_target_user_ != nullptr) advanced_target_user_->setText(privacy_target->text().trimmed());
            advanced_block_action(true);
        });
        QObject::connect(privacy_unblock, &QPushButton::clicked, [this, privacy_target] {
            if (advanced_target_user_ != nullptr) advanced_target_user_->setText(privacy_target->text().trimmed());
            advanced_block_action(false);
        });
        QObject::connect(privacy_mute, &QPushButton::clicked,
                         [this] { advanced_chat_ack_action(AdvancedChatOp::Mute); });
        QObject::connect(privacy_unmute, &QPushButton::clicked,
                         [this] { advanced_chat_ack_action(AdvancedChatOp::Unmute); });
        settings_pages_->addWidget(
            make_page("Privacy", "Block users and mute selected chats.", privacy_body));

        // === Appearance page (M139) — light/dark theme + cosmetic notes ===
        // Telegram desktop's appearance section gives the user a visible
        // toggle for the theme; we match that via two QRadioButton choices
        // backed by a re-application of telegram_stylesheet() and a fresh
        // bubble palette push. The choice persists in QSettings under
        // "appearance/dark_theme" so subsequent launches start in the
        // last-selected mode without needing the env var.
        auto* appearance_body = new QVBoxLayout();
        appearance_body->setSpacing(10);
        auto* appearance_label = new QLabel("Theme");
        appearance_label->setObjectName("fieldLabel");
        appearance_body->addWidget(appearance_label);
        appearance_light_ = new QRadioButton("Light");
        appearance_dark_  = new QRadioButton("Dark");
        appearance_light_->setChecked(!telegram_like::client::app_desktop::design::is_dark_theme());
        appearance_dark_->setChecked(telegram_like::client::app_desktop::design::is_dark_theme());
        appearance_body->addWidget(appearance_light_);
        appearance_body->addWidget(appearance_dark_);
        auto* appearance_hint = new QLabel(
            "Light is the Telegram-Web-Z baseline; Dark mirrors the desktop \"Night\" palette. "
            "Changes apply immediately and are saved to your local settings file.");
        appearance_hint->setObjectName("pageSubtitle");
        appearance_hint->setWordWrap(true);
        appearance_body->addWidget(appearance_hint);
        settings_pages_->addWidget(
            make_page("Appearance", "Pick light or dark for the chat surface.", appearance_body));

        // === Connection page ===
        auto* connection_body = new QVBoxLayout();
        connection_body->setSpacing(10);
        auto* conn_host_lab = new QLabel("Host");
        conn_host_lab->setObjectName("fieldLabel");
        connection_body->addWidget(conn_host_lab);
        auto* conn_host_row = new QHBoxLayout();
        conn_host_row->addWidget(host_, 1);
        conn_host_row->addWidget(new QLabel("Port"));
        conn_host_row->addWidget(port_);
        connection_body->addLayout(conn_host_row);
        auto* conn_tls_lab = new QLabel("Transport security");
        conn_tls_lab->setObjectName("fieldLabel");
        connection_body->addWidget(conn_tls_lab);
        auto* conn_tls_row = new QHBoxLayout();
        conn_tls_row->addWidget(tls_);
        conn_tls_row->addWidget(tls_insecure_);
        conn_tls_row->addStretch(1);
        connection_body->addLayout(conn_tls_row);
        auto* conn_conv_lab = new QLabel("Default conversation");
        conn_conv_lab->setObjectName("fieldLabel");
        connection_body->addWidget(conn_conv_lab);
        connection_body->addWidget(conversation_);
        settings_pages_->addWidget(
            make_page("Connection", "Where to connect and how to secure the link.", connection_body));

        // === Devices page ===
        auto* devices_body = new QVBoxLayout();
        devices_body->setSpacing(10);
        auto* dev_top = new QHBoxLayout();
        dev_top->addWidget(refresh_devices_);
        dev_top->addStretch(1);
        devices_body->addLayout(dev_top);
        devices_body->addWidget(devices_);
        auto* dev_action_lab = new QLabel("Manage device");
        dev_action_lab->setObjectName("fieldLabel");
        devices_body->addWidget(dev_action_lab);
        devices_body->addWidget(device_action_id_);
        auto* dev_btns = new QHBoxLayout();
        dev_btns->addWidget(revoke_device_);
        dev_btns->addWidget(trust_device_);
        dev_btns->addWidget(untrust_device_);
        dev_btns->addStretch(1);
        devices_body->addLayout(dev_btns);
        settings_pages_->addWidget(
            make_page("Devices", "Sessions signed in to this account. Revoke or trust each device.", devices_body));

        // === Contacts page ===
        auto* contacts_body = new QVBoxLayout();
        contacts_body->setSpacing(10);
        auto* con_top = new QHBoxLayout();
        con_top->addWidget(refresh_contacts_);
        con_top->addStretch(1);
        contacts_body->addLayout(con_top);
        auto* con_id_lab = new QLabel("Contact user_id");
        con_id_lab->setObjectName("fieldLabel");
        contacts_body->addWidget(con_id_lab);
        contacts_body->addWidget(contact_user_id_);
        auto* con_btns = new QHBoxLayout();
        con_btns->addWidget(add_contact_);
        con_btns->addWidget(remove_contact_);
        con_btns->addStretch(1);
        contacts_body->addLayout(con_btns);
        contacts_body->addWidget(contacts_);
        settings_pages_->addWidget(
            make_page("Contacts", "Your saved contacts and their online state.", contacts_body));

        // === Find Users page ===
        auto* find_body = new QVBoxLayout();
        find_body->setSpacing(10);
        auto* find_lab = new QLabel("Search query");
        find_lab->setObjectName("fieldLabel");
        find_body->addWidget(find_lab);
        auto* find_row = new QHBoxLayout();
        find_row->addWidget(user_search_query_, 1);
        find_row->addWidget(search_users_);
        find_body->addLayout(find_row);
        find_body->addWidget(user_search_results_);
        settings_pages_->addWidget(
            make_page("Find Users", "Search by username, display name or user_id.", find_body));

        // === Groups page ===
        auto* groups_body = new QVBoxLayout();
        groups_body->setSpacing(10);
        auto* grp_title_lab = new QLabel("New group");
        grp_title_lab->setObjectName("fieldLabel");
        groups_body->addWidget(grp_title_lab);
        groups_body->addWidget(group_title_);
        auto* grp_part_lab = new QLabel("Initial participants (comma-separated user_ids)");
        grp_part_lab->setObjectName("fieldLabel");
        groups_body->addWidget(grp_part_lab);
        groups_body->addWidget(group_participants_);
        auto* grp_create_row = new QHBoxLayout();
        grp_create_row->addWidget(create_group_);
        grp_create_row->addStretch(1);
        groups_body->addLayout(grp_create_row);
        auto* grp_member_lab = new QLabel("Add or remove a member from the selected chat");
        grp_member_lab->setObjectName("fieldLabel");
        groups_body->addWidget(grp_member_lab);
        groups_body->addWidget(member_user_id_);
        auto* grp_member_btns = new QHBoxLayout();
        grp_member_btns->addWidget(add_member_);
        grp_member_btns->addWidget(remove_member_);
        grp_member_btns->addStretch(1);
        groups_body->addLayout(grp_member_btns);
        settings_pages_->addWidget(
            make_page("Groups", "Create new groups and manage selected chat membership.", groups_body));

        // === Chat Tools page ===
        auto* chat_tools_body = new QVBoxLayout();
        chat_tools_body->setSpacing(10);
        auto* chat_tools_lab = new QLabel("Selected chat");
        chat_tools_lab->setObjectName("fieldLabel");
        chat_tools_body->addWidget(chat_tools_lab);
        auto* chat_tools_draft = new QLineEdit();
        chat_tools_draft->setObjectName("chatToolsDraftInput");
        chat_tools_draft->setPlaceholderText("draft text");
        chat_tools_body->addWidget(chat_tools_draft);
        auto* chat_tools_row = new QHBoxLayout();
        auto* chat_save_draft = new QPushButton("Save Draft");
        chat_save_draft->setObjectName("chatToolsSaveDraft");
        auto* chat_pin = new QPushButton("Pin Chat");
        chat_pin->setObjectName("chatToolsPin");
        auto* chat_archive = new QPushButton("Archive Chat");
        chat_archive->setObjectName("chatToolsArchive");
        chat_tools_row->addWidget(chat_save_draft);
        chat_tools_row->addWidget(chat_pin);
        chat_tools_row->addWidget(chat_archive);
        chat_tools_row->addStretch(1);
        chat_tools_body->addLayout(chat_tools_row);
        auto* chat_poll_lab = new QLabel("Poll composer");
        chat_poll_lab->setObjectName("fieldLabel");
        chat_tools_body->addWidget(chat_poll_lab);
        auto* chat_poll_question = new QLineEdit();
        chat_poll_question->setObjectName("chatToolsPollQuestion");
        chat_poll_question->setPlaceholderText("question");
        auto* chat_poll_options = new QLineEdit();
        chat_poll_options->setObjectName("chatToolsPollOptions");
        chat_poll_options->setPlaceholderText("options comma-separated");
        chat_tools_body->addWidget(chat_poll_question);
        chat_tools_body->addWidget(chat_poll_options);
        auto* chat_poll_create = new QPushButton("Create Poll");
        chat_poll_create->setObjectName("chatToolsCreatePoll");
        chat_tools_body->addWidget(chat_poll_create, 0, Qt::AlignLeft);
        QObject::connect(chat_save_draft, &QPushButton::clicked, [this, chat_tools_draft] {
            if (advanced_draft_ != nullptr) advanced_draft_->setText(chat_tools_draft->text());
            advanced_chat_ack_action(AdvancedChatOp::SaveDraft);
        });
        QObject::connect(chat_pin, &QPushButton::clicked,
                         [this] { advanced_chat_ack_action(AdvancedChatOp::Pin); });
        QObject::connect(chat_archive, &QPushButton::clicked,
                         [this] { advanced_chat_ack_action(AdvancedChatOp::Archive); });
        QObject::connect(chat_poll_create, &QPushButton::clicked,
                         [this, chat_poll_question, chat_poll_options] {
                             if (advanced_poll_question_ != nullptr) advanced_poll_question_->setText(chat_poll_question->text());
                             if (advanced_poll_options_ != nullptr) advanced_poll_options_->setText(chat_poll_options->text());
                             advanced_poll_create_action();
                         });
        settings_pages_->addWidget(
            make_page("Chat Tools", "Drafts, pin/archive and polls for the selected chat.", chat_tools_body));

        // === Attachments page ===
        auto* attach_body = new QVBoxLayout();
        attach_body->setSpacing(10);
        auto* att_lab = new QLabel("Attachment id");
        att_lab->setObjectName("fieldLabel");
        attach_body->addWidget(att_lab);
        attach_body->addWidget(attachment_id_);
        auto* att_btns = new QHBoxLayout();
        att_btns->addWidget(save_attachment_);
        att_btns->addStretch(1);
        attach_body->addLayout(att_btns);
        settings_pages_->addWidget(
            make_page("Attachments", "Save received attachments by id to disk.", attach_body));

        // === Remote-control page (M108) ===
        auto* remote_body = new QVBoxLayout();
        remote_body->setSpacing(10);
        auto* remote_invite_lab = new QLabel("Invite a target device into a remote session");
        remote_invite_lab->setObjectName("fieldLabel");
        remote_body->addWidget(remote_invite_lab);
        remote_body->addWidget(remote_target_device_);
        auto* remote_invite_row = new QHBoxLayout();
        remote_invite_row->addWidget(remote_invite_);
        remote_invite_row->addStretch(1);
        remote_body->addLayout(remote_invite_row);
        auto* remote_session_lab = new QLabel(
            "Existing remote_session_id (received via push or copied from invite)");
        remote_session_lab->setObjectName("fieldLabel");
        remote_body->addWidget(remote_session_lab);
        remote_body->addWidget(remote_session_id_input_);
        auto* remote_btns = new QHBoxLayout();
        remote_btns->addWidget(remote_approve_);
        remote_btns->addWidget(remote_reject_);
        remote_btns->addWidget(remote_cancel_);
        remote_btns->addWidget(remote_terminate_);
        remote_btns->addWidget(remote_rendezvous_);
        remote_btns->addStretch(1);
        remote_body->addLayout(remote_btns);
        auto* remote_log_lab = new QLabel("RPC results");
        remote_log_lab->setObjectName("fieldLabel");
        remote_body->addWidget(remote_log_lab);
        remote_body->addWidget(remote_log_);
        settings_pages_->addWidget(
            make_page(
                "Remote",
                "Invite, approve, terminate and discover relay info for remote-control sessions.",
                remote_body));

        // === Call page (M128) ===
        auto* call_body = new QVBoxLayout();
        call_body->setSpacing(10);
        auto* call_callee_lab = new QLabel("Place a call");
        call_callee_lab->setObjectName("fieldLabel");
        call_body->addWidget(call_callee_lab);
        call_body->addWidget(call_callee_user_);
        call_body->addWidget(call_callee_device_);
        auto* call_kind_row = new QHBoxLayout();
        call_kind_row->addWidget(call_kind_);
        call_kind_row->addWidget(call_invite_);
        call_kind_row->addStretch(1);
        call_body->addLayout(call_kind_row);
        auto* call_id_lab = new QLabel("Active call_id");
        call_id_lab->setObjectName("fieldLabel");
        call_body->addWidget(call_id_lab);
        call_body->addWidget(call_id_input_);
        auto* call_btns = new QHBoxLayout();
        call_btns->addWidget(call_accept_);
        call_btns->addWidget(call_decline_);
        call_btns->addWidget(call_end_);
        call_btns->addStretch(1);
        call_body->addLayout(call_btns);
        auto* call_log_lab = new QLabel("FSM log");
        call_log_lab->setObjectName("fieldLabel");
        call_body->addWidget(call_log_lab);
        call_body->addWidget(call_log_);
        settings_pages_->addWidget(
            make_page(
                "Call",
                "Voice/video call invite/accept/decline/end. Per-call AES-256-GCM key minted on accept.",
                call_body));

        // === Advanced page (RC-005) ===
        auto* advanced_body = new QVBoxLayout();
        advanced_body->setSpacing(10);
        auto* adv_target_lab = new QLabel("Target user or phone");
        adv_target_lab->setObjectName("fieldLabel");
        advanced_body->addWidget(adv_target_lab);
        advanced_body->addWidget(advanced_target_user_);
        auto* adv_code_row = new QHBoxLayout();
        adv_code_row->addWidget(advanced_code_, 1);
        adv_code_row->addWidget(advanced_password_, 1);
        advanced_body->addLayout(adv_code_row);
        auto* adv_auth_row = new QHBoxLayout();
        adv_auth_row->addWidget(advanced_phone_request_);
        adv_auth_row->addWidget(advanced_phone_verify_);
        adv_auth_row->addWidget(advanced_twofa_begin_);
        adv_auth_row->addWidget(advanced_twofa_confirm_);
        adv_auth_row->addWidget(advanced_twofa_disable_);
        adv_auth_row->addStretch(1);
        advanced_body->addLayout(adv_auth_row);
        auto* adv_account_row = new QHBoxLayout();
        adv_account_row->addWidget(advanced_export_);
        adv_account_row->addWidget(advanced_delete_);
        adv_account_row->addWidget(advanced_block_);
        adv_account_row->addWidget(advanced_unblock_);
        adv_account_row->addStretch(1);
        advanced_body->addLayout(adv_account_row);
        auto* adv_chat_lab = new QLabel("Selected chat actions");
        adv_chat_lab->setObjectName("fieldLabel");
        advanced_body->addWidget(adv_chat_lab);
        advanced_body->addWidget(advanced_draft_);
        auto* adv_chat_row = new QHBoxLayout();
        adv_chat_row->addWidget(advanced_save_draft_);
        adv_chat_row->addWidget(advanced_clear_draft_);
        adv_chat_row->addWidget(advanced_mute_);
        adv_chat_row->addWidget(advanced_unmute_);
        adv_chat_row->addWidget(advanced_pin_chat_);
        adv_chat_row->addWidget(advanced_unpin_chat_);
        adv_chat_row->addWidget(advanced_archive_chat_);
        adv_chat_row->addWidget(advanced_unarchive_chat_);
        adv_chat_row->addStretch(1);
        advanced_body->addLayout(adv_chat_row);
        auto* adv_media_lab = new QLabel("Avatar and poll");
        adv_media_lab->setObjectName("fieldLabel");
        advanced_body->addWidget(adv_media_lab);
        advanced_body->addWidget(advanced_avatar_id_);
        auto* adv_avatar_row = new QHBoxLayout();
        adv_avatar_row->addWidget(advanced_profile_avatar_);
        adv_avatar_row->addWidget(advanced_chat_avatar_);
        adv_avatar_row->addStretch(1);
        advanced_body->addLayout(adv_avatar_row);
        advanced_body->addWidget(advanced_poll_question_);
        advanced_body->addWidget(advanced_poll_options_);
        auto* adv_poll_row = new QHBoxLayout();
        adv_poll_row->addWidget(advanced_poll_message_id_, 1);
        adv_poll_row->addWidget(advanced_poll_multi_);
        adv_poll_row->addWidget(advanced_poll_create_);
        adv_poll_row->addWidget(advanced_poll_vote_);
        adv_poll_row->addWidget(advanced_poll_close_);
        advanced_body->addLayout(adv_poll_row);
        auto* adv_log_lab = new QLabel("RPC results");
        adv_log_lab->setObjectName("fieldLabel");
        advanced_body->addWidget(adv_log_lab);
        advanced_body->addWidget(advanced_log_);
        settings_pages_->addWidget(
            make_page(
                "Advanced",
                "Server-backed account, privacy, draft, archive, avatar and poll RPCs.",
                advanced_body));

        body_layout->addWidget(settings_pages_, 1);
        details_root_layout->addWidget(body_wrap, 1);

        QObject::connect(settings_nav_, &QListWidget::currentRowChanged,
                         [this](int row) {
                             if (row >= 0) settings_pages_->setCurrentIndex(row);
                         });
        QObject::connect(settings_close, &QToolButton::clicked,
                         [this] { if (details_stack_ != nullptr) details_stack_->setCurrentIndex(0); });
        QObject::connect(detail_close, &QToolButton::clicked,
                         [this] { if (details_panel_ != nullptr) details_panel_->setVisible(false); });
        settings_nav_->setCurrentRow(0);

        details_stack_->addWidget(details_inner);
        details_stack_->setCurrentIndex(0);
        details_panel_->setWidget(details_stack_);
        details_panel_->setMinimumWidth(420);
        details_panel_->setVisible(false);

        // ---- compose splitter ----
        auto* splitter = new QSplitter(Qt::Horizontal);
        splitter->setObjectName("mainSplitter");
        splitter->addWidget(sidebar);
        splitter->addWidget(center);
        splitter->addWidget(details_panel_);
        splitter->setStretchFactor(0, 0);
        splitter->setStretchFactor(1, 1);
        splitter->setStretchFactor(2, 0);
        splitter->setSizes({390, 560, 415});
        splitter->setChildrenCollapsible(false);

        setCentralWidget(splitter);
        resize(1492, 1009);
        setWindowTitle("Telegram-like Desktop");
        setStyleSheet(telegram_stylesheet());
        statusBar()->showMessage("Disconnected");
        QObject::connect(menu_btn, &QToolButton::clicked,
                         [this] { show_account_drawer(); });
        QObject::connect(birthday_close, &QToolButton::clicked,
                         birthday_banner, &QWidget::hide);
        QObject::connect(header_search, &QToolButton::clicked, [this] {
            if (search_row_wrap_ != nullptr) {
                search_row_wrap_->setVisible(!search_row_wrap_->isVisible());
            }
            message_search_->setFocus();
            message_search_->selectAll();
        });
        QObject::connect(details_toggle_btn_, &QToolButton::clicked,
                         [this] { toggle_details_panel(); });
        has_remembered_login_ = has_remembered_login && !args_.gui_smoke;
        connecting_ = has_remembered_login_;
        store_.set_selected_conversation(args.conversation);
        load_cache();
        update_chat_header();
        render_store();
        if (has_remembered_login_ && !args_.gui_smoke) {
            QTimer::singleShot(150, this, [this] { connect_and_sync(); });
        } else if (!args_.gui_smoke) {
            QTimer::singleShot(180, this, [this] { show_login_dialog(); });
        }
        if (args_.gui_smoke) {
            QTimer::singleShot(250, this, [this] { run_gui_interaction_smoke(); });
        }

        // M140 demo hook: TELEGRAM_LIKE_DEMO_TYPING=1 spins up the typing
        // indicator with a fake peer so the animation is visible without
        // a real backend pulse. Real fanout (TYPING_START/TYPING_STOP) is
        // a separate milestone — this primitive is the UI half.
        if (typing_indicator_ != nullptr) {
            const char* demo = std::getenv("TELEGRAM_LIKE_DEMO_TYPING");
            if (demo != nullptr && demo[0] == '1') {
                typing_indicator_->setActive(QStringLiteral("u_bob"), true);
            }
        }

        // M139: appearance toggle — flip the active theme, repaint every
        // surface (QSS for widgets + bubble palette for the message view)
        // and persist the choice so the next launch picks the same mode.
        auto apply_theme = [this](bool dark) {
            namespace dt = telegram_like::client::app_desktop::design;
            dt::set_active_theme(dark);
            if (auto* app = qobject_cast<QApplication*>(QCoreApplication::instance())) {
                app->setStyleSheet(telegram_stylesheet());
            }
            QSettings().setValue(QStringLiteral("appearance/dark_theme"), dark);
            render_store();
        };
        QObject::connect(appearance_light_, &QRadioButton::toggled,
            [this, apply_theme](bool checked) { if (checked) apply_theme(false); });
        QObject::connect(appearance_dark_, &QRadioButton::toggled,
            [this, apply_theme](bool checked) { if (checked) apply_theme(true); });
        // M144: clicking the pin bar focuses the pinned message — same
        // mechanism as in-chat search "Use Match" so the bubble scrolls
        // into view + the focused outline lights up.
        QObject::connect(pin_bar_, &QPushButton::clicked, [this] {
            if (pin_bar_target_id_.isEmpty() || messages_ == nullptr) return;
            messages_->setSearchHighlight(message_search_->text().trimmed(),
                                          pin_bar_target_id_);
        });
        // M147: composer typing → debounced TYPING_PULSE(true). Only fires
        // once every 2s so a fast typist doesn't generate a flood; the
        // indicator on the receiving side decays 5s after the last
        // inbound pulse via typing_decay_timer_.
        typing_decay_timer_ = new QTimer(this);
        typing_decay_timer_->setInterval(5000);
        typing_decay_timer_->setSingleShot(true);
        QObject::connect(typing_decay_timer_, &QTimer::timeout, [this] {
            if (typing_indicator_ != nullptr) {
                typing_indicator_->setActive(QString(), false);
            }
        });
        QObject::connect(composer_, &QLineEdit::textEdited, [this](const QString& text) {
            if (!client_ || text.isEmpty()) return;
            const auto conv = store_.selected_conversation_id();
            if (conv.empty()) return;
            const qint64 now = QDateTime::currentMSecsSinceEpoch();
            if (now - last_typing_sent_ms_ < 2000) return;
            last_typing_sent_ms_ = now;
            auto client = client_;
            std::thread([client, conv] {
                (void)client->send_typing_pulse(conv, true);
            }).detach();
        });
        // Header overflow stays lightweight; the always-visible split-panel
        // button next to it owns the right sidebar toggle, matching the
        // Telegram Desktop reference screenshots.
        QObject::connect(chat_info_btn_, &QToolButton::clicked, [this] {
            QMenu menu(this);
            menu.setObjectName("topOverflowMenu");
            menu.addAction("Search", [this] {
                show_search_results_dialog(message_search_->text().trimmed());
            });
            menu.addAction(details_panel_ != nullptr && details_panel_->isVisible()
                ? "Hide Info" : "Show Info", [this] { toggle_details_panel(); });
            menu.addSeparator();
            menu.addAction("Chat info", [this] { show_chat_info_dialog(); });
            menu.exec(chat_info_btn_->mapToGlobal(QPoint(0, chat_info_btn_->height())));
        });

        QObject::connect(connect_, &QPushButton::clicked, [this] { connect_and_sync(); });
        QObject::connect(register_, &QPushButton::clicked, [this] { register_and_sync(); });
        QObject::connect(send_, &QPushButton::clicked, [this] { send_message(); });
        QObject::connect(attach_, &QPushButton::clicked, [this] {
            QMenu menu(this);
            menu.setObjectName("attachmentMenu");
            menu.addAction(line_icon("photo", 22, QColor("#7d8790")), "Photo or Video",
                           [this] { send_attachment(); });
            menu.addAction(line_icon("files", 22, QColor("#7d8790")), "File",
                           [this] { send_attachment(); });
            menu.addSeparator();
            menu.addAction(line_icon("saved", 22, QColor("#7d8790")), "Save Received File",
                           [this] { save_attachment(); });
            menu.exec(attach_->mapToGlobal(QPoint(0, -menu.sizeHint().height())));
        });
        QObject::connect(emoji_panel_, &QPushButton::clicked,
                         [this] { show_emoji_sticker_panel(); });
        QObject::connect(reply_, &QPushButton::clicked, [this] { reply_message(); });
        QObject::connect(forward_, &QPushButton::clicked, [this] { forward_message(); });
        QObject::connect(react_, &QPushButton::clicked, [this] { react_to_message(); });
        QObject::connect(pin_, &QPushButton::clicked, [this] { pin_message(true); });
        QObject::connect(unpin_, &QPushButton::clicked, [this] { pin_message(false); });
        QObject::connect(edit_, &QPushButton::clicked, [this] { edit_message_action(); });
        QObject::connect(delete_, &QPushButton::clicked, [this] { delete_message_action(); });
        QObject::connect(use_match_, &QPushButton::clicked, [this] { use_focused_message_as_action_target(); });
        QObject::connect(use_latest_, &QPushButton::clicked, [this] { use_latest_message_as_action_target(); });
        // M138: double-click a bubble to focus it as the current message
        // action target (used by the bottom-bar Reply/Forward/etc. fallback
        // controls, while the right-click context menu is the primary UX).
        QObject::connect(messages_,
            &telegram_like::client::app_desktop::BubbleListView::messageActivated,
            [this](const QString& message_id) {
                if (message_id.isEmpty()) return;
                message_action_id_->setText(message_id);
                statusBar()->showMessage("Selected message " + message_id, 2000);
            });
        QObject::connect(messages_,
            &telegram_like::client::app_desktop::BubbleListView::messageContextMenuRequested,
            [this](const QString& message_id, const QPoint& globalPos) {
                if (message_id.isEmpty()) return;
                message_action_id_->setText(message_id);
                QMenu menu(this);
                menu.setObjectName("messageContextMenu");
                menu.addAction("Reply",   [this] { reply_message(); });
                menu.addAction("Forward", [this] { forward_message(); });
                menu.addAction("React",   [this] { react_to_message(); });
                menu.addSeparator();
                menu.addAction("Pin",   [this] { pin_message(true);  });
                menu.addAction("Unpin", [this] { pin_message(false); });
                menu.addSeparator();
                auto* edit_action = menu.addAction("Edit", [this] { edit_message_action(); });
                auto* delete_action = menu.addAction("Delete", [this] { delete_message_action(); });
                const bool can_modify = can_modify_message(str(message_id));
                edit_action->setEnabled(can_modify);
                delete_action->setEnabled(can_modify);
                menu.exec(globalPos);
            });
        QObject::connect(save_attachment_, &QPushButton::clicked, [this] { save_attachment(); });
        QObject::connect(refresh_devices_, &QPushButton::clicked, [this] { refresh_devices(); });
        QObject::connect(refresh_profile_, &QPushButton::clicked, [this] { refresh_profile(); });
        QObject::connect(save_profile_, &QPushButton::clicked, [this] { save_profile(); });
        QObject::connect(revoke_device_, &QPushButton::clicked, [this] { manage_device(DeviceAction::Revoke); });
        QObject::connect(trust_device_, &QPushButton::clicked, [this] { manage_device(DeviceAction::Trust); });
        QObject::connect(untrust_device_, &QPushButton::clicked, [this] { manage_device(DeviceAction::Untrust); });
        QObject::connect(refresh_contacts_, &QPushButton::clicked, [this] { refresh_contacts(); });
        QObject::connect(add_contact_, &QPushButton::clicked, [this] { manage_contact(true); });
        QObject::connect(remove_contact_, &QPushButton::clicked, [this] { manage_contact(false); });
        QObject::connect(search_users_, &QPushButton::clicked, [this] { search_users(); });
        QObject::connect(create_group_, &QPushButton::clicked, [this] { create_group(); });
        QObject::connect(add_member_, &QPushButton::clicked, [this] { manage_group_member(true); });
        QObject::connect(remove_member_, &QPushButton::clicked, [this] { manage_group_member(false); });
        QObject::connect(remote_invite_, &QPushButton::clicked, [this] { remote_invite_action(); });
        QObject::connect(remote_approve_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Approve); });
        QObject::connect(remote_reject_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Reject); });
        QObject::connect(remote_cancel_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Cancel); });
        QObject::connect(remote_terminate_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Terminate); });
        QObject::connect(remote_rendezvous_, &QPushButton::clicked, [this] { remote_rendezvous_action(); });
        QObject::connect(call_invite_, &QPushButton::clicked, [this] { call_invite_action(); });
        QObject::connect(call_accept_, &QPushButton::clicked, [this] { call_terminal_action(CallOp::Accept); });
        QObject::connect(call_decline_, &QPushButton::clicked, [this] { call_terminal_action(CallOp::Decline); });
        QObject::connect(call_end_, &QPushButton::clicked, [this] { call_terminal_action(CallOp::End); });
        QObject::connect(advanced_phone_request_, &QPushButton::clicked, [this] { advanced_phone_request_action(); });
        QObject::connect(advanced_phone_verify_, &QPushButton::clicked, [this] { advanced_phone_verify_action(); });
        QObject::connect(advanced_twofa_begin_, &QPushButton::clicked, [this] { advanced_twofa_begin_action(); });
        QObject::connect(advanced_twofa_confirm_, &QPushButton::clicked, [this] { advanced_twofa_code_action(true); });
        QObject::connect(advanced_twofa_disable_, &QPushButton::clicked, [this] { advanced_twofa_code_action(false); });
        QObject::connect(advanced_export_, &QPushButton::clicked, [this] { advanced_export_action(); });
        QObject::connect(advanced_delete_, &QPushButton::clicked, [this] { advanced_delete_action(); });
        QObject::connect(advanced_block_, &QPushButton::clicked, [this] { advanced_block_action(true); });
        QObject::connect(advanced_unblock_, &QPushButton::clicked, [this] { advanced_block_action(false); });
        QObject::connect(advanced_mute_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::Mute); });
        QObject::connect(advanced_unmute_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::Unmute); });
        QObject::connect(advanced_save_draft_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::SaveDraft); });
        QObject::connect(advanced_clear_draft_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::ClearDraft); });
        QObject::connect(advanced_pin_chat_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::Pin); });
        QObject::connect(advanced_unpin_chat_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::Unpin); });
        QObject::connect(advanced_archive_chat_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::Archive); });
        QObject::connect(advanced_unarchive_chat_, &QPushButton::clicked, [this] { advanced_chat_ack_action(AdvancedChatOp::Unarchive); });
        QObject::connect(advanced_profile_avatar_, &QPushButton::clicked, [this] { advanced_avatar_action(false); });
        QObject::connect(advanced_chat_avatar_, &QPushButton::clicked, [this] { advanced_avatar_action(true); });
        QObject::connect(advanced_poll_create_, &QPushButton::clicked, [this] { advanced_poll_create_action(); });
        QObject::connect(advanced_poll_vote_, &QPushButton::clicked, [this] { advanced_poll_action(true); });
        QObject::connect(advanced_poll_close_, &QPushButton::clicked, [this] { advanced_poll_action(false); });
        QObject::connect(chat_filter_, &QLineEdit::textChanged, [this] { render_conversation_list(); });
        QObject::connect(chat_filter_, &QLineEdit::returnPressed, [this] {
            show_search_results_dialog(chat_filter_->text().trimmed());
        });
        QObject::connect(message_search_, &QLineEdit::textChanged, [this] {
            current_search_index_ = -1;
            refresh_message_search();
        });
        QObject::connect(prev_match_, &QPushButton::clicked, [this] { step_message_search(-1); });
        QObject::connect(next_match_, &QPushButton::clicked, [this] { step_message_search(1); });
        QObject::connect(load_older_, &QPushButton::clicked, [this] { load_older_history(); });
        QObject::connect(server_search_, &QPushButton::clicked, [this] { search_server_messages(); });
        QObject::connect(composer_, &QLineEdit::returnPressed, [this] { send_message(); });
        QObject::connect(conversations_, &QListWidget::itemClicked, [this](QListWidgetItem* item) {
            if (item == nullptr) return;
            const auto conversation_id = str(item->data(Qt::UserRole).toString());
            if (conversation_id.empty()) return;
            store_.set_selected_conversation(conversation_id);
            conversation_->setText(qstr(conversation_id));
            attachment_id_->setText(qstr(store_.latest_attachment_id(conversation_id)));
            message_action_id_->setText(qstr(store_.last_message_id(conversation_id)));
            current_search_index_ = -1;
            refresh_message_search();
            update_chat_header();
            save_cache();
            render_store();
        });
        QObject::connect(toggle_details_, &QPushButton::clicked, [this] { show_settings_dialog(); });
    }

    ~DesktopWindow() override {
        shutting_down_ = true;
        if (client_) client_->disconnect();
    }

private:
    void append_line(const QString& line) {
        // M138: BubbleListView only renders messages, not log/error lines.
        // System info (errors, transfer progress, debug crumbs) used to be
        // appended into the chat area as plain text — that polluted the
        // bubble list. Route them to the status bar instead so they show
        // briefly without breaking the timeline.
        statusBar()->showMessage(line, 5000);
    }

    void show_emoji_sticker_panel() {
        if (emoji_panel_ == nullptr || composer_ == nullptr) return;
        QMenu panel(this);
        panel.setObjectName("emojiStickerPanel");
        auto insert_text = [this](const QString& token) {
            composer_->insert(token);
            composer_->setFocus();
        };
        auto* emoji_section = panel.addSection("Emoji");
        emoji_section->setObjectName("emojiSection");
        emoji_section->setData(QStringLiteral("emojiGrid"));
        panel.addAction("👍  Like", [insert_text] { insert_text(QStringLiteral("+1")); });
        panel.addAction("❤️  Heart", [insert_text] { insert_text(QStringLiteral("<3")); });
        panel.addAction("😂  Laugh", [insert_text] { insert_text(QStringLiteral(":joy:")); });
        panel.addAction("🔥  Fire", [insert_text] { insert_text(QStringLiteral(":fire:")); });
        panel.addAction("🎉  Party", [insert_text] { insert_text(QStringLiteral(":party:")); });
        panel.addSeparator();
        auto* sticker_section = panel.addSection("Stickers");
        sticker_section->setObjectName("stickerSection");
        sticker_section->setData(QStringLiteral("stickerGrid"));
        auto* wave = panel.addAction("Telegram Wave", [insert_text] { insert_text(QStringLiteral("[sticker:wave]")); });
        wave->setObjectName("stickerWaveAction");
        auto* ok = panel.addAction("OK Hand", [insert_text] { insert_text(QStringLiteral("[sticker:ok]")); });
        ok->setObjectName("stickerOkAction");
        auto* party = panel.addAction("Party", [insert_text] { insert_text(QStringLiteral("[sticker:party]")); });
        party->setObjectName("stickerPartyAction");
        panel.exec(emoji_panel_->mapToGlobal(QPoint(0, -panel.sizeHint().height())));
    }

    static QString telegram_stylesheet() {
        // M125 introduced design_tokens.h; M135 finishes the migration —
        // every QSS color now reads from the active theme so dark mode
        // toggling (TELEGRAM_LIKE_THEME=dark env var) actually changes
        // every surface instead of a leaky half-themed window.
        namespace dt = telegram_like::client::app_desktop::design;
        const auto& t = dt::active_theme();
        QString css = QString::fromUtf8(R"(
            QMainWindow, QWidget { background:{app_background}; color:{text_primary}; font-family:{font_stack}; font-size:{font_px}px; }
            QSplitter#mainSplitter::handle { background:{splitter}; width:1px; }
            QWidget#sidebar { background:{surface}; border-right:1px solid {border}; }
            QWidget#sidebarSearch { background:{surface}; border-bottom:1px solid {border_subtle}; min-height:64px; }
            QWidget#birthdayBanner { background:{surface}; border-bottom:1px solid {border_subtle}; }
            QLabel#birthdayText { color:{text_primary}; }
            QLabel#birthdayText span { color:{text_muted}; }
            QWidget#sidebarFooter { background:{surface_muted}; border-top:1px solid {border_subtle}; }
            QWidget#reconnectIndicator { background:{surface}; border-top:1px solid {border_subtle}; }
            QLabel#reconnectIndicatorText { color:{text_muted}; font-size:15px; }
            QListWidget#chatList { background:{surface}; border:none; padding:0; outline:0; }
            QListWidget#chatList::item { border:none; }
            QListWidget#chatList::item:selected { background:transparent; }
            QListWidget#chatList::item:hover { background:transparent; }
            QWidget#centerPane { background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {chat_area_start}, stop:0.5 {chat_area}, stop:1 {chat_area_end}); }
            QWidget#chatHeader { background:{surface}; border-bottom:1px solid {border}; }
            QLabel#chatHeaderTitle { font-weight:600; font-size:20px; color:{text_primary}; }
            QLabel#chatHeaderSubtitle { font-size:17px; color:{text_muted}; }
            QWidget#inChatSearch { background:{in_chat_search_bg}; border-bottom:1px solid {border}; }
            QWidget#connectionNotice { background:{surface}; border-bottom:1px solid {border_subtle}; }
            QLabel#connectionNoticeText { color:{text_secondary}; font-size:14px; }
            QLabel#searchStatus { color:{text_muted}; font-size:11px; padding-left:6px; }
            QTextBrowser { background:{chat_area}; border:none; color:{text_primary}; }
            QWidget#composer { background:{surface}; border-top:1px solid {border}; }
            QWidget#messageActions { background:{secondary_header_tint}; border-top:1px solid {border_subtle}; }
            QScrollArea#detailsPanel { background:{surface}; border-left:1px solid {border}; }
            QScrollArea#detailsPanel > QWidget > QWidget { background:{surface}; }
            QStackedWidget#detailsStack { background:{surface}; }
            QWidget#profileDetailsPage { background:{surface}; }
            QWidget#profileDetailsHeader { background:{app_background}; border-bottom:1px solid {border}; }
            QLabel#detailTitle { font-weight:700; font-size:20px; color:{text_primary}; }
            QLabel#detailSubtitle { font-size:17px; color:{text_muted}; }
            QWidget#detailSection { background:{surface}; border-bottom:8px solid {app_background}; }
            QLabel#detailLink { color:{primary}; font-size:13px; }
            QLabel#detailDescription { color:{text_secondary}; font-size:13px; }
            QListWidget#detailMembers { background:{surface}; border:none; outline:0; }
            QListWidget#detailMembers::item { padding:8px 2px; color:{text_primary}; }
            QListWidget#detailMediaRows { background:{surface}; border:none; outline:0; color:{text_primary}; font-size:15px; }
            QTabWidget#detailMediaTabs::pane { border:none; }
            QTabWidget#detailMediaTabs QTabBar::tab { padding:6px 10px; color:{text_secondary}; border-radius:8px; }
            QTabWidget#detailMediaTabs QTabBar::tab:selected { background:{selection_tint}; color:{text_primary}; font-weight:600; }
            QListWidget#detailMediaRows::item { min-height:38px; padding:5px 2px; color:{text_primary}; }
            QListWidget#detailFilesRows, QListWidget#detailLinksRows, QListWidget#detailVoiceRows { background:{surface}; border:none; outline:0; color:{text_primary}; }
            QToolButton#detailAction { background:{surface}; border:none; border-radius:8px; color:{primary}; padding:7px 4px 6px 4px; font-size:13px; }
            QToolButton#detailAction:hover { background:{hover}; }
            QPushButton#detailFlatAction { background:transparent; border:none; text-align:left; color:{text_primary}; padding:10px 2px; }
            QPushButton#dangerAction { background:transparent; border:none; text-align:left; color:{danger}; padding:10px 2px; }
            QWidget#settingsHeader { background:{surface}; border-bottom:1px solid {border_subtle}; }
            QLabel#settingsTitle { font-weight:700; font-size:15px; color:{text_primary}; }
            QToolButton#settingsClose { border:none; background:transparent; color:{text_muted}; font-size:14px; padding:4px 8px; border-radius:6px; }
            QToolButton#settingsClose:hover { background:{hover}; color:{text_primary}; }
            QDialog#contactsModal { background:{surface}; }
            QWidget#contactsModalBody { background:{surface}; }
            QWidget#telegramCreateBody { background:{surface}; }
            QLabel#groupCreateAvatar, QLabel#channelCreateAvatar { background:{primary}; border-radius:44px; }
            QLineEdit#contactsSearchInput { background:{surface_muted}; border:1px solid {border_subtle}; border-radius:18px; padding:8px 14px; font-size:14px; }
            QLineEdit#telegramCreateInput { background:{surface}; border:none; border-bottom:1px solid {border}; border-radius:0; padding:10px 4px; font-size:15px; }
            QListWidget#contactsModalList { background:{surface}; border:none; outline:0; font-size:14px; }
            QListWidget#contactsModalList::item { padding:7px 4px; color:{text_primary}; border-radius:8px; }
            QListWidget#contactsModalList::item:hover { background:{hover}; }
            QListWidget#searchResultsList { background:{surface}; border:none; outline:0; font-size:14px; }
            QListWidget#searchResultsList::item { padding:7px 12px; color:{text_primary}; border-bottom:1px solid {border_subtle}; }
            QListWidget#searchResultsList::item:hover { background:{hover}; }
            QMenu { background:{surface}; color:{text_primary}; border:1px solid {border}; padding:6px; }
            QMenu::item { padding:8px 28px 8px 24px; border-radius:6px; }
            QMenu::item:selected { background:{hover}; }
            QMenu::item:disabled { color:{text_disabled}; }
            QListWidget#settingsNav { background:{surface_muted}; border-right:1px solid {border_subtle}; padding:8px 4px; }
            QListWidget#settingsNav::item { padding:9px 12px; border-radius:8px; margin:1px 4px; color:{text_secondary}; }
            QListWidget#settingsNav::item:selected { background:{selection_tint}; color:{text_primary}; font-weight:600; }
            QListWidget#settingsNav::item:hover { background:{hover}; }
            QStackedWidget#settingsPages { background:{surface}; }
            QLabel#pageHeading { font-size:18px; font-weight:600; color:{text_primary}; }
            QLabel#pageSubtitle { font-size:12px; color:{text_muted}; padding-bottom:4px; }
            QLabel#fieldLabel { font-size:11px; font-weight:600; color:{text_muted}; text-transform:uppercase; letter-spacing:0.5px; }
            QLabel#profileIdentity { font-size:13px; color:{text_primary}; }
            QGroupBox#detailsGroup { border:1px solid {border}; border-radius:10px; margin-top:8px; padding-top:8px; background:{surface}; color:{text_primary}; }
            QGroupBox#detailsGroup::title { subcontrol-origin:margin; left:12px; padding:0 4px; color:{primary}; font-weight:600; }
            QLineEdit, QSpinBox, QPlainTextEdit { background:{surface}; color:{text_primary}; border:1px solid {border_input}; border-radius:8px; padding:6px 9px; selection-background-color:{primary}; selection-color:#ffffff; }
            QLineEdit#sidebarSearchInput { background:{surface_muted}; border:none; border-radius:24px; padding:11px 18px; color:{text_primary}; font-size:16px; min-height:26px; }
            QLineEdit#composerInput { border:none; border-radius:0; padding:10px 12px; font-size:17px; }
            QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border:1px solid {primary}; }
            QPushButton { background:{surface}; border:1px solid {border_input}; border-radius:8px; padding:6px 14px; color:{text_primary}; }
            QPushButton:hover { background:{hover}; }
            QPushButton:disabled { color:{text_disabled}; background:{secondary_header_tint}; border:1px solid {border}; }
            QPushButton#primary { background:{primary}; color:#ffffff; border:1px solid {primary}; font-weight:600; }
            QPushButton#primary:hover { background:{primary_hover}; border:1px solid {primary_hover}; }
            QPushButton#primary:disabled { background:{primary_disabled}; color:#ffffff; border:1px solid {primary_disabled}; }
            QPushButton#ghost { background:transparent; border:none; color:{primary}; padding:4px 8px; }
            QPushButton#ghost:hover { background:{primary_ghost_hover}; }
            QPushButton#dangerActionButton { color:{danger}; border-color:{danger}; }
            QPushButton#dangerActionButton:hover { background:{danger_hover}; }
            QToolButton#hamburgerButton, QToolButton#chatInfoBtn { border:none; background:transparent; color:{text_muted}; padding:7px 9px; border-radius:17px; font-size:24px; }
            QToolButton#hamburgerButton:hover, QToolButton#chatInfoBtn:hover { background:{hover}; color:{text_primary}; }
            QDialog#accountDrawer, QDialog#settingsModal, QDialog#loginModal { background:{surface}; }
            QScrollArea#accountDrawerScroll { background:{surface}; border:none; }
            QScrollArea#accountDrawerScroll > QWidget > QWidget { background:{surface}; }
            QWidget#drawerHeader { background:{surface}; border-bottom:1px solid {border_subtle}; }
            QLabel#drawerName { font-weight:700; font-size:15px; color:{text_primary}; }
            QLabel#drawerStatus { color:{primary}; font-size:13px; }
            QPushButton#drawerRow { background:{surface}; border:none; border-radius:0; text-align:left; padding:0 26px; font-size:20px; color:{text_primary}; }
            QPushButton#drawerRow:hover { background:{hover}; }
            QPushButton#drawerSettingsButton { background:{surface}; border:none; border-radius:0; text-align:left; padding:0 26px; font-size:20px; color:{text_primary}; min-height:64px; }
            QPushButton#drawerSettingsButton:hover { background:{hover}; }
            QWidget#drawerNightRow { background:{surface}; border-top:1px solid {border_subtle}; }
            QLabel#drawerFooter { color:{text_muted}; font-size:18px; }
            QWidget#loginChrome { background:{login_chrome_bg}; border-bottom:1px solid {login_chrome_border}; }
            QToolButton#loginBackButton { border:none; background:transparent; color:{login_back}; font-size:34px; padding:8px 16px; }
            QToolButton#loginBackButton:hover { background:{login_back_hover}; }
            QPushButton#loginSettingsButton { background:transparent; border:none; color:{primary}; font-size:18px; font-weight:600; padding:10px 18px; }
            QPushButton#loginSettingsButton:hover { background:{primary_ghost_hover}; }
            QWidget#loginHeroBanner { background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {login_hero_start}, stop:1 {login_hero_end}); }
            QLabel#loginHeroPlane { color:#ffffff; font-size:92px; font-weight:700; }
            QLabel#loginHeroHint { color:rgba(255,255,255,0.42); font-size:34px; font-weight:700; }
            QLabel#loginLogo { background:{primary}; border-radius:66px; }
            QLabel#loginTitle { color:{text_primary}; font-size:28px; font-weight:700; }
            QLabel#loginSubtitle, QLabel#loginStatus { color:{text_muted}; font-size:18px; }
            QTabWidget#loginModeTabs::pane { border:none; padding:0; }
            QTabWidget#loginModeTabs QTabBar::tab { max-height:0px; padding:0; margin:0; border:none; }
            QLabel#loginWelcomeCopy { color:{text_muted}; font-size:22px; line-height:150%; }
            QLabel#loginQrPlaceholder { background:{surface}; color:{primary}; border:10px solid {qr_border}; border-radius:18px; font-size:42px; font-weight:700; }
            QLabel#loginStepText { color:{text_primary}; font-size:20px; }
            QWidget#loginAdvancedFields { background:{surface}; border-top:1px solid {border_subtle}; }
            QLineEdit#loginInput { background:{surface}; border:none; border-bottom:1px solid {border}; border-radius:0; padding:10px 4px; font-size:15px; }
            QLineEdit#loginPhoneInput, QLineEdit#loginPhoneCodeInput { background:{surface}; border:none; border-bottom:2px solid {primary}; border-radius:0; padding:10px 4px; font-size:20px; }
            QSpinBox#loginPort { background:{surface}; border:1px solid {border}; border-radius:8px; padding:8px; font-size:14px; }
            QWidget#settingsModalHeader { background:{surface}; }
            QWidget#settingsModalHeader QLabel { background:transparent; }
            QLabel#settingsModalTitle { font-weight:700; font-size:22px; color:{text_primary}; background:transparent; }
            QWidget#settingsIdentity { background:{surface}; border-bottom:8px solid {app_background}; }
            QWidget#settingsIdentity QLabel { background:transparent; }
            QWidget#settingsModalContent { background:{surface}; }
            QScrollArea QWidget#settingsModalContent { background:{surface}; }
            QWidget#settingsModalRow { background:{surface}; min-height:80px; border-bottom:1px solid {border_subtle}; font-size:22px; }
            QWidget#settingsModalRow QLabel { background:transparent; }
            QWidget#settingsModalRow:hover { background:{hover}; }
            QLabel#settingsRowLabel { color:{text_primary}; font-size:22px; }
            QLabel#settingsTrailing { color:{primary}; font-size:19px; }
            QWidget#settingsScaleBlock { background:{surface}; border-top:8px solid {app_background}; border-bottom:8px solid {app_background}; }
            QWidget#settingsScaleBlock QLabel { background:transparent; }
            QDialog#proxySettingsModal, QDialog#proxyEditModal { background:{surface}; border-radius:12px; }
            QLabel#proxyTitle { color:{text_primary}; font-size:24px; font-weight:700; }
            QLabel#proxyHelp, QLabel#proxyEmpty { color:{text_muted}; font-size:18px; }
            QLabel#proxySectionTitle { color:{text_primary}; font-size:20px; font-weight:600; }
            QRadioButton#proxyRadio, QCheckBox#proxyCheck { color:{text_primary}; font-size:19px; spacing:16px; }
            QLineEdit#proxyInput { background:{surface}; border:none; border-bottom:2px solid {border_subtle}; border-radius:0; padding:10px 0; font-size:20px; color:{text_primary}; }
            QLineEdit#proxyInput:focus { border-bottom:2px solid {primary}; }
            QScrollBar:vertical { background:transparent; width:6px; margin:0; }
            QScrollBar::handle:vertical { background:{border_input}; border-radius:3px; min-height:28px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; background:transparent; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
            QScrollBar:horizontal { height:0px; background:transparent; }
            QCheckBox { spacing:6px; color:{text_primary}; }
            QStatusBar { background:{surface}; border-top:1px solid {border}; color:{text_muted}; max-height:0px; }
            QProgressBar { border:1px solid {border_input}; border-radius:6px; background:{surface}; color:{text_primary}; height:14px; text-align:center; }
            QProgressBar::chunk { background:{primary}; border-radius:6px; }
            QSlider::groove:horizontal { background:{border_subtle}; height:4px; border-radius:2px; }
            QSlider::handle:horizontal { background:{primary}; width:16px; height:16px; margin:-6px 0; border-radius:8px; }
            QSlider::sub-page:horizontal { background:{primary}; height:4px; border-radius:2px; }
        )");
        // Substitute the {name} placeholders with active-theme values. Done
        // as a pass over named keys so the QSS source stays human-readable
        // rather than a chain of ~30 .arg() calls.
        const bool dark_chat_area = QString::fromUtf8(t.chat_area) == QStringLiteral("#0e1621");
        const char* chat_area_start = dark_chat_area ? t.chat_area : "#dfe79d";
        const char* chat_area_end = dark_chat_area ? t.chat_area : "#8ac5b0";
        const std::pair<const char*, const char*> subs[] = {
            {"app_background",        t.app_background},
            {"surface",               t.surface},
            {"surface_muted",         t.surface_muted},
            {"chat_area_start",       chat_area_start},
            {"chat_area",             t.chat_area},
            {"chat_area_end",         chat_area_end},
            {"border",                t.border},
            {"border_subtle",         t.border_subtle},
            {"border_input",          t.border_input},
            {"splitter",              t.splitter},
            {"selection_tint",        t.selection_tint},
            {"hover",                 t.hover},
            {"primary",               t.primary},
            {"primary_hover",         t.primary_hover},
            {"primary_disabled",      t.primary_disabled},
            {"primary_ghost_hover",   t.primary_ghost_hover},
            {"danger",                "#e53935"},
            {"danger_hover",          t.primary_ghost_hover},
            {"login_chrome_bg",       t.app_background},
            {"login_chrome_border",   t.border},
            {"login_back",            t.text_disabled},
            {"login_back_hover",      t.hover},
            {"login_hero_start",      t.primary},
            {"login_hero_end",        t.primary_hover},
            {"qr_border",             t.text_primary},
            {"secondary_header_tint", t.secondary_header_tint},
            {"in_chat_search_bg",     t.in_chat_search_bg},
            {"text_primary",          t.text_primary},
            {"text_secondary",        t.text_secondary},
            {"text_muted",            t.text_muted},
            {"text_disabled",         t.text_disabled},
        };
        for (const auto& [name, value] : subs) {
            css.replace(QString::fromUtf8("{") + QString::fromUtf8(name) + QString::fromUtf8("}"),
                        QString::fromUtf8(value));
        }
        // font_stack + font_px aren't theme-dependent but stay in the same
        // substitution scheme so the QSS template doesn't mix two styles.
        css.replace(QStringLiteral("{font_stack}"), QString::fromUtf8(dt::kFontStack));
        css.replace(QStringLiteral("{font_px}"),    QString::number(dt::kFontPxBase));
        return css;
    }

    void request_thumbnails_for_visible_messages() {
        // M148: scan the selected conversation for image-MIME attachments
        // that aren't in the cache + aren't already being fetched, then
        // kick a worker thread per miss. Cache is capped at 64 entries
        // (newest wins) so a long history of images doesn't bloat memory.
        if (client_ == nullptr) return;
        const auto* conv = store_.selected_conversation();
        if (conv == nullptr) return;
        for (auto it = conv->messages.rbegin(); it != conv->messages.rend(); ++it) {
            const auto& m = *it;
            if (m.attachment_id.empty()) continue;
            const QString key = qstr(m.attachment_id);
            if (m.mime_type.rfind("image/", 0) != 0) continue;
            if (thumbnail_cache_.contains(key)) continue;
            if (thumbnail_inflight_.contains(key)) continue;
            thumbnail_inflight_.insert(key);
            const std::string aid = m.attachment_id;
            auto client = client_;
            std::thread([this, client, aid, key] {
                const auto fetched = client->fetch_attachment(aid);
                QMetaObject::invokeMethod(this, [this, key, fetched] {
                    if (shutting_down_) return;
                    thumbnail_inflight_.remove(key);
                    if (!fetched.ok || fetched.content.empty()) return;
                    QImage img;
                    img.loadFromData(QByteArray::fromStdString(fetched.content));
                    if (img.isNull()) return;
                    if (img.width() > 480 || img.height() > 480) {
                        img = img.scaled(480, 480, Qt::KeepAspectRatio,
                                          Qt::SmoothTransformation);
                    }
                    if (thumbnail_cache_.size() >= 64) {
                        // Drop an arbitrary entry to keep memory bounded.
                        thumbnail_cache_.erase(thumbnail_cache_.begin());
                    }
                    thumbnail_cache_.insert(key, QPixmap::fromImage(img));
                    if (messages_ != nullptr) {
                        messages_->setThumbnailCache(thumbnail_cache_);
                    }
                }, Qt::QueuedConnection);
            }).detach();
            // Cap to ~8 inflight at a time so fast scrolls don't flood.
            if (thumbnail_inflight_.size() >= 8) break;
        }
    }

    void handle_typing_pulse_push(const std::string& envelope) {
        // M147: parse the JSON envelope sent by the server (shape:
        // {type:"typing_pulse", payload:{conversation_id, is_typing,
        // sender_user_id}, ...}) and flip the indicator. Self-pulses are
        // suppressed — server filters by `_fanout_to_conversation`'s
        // origin_session_id but a defensive check costs nothing here.
        if (typing_indicator_ == nullptr) return;
        const QJsonDocument doc = QJsonDocument::fromJson(
            QByteArray::fromStdString(envelope));
        if (!doc.isObject()) return;
        const QJsonObject root = doc.object();
        const QJsonObject payload = root.value("payload").toObject();
        const QString sender = payload.value("sender_user_id").toString();
        const QString conv = payload.value("conversation_id").toString();
        const bool is_typing = payload.value("is_typing").toBool(true);
        if (sender.isEmpty() || sender == qstr(store_.current_user_id())) return;
        // Only show typing for the currently-open conversation; pulses
        // from other rooms would be confusing in the header subtitle.
        if (conv != qstr(store_.selected_conversation_id())) return;
        if (is_typing) {
            typing_indicator_->setActive(sender, true);
            if (typing_decay_timer_ != nullptr) typing_decay_timer_->start();
        } else {
            typing_indicator_->setActive(QString(), false);
            if (typing_decay_timer_ != nullptr) typing_decay_timer_->stop();
        }
    }

    void show_chat_info_dialog() {
        // M145: Telegram-style chat-info popup. Shows
        //   title + conv id (header)
        //   participants list (each entry "uid · role" — owner/admin/member
        //                      derived from M103 participant_role_for if
        //                      available; falls back to plain id)
        //   pinned messages list ("[id] sender · snippet")
        //   summary footer (attachment count + last sync version)
        // Built on every click so the lists stay current; closes on Esc / X.
        const auto* conv = store_.selected_conversation();
        if (conv == nullptr) {
            QMessageBox::information(this, "Chat info",
                "Pick a chat from the list first.");
            return;
        }
        auto* dlg = new QDialog(this);
        dlg->setWindowTitle("Chat info");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        // M150: dock as a frameless tool window on the right edge of the
        // main window and slide in from off-screen-right via
        // QPropertyAnimation. Closing animates it back out before
        // accepting so the disappearance feels intentional rather than
        // a hard pop.
        dlg->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint);
        dlg->setAttribute(Qt::WA_TranslucentBackground, false);
        const int panelW = 360;
        const QRect mainGeo = this->geometry();
        const int targetY = mainGeo.top() + 32;  // skip past system title
        const int targetH = std::max(360, mainGeo.height() - 64);
        const int targetX = mainGeo.right() - panelW - 8;
        const QRect dockedGeo(targetX, targetY, panelW, targetH);
        const QRect offGeo(mainGeo.right() + 8, targetY, panelW, targetH);
        dlg->setGeometry(offGeo);

        auto* root = new QVBoxLayout(dlg);
        root->setSpacing(10);
        root->setContentsMargins(16, 14, 16, 14);

        const QString title = conv->title.empty()
            ? qstr(conv->conversation_id)
            : qstr(conv->title);
        auto* title_label = new QLabel(QString("<b style='font-size:14pt'>%1</b>")
            .arg(title.toHtmlEscaped()));
        title_label->setTextFormat(Qt::RichText);
        root->addWidget(title_label);
        auto* sub_label = new QLabel(QString("<span style='color:#7c8a96'>%1 · %2 participants</span>")
            .arg(qstr(conv->conversation_id).toHtmlEscaped())
            .arg(conv->participant_user_ids.size()));
        sub_label->setTextFormat(Qt::RichText);
        root->addWidget(sub_label);

        // Participants
        auto* members_label = new QLabel("<b>Members</b>");
        members_label->setTextFormat(Qt::RichText);
        root->addWidget(members_label);
        auto* members = new QListWidget();
        members->setFrameShape(QFrame::NoFrame);
        for (const auto& uid : conv->participant_user_ids) {
            members->addItem(qstr(uid));
        }
        if (conv->participant_user_ids.empty()) {
            members->addItem("(no participant data — try Connect to refresh)");
        }
        root->addWidget(members, 1);

        // Pinned + attachments summary
        std::size_t attachment_count = 0;
        std::vector<const telegram_like::client::app_desktop::DesktopMessage*> pinned_list;
        for (const auto& m : conv->messages) {
            if (!m.attachment_id.empty()) ++attachment_count;
            if (m.pinned && !m.deleted) pinned_list.push_back(&m);
        }
        auto* pinned_label = new QLabel(
            QString("<b>Pinned (%1)</b>").arg(pinned_list.size()));
        pinned_label->setTextFormat(Qt::RichText);
        root->addWidget(pinned_label);
        auto* pinned_widget = new QListWidget();
        pinned_widget->setFrameShape(QFrame::NoFrame);
        pinned_widget->setMaximumHeight(96);
        for (const auto* m : pinned_list) {
            pinned_widget->addItem(QString("[%1] %2  %3")
                .arg(qstr(m->message_id),
                     qstr(m->sender_user_id),
                     qstr(m->text).left(48)));
        }
        if (pinned_list.empty()) pinned_widget->addItem("(nothing pinned)");
        root->addWidget(pinned_widget);

        auto* footer = new QLabel(QString("Attachments: %1   Sync version: %2")
            .arg(attachment_count)
            .arg(conv->sync_version));
        footer->setStyleSheet("color:#7c8a96; font-size:11px;");
        root->addWidget(footer);

        auto* btn_row = new QHBoxLayout();
        btn_row->addStretch(1);
        auto* close_btn = new QPushButton("Close");
        close_btn->setObjectName("primary");
        // M150: closing animates the panel back off-screen-right before
        // the dialog actually accepts, so the disappearance feels like
        // a slide rather than a pop.
        QObject::connect(close_btn, &QPushButton::clicked, dlg, [dlg, dockedGeo, offGeo] {
            auto* outAnim = new QPropertyAnimation(dlg, "geometry", dlg);
            outAnim->setDuration(180);
            outAnim->setEasingCurve(QEasingCurve::InCubic);
            outAnim->setStartValue(dockedGeo);
            outAnim->setEndValue(offGeo);
            QObject::connect(outAnim, &QPropertyAnimation::finished, dlg, &QDialog::accept);
            outAnim->start(QAbstractAnimation::DeleteWhenStopped);
        });
        btn_row->addWidget(close_btn);
        root->addLayout(btn_row);

        dlg->show();
        // M150: slide-in animation from off-screen right to the docked
        // position. 220 ms with an out-cubic curve for a Telegram-feel
        // swoosh. DeleteWhenStopped frees the QPropertyAnimation once
        // the slide finishes.
        auto* inAnim = new QPropertyAnimation(dlg, "geometry", dlg);
        inAnim->setDuration(220);
        inAnim->setEasingCurve(QEasingCurve::OutCubic);
        inAnim->setStartValue(offGeo);
        inAnim->setEndValue(dockedGeo);
        inAnim->start(QAbstractAnimation::DeleteWhenStopped);
    }

    void show_account_drawer() {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("accountDrawer");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint);
        const QRect dockedGeo = account_drawer_geometry(false);
        const QRect offGeo = account_drawer_geometry(true);
        const int panelW = dockedGeo.width();
        const int panelH = dockedGeo.height();
        dlg->setFixedSize(panelW, panelH);
        dlg->setGeometry(offGeo);
        auto close_drawer = [this, dlg] {
            if (dlg == nullptr || !dlg->isVisible()) return;
            const QRect docked = account_drawer_geometry(false);
            const QRect offscreen = account_drawer_geometry(true);
            auto* outAnim = new QPropertyAnimation(dlg, "geometry", dlg);
            outAnim->setDuration(160);
            outAnim->setEasingCurve(QEasingCurve::InCubic);
            outAnim->setStartValue(docked);
            outAnim->setEndValue(offscreen);
            QObject::connect(outAnim, &QPropertyAnimation::finished, dlg, &QDialog::accept);
            outAnim->start(QAbstractAnimation::DeleteWhenStopped);
        };

        account_drawer_ = dlg;
        QObject::connect(dlg, &QDialog::finished, this, [this, dlg] {
            if (account_drawer_ == dlg) account_drawer_ = nullptr;
        });

        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        auto* scroll = new QScrollArea();
        scroll->setObjectName("accountDrawerScroll");
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        auto* content = new QWidget();
        content->setObjectName("accountDrawerContent");
        content->setMinimumWidth(panelW);
        scroll->setWidget(content);
        root->addWidget(scroll, 1);
        auto* content_layout = new QVBoxLayout(content);
        content_layout->setContentsMargins(0, 0, 0, 0);
        content_layout->setSpacing(0);
        auto* header = new QWidget();
        header->setObjectName("drawerHeader");
        auto* header_layout = new QVBoxLayout(header);
        header_layout->setContentsMargins(32, 36, 28, 22);
        header_layout->setSpacing(10);
        const QString drawer_display = display_name_->text().trimmed().isEmpty()
            ? (args_.gui_smoke ? QStringLiteral("XZMQ") : user_->text().trimmed())
            : display_name_->text().trimmed();
        const std::string drawer_seed = args_.gui_smoke && store_.current_user_id().empty()
            ? std::string("xirmir")
            : (store_.current_user_id().empty() ? args_.user : store_.current_user_id());
        auto* avatar = new QLabel();
        avatar->setFixedSize(96, 96);
        avatar->setPixmap(avatar_pixmap_for(drawer_seed, drawer_display, 96));
        header_layout->addWidget(avatar);
        auto* name = new QLabel(drawer_display);
        name->setObjectName("drawerName");
        header_layout->addWidget(name);
        auto* status = new QLabel("Set Emoji Status");
        status->setObjectName("drawerStatus");
        header_layout->addWidget(status);
        content_layout->addWidget(header);

        auto add_row = [&](const QString& icon_key, const QString& text, QObject* receiver = nullptr,
                           const char* slot = nullptr) -> QPushButton* {
            auto* btn = new QPushButton(text);
            btn->setObjectName("drawerRow");
            btn->setIcon(line_icon(icon_key, 28));
            btn->setIconSize(QSize(28, 28));
            btn->setMinimumHeight(64);
            btn->setCursor(Qt::PointingHandCursor);
            content_layout->addWidget(btn);
            if (receiver != nullptr && slot != nullptr) {
                QObject::connect(btn, SIGNAL(clicked()), receiver, slot);
            } else if (text != "Settings" && text != "New Group"
                       && text != "New Channel" && text != "Contacts") {
                QObject::connect(btn, &QPushButton::clicked, dlg, close_drawer);
            }
            return btn;
        };
        add_row("profile", "My Profile");
        add_row("wallet", "Wallet");
        auto* group_row = add_row("group", "New Group");
        QObject::connect(group_row, &QPushButton::clicked, dlg, [this, dlg] {
            dlg->accept();
            show_conversation_create_dialog(false);
        });
        auto* channel_row = add_row("channel", "New Channel");
        QObject::connect(channel_row, &QPushButton::clicked, dlg, [this, dlg] {
            dlg->accept();
            show_conversation_create_dialog(true);
        });
        auto* contacts_row = add_row("contact", "Contacts");
        QObject::connect(contacts_row, &QPushButton::clicked, dlg, [this, dlg] {
            dlg->accept();
            show_contacts_dialog();
        });
        add_row("call", "Calls");
        add_row("saved", "Saved Messages");
        auto* settings = add_row("settings", "Settings");
        settings->setObjectName("drawerSettingsButton");
        QObject::connect(settings, &QPushButton::clicked, dlg, [this, dlg] {
            dlg->accept();
            show_settings_dialog();
        });

        auto* night_wrap = new QWidget();
        night_wrap->setObjectName("drawerNightRow");
        auto* night_layout = new QHBoxLayout(night_wrap);
        night_layout->setContentsMargins(32, 10, 32, 10);
        auto* night_icon = new QLabel();
        night_icon->setPixmap(line_icon("moon", 28).pixmap(28, 28));
        night_layout->addWidget(night_icon);
        night_layout->addWidget(new QLabel("Night Mode"), 1);
        auto* night = new QCheckBox();
        night->setChecked(telegram_like::client::app_desktop::design::is_dark_theme());
        night_layout->addWidget(night);
        content_layout->addWidget(night_wrap);
        QObject::connect(night, &QCheckBox::toggled, [this](bool dark) {
            telegram_like::client::app_desktop::design::set_active_theme(dark);
            QSettings prefs;
            prefs.setValue(QStringLiteral("appearance/dark_theme"), dark);
            if (auto* app = qobject_cast<QApplication*>(QApplication::instance())) {
                app->setStyleSheet(telegram_stylesheet());
            }
            setStyleSheet(telegram_stylesheet());
            render_store();
        });

        content_layout->addStretch(1);
        auto* footer = new QLabel("Telegram Desktop<br>Version 6.7.5 x64 - About");
        footer->setObjectName("drawerFooter");
        footer->setTextFormat(Qt::RichText);
        footer->setContentsMargins(32, 14, 32, 30);
        content_layout->addWidget(footer);
        QObject::connect(qApp, &QApplication::focusChanged, dlg,
                         [dlg, close_drawer](QWidget*, QWidget* now) {
                             if (dlg == nullptr || !dlg->isVisible() || now == nullptr) return;
                             if (now != dlg && !dlg->isAncestorOf(now)) close_drawer();
                         });

        dlg->show();
        auto* inAnim = new QPropertyAnimation(dlg, "geometry", dlg);
        inAnim->setDuration(190);
        inAnim->setEasingCurve(QEasingCurve::OutCubic);
        inAnim->setStartValue(offGeo);
        inAnim->setEndValue(dockedGeo);
        QObject::connect(inAnim, &QPropertyAnimation::finished, dlg, [this, dlg] {
            if (dlg != nullptr && dlg->isVisible()) dlg->setGeometry(account_drawer_geometry(false));
        });
        inAnim->start(QAbstractAnimation::DeleteWhenStopped);
    }

    QRect account_drawer_geometry(bool offscreen) const {
        const QPoint mainTopLeft = mapToGlobal(QPoint(0, 0));
        const int panelW = sidebar_panel_ != nullptr && sidebar_panel_->width() > 0
            ? sidebar_panel_->width()
            : 390;
        const int panelH = height();
        const int x = offscreen ? mainTopLeft.x() - panelW : mainTopLeft.x();
        return QRect(x, mainTopLeft.y(), panelW, panelH);
    }

    void sync_account_drawer_geometry() {
        if (account_drawer_ == nullptr || !account_drawer_->isVisible()) return;
        const QRect docked = account_drawer_geometry(false);
        account_drawer_->setFixedSize(docked.size());
        account_drawer_->setGeometry(docked);
        if (auto* content = account_drawer_->findChild<QWidget*>("accountDrawerContent")) {
            content->setMinimumWidth(docked.width());
        }
    }

protected:
    void resizeEvent(QResizeEvent* event) override {
        QMainWindow::resizeEvent(event);
        sync_account_drawer_geometry();
    }

    void moveEvent(QMoveEvent* event) override {
        QMainWindow::moveEvent(event);
        sync_account_drawer_geometry();
    }

    void show_login_dialog() {
        if (logged_in_ || connecting_) return;
        auto* dlg = new QDialog(this);
        login_dialog_ = dlg;
        dlg->setObjectName("loginModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setModal(false);
        dlg->setWindowTitle("Telegram-like");
        dlg->resize(980, 760);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);

        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);

        auto* chrome = new QWidget();
        chrome->setObjectName("loginChrome");
        auto* chrome_layout = new QHBoxLayout(chrome);
        chrome_layout->setContentsMargins(20, 6, 22, 6);
        auto* back_btn = new QToolButton();
        back_btn->setObjectName("loginBackButton");
        back_btn->setText("←");
        back_btn->setToolTip("Back to QR login");
        chrome_layout->addWidget(back_btn);
        chrome_layout->addStretch(1);
        auto* settings_btn = new QPushButton("SETTINGS");
        settings_btn->setObjectName("loginSettingsButton");
        chrome_layout->addWidget(settings_btn);
        root->addWidget(chrome);

        auto* login_modes = new QTabWidget();
        login_modes->setObjectName("loginModeTabs");
        auto* welcome_page = new QWidget();
        welcome_page->setObjectName("loginWelcomePage");
        auto* welcome_layout = new QVBoxLayout(welcome_page);
        welcome_layout->setContentsMargins(0, 0, 0, 0);
        welcome_layout->setSpacing(0);
        auto* hero = new QWidget();
        hero->setObjectName("loginHeroBanner");
        hero->setFixedHeight(285);
        auto* hero_layout = new QVBoxLayout(hero);
        hero_layout->setContentsMargins(0, 26, 0, 0);
        auto* hero_plane = new QLabel("✈");
        hero_plane->setObjectName("loginHeroPlane");
        hero_plane->setAlignment(Qt::AlignCenter);
        hero_layout->addWidget(hero_plane);
        auto* hero_hint = new QLabel("♪   ☁      ◇      ▣");
        hero_hint->setObjectName("loginHeroHint");
        hero_hint->setAlignment(Qt::AlignCenter);
        hero_layout->addWidget(hero_hint);
        welcome_layout->addWidget(hero);
        welcome_layout->addSpacing(58);
        auto* title = new QLabel("Telegram Desktop");
        title->setObjectName("loginTitle");
        title->setAlignment(Qt::AlignCenter);
        welcome_layout->addWidget(title);
        auto* welcome_copy = new QLabel("Welcome to the official Telegram Desktop app.\nIt's fast and secure.");
        welcome_copy->setObjectName("loginWelcomeCopy");
        welcome_copy->setWordWrap(true);
        welcome_copy->setAlignment(Qt::AlignCenter);
        welcome_layout->addWidget(welcome_copy);
        welcome_layout->addStretch(1);
        auto* phone_page = new QWidget();
        phone_page->setObjectName("loginPhonePage");
        auto* phone_layout = new QVBoxLayout(phone_page);
        phone_layout->setContentsMargins(250, 86, 250, 0);
        phone_layout->setSpacing(22);
        auto* phone_title = new QLabel("Your Phone Number");
        phone_title->setObjectName("loginTitle");
        phone_layout->addWidget(phone_title);
        auto* phone_copy = new QLabel("Please confirm your country code\nand enter your phone number.");
        phone_copy->setObjectName("loginSubtitle");
        phone_layout->addWidget(phone_copy);
        phone_layout->addSpacing(42);
        auto* country = new QLineEdit("USA");
        country->setObjectName("loginPhoneInput");
        country->setReadOnly(true);
        phone_layout->addWidget(country);
        auto* phone_input = new QLineEdit();
        phone_input->setObjectName("loginPhoneInput");
        phone_input->setPlaceholderText("+1        --- --- ----");
        phone_layout->addWidget(phone_input);
        auto* phone_code = new QLineEdit();
        phone_code->setObjectName("loginPhoneCodeInput");
        phone_code->setPlaceholderText("Code");
        phone_layout->addWidget(phone_code);
        phone_layout->addStretch(1);
        auto* phone_to_qr = new QPushButton("Quick log in using QR code");
        phone_to_qr->setObjectName("ghost");
        phone_layout->addWidget(phone_to_qr, 0, Qt::AlignHCenter);
        auto* qr_page = new QWidget();
        qr_page->setObjectName("loginQrPage");
        auto* qr_layout = new QVBoxLayout(qr_page);
        qr_layout->setContentsMargins(0, 78, 0, 0);
        qr_layout->setSpacing(18);
        auto* qr_box = new QLabel("QR");
        qr_box->setObjectName("loginQrPlaceholder");
        qr_box->setAlignment(Qt::AlignCenter);
        qr_box->setFixedSize(230, 230);
        qr_layout->addWidget(qr_box, 0, Qt::AlignHCenter);
        auto* qr_title = new QLabel("Scan From Mobile Telegram");
        qr_title->setObjectName("loginTitle");
        qr_title->setAlignment(Qt::AlignCenter);
        qr_layout->addWidget(qr_title);
        auto* qr_hint = new QLabel("1. Open Telegram on your phone\n\n2. Go to Settings > Devices > Link Desktop Device\n\n3. Scan this image to Log In");
        qr_hint->setObjectName("loginStepText");
        qr_hint->setAlignment(Qt::AlignCenter);
        qr_layout->addWidget(qr_hint);
        qr_layout->addStretch(1);
        auto* qr_to_phone = new QPushButton("Log in using phone number");
        qr_to_phone->setObjectName("ghost");
        qr_layout->addWidget(qr_to_phone, 0, Qt::AlignHCenter);
        login_modes->addTab(welcome_page, "Welcome");
        login_modes->addTab(phone_page, "Phone");
        login_modes->addTab(qr_page, "QR");
        root->addWidget(login_modes, 1);

        auto* advanced_fields = new QWidget();
        advanced_fields->setObjectName("loginAdvancedFields");
        advanced_fields->setVisible(false);
        auto* advanced_layout = new QVBoxLayout(advanced_fields);
        advanced_layout->setContentsMargins(250, 12, 250, 10);
        advanced_layout->setSpacing(8);
        auto* user = new QLineEdit(user_->text());
        user->setObjectName("loginInput");
        user->setPlaceholderText("Username");
        advanced_layout->addWidget(user);
        auto* pass = new QLineEdit(password_->text());
        pass->setObjectName("loginInput");
        pass->setPlaceholderText("Password");
        pass->setEchoMode(QLineEdit::Password);
        advanced_layout->addWidget(pass);
        auto* device = new QLineEdit(device_->text());
        device->setObjectName("loginInput");
        device->setPlaceholderText("Device name");
        advanced_layout->addWidget(device);
        auto* host_row = new QHBoxLayout();
        auto* host = new QLineEdit(host_->text());
        host->setObjectName("loginInput");
        host->setPlaceholderText("Host");
        auto* port = new QSpinBox();
        port->setObjectName("loginPort");
        port->setRange(1, 65535);
        port->setValue(port_->value());
        host_row->addWidget(host, 1);
        host_row->addWidget(port);
        advanced_layout->addLayout(host_row);
        root->addWidget(advanced_fields);
        auto* status = new QLabel();
        login_status_ = status;
        status->setObjectName("loginStatus");
        status->setWordWrap(true);
        status->setAlignment(Qt::AlignCenter);
        root->addWidget(status);
        auto* login = new QPushButton("Start Messaging");
        login_submit_ = login;
        login->setObjectName("primary");
        login->setFixedWidth(430);
        root->addWidget(login);
        root->setAlignment(login, Qt::AlignHCenter);
        auto* register_btn = new QPushButton("Create Account");
        login_register_ = register_btn;
        register_btn->setObjectName("ghost");
        root->addWidget(register_btn);
        root->setAlignment(register_btn, Qt::AlignHCenter);

        auto apply_fields = [this, user, pass, device, host, port] {
            user_->setText(user->text().trimmed());
            password_->setText(pass->text());
            display_name_->setText(user->text().trimmed());
            device_->setText(device->text().trimmed());
            host_->setText(host->text().trimmed());
            port_->setValue(port->value());
        };
        QObject::connect(login, &QPushButton::clicked, this, [this, dlg, status, apply_fields] {
            apply_fields();
            status->setText("Connecting to server...");
            if (login_submit_) login_submit_->setEnabled(false);
            if (login_register_) login_register_->setEnabled(false);
            connect_and_sync();
        });
        QObject::connect(register_btn, &QPushButton::clicked, this, [this, dlg, status, apply_fields] {
            apply_fields();
            status->setText("Creating account on server...");
            if (login_submit_) login_submit_->setEnabled(false);
            if (login_register_) login_register_->setEnabled(false);
            register_and_sync();
        });
        QObject::connect(dlg, &QDialog::destroyed, this, [this] {
            login_dialog_.clear();
            login_status_.clear();
            login_submit_.clear();
            login_register_.clear();
        });
        QObject::connect(back_btn, &QToolButton::clicked, login_modes, [login_modes] {
            login_modes->setCurrentIndex(2);
        });
        QObject::connect(settings_btn, &QPushButton::clicked, advanced_fields, [advanced_fields] {
            advanced_fields->setVisible(!advanced_fields->isVisible());
        });
        QObject::connect(qr_to_phone, &QPushButton::clicked, login_modes, [login_modes] {
            login_modes->setCurrentIndex(1);
        });
        QObject::connect(phone_to_qr, &QPushButton::clicked, login_modes, [login_modes] {
            login_modes->setCurrentIndex(2);
        });
        QObject::connect(pass, &QLineEdit::returnPressed, login, &QPushButton::click);
        dlg->show();
        login->setFocus();
    }

    void show_contacts_dialog() {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("contactsModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle("Contacts");
        dlg->setModal(false);
        dlg->resize(520, 680);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);

        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        auto* header = new QWidget();
        header->setObjectName("settingsModalHeader");
        auto* header_layout = new QHBoxLayout(header);
        header_layout->setContentsMargins(24, 22, 20, 18);
        auto* title = new QLabel("Contacts");
        title->setObjectName("settingsModalTitle");
        header_layout->addWidget(title, 1);
        auto* close = new QToolButton();
        close->setObjectName("settingsClose");
        close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        close->setCursor(Qt::PointingHandCursor);
        header_layout->addWidget(close);
        QObject::connect(close, &QToolButton::clicked, dlg, &QDialog::accept);
        root->addWidget(header);

        auto* body = new QWidget();
        body->setObjectName("contactsModalBody");
        auto* body_layout = new QVBoxLayout(body);
        body_layout->setContentsMargins(24, 18, 24, 24);
        body_layout->setSpacing(14);
        auto* search = new QLineEdit();
        search->setObjectName("contactsSearchInput");
        search->setPlaceholderText("Search or add user_id");
        search->setClearButtonEnabled(true);
        body_layout->addWidget(search);
        auto* status = new QLabel(client_ ? "Loading contacts..." : "Connect to load contacts");
        status->setObjectName("pageSubtitle");
        body_layout->addWidget(status);
        auto* list = new QListWidget();
        list->setObjectName("contactsModalList");
        list->setFrameShape(QFrame::NoFrame);
        list->setFocusPolicy(Qt::NoFocus);
        list->setSelectionMode(QAbstractItemView::NoSelection);
        body_layout->addWidget(list, 1);
        auto* actions = new QHBoxLayout();
        auto* add = new QPushButton("Add Contact");
        add->setObjectName("primary");
        add->setEnabled(client_ != nullptr);
        actions->addWidget(add);
        auto* refresh = new QPushButton("Refresh");
        refresh->setEnabled(client_ != nullptr);
        actions->addWidget(refresh);
        body_layout->addLayout(actions);
        root->addWidget(body, 1);

        auto render_result = [list, status](const telegram_like::client::transport::ContactListResult& result) {
            list->clear();
            if (!result.ok) {
                status->setText("Contact load failed: " + qstr(result.error_code + " " + result.error_message));
                return;
            }
            status->setText(QString("%1 contacts").arg(result.contacts.size()));
            for (const auto& contact : result.contacts) {
                const QString label = qstr(contact.display_name.empty() ? contact.user_id : contact.display_name)
                    + QStringLiteral("\n")
                    + qstr(contact.user_id)
                    + (contact.online ? QStringLiteral("  online") : QStringLiteral("  offline"));
                auto* item = new QListWidgetItem(line_icon("contact", 28, QColor("#7d8790")), label);
                item->setSizeHint(QSize(0, 62));
                list->addItem(item);
            }
            if (result.contacts.empty()) {
                auto* empty = new QListWidgetItem(line_icon("search", 28, QColor("#7d8790")),
                                                  QStringLiteral("No contacts yet"));
                empty->setSizeHint(QSize(0, 54));
                list->addItem(empty);
            }
        };
        auto load_contacts = [this, dlg, render_result] {
            if (!client_) return;
            auto client = client_;
            std::thread([this, dlg, client, render_result] {
                const auto result = client->list_contacts();
                QMetaObject::invokeMethod(this, [dlg, result, render_result] {
                    if (dlg == nullptr || !dlg->isVisible()) return;
                    render_result(result);
                }, Qt::QueuedConnection);
            }).detach();
        };
        QObject::connect(refresh, &QPushButton::clicked, this, load_contacts);
        QObject::connect(add, &QPushButton::clicked, this, [this, dlg, search, status, render_result] {
            if (!client_) return;
            const auto target = str(search->text().trimmed());
            if (target.empty()) {
                status->setText("Enter a username, display name, or user_id");
                return;
            }
            status->setText("Adding " + qstr(target) + "...");
            auto client = client_;
            std::thread([this, dlg, client, target, render_result] {
                std::string user_id = target;
                telegram_like::client::transport::ContactListResult result;
                if (target.rfind("u_", 0) != 0) {
                    const auto search = client->search_users(target, 1);
                    if (!search.ok || search.results.empty()) {
                        result.ok = false;
                        result.error_code = search.ok ? "user_not_found" : search.error_code;
                        result.error_message = search.ok ? "No matching user." : search.error_message;
                    } else {
                        user_id = search.results.front().user_id;
                    }
                }
                if (result.error_code.empty()) {
                    result = client->add_contact(user_id);
                }
                QMetaObject::invokeMethod(this, [dlg, result, render_result] {
                    if (dlg == nullptr || !dlg->isVisible()) return;
                    render_result(result);
                }, Qt::QueuedConnection);
            }).detach();
        });
        load_contacts();
        dlg->show();
        if (args_.gui_smoke) {
            telegram_like::client::transport::ContactListResult result;
            result.ok = true;
            result.contacts.push_back(telegram_like::client::transport::ContactEntry {
                "u_blake",
                "Hello Blake",
                false,
            });
            render_result(result);
            status->clear();
        }
    }

    void show_profile_reference_dialog() {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("profileModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle("Profile");
        dlg->resize(785, 802);
        dlg->setStyleSheet(QStringLiteral(
            "QDialog#profileModal { background:#ffffff; border-radius:12px; }"
            "QWidget#profileModalHero { background:#f3f3f3; }"
            "QLabel#profileModalName { color:#0f1419; font-size:28px; font-weight:700; }"
            "QLabel#profileModalOnline { color:#168acd; font-size:24px; }"
            "QWidget#profileModalRow { background:#ffffff; border-bottom:1px solid #e7e9eb; }"
            "QLabel#profileModalPrimary { color:#0f1419; font-size:24px; }"
            "QLabel#profileModalSecondary { color:#8a9299; font-size:24px; }"
            "QLabel#profileModalStories { color:#8a9299; font-size:24px; border-top:1px solid #e7e9eb; background:#ffffff; }"
        ));
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);
        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        auto* hero = new QWidget();
        hero->setObjectName("profileModalHero");
        auto* hero_layout = new QVBoxLayout(hero);
        hero_layout->setContentsMargins(28, 34, 28, 56);
        auto* top = new QHBoxLayout();
        top->addStretch(1);
        auto* edit = new QToolButton();
        edit->setObjectName("chatInfoBtn");
        edit->setText(QString::fromUtf8("\xe2\x9c\x8e"));
        top->addWidget(edit);
        auto* close = new QToolButton();
        close->setObjectName("settingsClose");
        close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        top->addWidget(close);
        hero_layout->addLayout(top);
        auto* avatar = new QLabel();
        avatar->setFixedSize(160, 160);
        avatar->setPixmap(avatar_pixmap_for("xirmir", QStringLiteral("XZMQ"), 160));
        hero_layout->addWidget(avatar, 0, Qt::AlignHCenter);
        auto* name = new QLabel("XZMQ");
        name->setObjectName("profileModalName");
        name->setAlignment(Qt::AlignCenter);
        hero_layout->addWidget(name);
        auto* online = new QLabel("online");
        online->setObjectName("profileModalOnline");
        online->setAlignment(Qt::AlignCenter);
        hero_layout->addWidget(online);
        root->addWidget(hero);
        auto add_field = [&](const QString& primary, const QString& secondary, bool qr = false) {
            auto* row = new QWidget();
            row->setObjectName("profileModalRow");
            auto* layout = new QHBoxLayout(row);
            layout->setContentsMargins(48, 22, 48, 18);
            auto* texts = new QVBoxLayout();
            auto* p = new QLabel(primary);
            p->setObjectName("profileModalPrimary");
            auto* s = new QLabel(secondary);
            s->setObjectName("profileModalSecondary");
            texts->addWidget(p);
            texts->addWidget(s);
            layout->addLayout(texts, 1);
            if (qr) {
                auto* q = new QLabel(QString::fromUtf8("\xe2\x96\xa6"));
                q->setObjectName("settingsTrailing");
                layout->addWidget(q);
            }
            root->addWidget(row);
        };
        add_field("+1 302 276 8530", "Mobile");
        add_field("@xirmir", "Username", true);
        auto* stories = new QLabel("Your stories will be here.");
        stories->setObjectName("profileModalStories");
        stories->setAlignment(Qt::AlignCenter);
        stories->setMinimumHeight(168);
        root->addWidget(stories, 1);
        QObject::connect(close, &QToolButton::clicked, dlg, &QDialog::accept);
        dlg->show();
    }

    void show_conversation_create_dialog(bool channel_mode) {
        auto* dlg = new QDialog(this);
        if (channel_mode) {
            dlg->setObjectName("newChannelModal");
        } else {
            dlg->setObjectName("newGroupModal");
        }
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle(channel_mode ? "New Channel" : "New Group");
        dlg->resize(520, 620);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);

        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        auto* header = new QWidget();
        header->setObjectName("settingsModalHeader");
        auto* header_layout = new QHBoxLayout(header);
        header_layout->setContentsMargins(24, 22, 20, 18);
        auto* title = new QLabel(channel_mode ? "New Channel" : "New Group");
        title->setObjectName("settingsModalTitle");
        header_layout->addWidget(title, 1);
        auto* close = new QToolButton();
        close->setObjectName("settingsClose");
        close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        close->setCursor(Qt::PointingHandCursor);
        header_layout->addWidget(close);
        QObject::connect(close, &QToolButton::clicked, dlg, &QDialog::accept);
        root->addWidget(header);

        auto* body = new QWidget();
        body->setObjectName("telegramCreateBody");
        auto* body_layout = new QVBoxLayout(body);
        body_layout->setContentsMargins(28, 22, 28, 28);
        body_layout->setSpacing(14);
        auto* avatar = new QLabel();
        avatar->setFixedSize(88, 88);
        avatar->setAlignment(Qt::AlignCenter);
        avatar->setPixmap(line_icon(channel_mode ? "channel" : "group", 58, QColor("#ffffff")).pixmap(58, 58));
        avatar->setObjectName(channel_mode ? "channelCreateAvatar" : "groupCreateAvatar");
        body_layout->addWidget(avatar, 0, Qt::AlignHCenter);

        auto* name = new QLineEdit();
        name->setObjectName("telegramCreateInput");
        name->setPlaceholderText(channel_mode ? "Channel name" : "Group name");
        body_layout->addWidget(name);
        auto* participants = new QLineEdit();
        participants->setObjectName("telegramCreateInput");
        participants->setPlaceholderText("Add members by user_id, comma-separated");
        body_layout->addWidget(participants);
        auto* hint = new QLabel(channel_mode
            ? "Channel UI is matched to the reference; current backend stores it as a named conversation."
            : "Create a real backend conversation with the selected members.");
        hint->setWordWrap(true);
        hint->setObjectName("pageSubtitle");
        body_layout->addWidget(hint);
        auto* status = new QLabel(client_ ? "Ready" : "Connect first");
        status->setObjectName("pageSubtitle");
        body_layout->addWidget(status);
        body_layout->addStretch(1);
        auto* create = new QPushButton(channel_mode ? "Create Channel" : "Create Group");
        create->setObjectName("primary");
        create->setEnabled(client_ != nullptr);
        body_layout->addWidget(create);
        root->addWidget(body, 1);

        QObject::connect(create, &QPushButton::clicked, this,
            [this, dlg, name, participants, status, channel_mode] {
                if (!client_) return;
                const auto ids = parse_user_ids(participants->text());
                if (ids.empty()) {
                    status->setText("Add at least one member user_id");
                    return;
                }
                const QString typed_title = name->text().trimmed();
                const auto title = str(typed_title.isEmpty()
                    ? (channel_mode ? QStringLiteral("New Channel") : QStringLiteral("New Group"))
                    : typed_title);
                status->setText("Creating...");
                auto client = client_;
                QPointer<QDialog> guard(dlg);
                QPointer<QLabel> status_guard(status);
                std::thread([this, client, ids, title, guard, status_guard] {
                    const auto result = client->create_conversation(ids, title);
                    QMetaObject::invokeMethod(this, [this, result, guard, status_guard] {
                        if (shutting_down_) return;
                        if (!result.ok) {
                            if (status_guard) {
                                status_guard->setText("Create failed: "
                                    + qstr(result.error_code + " " + result.error_message));
                            }
                            return;
                        }
                        apply_conversation_action(result);
                        conversation_->setText(qstr(result.conversation.conversation_id));
                        store_.set_selected_conversation(result.conversation.conversation_id);
                        render_store();
                        if (guard) guard->accept();
                        statusBar()->showMessage("Created " + qstr(result.conversation.conversation_id));
                    }, Qt::QueuedConnection);
                }).detach();
            });
        dlg->show();
    }

    void show_search_results_dialog(const QString& initial_query = {}) {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("searchResultsModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle("Search");
        dlg->resize(560, 720);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);
        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        auto* header = new QWidget();
        header->setObjectName("settingsModalHeader");
        auto* header_layout = new QHBoxLayout(header);
        header_layout->setContentsMargins(20, 18, 18, 16);
        auto* input = new QLineEdit(initial_query.trimmed());
        input->setObjectName("contactsSearchInput");
        input->setPlaceholderText("Search");
        input->setClearButtonEnabled(true);
        header_layout->addWidget(input, 1);
        auto* close = new QToolButton();
        close->setObjectName("settingsClose");
        close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        header_layout->addWidget(close);
        QObject::connect(close, &QToolButton::clicked, dlg, &QDialog::accept);
        root->addWidget(header);
        auto* list = new QListWidget();
        list->setObjectName("searchResultsList");
        list->setFrameShape(QFrame::NoFrame);
        list->setFocusPolicy(Qt::NoFocus);
        root->addWidget(list, 1);

        auto render_local = [this, list](const QString& query) {
            list->clear();
            const auto chats = store_.filtered_conversations(str(query));
            for (const auto& conv : chats) {
                const QString title = reference_title_for(conv.conversation_id, conv.title);
                QString snippet = conv.messages.empty()
                    ? QStringLiteral("No messages")
                    : qstr(conv.messages.back().text).left(80);
                auto* item = new QListWidgetItem(line_icon("chat", 26, QColor("#7d8790")),
                                                 title + QStringLiteral("\n") + snippet);
                item->setData(Qt::UserRole, qstr(conv.conversation_id));
                item->setSizeHint(QSize(0, 64));
                list->addItem(item);
            }
            if (query.trimmed().isEmpty()) return;
            const auto local_messages = store_.search_selected_messages(str(query.trimmed()));
            for (const auto& msg : local_messages) {
                auto* item = new QListWidgetItem(line_icon("search", 26, QColor("#7d8790")),
                                                 QStringLiteral("In current chat\n") + qstr(msg.snippet));
                item->setData(Qt::UserRole, qstr(msg.message_id));
                item->setSizeHint(QSize(0, 64));
                list->addItem(item);
            }
        };
        QObject::connect(input, &QLineEdit::textChanged, this, [render_local](const QString& text) {
            render_local(text);
        });
        QObject::connect(input, &QLineEdit::returnPressed, this, [this, input, list] {
            if (!client_ || input->text().trimmed().isEmpty()) return;
            const auto query = str(input->text().trimmed());
            auto client = client_;
            QPointer<QListWidget> list_guard(list);
            std::thread([this, client, query, list_guard] {
                const auto result = client->search_users(query, 8);
                QMetaObject::invokeMethod(this, [list_guard, result] {
                    if (!list_guard) return;
                    if (!result.ok) return;
                    for (const auto& user : result.results) {
                        auto* item = new QListWidgetItem(line_icon("contact", 26, QColor("#7d8790")),
                            qstr((user.display_name.empty() ? user.username : user.display_name)
                                 + "\n" + user.user_id + (user.is_contact ? "  contact" : "")));
                        item->setSizeHint(QSize(0, 64));
                        list_guard->addItem(item);
                    }
                }, Qt::QueuedConnection);
            }).detach();
        });
        QObject::connect(list, &QListWidget::itemDoubleClicked, this, [this, dlg](QListWidgetItem* item) {
            const auto id = str(item->data(Qt::UserRole).toString());
            if (id.rfind("conv_", 0) == 0) {
                conversation_->setText(qstr(id));
                store_.set_selected_conversation(id);
                render_store();
                dlg->accept();
            } else if (!id.empty()) {
                message_action_id_->setText(qstr(id));
            }
        });
        render_local(input->text());
        dlg->show();
        input->setFocus();
    }

    void show_settings_dialog() {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("settingsModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle("Settings");
        dlg->setModal(false);
        dlg->setMinimumSize(700, 780);
        dlg->resize(700, 820);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);
        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);

        auto* header = new QWidget();
        header->setObjectName("settingsModalHeader");
        auto* header_layout = new QHBoxLayout(header);
        header_layout->setContentsMargins(32, 30, 28, 26);
        auto* title = new QLabel("Settings");
        title->setObjectName("settingsModalTitle");
        header_layout->addWidget(title, 1);
        for (const QString& icon : {QString::fromUtf8("\xe2\x8c\x95"), QString::fromUtf8("\xe2\x8b\xae")}) {
            auto* b = new QToolButton();
            b->setObjectName("chatInfoBtn");
            b->setText(icon);
            header_layout->addWidget(b);
        }
        auto* close = new QToolButton();
        close->setObjectName("settingsClose");
        close->setText(QString::fromUtf8("\xe2\x9c\x95"));
        header_layout->addWidget(close);
        root->addWidget(header);
        QObject::connect(close, &QToolButton::clicked, dlg, &QDialog::accept);

        auto* identity = new QWidget();
        identity->setObjectName("settingsIdentity");
        auto* identity_layout = new QHBoxLayout(identity);
        identity_layout->setContentsMargins(32, 20, 32, 30);
        identity_layout->setSpacing(30);
        auto* avatar = new QLabel();
        avatar->setFixedSize(112, 112);
        const QString display = display_name_->text().trimmed().isEmpty()
            ? (args_.gui_smoke ? QStringLiteral("XZMQ") : user_->text().trimmed())
            : display_name_->text().trimmed();
        const QString phone = args_.gui_smoke
            ? QStringLiteral("+1 302 276 8530")
            : qstr(args_.user);
        const QString handle = user_->text().trimmed().isEmpty()
            ? (args_.gui_smoke ? QStringLiteral("xirmir") : QString())
            : user_->text().trimmed();
        avatar->setPixmap(avatar_pixmap_for(
            store_.current_user_id().empty() ? args_.user : store_.current_user_id(),
            display,
            112));
        identity_layout->addWidget(avatar);
        auto* identity_text = new QLabel(QStringLiteral(
            "<b style='font-size:24px'>%1</b><br>"
            "<span style='font-size:21px'>%2</span><br>"
            "<span style='font-size:20px;color:#8a9299'>@%3</span>")
            .arg(display.toHtmlEscaped(),
                 phone.toHtmlEscaped(),
                 handle.toHtmlEscaped()));
        identity_text->setTextFormat(Qt::RichText);
        identity_layout->addWidget(identity_text, 1);
        root->addWidget(identity);

        auto* scroll = new QScrollArea();
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setWidgetResizable(true);
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        auto* content = new QWidget();
        content->setObjectName("settingsModalContent");
        auto* layout = new QVBoxLayout(content);
        layout->setContentsMargins(0, 0, 0, 0);
        layout->setSpacing(0);
        auto add_settings_row = [&](const QString& icon_key, const QString& text,
                                    const QString& trailing = {}) {
            auto* row = new QWidget();
            row->setObjectName("settingsModalRow");
            auto* row_layout = new QHBoxLayout(row);
            row_layout->setContentsMargins(42, 0, 28, 0);
            row_layout->setSpacing(30);
            auto* icon = new QLabel();
            icon->setFixedSize(34, 34);
            icon->setPixmap(line_icon(icon_key, 34).pixmap(34, 34));
            row_layout->addWidget(icon);
            auto* label = new QLabel(text);
            label->setObjectName("settingsRowLabel");
            row_layout->addWidget(label, 1);
            if (!trailing.isEmpty()) {
                auto* tail = new QLabel(trailing);
                tail->setObjectName("settingsTrailing");
                row_layout->addWidget(tail);
            }
            layout->addWidget(row);
        };

        add_settings_row("account", "My Account");
        add_settings_row("bell", "Notifications and Sounds");
        add_settings_row("lock", "Privacy and Security");
        add_settings_row("chat", "Chat Settings");
        add_settings_row("folder", "Folders");
        add_settings_row("advanced", "Advanced");
        add_settings_row("speaker", "Speakers and Camera");
        add_settings_row("battery", "Battery and Animations");
        add_settings_row("language", "Language", "English");

        auto* scale = new QWidget();
        scale->setObjectName("settingsScaleBlock");
        auto* scale_layout = new QVBoxLayout(scale);
        scale_layout->setContentsMargins(28, 16, 28, 18);
        auto* scale_top = new QHBoxLayout();
        auto* scale_icon = new QLabel();
        scale_icon->setFixedSize(28, 28);
        scale_icon->setPixmap(line_icon("scale", 28).pixmap(28, 28));
        scale_top->addWidget(scale_icon);
        auto* scale_label = new QLabel("Default interface scale");
        scale_label->setObjectName("settingsRowLabel");
        scale_top->addWidget(scale_label, 1);
        auto* scale_toggle = new QCheckBox();
        scale_toggle->setChecked(true);
        scale_top->addWidget(scale_toggle);
        scale_layout->addLayout(scale_top);
        auto* slider_row = new QHBoxLayout();
        auto* slider = new QSlider(Qt::Horizontal);
        slider->setRange(80, 220);
        slider->setValue(200);
        slider_row->addWidget(slider, 1);
        auto* scale_value = new QLabel("200%");
        scale_value->setObjectName("settingsTrailing");
        slider_row->addWidget(scale_value);
        scale_layout->addLayout(slider_row);
        QObject::connect(slider, &QSlider::valueChanged,
                         [scale_value](int value) { scale_value->setText(QString::number(value) + "%"); });
        layout->addWidget(scale);

        add_settings_row("premium", "Telegram Premium");
        add_settings_row("stars", "My Stars");
        layout->addStretch(1);
        scroll->setWidget(content);
        root->addWidget(scroll, 1);
        dlg->show();
    }

    void show_proxy_settings_dialog() {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("proxySettingsModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle("Proxy settings");
        dlg->setModal(false);
        dlg->resize(700, 820);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);

        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(44, 32, 44, 30);
        root->setSpacing(18);
        auto* header = new QHBoxLayout();
        auto* title = new QLabel("Proxy settings");
        title->setObjectName("proxyTitle");
        header->addWidget(title, 1);
        auto* more = new QToolButton();
        more->setText(QString::fromUtf8("\xe2\x8b\xae"));
        more->setObjectName("chatInfoBtn");
        header->addWidget(more);
        root->addLayout(header);

        auto* ipv6 = new QCheckBox("Try connecting through IPv6");
        ipv6->setObjectName("proxyCheck");
        root->addWidget(ipv6);
        auto* disable = new QRadioButton("Disable proxy");
        disable->setObjectName("proxyRadio");
        root->addWidget(disable);
        auto* system = new QRadioButton("Use system proxy settings");
        system->setObjectName("proxyRadio");
        system->setChecked(true);
        root->addWidget(system);
        auto* custom = new QRadioButton("Use custom proxy");
        custom->setObjectName("proxyRadio");
        root->addWidget(custom);

        auto* help = new QLabel("Proxy servers may be helpful in accessing Telegram\nif there is no connection in a specific region.");
        help->setObjectName("proxyHelp");
        help->setWordWrap(true);
        root->addSpacing(8);
        root->addWidget(help);
        root->addStretch(1);
        auto* empty = new QLabel("Your saved proxy list will be here.");
        empty->setObjectName("proxyEmpty");
        empty->setAlignment(Qt::AlignCenter);
        root->addWidget(empty);
        root->addStretch(1);

        auto* buttons = new QHBoxLayout();
        buttons->addStretch(1);
        auto* close = new QPushButton("Close");
        close->setObjectName("ghost");
        auto* add = new QPushButton("Add proxy");
        add->setObjectName("ghost");
        buttons->addWidget(close);
        buttons->addSpacing(24);
        buttons->addWidget(add);
        root->addLayout(buttons);
        QObject::connect(close, &QPushButton::clicked, dlg, &QDialog::close);
        QObject::connect(add, &QPushButton::clicked, this, [this] { show_proxy_edit_dialog(); });
        dlg->show();
    }

    void show_proxy_edit_dialog() {
        auto* dlg = new QDialog(this);
        dlg->setObjectName("proxyEditModal");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->setWindowTitle("Edit proxy");
        dlg->setModal(false);
        dlg->resize(700, 820);
        const QRect mainGeo = geometry();
        dlg->move(mainGeo.center().x() - dlg->width() / 2,
                  mainGeo.center().y() - dlg->height() / 2);

        auto* root = new QVBoxLayout(dlg);
        root->setContentsMargins(44, 32, 44, 30);
        root->setSpacing(18);
        auto* title = new QLabel("Edit proxy");
        title->setObjectName("proxyTitle");
        root->addWidget(title);
        auto* socks = new QRadioButton("SOCKS5");
        socks->setObjectName("proxyRadio");
        socks->setChecked(true);
        root->addWidget(socks);
        auto* http = new QRadioButton("HTTP");
        http->setObjectName("proxyRadio");
        root->addWidget(http);
        auto* mtproto = new QRadioButton("MTPROTO");
        mtproto->setObjectName("proxyRadio");
        root->addWidget(mtproto);
        root->addSpacing(22);
        auto* socket = new QLabel("Socket address");
        socket->setObjectName("proxySectionTitle");
        root->addWidget(socket);
        auto* socket_row = new QHBoxLayout();
        auto* host = new QLineEdit();
        host->setObjectName("proxyInput");
        host->setPlaceholderText("Hostname");
        auto* port = new QLineEdit();
        port->setObjectName("proxyInput");
        port->setPlaceholderText("Port");
        port->setFixedWidth(110);
        socket_row->addWidget(host, 1);
        socket_row->addSpacing(28);
        socket_row->addWidget(port);
        root->addLayout(socket_row);
        auto* creds = new QLabel("Credentials (optional)");
        creds->setObjectName("proxySectionTitle");
        root->addSpacing(14);
        root->addWidget(creds);
        auto* username = new QLineEdit();
        username->setObjectName("proxyInput");
        username->setPlaceholderText("Username");
        root->addWidget(username);
        auto* password = new QLineEdit();
        password->setObjectName("proxyInput");
        password->setPlaceholderText("Password");
        root->addWidget(password);
        root->addStretch(1);
        auto* buttons = new QHBoxLayout();
        auto* share = new QPushButton("Share");
        share->setObjectName("ghost");
        buttons->addWidget(share);
        buttons->addStretch(1);
        auto* cancel = new QPushButton("Cancel");
        cancel->setObjectName("ghost");
        auto* save = new QPushButton("Save");
        save->setObjectName("ghost");
        buttons->addWidget(cancel);
        buttons->addSpacing(24);
        buttons->addWidget(save);
        root->addLayout(buttons);
        QObject::connect(cancel, &QPushButton::clicked, dlg, &QDialog::close);
        QObject::connect(save, &QPushButton::clicked, dlg, &QDialog::close);
        dlg->show();
        host->setFocus();
    }

    static int top_level_count(const char* object_name) {
        int count = 0;
        for (QWidget* widget : QApplication::topLevelWidgets()) {
            if (widget != nullptr && widget->isVisible()
                && widget->objectName() == QString::fromUtf8(object_name)) {
                ++count;
            }
        }
        return count;
    }

    static void close_top_levels(const char* object_name) {
        for (QWidget* widget : QApplication::topLevelWidgets()) {
            if (widget != nullptr && widget->isVisible()
                && widget->objectName() == QString::fromUtf8(object_name)) {
                widget->close();
            }
        }
    }

    static QWidget* first_top_level(const char* object_name) {
        for (QWidget* widget : QApplication::topLevelWidgets()) {
            if (widget != nullptr && widget->isVisible()
                && widget->objectName() == QString::fromUtf8(object_name)) {
                return widget;
            }
        }
        return nullptr;
    }

    bool save_gui_smoke_capture(
        QWidget* widget,
        const QString& name,
        const QRect& region = QRect()) {
        if (args_.smoke_save_dir.empty() || widget == nullptr) return true;
        QDir dir(qstr(args_.smoke_save_dir));
        if (!dir.exists() && !dir.mkpath(QStringLiteral("."))) {
            std::cerr << "desktop gui smoke failed: could not create screenshot dir "
                      << args_.smoke_save_dir << "\n";
            return false;
        }
        const QString path = dir.filePath(name + QStringLiteral(".png"));
        const QPixmap pix = region.isNull() ? widget->grab() : widget->grab(region);
        if (pix.isNull() || !pix.save(path, "PNG")) {
            std::cerr << "desktop gui smoke failed: could not save screenshot "
                      << path.toStdString() << "\n";
            return false;
        }
        std::cout << "desktop gui smoke screenshot: "
                  << path.toStdString()
                  << " " << pix.width() << "x" << pix.height() << "\n";
        return true;
    }

    bool save_gui_smoke_drawer_overlay_capture(
        QWidget* drawer,
        const QString& name,
        const QRect& region = QRect()) {
        if (args_.smoke_save_dir.empty() || drawer == nullptr) return true;
        QDir dir(qstr(args_.smoke_save_dir));
        if (!dir.exists() && !dir.mkpath(QStringLiteral("."))) {
            std::cerr << "desktop gui smoke failed: could not create screenshot dir "
                      << args_.smoke_save_dir << "\n";
            return false;
        }
        QPixmap pix = grab();
        if (pix.isNull()) {
            std::cerr << "desktop gui smoke failed: could not capture drawer overlay base\n";
            return false;
        }
        QPainter painter(&pix);
        painter.fillRect(pix.rect(), QColor(0, 0, 0, 105));
        painter.drawPixmap(0, 0, drawer->grab());
        painter.end();
        const QString path = dir.filePath(name + QStringLiteral(".png"));
        const QPixmap out = region.isNull() ? pix : pix.copy(region);
        if (out.isNull() || !out.save(path, "PNG")) {
            std::cerr << "desktop gui smoke failed: could not save screenshot "
                      << path.toStdString() << "\n";
            return false;
        }
        std::cout << "desktop gui smoke screenshot: "
                  << path.toStdString()
                  << " " << out.width() << "x" << out.height() << "\n";
        return true;
    }

    bool save_gui_smoke_modal_overlay_capture(QWidget* modal, const QString& name) {
        if (args_.smoke_save_dir.empty() || modal == nullptr) return true;
        QDir dir(qstr(args_.smoke_save_dir));
        if (!dir.exists() && !dir.mkpath(QStringLiteral("."))) {
            std::cerr << "desktop gui smoke failed: could not create screenshot dir "
                      << args_.smoke_save_dir << "\n";
            return false;
        }
        QPixmap pix = grab();
        if (pix.isNull()) {
            std::cerr << "desktop gui smoke failed: could not capture modal overlay base\n";
            return false;
        }
        const QRect mainGeo = geometry();
        const QPoint modalPos = modal->geometry().topLeft() - mainGeo.topLeft();
        QPainter painter(&pix);
        painter.fillRect(pix.rect(), QColor(0, 0, 0, 105));
        painter.drawPixmap(modalPos, modal->grab());
        painter.end();
        const QString path = dir.filePath(name + QStringLiteral(".png"));
        if (!pix.save(path, "PNG")) {
            std::cerr << "desktop gui smoke failed: could not save screenshot "
                      << path.toStdString() << "\n";
            return false;
        }
        std::cout << "desktop gui smoke screenshot: "
                  << path.toStdString()
                  << " " << pix.width() << "x" << pix.height() << "\n";
        return true;
    }

    static transport::SyncedMessage gui_smoke_message(
        const std::string& id,
        const std::string& sender,
        const std::string& text,
        long long created_at_ms,
        bool pinned = false,
        const std::string& attachment_id = {},
        const std::string& filename = {},
        const std::string& mime_type = {}) {
        transport::SyncedMessage message;
        message.message_id = id;
        message.sender_user_id = sender;
        message.text = text;
        message.created_at_ms = created_at_ms;
        message.pinned = pinned;
        message.attachment_id = attachment_id;
        message.filename = filename;
        message.mime_type = mime_type;
        return message;
    }

    static transport::SyncedConversation gui_smoke_conversation(
        const std::string& id,
        const std::string& title,
        std::vector<std::string> participants,
        std::vector<transport::SyncedMessage> messages,
        int version) {
        transport::SyncedConversation conversation;
        conversation.conversation_id = id;
        conversation.title = title;
        conversation.participant_user_ids = std::move(participants);
        conversation.messages = std::move(messages);
        conversation.version = version;
        if (!conversation.messages.empty()) {
            conversation.read_markers.push_back(transport::ReadMarker {
                "alice",
                conversation.messages.back().message_id,
            });
        }
        return conversation;
    }

    static transport::SyncResult gui_smoke_reference_sync() {
        constexpr long long base_time = 1762261200000LL;
        transport::SyncResult sync;
        sync.ok = true;
        sync.conversations.push_back(gui_smoke_conversation(
            "ref_channel_m_team",
            "M-Team",
            {"alice", "m_team"},
            {
                gui_smoke_message("ref_channel_1", "m_team",
                                  "New internal build is available: https://telegram.org",
                                  base_time, true),
                gui_smoke_message("ref_channel_2", "m_team",
                                  "Release checklist and screenshots are ready.",
                                  base_time + 62000, false,
                                  "att_channel_1", "release.png", "image/png"),
            },
            91));
        sync.conversations.push_back(gui_smoke_conversation(
            "ref_service_telegram",
            "Telegram",
            {"alice", "telegram"},
            {
                gui_smoke_message("ref_service_1", "telegram",
                                  "Login code: 23720. Do not give this code to anyone, even if they say they are from Telegram!\n\n! This code can be used to log in to your Telegram account. We never ask it for anything else.\n\nIf you didn't request this code by trying to log in on another device, simply ignore this message.",
                                  base_time + 310000),
                gui_smoke_message("ref_service_2", "telegram",
                                  "Login code: 69286. Do not give this code to anyone, even if they say they are from Telegram!\n\n! This code can be used to log in to your Telegram account. We never ask it for anything else.\n\nIf you didn't request this code by trying to log in on another device, simply ignore this message.",
                                  base_time + 372000),
            },
            94));
        sync.conversations.push_back(gui_smoke_conversation(
            "ref_user_hello_blake",
            "Hello Blake",
            {"alice", "blake"},
            {
                gui_smoke_message("ref_user_1", "blake",
                                  "Hey, are the Desktop screens ready?",
                                  base_time + 120000),
                gui_smoke_message("ref_user_2", "alice",
                                  "Yes, I am checking the info panel states now.",
                                  base_time + 181000),
            },
            92));
        sync.conversations.push_back(gui_smoke_conversation(
            "ref_group_three",
            QString::fromUtf8("三叉戟").toStdString(),
            {"XZMQ", "Hello Blake", "michael jordan"},
            {
                gui_smoke_message("ref_group_1", "XZMQ",
                                  "[system] You set messages to auto-delete in 1 week",
                                  base_time + 240000),
            },
            93));
        return sync;
    }

    bool capture_gui_smoke_reference_shell_states() {
        logged_in_ = true;
        connecting_ = false;
        has_remembered_login_ = false;
        last_connection_error_.clear();
        if (message_search_ != nullptr) message_search_->clear();
        if (chat_filter_ != nullptr) chat_filter_->clear();
        current_search_index_ = -1;
        store_.set_current_user("alice");
        store_.apply_sync(gui_smoke_reference_sync());

        store_.set_selected_conversation({});
        render_store();
        if (details_panel_ != nullptr) details_panel_->setVisible(false);
        qApp->processEvents();
        if (!save_gui_smoke_capture(this, "main-empty-chat-list", QRect(0, 0, 1391, 1009))) return false;

        if (details_panel_ != nullptr) details_panel_->setVisible(true);
        if (details_stack_ != nullptr) details_stack_->setCurrentIndex(0);
        const std::vector<std::pair<std::string, QString>> states {
            {"ref_channel_m_team", QStringLiteral("info-channel")},
            {"ref_service_telegram", QStringLiteral("service-chat-info")},
            {"ref_user_hello_blake", QStringLiteral("info-user")},
            {"ref_group_three", QStringLiteral("info-group")},
        };
        for (const auto& [conversation_id, screenshot] : states) {
            store_.set_selected_conversation(conversation_id);
            render_store();
            qApp->processEvents();
            if (!save_gui_smoke_capture(this, screenshot)) return false;
        }
        if (details_panel_ != nullptr) details_panel_->setVisible(false);
        const std::vector<std::pair<std::string, QString>> content_states {
            {"ref_service_telegram", QStringLiteral("service-chat")},
            {"ref_channel_m_team", QStringLiteral("channel-pinned-unread")},
            {"ref_group_three", QStringLiteral("group-autodelete-empty")},
        };
        for (const auto& [conversation_id, screenshot] : content_states) {
            store_.set_selected_conversation(conversation_id);
            render_store();
            qApp->processEvents();
            if (!save_gui_smoke_capture(this, screenshot)) return false;
        }
        if (details_panel_ != nullptr) details_panel_->setVisible(true);
        store_.set_selected_conversation("ref_user_hello_blake");
        render_store();
        qApp->processEvents();
        return true;
    }

    void finish_gui_smoke(bool ok, const QString& message) {
        if (ok) {
            std::cout << "desktop gui smoke ok: " << message.toStdString() << "\n";
            QApplication::exit(0);
        } else {
            std::cerr << "desktop gui smoke failed: " << message.toStdString() << "\n";
            QApplication::exit(1);
        }
    }

    void run_gui_interaction_smoke() {
        std::cout << "desktop gui smoke: start\n";
        run_gui_smoke_login_reference_step();
    }

    void run_gui_smoke_login_reference_step() {
        show_login_dialog();
        QTimer::singleShot(220, this, [this] {
            QWidget* login = first_top_level("loginModal");
            if (login == nullptr) {
                finish_gui_smoke(false, "login modal did not open for reference capture");
                return;
            }
            auto* tabs = login->findChild<QTabWidget*>("loginModeTabs");
            if (tabs == nullptr) {
                finish_gui_smoke(false, "login mode tabs missing for reference capture");
                return;
            }
            tabs->setCurrentIndex(0);
            if (!save_gui_smoke_capture(login, "login-welcome")) {
                finish_gui_smoke(false, "login welcome screenshot failed");
                return;
            }
            tabs->setCurrentIndex(2);
            qApp->processEvents();
            if (!save_gui_smoke_capture(login, "login-qr")) {
                finish_gui_smoke(false, "login QR screenshot failed");
                return;
            }
            tabs->setCurrentIndex(1);
            qApp->processEvents();
            if (!save_gui_smoke_capture(login, "login-phone")) {
                finish_gui_smoke(false, "login phone screenshot failed");
                return;
            }
            close_top_levels("loginModal");
            QTimer::singleShot(140, this, [this] {
                if (top_level_count("loginModal") != 0) {
                    finish_gui_smoke(false, "login modal did not close after reference capture");
                    return;
                }
                run_gui_smoke_main_shell_step();
            });
        });
    }

    void run_gui_smoke_main_shell_step() {
        if (!capture_gui_smoke_reference_shell_states()) {
            finish_gui_smoke(false, "reference shell screenshot failed");
            return;
        }
        if (details_panel_ == nullptr || !details_panel_->isVisible()
            || details_stack_ == nullptr || details_stack_->currentIndex() != 0) {
            finish_gui_smoke(false, "right details profile panel is not visible");
            return;
        }
        if (!save_gui_smoke_capture(this, "main-window")) {
            finish_gui_smoke(false, "main window screenshot failed");
            return;
        }
        if (details_toggle_btn_ == nullptr) {
            finish_gui_smoke(false, "right info panel toggle is missing");
            return;
        }
        details_toggle_btn_->click();
        if (details_panel_ == nullptr || details_panel_->isVisible()) {
            finish_gui_smoke(false, "right info panel toggle did not hide the panel");
            return;
        }
        details_toggle_btn_->click();
        if (details_panel_ == nullptr || !details_panel_->isVisible()) {
            finish_gui_smoke(false, "right info panel toggle did not show the panel");
            return;
        }
        run_gui_smoke_side_menu_empty_step();
    }

    void run_gui_smoke_side_menu_empty_step() {
        store_.set_selected_conversation({});
        render_store();
        if (details_panel_ != nullptr) details_panel_->setVisible(false);
        qApp->processEvents();
        if (hamburger_button_ == nullptr) {
            finish_gui_smoke(false, "hamburger button is missing");
            return;
        }
        hamburger_button_->click();
        QTimer::singleShot(260, this, [this] {
            QWidget* drawer = first_top_level("accountDrawer");
            if (drawer == nullptr) {
                finish_gui_smoke(false, "account drawer did not open for empty side-menu capture");
                return;
            }
            if (!save_gui_smoke_drawer_overlay_capture(
                    drawer,
                    "side-menu-empty-scrolled",
                    QRect(0, 0, 1391, 1009))) {
                finish_gui_smoke(false, "side menu empty scrolled screenshot failed");
                return;
            }
            if (!save_gui_smoke_drawer_overlay_capture(
                    drawer,
                    "side-menu-empty-full",
                    QRect(0, 0, 1491, 1009))) {
                finish_gui_smoke(false, "side menu empty full screenshot failed");
                return;
            }
            close_top_levels("accountDrawer");
            QTimer::singleShot(220, this, [this] {
                if (top_level_count("accountDrawer") != 0) {
                    finish_gui_smoke(false, "empty side-menu drawer cannot close");
                    return;
                }
                run_gui_smoke_group_drawer_step();
            });
        });
    }

    void run_gui_smoke_group_drawer_step() {
        store_.set_selected_conversation("ref_group_three");
        render_store();
        if (details_panel_ != nullptr) details_panel_->setVisible(true);
        if (details_stack_ != nullptr) details_stack_->setCurrentIndex(0);
        qApp->processEvents();
        if (hamburger_button_ == nullptr) {
            finish_gui_smoke(false, "hamburger button is missing");
            return;
        }
        hamburger_button_->click();
        QTimer::singleShot(260, this, [this] {
            if (top_level_count("accountDrawer") != 1) {
                finish_gui_smoke(false, "account drawer did not open from hamburger click");
                return;
            }
            if (!save_gui_smoke_capture(first_top_level("accountDrawer"), "account-drawer")) {
                finish_gui_smoke(false, "account drawer screenshot failed");
                return;
            }
            if (!save_gui_smoke_drawer_overlay_capture(first_top_level("accountDrawer"), "side-menu-overlay")) {
                finish_gui_smoke(false, "side menu overlay screenshot failed");
                return;
            }
            this->setFocus();
            QTimer::singleShot(260, this, [this] {
                if (top_level_count("accountDrawer") != 0) {
                    close_top_levels("accountDrawer");
                    QTimer::singleShot(220, this, [this] {
                        if (top_level_count("accountDrawer") != 0) {
                            finish_gui_smoke(false, "account drawer cannot close");
                            return;
                        }
                        run_gui_smoke_settings_step(true);
                    });
                    return;
                }
                run_gui_smoke_settings_step(true);
            });
        });
    }

    void run_gui_smoke_settings_step(bool reopen_drawer) {
        if (reopen_drawer) {
            hamburger_button_->click();
            QTimer::singleShot(220, this, [this] {
                QWidget* drawer = first_top_level("accountDrawer");
                if (drawer == nullptr) {
                    finish_gui_smoke(false, "account drawer did not reopen for settings click");
                    return;
                }
                auto* settings = drawer->findChild<QPushButton*>("drawerSettingsButton");
                if (settings == nullptr) {
                    finish_gui_smoke(false, "drawer settings button is missing");
                    return;
                }
                settings->click();
                run_gui_smoke_settings_step(false);
            });
            return;
        }
        QTimer::singleShot(220, this, [this] {
            if (top_level_count("settingsModal") != 1) {
                finish_gui_smoke(false, "settings modal did not open from drawer settings click");
                return;
            }
            QWidget* settings = first_top_level("settingsModal");
            if (!save_gui_smoke_capture(settings, "settings-modal")) {
                finish_gui_smoke(false, "settings modal screenshot failed");
                return;
            }
            if (!save_gui_smoke_capture(settings, "settings-general")) {
                finish_gui_smoke(false, "settings general screenshot failed");
                return;
            }
            show_proxy_settings_dialog();
            qApp->processEvents();
            QWidget* proxy = first_top_level("proxySettingsModal");
            if (proxy == nullptr) {
                finish_gui_smoke(false, "proxy settings modal did not open");
                return;
            }
            if (!save_gui_smoke_capture(proxy, "proxy-list")) {
                finish_gui_smoke(false, "proxy list screenshot failed");
                return;
            }
            show_proxy_edit_dialog();
            qApp->processEvents();
            QWidget* proxy_edit = first_top_level("proxyEditModal");
            if (proxy_edit == nullptr) {
                finish_gui_smoke(false, "proxy edit modal did not open");
                return;
            }
            if (!save_gui_smoke_capture(proxy_edit, "proxy-edit")) {
                finish_gui_smoke(false, "proxy edit screenshot failed");
                return;
            }
            close_top_levels("proxyEditModal");
            close_top_levels("proxySettingsModal");
            close_top_levels("settingsModal");
            QTimer::singleShot(120, this, [this] {
                if (top_level_count("settingsModal") != 0) {
                    finish_gui_smoke(false, "settings modal did not close");
                    return;
                }
                if (detail_title_label_ == nullptr || detail_title_label_->text().trimmed().isEmpty()) {
                    finish_gui_smoke(false, "right profile title did not render");
                    return;
                }
                run_gui_smoke_modal_reference_step();
            });
        });
    }

    void run_gui_smoke_modal_reference_step() {
        store_.set_selected_conversation("ref_group_three");
        render_store();
        if (details_panel_ != nullptr) details_panel_->setVisible(false);
        qApp->processEvents();
        show_profile_reference_dialog();
        QTimer::singleShot(180, this, [this] {
            QWidget* profile = first_top_level("profileModal");
            if (profile == nullptr) {
                finish_gui_smoke(false, "profile modal did not open");
                return;
            }
            if (!save_gui_smoke_modal_overlay_capture(profile, "profile-modal")) {
                finish_gui_smoke(false, "profile modal screenshot failed");
                return;
            }
            close_top_levels("profileModal");
            QTimer::singleShot(120, this, [this] { run_gui_smoke_create_dialog_step(false); });
        });
    }

    void run_gui_smoke_create_dialog_step(bool channel_mode) {
        show_conversation_create_dialog(channel_mode);
        QTimer::singleShot(180, this, [this, channel_mode] {
            QWidget* dialog = first_top_level(channel_mode ? "newChannelModal" : "newGroupModal");
            if (dialog == nullptr) {
                finish_gui_smoke(false, channel_mode ? "new channel dialog did not open"
                                                     : "new group dialog did not open");
                return;
            }
            const QString shot = channel_mode ? QStringLiteral("new-channel-dialog")
                                             : QStringLiteral("new-group-dialog");
            if (!save_gui_smoke_modal_overlay_capture(dialog, shot)) {
                finish_gui_smoke(false, channel_mode ? "new channel screenshot failed"
                                                     : "new group screenshot failed");
                return;
            }
            close_top_levels(channel_mode ? "newChannelModal" : "newGroupModal");
            QTimer::singleShot(120, this, [this, channel_mode] {
                if (channel_mode) {
                    run_gui_smoke_contacts_dialog_step();
                } else {
                    run_gui_smoke_create_dialog_step(true);
                }
            });
        });
    }

    void run_gui_smoke_contacts_dialog_step() {
        show_contacts_dialog();
        QTimer::singleShot(220, this, [this] {
            QWidget* contacts = first_top_level("contactsModal");
            if (contacts == nullptr) {
                finish_gui_smoke(false, "contacts dialog did not open");
                return;
            }
            if (!save_gui_smoke_modal_overlay_capture(contacts, "contacts-dialog")) {
                finish_gui_smoke(false, "contacts dialog screenshot failed");
                return;
            }
            close_top_levels("contactsModal");
            QTimer::singleShot(120, this, [this] {
                run_gui_smoke_no_network_reference_step();
            });
        });
    }

    void run_gui_smoke_no_network_reference_step() {
        logged_in_ = false;
        connecting_ = false;
        has_remembered_login_ = true;
        last_connection_error_.clear();
        store_.set_selected_conversation({});
        if (message_search_ != nullptr) message_search_->clear();
        if (chat_filter_ != nullptr) chat_filter_->clear();
        if (details_panel_ != nullptr) details_panel_->setVisible(false);
        if (auto* birthday_banner = findChild<QWidget*>("birthdayBanner")) {
            birthday_banner->setVisible(false);
        }
        render_store();
        qApp->processEvents();
        if (!save_gui_smoke_capture(this, "logined-no-network", QRect(0, 0, 1484, 1008))) {
            finish_gui_smoke(false, "logged-in no-network screenshot failed");
            return;
        }
        finish_gui_smoke(true, "drawer open/close, settings modal, right profile panel, reference dialogs, no-network state");
    }

    void update_details_profile_panel() {
        if (detail_title_label_ == nullptr) return;
        const auto* conv = store_.selected_conversation();
        if (conv == nullptr) {
            for (auto* button : detail_action_buttons_) button->setVisible(false);
            if (detail_identity_section_ != nullptr) detail_identity_section_->setVisible(false);
            if (detail_media_section_ != nullptr) detail_media_section_->setVisible(false);
            if (detail_members_section_ != nullptr) detail_members_section_->setVisible(false);
            if (detail_danger_section_ != nullptr) detail_danger_section_->setVisible(false);
            detail_avatar_label_->setPixmap(avatar_pixmap_for("empty", "?", 112));
            detail_title_label_->setText("No chat selected");
            detail_subtitle_label_->setText("Pick a chat from the list");
            detail_link_label_->clear();
            detail_description_label_->clear();
            if (detail_media_list_ != nullptr) {
                detail_media_list_->clear();
                detail_media_list_->setFixedHeight(0);
            }
            if (detail_members_title_ != nullptr) detail_members_title_->clear();
            detail_members_list_->clear();
            return;
        }
        for (auto* button : detail_action_buttons_) button->setVisible(true);
        if (detail_identity_section_ != nullptr) detail_identity_section_->setVisible(true);
        if (detail_media_section_ != nullptr) detail_media_section_->setVisible(true);
        if (detail_members_section_ != nullptr) detail_members_section_->setVisible(true);
        if (detail_danger_section_ != nullptr) detail_danger_section_->setVisible(true);
        const QString title = reference_title_for(conv->conversation_id, conv->title);
        const std::size_t members = conv->participant_user_ids.size();
        const bool is_group = members > 2
            || title.contains(QString::fromUtf8("三叉戟"))
            || conv->conversation_id.find("group") != std::string::npos;
        const bool is_channel = !is_group && (title.contains("channel", Qt::CaseInsensitive)
            || title.contains("team", Qt::CaseInsensitive)
            || title.contains("proxy", Qt::CaseInsensitive));
        detail_avatar_label_->setPixmap(avatar_pixmap_for(conv->conversation_id, title, 112));
        detail_title_label_->setText(title);
        detail_subtitle_label_->setText(reference_subtitle_for(*conv));
        set_detail_action_texts(is_channel, is_group);
        detail_link_label_->setText(is_channel
            ? QString("t.me/%1").arg(title.simplified().replace(' ', '_'))
            : (is_group ? qstr(conv->conversation_id) : QString("@%1").arg(QString(title).remove(' ').toLower())));
        detail_description_label_->setText(is_channel
            ? QString()
            : (is_group ? QString("%1 members").arg(members)
                        : QString()));

        std::size_t attachments = 0;
        std::size_t links = 0;
        std::size_t pinned = 0;
        for (const auto& m : conv->messages) {
            if (!m.attachment_id.empty()) ++attachments;
            if (m.text.find("http://") != std::string::npos || m.text.find("https://") != std::string::npos) ++links;
            if (m.pinned) ++pinned;
        }
        set_detail_media_rows(is_channel, is_group, attachments, links, pinned);

        detail_members_list_->clear();
        if (detail_members_title_ != nullptr) {
            detail_members_title_->setText(is_group ? QString("%1 MEMBERS").arg(std::max<std::size_t>(members, 3))
                : (is_channel ? QStringLiteral("CHANNEL") : QStringLiteral("CONTACT ACTIONS")));
        }
        if (is_group) {
            for (const auto& participant : conv->participant_user_ids) {
                detail_members_list_->addItem(qstr(participant));
            }
        } else if (is_channel) {
            detail_members_list_->addItem(QStringLiteral("Leave channel"));
            detail_members_list_->addItem(QStringLiteral("Report"));
        } else {
            detail_members_list_->addItem(QStringLiteral("Share this contact"));
            detail_members_list_->addItem(QStringLiteral("Edit contact"));
            detail_members_list_->addItem(QStringLiteral("Delete contact"));
        }
    }

    void set_detail_action_texts(bool is_channel, bool is_group) {
        if (detail_action_buttons_.size() < 3) return;
        const QStringList labels = is_group
            ? QStringList{QStringLiteral("Mute"),
                          QStringLiteral("Manage"),
                          QStringLiteral("Leave")}
            : (is_channel
                ? QStringList{QStringLiteral("Unmute"),
                              QStringLiteral("Discuss"),
                              QStringLiteral("Gift")}
                : QStringList{QStringLiteral("Message"),
                              QStringLiteral("Mute"),
                              QStringLiteral("Gift")});
        const QStringList icons = is_group
            ? QStringList{QStringLiteral("mute"), QStringLiteral("settings"), QStringLiteral("leave")}
            : (is_channel
                ? QStringList{QStringLiteral("mute"), QStringLiteral("discuss"), QStringLiteral("gift")}
                : QStringList{QStringLiteral("message"), QStringLiteral("mute"), QStringLiteral("gift")});
        for (int i = 0; i < 3; ++i) {
            auto* button = detail_action_buttons_[static_cast<std::size_t>(i)];
            button->setText(labels.at(i));
            button->setIcon(line_icon(icons.at(i), 28, QColor("#2aabee")));
            button->setIconSize(QSize(28, 28));
        }
    }

    void set_detail_media_rows(
        bool is_channel,
        bool is_group,
        std::size_t attachments,
        std::size_t links,
        std::size_t pinned) {
        if (detail_media_list_ == nullptr) return;
        detail_media_list_->clear();
        auto add_row = [this](const QString& icon_key, const QString& label) {
            auto* item = new QListWidgetItem(line_icon(icon_key, 24, QColor("#7d8790")), label);
            item->setSizeHint(QSize(0, 38));
            detail_media_list_->addItem(item);
        };
        if (is_group) {
            add_row(QStringLiteral("timer"), QStringLiteral("Auto-delete messages: 1 week"));
            add_row(QStringLiteral("members"), QStringLiteral("Add members"));
            add_row(QStringLiteral("pin"), QString("%1 pinned messages").arg(static_cast<int>(pinned)));
        } else if (is_channel) {
            add_row(QStringLiteral("gift"), QStringLiteral("0 gifts"));
            add_row(QStringLiteral("photo"), QString("%1 photos").arg(static_cast<int>(attachments)));
            add_row(QStringLiteral("link"), QString("%1 shared links").arg(static_cast<int>(links)));
            add_row(QStringLiteral("poll"), QStringLiteral("0 polls"));
            add_row(QStringLiteral("channel"), QStringLiteral("0 similar channels"));
        } else {
            add_row(QStringLiteral("photo"), QString("%1 photos").arg(static_cast<int>(attachments)));
            add_row(QStringLiteral("files"), QStringLiteral("0 files"));
            add_row(QStringLiteral("link"), QString("%1 shared links").arg(static_cast<int>(links)));
            add_row(QStringLiteral("voice"), QStringLiteral("0 voice messages"));
            add_row(QStringLiteral("group"), QStringLiteral("0 groups in common"));
        }
        detail_media_list_->setFixedHeight(detail_media_list_->sizeHintForRow(0) * detail_media_list_->count() + 8);
    }

    void update_chat_header() {
        const auto* conversation = store_.selected_conversation();
        if (conversation == nullptr) {
            chat_header_title_->setText(QString());
            chat_header_subtitle_->setText(connecting_ ? QStringLiteral("Connecting...") : QString());
            return;
        }
        const QString title = reference_title_for(conversation->conversation_id, conversation->title);
        chat_header_title_->setText(title);
        chat_header_subtitle_->setText(reference_subtitle_for(*conversation));
    }

    void toggle_details_panel() {
        const bool visible = details_panel_->isVisible();
        details_panel_->setVisible(!visible);
        if (!visible && details_stack_ != nullptr) details_stack_->setCurrentIndex(0);
        toggle_details_->setText(visible ? "Info ▸" : "Info ▾");
    }

    static QColor avatar_color_for(const std::string& seed) {
        // 8 Telegram-style accent colors, picked deterministically from seed.
        static const QColor palette[] = {
            QColor("#e17076"), QColor("#7bc862"), QColor("#65aadd"),
            QColor("#a695e7"), QColor("#ee7aae"), QColor("#6ec9cb"),
            QColor("#faa774"), QColor("#7d8ea0")
        };
        if (seed.empty()) return palette[0];
        unsigned hash = 0;
        for (char c : seed) hash = hash * 31u + static_cast<unsigned char>(c);
        return palette[hash % (sizeof(palette) / sizeof(palette[0]))];
    }

    static QPixmap avatar_pixmap_for(const std::string& seed,
                                     const QString& label,
                                     int side) {
        QString initials;
        const auto qsource = label.trimmed().isEmpty() ? qstr(seed).trimmed() : label.trimmed();
        if (!qsource.isEmpty()) {
            initials += qsource.at(0).toUpper();
            const int space = qsource.indexOf(' ');
            if (space >= 0 && space + 1 < qsource.size()) {
                initials += qsource.at(space + 1).toUpper();
            }
        }
        if (initials.isEmpty()) initials = "?";
        QPixmap pixmap(side, side);
        pixmap.fill(Qt::transparent);
        QPainter painter(&pixmap);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setBrush(avatar_color_for(seed));
        painter.setPen(Qt::NoPen);
        painter.drawEllipse(0, 0, side, side);
        QFont f = painter.font();
        f.setBold(true);
        f.setPointSize(std::max(12, side / 3));
        painter.setFont(f);
        painter.setPen(Qt::white);
        painter.drawText(QRect(0, 0, side, side), Qt::AlignCenter, initials.left(2));
        return pixmap;
    }

    void update_avatar_pixmap(const std::string& user_id, const std::string& display_name) {
        if (avatar_label_ == nullptr) return;
        const std::string& source = display_name.empty() ? user_id : display_name;
        avatar_label_->setPixmap(avatar_pixmap_for(source, qstr(source), 96));
    }

    void update_profile_identity(const std::string& user_id, const std::string& display_name) {
        if (profile_identity_label_ == nullptr) return;
        if (user_id.empty()) {
            profile_identity_label_->setText("Not connected");
            return;
        }
        const auto display = display_name.empty() ? user_id : display_name;
        const QString html = QStringLiteral(
            "<div style='font-size:16px;font-weight:600;color:#0f1419;'>%1</div>"
            "<div style='font-size:12px;color:#7c8a96;'>%2</div>")
            .arg(qstr(display).toHtmlEscaped(),
                 qstr(user_id).toHtmlEscaped());
        profile_identity_label_->setText(html);
    }

    void render_store() {
        const auto focused_id = focused_search_message_id();
        // M138: drive the BubbleListView from the store + theme palette.
        // The previous setHtml(render_selected_timeline_html(...)) path is
        // kept on DesktopChatStore for store_test (which still verifies the
        // HTML renderer) but app_desktop no longer points its main view at
        // it — the bubble delegate paints directly.
        namespace dt = telegram_like::client::app_desktop::design;
        const auto& t = dt::active_theme();
        telegram_like::client::app_desktop::DesktopBubblePalette palette;
        palette.chat_area_bg     = t.chat_area;
        palette.own_bubble       = t.own_bubble_bottom;
        palette.own_bubble_text  = t.own_bubble_text;
        palette.peer_bubble      = t.peer_bubble;
        palette.peer_bubble_text = t.peer_bubble_text;
        palette.primary          = t.primary;
        palette.text_muted       = t.text_muted;
        palette.tick_sent        = t.tick_unread;
        palette.tick_read        = t.tick_read;
        // failed_bubble stays at the default `#ffd7cf` — it's a neutral
        // alarm signal independent of theme so the red shows in both modes.
        messages_->setBubblePalette(palette);
        if (connecting_ || (has_remembered_login_ && !logged_in_)) {
            messages_->setEmptyStateText(QStringLiteral("Select a chat to start messaging"));
        } else if (!logged_in_) {
            messages_->setEmptyStateText(QStringLiteral("Log in to start messaging"));
        } else {
            messages_->setEmptyStateText(QStringLiteral("Select a chat to start messaging"));
        }
        if (connection_notice_ != nullptr && connection_notice_text_ != nullptr) {
            if (connecting_) {
                connection_notice_text_->setText(QStringLiteral("Reconnecting to Telegram-like..."));
                connection_notice_->setVisible(true);
            } else if (!last_connection_error_.isEmpty() && has_remembered_login_ && !logged_in_) {
                connection_notice_text_->setText(
                    QStringLiteral("Waiting for network. %1").arg(last_connection_error_));
                connection_notice_->setVisible(true);
            } else {
                connection_notice_->setVisible(false);
            }
        }
        if (reconnect_indicator_ != nullptr && reconnect_indicator_text_ != nullptr) {
            const bool show_reconnect_indicator = connecting_ || (has_remembered_login_ && !logged_in_);
            reconnect_indicator_->setVisible(show_reconnect_indicator);
            if (show_reconnect_indicator) {
                reconnect_indicator_text_->setText(
                    last_connection_error_.isEmpty()
                        ? QStringLiteral("Loading...")
                        : QStringLiteral("Waiting for network"));
            }
        }
        messages_->setStore(&store_, store_.current_user_id());
        messages_->setSearchHighlight(message_search_->text().trimmed(), qstr(focused_id));
        messages_->setThumbnailCache(thumbnail_cache_);
        messages_->refresh();
        request_thumbnails_for_visible_messages();
        // M140: theme the typing indicator from the same palette so the
        // dots flip to the dark dot color when the user toggles theme.
        if (typing_indicator_ != nullptr) {
            typing_indicator_->setDotColor(QColor(t.text_muted));
            typing_indicator_->setLabelColor(QColor(t.text_muted));
        }
        // M144: refresh the pin bar — show the first (oldest) pinned
        // message in the conversation, hide the bar when nothing is pinned.
        if (pin_bar_ != nullptr) {
            const auto* conv = store_.selected_conversation();
            const telegram_like::client::app_desktop::DesktopMessage* pinned = nullptr;
            if (conv != nullptr) {
                for (const auto& m : conv->messages) {
                    if (m.pinned && !m.deleted) { pinned = &m; break; }
                }
            }
            if (pinned == nullptr) {
                pin_bar_->setVisible(false);
                pin_bar_target_id_.clear();
            } else {
                pin_bar_target_id_ = qstr(pinned->message_id);
                const QString sender = qstr(pinned->sender_user_id);
                const QString snippet = qstr(pinned->text).left(80);
                pin_bar_->setIcon(line_icon("pin", 22, QColor(t.primary)));
                pin_bar_->setIconSize(QSize(22, 22));
                pin_bar_->setText(QStringLiteral(
                    "<b>Pinned by %1</b>  %2")
                    .arg(sender, snippet));
                pin_bar_->setStyleSheet(QString::fromUtf8(
                    "QPushButton#pinBar { text-align:left; padding:6px 12px; "
                    "border:none; border-bottom:1px solid %1; "
                    "background:%2; color:%3; } "
                    "QPushButton#pinBar:hover { background:%4; }")
                    .arg(QString::fromUtf8(t.border_subtle),
                         QString::fromUtf8(t.surface_muted),
                         QString::fromUtf8(t.text_primary),
                         QString::fromUtf8(t.hover)));
                pin_bar_->setVisible(true);
            }
        }
        render_conversation_list();
        render_search_status();
        update_chat_header();
        update_details_profile_panel();
        const auto summary = store_.render_conversation_summary();
        const auto selected = store_.selected_conversation_id();
        std::string status = logged_in_ ? "Connected" : (connecting_ ? "Connecting" : "Disconnected");
        if (!selected.empty()) status += " | selected=" + selected;
        if (!summary.empty()) status += " | " + summary;
        statusBar()->showMessage(qstr(status));
    }

    void render_conversation_list() {
        conversations_->clear();
        if (connecting_ || (has_remembered_login_ && !logged_in_)) {
            auto* item = new QListWidgetItem();
            item->setSizeHint(QSize(360, 82));
            item->setData(ChatTitleRole, QStringLiteral("Loading..."));
            item->setData(ChatSnippetRole, QString());
            item->setData(ChatTimeRole, QString());
            item->setData(ChatUnreadRole, 0);
            item->setData(ChatAvatarSeedRole, QStringLiteral("loading"));
            conversations_->addItem(item);
            return;
        }
        if (!logged_in_) {
            auto* item = new QListWidgetItem();
            item->setSizeHint(QSize(360, 82));
            item->setData(ChatTitleRole, QStringLiteral("Log in to Telegram-like"));
            item->setData(ChatSnippetRole, QStringLiteral("Use the login prompt to connect"));
            item->setData(ChatTimeRole, QString());
            item->setData(ChatUnreadRole, 0);
            item->setData(ChatAvatarSeedRole, QStringLiteral("login"));
            conversations_->addItem(item);
            return;
        }
        const auto selected = store_.selected_conversation_id();
        const auto filter = str(chat_filter_->text().trimmed());
        int selected_row = -1;
        int row = 0;
        for (const auto& conversation : store_.filtered_conversations(filter)) {
            const QString title = reference_title_for(conversation.conversation_id, conversation.title);
            QString snippet = QStringLiteral("No messages yet");
            QString time;
            if (!conversation.messages.empty()) {
                const auto& last = conversation.messages.back();
                const QString sender = qstr(last.sender_user_id);
                const QString text = last.text.empty()
                    ? (last.attachment_id.empty() ? QStringLiteral("Message") : QStringLiteral("Photo"))
                    : qstr(last.text);
                snippet = sender.isEmpty() ? text : sender + QStringLiteral(": ") + text;
                if (last.created_at_ms > 0) {
                    const auto dt = QDateTime::fromMSecsSinceEpoch(last.created_at_ms);
                    const auto now = QDateTime::currentDateTime();
                    time = dt.date() == now.date()
                        ? dt.toString(QStringLiteral("h:mm AP"))
                        : dt.toString(QStringLiteral("M/d/yyyy"));
                }
            } else if (!conversation.last_message_id.empty()) {
                snippet = QStringLiteral("last ") + qstr(conversation.last_message_id);
            }
            auto* item = new QListWidgetItem();
            item->setSizeHint(QSize(360, 82));
            item->setData(ChatTitleRole, title);
            item->setData(ChatSnippetRole, snippet);
            item->setData(ChatTimeRole, time);
            item->setData(ChatUnreadRole, static_cast<int>(conversation.unread_count));
            item->setData(ChatAvatarSeedRole, qstr(conversation.conversation_id));
            item->setData(Qt::UserRole, qstr(conversation.conversation_id));
            conversations_->addItem(item);
            if (conversation.conversation_id == selected) selected_row = row;
            ++row;
        }
        if (selected_row >= 0) {
            conversations_->setCurrentRow(selected_row);
        }
    }

    std::string focused_search_message_id() const {
        const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
        if (results.empty() || current_search_index_ < 0
            || current_search_index_ >= static_cast<int>(results.size())) {
            return {};
        }
        return results[static_cast<std::size_t>(current_search_index_)].message_id;
    }

    bool can_modify_message(const std::string& message_id) const {
        const auto* conversation = store_.selected_conversation();
        if (conversation == nullptr || message_id.empty()) return false;
        for (const auto& message : conversation->messages) {
            if (message.message_id == message_id) {
                return !message.deleted && message.sender_user_id == store_.current_user_id();
            }
        }
        return false;
    }

    void refresh_message_search() {
        const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
        if (results.empty()) {
            current_search_index_ = -1;
        } else if (current_search_index_ < 0 || current_search_index_ >= static_cast<int>(results.size())) {
            current_search_index_ = 0;
        }
        render_store();
    }

    void step_message_search(int delta) {
        const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
        if (results.empty()) {
            current_search_index_ = -1;
            render_store();
            return;
        }
        if (current_search_index_ < 0) current_search_index_ = 0;
        current_search_index_ = (current_search_index_ + delta + static_cast<int>(results.size()))
            % static_cast<int>(results.size());
        const auto& focused = results[static_cast<std::size_t>(current_search_index_)];
        message_action_id_->setText(qstr(focused.message_id));
        render_store();
    }

    void use_focused_message_as_action_target() {
        auto focused = focused_search_message_id();
        if (focused.empty()) {
            const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
            if (!results.empty()) focused = results.front().message_id;
        }
        if (!focused.empty()) {
            message_action_id_->setText(qstr(focused));
            statusBar()->showMessage("Selected message " + qstr(focused));
        }
    }

    void use_latest_message_as_action_target() {
        const auto conversation = str(conversation_->text().trimmed());
        if (conversation.empty()) return;
        const auto latest = store_.last_message_id(conversation);
        if (!latest.empty()) {
            message_action_id_->setText(qstr(latest));
            statusBar()->showMessage("Selected latest message " + qstr(latest));
        }
    }

    void render_search_status() {
        if (!search_status_) return;
        const auto query = str(message_search_->text().trimmed());
        const auto results = store_.search_selected_messages(query);
        if (query.empty()) {
            search_status_->setText("No search");
            return;
        }
        if (results.empty()) {
            search_status_->setText("0 matches");
            return;
        }
        const int visible_index = current_search_index_ < 0 ? 1 : current_search_index_ + 1;
        search_status_->setText(qstr(std::to_string(visible_index) + "/" + std::to_string(results.size())));
    }

    void load_older_history() {
        if (!client_) return;
        const auto conversation_id = str(conversation_->text().trimmed());
        if (conversation_id.empty()) return;
        const auto before = store_.history_next_before_message_id(conversation_id);
        load_older_->setEnabled(false);
        auto client = client_;
        std::thread([this, client, conversation_id, before] {
            const auto page = client->conversation_history_page(conversation_id, before, 25);
            QMetaObject::invokeMethod(this, [this, conversation_id, page] {
                if (shutting_down_) return;
                load_older_->setEnabled(true);
                if (!page.ok) {
                    append_line("[error] history page failed: " + qstr(page.error_code + " " + page.error_message));
                    return;
                }
                store_.apply_history_page(page);
                save_cache();
                render_store();
                statusBar()->showMessage("Loaded older history for " + qstr(conversation_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void search_server_messages() {
        if (!client_) return;
        const auto query = str(message_search_->text().trimmed());
        if (query.empty()) return;
        const auto conversation_id = str(conversation_->text().trimmed());
        server_search_->setEnabled(false);
        auto client = client_;
        std::thread([this, client, query, conversation_id] {
            const auto result = client->search_messages(query, conversation_id, 20, 0);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                server_search_->setEnabled(true);
                render_server_message_search(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void render_server_message_search(const telegram_like::client::transport::MessageSearchResult& result) {
        if (!message_search_results_) return;
        if (!result.ok) {
            message_search_results_->setPlainText("[error] message search failed: " + qstr(result.error_code + " " + result.error_message));
            return;
        }
        QString text;
        for (const auto& entry : result.results) {
            text += qstr(entry.conversation_id + "  " + entry.message_id + "  " + entry.sender_user_id + "\n");
            text += qstr("  " + (entry.conversation_title.empty() ? std::string("(untitled)") : entry.conversation_title) + "\n");
            text += qstr("  " + entry.snippet + "\n");
            if (!entry.filename.empty()) {
                text += qstr("  attachment: " + entry.filename + "\n");
            }
            text += "\n";
        }
        if (text.isEmpty()) text = "(no server matches)";
        if (result.has_more) {
            text += qstr("more results at offset " + std::to_string(result.next_offset) + "\n");
        }
        message_search_results_->setPlainText(text);
        if (!result.results.empty()) {
            const auto& first = result.results.front();
            message_action_id_->setText(qstr(first.message_id));
            if (first.conversation_id != store_.selected_conversation_id()) {
                store_.set_selected_conversation(first.conversation_id);
                conversation_->setText(qstr(first.conversation_id));
                render_store();
            }
        }
    }

    void connect_and_sync() {
        authenticate_and_sync(false);
    }

    void register_and_sync() {
        authenticate_and_sync(true);
    }

    void authenticate_and_sync(bool create_account) {
        connect_->setEnabled(false);
        register_->setEnabled(false);
        send_->setEnabled(false);
        connecting_ = true;
        logged_in_ = false;
        last_connection_error_.clear();
        statusBar()->showMessage(create_account ? "Registering..." : "Connecting...");
        append_line(create_account ? "[system] registering" : "[system] connecting");

        const auto host = str(host_->text());
        const auto port = static_cast<unsigned short>(port_->value());
        const auto use_tls = tls_->isChecked();
        const auto tls_insecure = tls_insecure_->isChecked();
        const auto tls_server_name = args_.tls_server_name;
        const auto user = str(user_->text());
        const auto password = str(password_->text());
        const auto display_name = str(display_name_->text());
        const auto device = str(device_->text());
        const auto selected_conversation = str(conversation_->text());

        store_.set_selected_conversation(selected_conversation);
        load_cache();
        if (selected_conversation.empty()) {
            store_.set_selected_conversation({});
        }
        render_store();
        const auto cursors = store_.sync_cursors();

        std::thread([this, host, port, use_tls, tls_insecure, tls_server_name,
                     user, password, display_name, device, selected_conversation, cursors, create_account] {
            auto next_client = std::make_shared<ControlPlaneClient>();
            const bool connected = use_tls
                ? next_client->connect_tls(host, port, tls_insecure, tls_server_name)
                : next_client->connect(host, port);
            if (!connected) {
                post_error("connect failed");
                return;
            }
            const auto auth = create_account
                ? next_client->register_user(user, password, display_name, device)
                : next_client->login(user, password, device);
            if (!auth.ok) {
                post_error(std::string(create_account ? "register failed: " : "login failed: ")
                           + auth.error_code + " " + auth.error_message);
                return;
            }
            next_client->set_push_handler([this](const std::string& type, const std::string& envelope) {
                QMetaObject::invokeMethod(this, [this, type, envelope] {
                    if (shutting_down_) return;
                    // M147: typing pulses are UI-only; they don't go through
                    // the chat store at all. Parse the envelope, flip the
                    // indicator with the (re)started 5s decay, return.
                    if (type == "typing_pulse") {
                        handle_typing_pulse_push(envelope);
                        return;
                    }
                    store_.apply_push(type, envelope);
                    save_cache();
                    render_store();
                }, Qt::QueuedConnection);
            });
            next_client->start_heartbeat(10000);
            const auto sync = next_client->conversation_sync_since(cursors);
            if (!sync.ok) {
                post_error("sync failed: " + sync.error_code + " " + sync.error_message);
                return;
            }

            QMetaObject::invokeMethod(this, [this, auth, sync, cursors, client = std::move(next_client),
                                             create_account, selected_conversation, host, port, user,
                                             password, display_name, device] {
                if (shutting_down_) return;
                client_ = client;
                connecting_ = false;
                logged_in_ = true;
                last_connection_error_.clear();
                store_.set_current_user(auth.user_id);
                if (cursors.empty()) {
                    store_.apply_sync(sync);
                } else {
                    store_.apply_incremental_sync(sync);
                }
                if (selected_conversation.empty()) {
                    store_.set_selected_conversation({});
                    conversation_->clear();
                }
                QSettings remembered;
                remembered.setValue(QStringLiteral("auth/remembered"), true);
                remembered.setValue(QStringLiteral("auth/host"), qstr(host));
                remembered.setValue(QStringLiteral("auth/port"), port);
                remembered.setValue(QStringLiteral("auth/user"), qstr(user));
                remembered.setValue(QStringLiteral("auth/password"), qstr(password));
                remembered.setValue(QStringLiteral("auth/display_name"), qstr(display_name));
                remembered.setValue(QStringLiteral("auth/device"), qstr(device));
                save_cache();
                render_store();
                if (login_status_) {
                    login_status_->setText(QStringLiteral("Connected."));
                }
                if (login_dialog_) {
                    login_dialog_->accept();
                }
                connect_->setEnabled(true);
                register_->setEnabled(true);
                send_->setEnabled(true);
                attach_->setEnabled(true);
                load_older_->setEnabled(true);
                server_search_->setEnabled(true);
                set_message_action_enabled(true);
                save_attachment_->setEnabled(true);
                set_profile_action_enabled(true);
                refresh_devices_->setEnabled(true);
                set_device_action_enabled(true);
                refresh_contacts_->setEnabled(true);
                set_contact_action_enabled(true);
                set_user_search_enabled(true);
                set_group_action_enabled(true);
                set_remote_action_enabled(true);
                set_call_action_enabled(true);
                set_advanced_action_enabled(true);
                statusBar()->showMessage(qstr(std::string(create_account ? "Registered as " : "Connected as ") + auth.user_id));
                refresh_profile();
                refresh_devices();
                refresh_contacts();
            }, Qt::QueuedConnection);
        }).detach();
    }

    void send_message() {
        if (!client_ || composer_->text().trimmed().isEmpty()) return;
        const auto text = str(composer_->text());
        const auto conversation = str(conversation_->text());
        if (conversation.empty()) {
            statusBar()->showMessage("Select a chat first");
            return;
        }
        const auto local_message_id = store_.add_pending_message(conversation, text);
        composer_->clear();
        save_cache();
        render_store();
        send_->setEnabled(false);

        auto client = client_;
        std::thread([this, client, conversation, text, local_message_id] {
            const auto sent = client->send_message(conversation, text);
            QMetaObject::invokeMethod(this, [this, conversation, local_message_id, sent] {
                if (shutting_down_) return;
                send_->setEnabled(true);
                if (!sent.ok) {
                    store_.fail_pending_message(conversation, local_message_id, sent.error_code + " " + sent.error_message);
                    save_cache();
                    render_store();
                    statusBar()->showMessage("Send failed");
                } else {
                    store_.resolve_pending_message(conversation, local_message_id, sent);
                    if (!sent.attachment_id.empty()) {
                        attachment_id_->setText(qstr(sent.attachment_id));
                    }
                    save_cache();
                    render_store();
                    statusBar()->showMessage("Sent " + qstr(sent.message_id));
                }
            }, Qt::QueuedConnection);
        }).detach();
    }

    void reply_message() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()
            || composer_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto reply_to = str(message_action_id_->text().trimmed());
        const auto text = str(composer_->text());
        const auto local_message_id = store_.add_pending_message(conversation, text);
        composer_->clear();
        save_cache();
        render_store();
        set_message_action_enabled(false);

        auto client = client_;
        std::thread([this, client, conversation, reply_to, text, local_message_id] {
            const auto sent = client->reply_message(conversation, reply_to, text);
            QMetaObject::invokeMethod(this, [this, conversation, local_message_id, sent] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!sent.ok) {
                    store_.fail_pending_message(conversation, local_message_id, sent.error_code + " " + sent.error_message);
                    save_cache();
                    render_store();
                    statusBar()->showMessage("Reply failed");
                    return;
                }
                store_.resolve_pending_message(conversation, local_message_id, sent);
                message_action_id_->setText(qstr(sent.message_id));
                save_cache();
                render_store();
                statusBar()->showMessage("Replied " + qstr(sent.message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void forward_message() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id] {
            const auto sent = client->forward_message(conversation, message_id, conversation);
            QMetaObject::invokeMethod(this, [this, conversation, sent] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!sent.ok) {
                    append_line("[error] forward failed: " + qstr(sent.error_code + " " + sent.error_message));
                    return;
                }
                store_.apply_sent_message(conversation, sent);
                message_action_id_->setText(qstr(sent.message_id));
                save_cache();
                render_store();
                statusBar()->showMessage("Forwarded " + qstr(sent.message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void react_to_message() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()
            || reaction_emoji_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        const auto emoji = str(reaction_emoji_->text().trimmed());
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, emoji] {
            const auto result = client->toggle_reaction(conversation, message_id, emoji);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] reaction failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                store_.apply_reaction_summary(result.conversation_id, result.message_id, result.reaction_summary);
                save_cache();
                render_store();
                statusBar()->showMessage("Reaction updated " + qstr(result.message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void sync_after_server_mutation() {
        if (!client_) return;
        auto client = client_;
        std::thread([this, client] {
            const auto sync = client->conversation_sync();
            QMetaObject::invokeMethod(this, [this, sync] {
                if (shutting_down_) return;
                if (!sync.ok) {
                    append_line("[error] sync failed: " + qstr(sync.error_code + " " + sync.error_message));
                    return;
                }
                store_.apply_sync(sync);
                save_cache();
                render_store();
            }, Qt::QueuedConnection);
        }).detach();
    }

    void pin_message(bool pinned) {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, pinned] {
            const auto result = client->set_message_pin(conversation, message_id, pinned);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] pin failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                store_.apply_pin_state(result.conversation_id, result.message_id, result.pinned);
                save_cache();
                render_store();
                statusBar()->showMessage(result.pinned ? "Pinned" : "Unpinned");
            }, Qt::QueuedConnection);
        }).detach();
    }

    void edit_message_action() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        bool ok = false;
        const QString new_text = QInputDialog::getText(
            this, "Edit message",
            "New text for " + qstr(message_id) + ":",
            QLineEdit::Normal, QString(), &ok);
        if (!ok || new_text.trimmed().isEmpty()) return;
        const auto text = str(new_text);
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, text] {
            const auto result = client->edit_message(conversation, message_id, text);
            QMetaObject::invokeMethod(this, [this, conversation, message_id, text, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] edit failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                // Server fans MESSAGE_EDITED to others; actor must apply locally.
                store_.apply_message_edited(conversation, message_id, text);
                save_cache();
                render_store();
                statusBar()->showMessage("Edited " + qstr(message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void delete_message_action() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        const auto answer = QMessageBox::question(
            this, "Delete message",
            "Delete " + qstr(message_id) + "? This cannot be undone.",
            QMessageBox::Yes | QMessageBox::No, QMessageBox::No);
        if (answer != QMessageBox::Yes) return;
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id] {
            const auto result = client->delete_message(conversation, message_id);
            QMetaObject::invokeMethod(this, [this, conversation, message_id, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] delete failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                store_.apply_message_deleted(conversation, message_id);
                save_cache();
                render_store();
                statusBar()->showMessage("Deleted " + qstr(message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void send_attachment() {
        if (!client_) return;
        const QString path = QFileDialog::getOpenFileName(this, "Attach file");
        if (path.isEmpty()) return;
        set_transfer_progress("Reading attachment", 10);
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) {
            set_transfer_progress("Attachment read failed", 0);
            append_line("[error] attachment open failed");
            return;
        }
        const QByteArray bytes = file.readAll();
        if (bytes.size() > 1'048'576) {
            set_transfer_progress("Attachment too large", 0);
            append_line("[error] attachment too large for current 1 MB cap");
            return;
        }
        const QFileInfo info(path);
        const auto conversation = str(conversation_->text());
        const auto caption = str(composer_->text());
        const auto filename = str(info.fileName());
        const auto mime_type = guess_mime_type(info);
        const std::string content(bytes.constData(), static_cast<std::size_t>(bytes.size()));
        const auto local_message_id = store_.add_pending_attachment_message(
            conversation,
            caption,
            filename,
            mime_type,
            static_cast<long long>(content.size())
        );
        composer_->clear();
        save_cache();
        render_store();
        send_->setEnabled(false);
        attach_->setEnabled(false);
        set_transfer_progress("Uploading " + filename, 35);

        auto client = client_;
        // M126: prefer chunked upload for files > 1 MB so we get byte-level
        // progress updates. Smaller files keep the single-shot path because
        // the per-chunk RPC overhead dominates for tiny payloads.
        constexpr std::size_t kChunkedThreshold = 1u * 1024 * 1024;
        const bool use_chunked = content.size() > kChunkedThreshold;
        std::thread([this, client, conversation, caption, filename, mime_type, content, local_message_id, use_chunked] {
            telegram_like::client::transport::MessageResult sent;
            if (use_chunked) {
                auto progress = [this, total = content.size()](std::size_t bytes_uploaded, std::size_t bytes_total) {
                    const int pct = bytes_total == 0 ? 0
                        : static_cast<int>((bytes_uploaded * 100) / bytes_total);
                    QMetaObject::invokeMethod(this, [this, bytes_uploaded, bytes_total, pct] {
                        if (shutting_down_) return;
                        set_transfer_progress(
                            "Uploading "
                            + std::to_string(bytes_uploaded) + " / " + std::to_string(bytes_total)
                            + " B",
                            pct);
                    }, Qt::QueuedConnection);
                };
                sent = client->send_attachment_chunked(
                    conversation, caption, filename, mime_type, content, progress);
            } else {
                sent = client->send_attachment(
                    conversation, caption, filename, mime_type, content);
            }
            QMetaObject::invokeMethod(this, [this, conversation, local_message_id, sent] {
                if (shutting_down_) return;
                send_->setEnabled(true);
                attach_->setEnabled(true);
                if (!sent.ok) {
                    store_.fail_pending_message(conversation, local_message_id, sent.error_code + " " + sent.error_message);
                    save_cache();
                    render_store();
                    set_transfer_progress("Upload failed", 0);
                    append_line("[error] attachment send failed: " + qstr(sent.error_code + " " + sent.error_message));
                } else {
                    store_.resolve_pending_message(conversation, local_message_id, sent);
                    save_cache();
                    render_store();
                    set_transfer_progress("Uploaded " + sent.filename, 100);
                    statusBar()->showMessage("Attached " + qstr(sent.attachment_id));
                }
            }, Qt::QueuedConnection);
        }).detach();
    }

    void save_attachment() {
        if (!client_) return;
        const auto attachment_id = str(attachment_id_->text().trimmed());
        if (attachment_id.empty()) return;
        const auto conversation_id = str(conversation_->text());
        const auto known_filename = store_.attachment_filename(conversation_id, attachment_id);
        const QString path = QFileDialog::getSaveFileName(
            this,
            "Save attachment",
            qstr(known_filename.empty() ? attachment_id + ".bin" : known_filename)
        );
        if (path.isEmpty()) return;
        save_attachment_->setEnabled(false);
        set_transfer_progress("Downloading " + attachment_id, 35);

        auto client = client_;
        const auto save_path = str(path);
        std::thread([this, client, attachment_id, save_path] {
            const auto fetched = client->fetch_attachment(attachment_id);
            QMetaObject::invokeMethod(this, [this, fetched, save_path] {
                if (shutting_down_) return;
                save_attachment_->setEnabled(true);
                if (!fetched.ok) {
                    set_transfer_progress("Download failed", 0);
                    append_line("[error] attachment fetch failed: " + qstr(fetched.error_code + " " + fetched.error_message));
                    return;
                }
                set_transfer_progress("Saving " + fetched.filename, 75);
                QFile file(qstr(save_path));
                if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                    set_transfer_progress("Save failed", 0);
                    append_line("[error] attachment save failed");
                    return;
                }
                const QByteArray bytes(fetched.content.data(), static_cast<int>(fetched.content.size()));
                if (file.write(bytes) != bytes.size()) {
                    set_transfer_progress("Save incomplete", 0);
                    append_line("[error] attachment write incomplete");
                    return;
                }
                file.close();
                set_transfer_progress("Saved " + fetched.filename, 100);
                statusBar()->showMessage("Saved attachment " + qstr(fetched.attachment_id));
                // M125: real thumbnail preview for image attachments. Decode
                // the bytes into a QPixmap and pop a non-modal dialog so the
                // user immediately sees the image they just downloaded.
                if (fetched.mime_type.rfind("image/", 0) == 0) {
                    QPixmap pixmap;
                    const QByteArray image_bytes(fetched.content.data(), static_cast<int>(fetched.content.size()));
                    if (pixmap.loadFromData(image_bytes)) {
                        auto* preview = new QDialog(this);
                        preview->setAttribute(Qt::WA_DeleteOnClose);
                        preview->setWindowTitle(qstr("Preview — " + fetched.filename));
                        auto* layout = new QVBoxLayout(preview);
                        auto* label = new QLabel();
                        label->setPixmap(pixmap.scaled(560, 560, Qt::KeepAspectRatio, Qt::SmoothTransformation));
                        label->setAlignment(Qt::AlignCenter);
                        layout->addWidget(label);
                        auto* meta = new QLabel(qstr(fetched.filename + "  ·  "
                            + std::to_string(fetched.size_bytes) + " B  ·  " + fetched.mime_type));
                        meta->setObjectName("pageSubtitle");
                        layout->addWidget(meta);
                        preview->resize(600, 640);
                        preview->show();
                    }
                }
            }, Qt::QueuedConnection);
        }).detach();
    }

    void refresh_profile() {
        if (!client_) return;
        set_profile_action_enabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto result = client->profile_get();
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_profile_action_enabled(true);
                if (!result.ok) {
                    profile_->setPlainText("[error] profile load failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_profile(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void save_profile() {
        if (!client_ || profile_display_name_->text().trimmed().isEmpty()) return;
        const auto display_name = str(profile_display_name_->text().trimmed());
        set_profile_action_enabled(false);
        auto client = client_;
        std::thread([this, client, display_name] {
            const auto result = client->profile_update(display_name);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_profile_action_enabled(true);
                if (!result.ok) {
                    profile_->setPlainText("[error] profile save failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_profile(result);
                statusBar()->showMessage("Saved profile for " + qstr(result.user_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void refresh_devices() {
        if (!client_) return;
        refresh_devices_->setEnabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto result = client->list_devices();
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                refresh_devices_->setEnabled(true);
                if (!result.ok) {
                    devices_->setPlainText("[error] device list failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_devices(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void manage_device(DeviceAction action) {
        if (!client_ || device_action_id_->text().trimmed().isEmpty()) return;
        const auto device_id = str(device_action_id_->text().trimmed());
        if (action == DeviceAction::Revoke) {
            const auto answer = QMessageBox::question(
                this,
                "Revoke device",
                "Revoke device " + qstr(device_id) + "?",
                QMessageBox::Yes | QMessageBox::No,
                QMessageBox::No);
            if (answer != QMessageBox::Yes) return;
        }
        set_device_action_enabled(false);
        auto client = client_;
        std::thread([this, client, device_id, action] {
            telegram_like::client::transport::DeviceListResult result;
            if (action == DeviceAction::Revoke) {
                result = client->revoke_device(device_id);
            } else {
                result = client->update_device_trust(device_id, action == DeviceAction::Trust);
            }
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_device_action_enabled(true);
                if (!result.ok) {
                    devices_->setPlainText("[error] device action failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_devices(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void refresh_contacts() {
        if (!client_) return;
        refresh_contacts_->setEnabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto result = client->list_contacts();
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                refresh_contacts_->setEnabled(true);
                if (!result.ok) {
                    contacts_->setPlainText("[error] contact list failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_contacts(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void manage_contact(bool add) {
        if (!client_ || contact_user_id_->text().trimmed().isEmpty()) return;
        const auto user_id = str(contact_user_id_->text().trimmed());
        set_contact_action_enabled(false);
        auto client = client_;
        std::thread([this, client, user_id, add] {
            const auto result = add ? client->add_contact(user_id) : client->remove_contact(user_id);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_contact_action_enabled(true);
                if (!result.ok) {
                    contacts_->setPlainText("[error] contact action failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_contacts(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void search_users() {
        if (!client_ || user_search_query_->text().trimmed().isEmpty()) return;
        const auto query = str(user_search_query_->text().trimmed());
        set_user_search_enabled(false);
        auto client = client_;
        std::thread([this, client, query] {
            const auto result = client->search_users(query, 20);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_user_search_enabled(true);
                if (!result.ok) {
                    user_search_results_->setPlainText("[error] user search failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_user_search(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    std::vector<std::string> parse_user_ids(const QString& raw) const {
        std::vector<std::string> ids;
        for (const auto& part : raw.split(',')) {
            const auto id = str(part.trimmed());
            if (!id.empty()) ids.push_back(id);
        }
        return ids;
    }

    void create_group() {
        if (!client_) return;
        const auto participants = parse_user_ids(group_participants_->text());
        if (participants.empty()) return;
        const auto title = str(group_title_->text().trimmed());
        set_group_action_enabled(false);
        auto client = client_;
        std::thread([this, client, participants, title] {
            const auto result = client->create_conversation(participants, title);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_group_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] group create failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                apply_conversation_action(result);
                statusBar()->showMessage("Created group " + qstr(result.conversation.conversation_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    enum class RemoteOp { Approve, Reject, Cancel, Terminate };
    enum class CallOp { Accept, Decline, End };
    enum class AdvancedChatOp {
        Mute,
        Unmute,
        SaveDraft,
        ClearDraft,
        Pin,
        Unpin,
        Archive,
        Unarchive,
    };

    void append_call_log(const QString& line) {
        if (!call_log_) return;
        call_log_->appendPlainText(line);
    }

    void call_invite_action() {
        if (!client_) return;
        const auto callee_user = str(call_callee_user_->text().trimmed());
        const auto callee_device = str(call_callee_device_->text().trimmed());
        if (callee_user.empty() || callee_device.empty()) {
            append_call_log("[error] callee user_id + device_id required");
            return;
        }
        const auto kind = str(call_kind_->currentText());
        set_call_action_enabled(false);
        auto client = client_;
        std::thread([this, client, callee_user, callee_device, kind] {
            const auto r = client->call_invite(callee_user, callee_device, kind);
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_call_action_enabled(true);
                if (!r.ok) {
                    append_call_log(qstr("[invite error] " + r.error_code + " " + r.error_message));
                    return;
                }
                if (call_id_input_) call_id_input_->setText(qstr(r.call_id));
                append_call_log(qstr("[invite ok] call_id=" + r.call_id + " state=" + r.state));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void call_terminal_action(CallOp op) {
        if (!client_) return;
        const auto cid = str(call_id_input_->text().trimmed());
        if (cid.empty()) { append_call_log("[error] call_id required"); return; }
        set_call_action_enabled(false);
        auto client = client_;
        std::thread([this, client, cid, op] {
            telegram_like::client::transport::CallStateResult r;
            std::string verb;
            switch (op) {
                case CallOp::Accept:  verb = "accept";  r = client->call_accept(cid);  break;
                case CallOp::Decline: verb = "decline"; r = client->call_decline(cid); break;
                case CallOp::End:     verb = "end";     r = client->call_end(cid);     break;
            }
            QMetaObject::invokeMethod(this, [this, verb, r] {
                if (shutting_down_) return;
                set_call_action_enabled(true);
                if (!r.ok) {
                    append_call_log(qstr("[" + verb + " error] " + r.error_code + " " + r.error_message));
                    return;
                }
                append_call_log(qstr("[" + verb + " ok] state=" + r.state
                                     + (r.detail.empty() ? std::string() : " " + r.detail)));
            }, Qt::QueuedConnection);
        }).detach();
    }


    void append_remote_log(const QString& line) {
        if (!remote_log_) return;
        remote_log_->appendPlainText(line);
    }

    void remote_invite_action() {
        if (!client_) return;
        const auto target_device = str(remote_target_device_->text().trimmed());
        if (target_device.empty()) {
            append_remote_log("[error] target device_id is required");
            return;
        }
        const auto requester_device = str(device_->text().trimmed());
        if (requester_device.empty()) {
            append_remote_log("[error] requester device_id (Connection > Device) is required");
            return;
        }
        set_remote_action_enabled(false);
        auto client = client_;
        std::thread([this, client, requester_device, target_device] {
            const auto result = client->remote_invite(requester_device, target_device);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_remote_action_enabled(true);
                if (!result.ok) {
                    append_remote_log(qstr(
                        "[invite error] " + result.error_code + " " + result.error_message));
                    return;
                }
                if (remote_session_id_input_) {
                    remote_session_id_input_->setText(qstr(result.remote_session_id));
                }
                append_remote_log(qstr(
                    "[invite ok] remote_session_id=" + result.remote_session_id
                    + " state=" + result.state));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void remote_terminal_action(RemoteOp op) {
        if (!client_) return;
        const auto rs_id = str(remote_session_id_input_->text().trimmed());
        if (rs_id.empty()) {
            append_remote_log("[error] remote_session_id is required");
            return;
        }
        set_remote_action_enabled(false);
        auto client = client_;
        std::thread([this, client, rs_id, op] {
            std::string verb;
            std::string state;
            std::string detail;
            std::string error_code;
            std::string error_message;
            bool ok = false;
            switch (op) {
                case RemoteOp::Approve: {
                    verb = "approve";
                    auto r = client->remote_approve(rs_id);
                    ok = r.ok;
                    state = r.state;
                    error_code = r.error_code;
                    error_message = r.error_message;
                    if (ok) {
                        detail = "relay=" + r.relay_endpoint + " region=" + r.relay_region;
                    }
                    break;
                }
                case RemoteOp::Reject: {
                    verb = "reject";
                    auto r = client->remote_reject(rs_id);
                    ok = r.ok; state = r.state; detail = r.detail;
                    error_code = r.error_code; error_message = r.error_message;
                    break;
                }
                case RemoteOp::Cancel: {
                    verb = "cancel";
                    auto r = client->remote_cancel(rs_id);
                    ok = r.ok; state = r.state; detail = r.detail;
                    error_code = r.error_code; error_message = r.error_message;
                    break;
                }
                case RemoteOp::Terminate: {
                    verb = "terminate";
                    auto r = client->remote_terminate(rs_id);
                    ok = r.ok; state = r.state; detail = r.detail;
                    error_code = r.error_code; error_message = r.error_message;
                    break;
                }
            }
            QMetaObject::invokeMethod(this, [this, verb, ok, state, detail, error_code, error_message] {
                if (shutting_down_) return;
                set_remote_action_enabled(true);
                if (!ok) {
                    append_remote_log(qstr("[" + verb + " error] " + error_code + " " + error_message));
                    return;
                }
                append_remote_log(qstr("[" + verb + " ok] state=" + state
                                       + (detail.empty() ? std::string() : " " + detail)));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void remote_rendezvous_action() {
        if (!client_) return;
        const auto rs_id = str(remote_session_id_input_->text().trimmed());
        if (rs_id.empty()) {
            append_remote_log("[error] remote_session_id is required");
            return;
        }
        set_remote_action_enabled(false);
        auto client = client_;
        std::thread([this, client, rs_id] {
            const auto r = client->remote_rendezvous_request(rs_id);
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_remote_action_enabled(true);
                if (!r.ok) {
                    append_remote_log(qstr(
                        "[rendezvous error] " + r.error_code + " " + r.error_message));
                    return;
                }
                std::string summary = "[rendezvous ok] state=" + r.state
                    + " region=" + r.relay_region
                    + " relay=" + r.relay_endpoint
                    + " key=" + (r.relay_key_b64.empty() ? "(none)" : "(set)")
                    + " candidates=" + std::to_string(r.candidates.size());
                append_remote_log(qstr(summary));
                for (const auto& c : r.candidates) {
                    append_remote_log(qstr(
                        "  " + c.kind + " " + c.address + ":" + std::to_string(c.port)
                        + " prio=" + std::to_string(c.priority)));
                }
            }, Qt::QueuedConnection);
        }).detach();
    }

    void append_advanced_log(const QString& line) {
        if (advanced_log_) advanced_log_->appendPlainText(line);
    }

    std::string selected_conversation_id() const {
        return str(conversation_->text().trimmed());
    }

    static std::vector<std::string> split_csv_options(const QString& text) {
        std::vector<std::string> options;
        for (const auto& part : text.split(',', Qt::SkipEmptyParts)) {
            const auto trimmed = part.trimmed();
            if (!trimmed.isEmpty()) options.push_back(str(trimmed));
        }
        return options;
    }

    void run_advanced_ack(std::string label, std::function<telegram_like::client::transport::AckResult()> fn) {
        if (!client_) return;
        set_advanced_action_enabled(false);
        std::thread([this, label = std::move(label), fn = std::move(fn)] {
            const auto r = fn();
            QMetaObject::invokeMethod(this, [this, label, r] {
                if (shutting_down_) return;
                set_advanced_action_enabled(true);
                if (!r.ok) {
                    append_advanced_log(qstr("[" + label + " error] " + r.error_code + " " + r.error_message));
                    return;
                }
                append_advanced_log(qstr("[" + label + " ok]"));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void advanced_phone_request_action() {
        if (!client_) return;
        const auto phone = str(advanced_target_user_->text().trimmed());
        if (phone.empty()) { append_advanced_log("[error] phone number required"); return; }
        auto client = client_;
        run_advanced_ack("phone otp request", [client, phone] {
            return client->phone_otp_request(phone);
        });
    }

    void advanced_phone_verify_action() {
        if (!client_) return;
        const auto phone = str(advanced_target_user_->text().trimmed());
        const auto code = str(advanced_code_->text().trimmed());
        const auto device_id = str(device_->text().trimmed());
        const auto display_name = str(display_name_->text().trimmed());
        if (phone.empty() || code.empty() || device_id.empty()) {
            append_advanced_log("[error] phone, code and device_id required");
            return;
        }
        set_advanced_action_enabled(false);
        auto client = client_;
        std::thread([this, client, phone, code, device_id, display_name] {
            const auto r = client->phone_otp_verify(phone, code, device_id, display_name);
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_advanced_action_enabled(true);
                if (!r.ok) {
                    append_advanced_log(qstr("[phone otp verify error] " + r.error_code + " " + r.error_message));
                    return;
                }
                store_.set_current_user(r.user_id);
                append_advanced_log(qstr("[phone otp verify ok] user_id=" + r.user_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void advanced_twofa_begin_action() {
        if (!client_) return;
        set_advanced_action_enabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto r = client->two_fa_begin_enable();
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_advanced_action_enabled(true);
                if (!r.ok) {
                    append_advanced_log(qstr("[2fa begin error] " + r.error_code + " " + r.error_message));
                    return;
                }
                append_advanced_log(qstr("[2fa begin ok] secret=" + r.secret));
                append_advanced_log(qstr(r.provisioning_uri));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void advanced_twofa_code_action(bool confirm) {
        if (!client_) return;
        const auto code = str(advanced_code_->text().trimmed());
        if (code.empty()) { append_advanced_log("[error] 2FA code required"); return; }
        auto client = client_;
        run_advanced_ack(confirm ? "2fa confirm" : "2fa disable", [client, code, confirm] {
            return confirm ? client->two_fa_confirm_enable(code) : client->two_fa_disable(code);
        });
    }

    void advanced_export_action() {
        if (!client_) return;
        set_advanced_action_enabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto r = client->account_export();
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_advanced_action_enabled(true);
                if (!r.ok) {
                    append_advanced_log(qstr("[account export error] " + r.error_code + " " + r.error_message));
                    return;
                }
                append_advanced_log(qstr("[account export ok] user_id=" + r.user_id
                    + " devices=" + std::to_string(r.devices)
                    + " sessions=" + std::to_string(r.sessions)
                    + " contacts=" + std::to_string(r.contacts)
                    + " messages=" + std::to_string(r.authored_messages)));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void advanced_delete_action() {
        if (!client_) return;
        const auto password = str(advanced_password_->text());
        const auto two_fa = str(advanced_code_->text().trimmed());
        if (password.empty()) { append_advanced_log("[error] password required for account delete"); return; }
        auto client = client_;
        run_advanced_ack("account delete", [client, password, two_fa] {
            return client->account_delete(password, two_fa);
        });
    }

    void advanced_block_action(bool block) {
        if (!client_) return;
        const auto user_id = str(advanced_target_user_->text().trimmed());
        if (user_id.empty()) { append_advanced_log("[error] target user_id required"); return; }
        auto client = client_;
        run_advanced_ack(block ? "block" : "unblock", [client, user_id, block] {
            return block ? client->block_user(user_id) : client->unblock_user(user_id);
        });
    }

    void advanced_chat_ack_action(AdvancedChatOp op) {
        if (!client_) return;
        const auto conversation = selected_conversation_id();
        if (conversation.empty()) { append_advanced_log("[error] selected conversation required"); return; }
        const auto draft = str(advanced_draft_->text());
        auto client = client_;
        run_advanced_ack("chat action", [client, conversation, draft, op] {
            switch (op) {
                case AdvancedChatOp::Mute: return client->set_conversation_mute(conversation, -1);
                case AdvancedChatOp::Unmute: return client->set_conversation_mute(conversation, 0);
                case AdvancedChatOp::SaveDraft: return client->save_draft(conversation, draft);
                case AdvancedChatOp::ClearDraft: return client->clear_draft(conversation);
                case AdvancedChatOp::Pin: return client->set_conversation_pinned(conversation, true);
                case AdvancedChatOp::Unpin: return client->set_conversation_pinned(conversation, false);
                case AdvancedChatOp::Archive: return client->set_conversation_archived(conversation, true);
                case AdvancedChatOp::Unarchive: return client->set_conversation_archived(conversation, false);
            }
            return telegram_like::client::transport::AckResult{};
        });
    }

    void advanced_avatar_action(bool conversation_avatar) {
        if (!client_) return;
        const auto attachment_id = str(advanced_avatar_id_->text().trimmed());
        const auto conversation = selected_conversation_id();
        if (conversation_avatar && conversation.empty()) {
            append_advanced_log("[error] selected conversation required");
            return;
        }
        auto client = client_;
        run_advanced_ack(conversation_avatar ? "chat avatar" : "profile avatar",
            [client, conversation, attachment_id, conversation_avatar] {
                return conversation_avatar
                    ? client->update_conversation_avatar(conversation, attachment_id)
                    : client->update_profile_avatar(attachment_id);
            });
    }

    void advanced_poll_create_action() {
        if (!client_) return;
        const auto conversation = selected_conversation_id();
        const auto question = str(advanced_poll_question_->text().trimmed());
        const auto options = split_csv_options(advanced_poll_options_->text());
        const bool multi = advanced_poll_multi_->isChecked();
        if (conversation.empty() || question.empty() || options.size() < 2) {
            append_advanced_log("[error] conversation, question and at least two options required");
            return;
        }
        set_advanced_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, question, options, multi] {
            const auto r = client->create_poll(conversation, question, options, multi);
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_advanced_action_enabled(true);
                if (!r.ok) {
                    append_advanced_log(qstr("[poll create error] " + r.error_code + " " + r.error_message));
                    return;
                }
                if (advanced_poll_message_id_) advanced_poll_message_id_->setText(qstr(r.message_id));
                append_advanced_log(qstr("[poll create ok] message_id=" + r.message_id));
                sync_after_server_mutation();
            }, Qt::QueuedConnection);
        }).detach();
    }

    void advanced_poll_action(bool vote) {
        if (!client_) return;
        const auto conversation = selected_conversation_id();
        const auto message_id = str(advanced_poll_message_id_->text().trimmed());
        if (conversation.empty() || message_id.empty()) {
            append_advanced_log("[error] conversation and poll message_id required");
            return;
        }
        set_advanced_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, vote] {
            const auto r = vote
                ? client->vote_poll(conversation, message_id, std::vector<int>{0})
                : client->close_poll(conversation, message_id);
            QMetaObject::invokeMethod(this, [this, r, vote] {
                if (shutting_down_) return;
                set_advanced_action_enabled(true);
                if (!r.ok) {
                    append_advanced_log(qstr(std::string(vote ? "[poll vote error] " : "[poll close error] ")
                        + r.error_code + " " + r.error_message));
                    return;
                }
                append_advanced_log(qstr(std::string(vote ? "[poll vote ok] " : "[poll close ok] ")
                    + "closed=" + (r.closed ? "true" : "false")));
                sync_after_server_mutation();
            }, Qt::QueuedConnection);
        }).detach();
    }

    void manage_group_member(bool add) {
        if (!client_ || member_user_id_->text().trimmed().isEmpty()) return;
        const auto selected = str(conversation_->text().trimmed());
        if (selected.empty()) return;
        const auto user_id = str(member_user_id_->text().trimmed());
        set_group_action_enabled(false);
        auto client = client_;
        std::thread([this, client, selected, user_id, add] {
            const auto result = add
                ? client->add_conversation_participant(selected, user_id)
                : client->remove_conversation_participant(selected, user_id);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_group_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] group member update failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                apply_conversation_action(result);
                statusBar()->showMessage("Updated group " + qstr(result.conversation.conversation_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void apply_conversation_action(const telegram_like::client::transport::ConversationActionResult& result) {
        telegram_like::client::transport::SyncResult sync;
        sync.ok = true;
        sync.conversations.push_back(result.conversation);
        store_.apply_incremental_sync(sync);
        store_.set_selected_conversation(result.conversation.conversation_id);
        conversation_->setText(qstr(result.conversation.conversation_id));
        save_cache();
        render_store();
    }

    void render_devices(const telegram_like::client::transport::DeviceListResult& result) {
        QString text;
        for (const auto& device : result.devices) {
            text += qstr(device.device_id + "  " + device.label + "  " + device.platform);
            text += device.active ? "  online" : "  offline";
            text += device.trusted ? "  trusted" : "  untrusted";
            text += "\n";
        }
        if (text.isEmpty()) text = "(no devices)";
        devices_->setPlainText(text);
    }

    void render_profile(const telegram_like::client::transport::ProfileResult& result) {
        profile_display_name_->setText(qstr(result.display_name));
        profile_->setPlainText(qstr(
            result.user_id + "  @" + result.username + "\n"
            + "display: " + result.display_name
        ));
        update_avatar_pixmap(result.user_id, result.display_name);
        update_profile_identity(result.user_id, result.display_name);
    }

    void render_contacts(const telegram_like::client::transport::ContactListResult& result) {
        QString text;
        for (const auto& contact : result.contacts) {
            text += qstr(contact.user_id + "  " + contact.display_name);
            text += contact.online ? "  online" : "  offline";
            text += "\n";
        }
        if (text.isEmpty()) text = "(no contacts)";
        contacts_->setPlainText(text);
    }

    void render_user_search(const telegram_like::client::transport::UserSearchResult& result) {
        QString text;
        for (const auto& user : result.results) {
            text += qstr(user.user_id + "  @" + user.username + "  " + user.display_name);
            text += user.online ? "  online" : "  offline";
            text += user.is_contact ? "  contact" : "  not-contact";
            text += "\n";
        }
        if (text.isEmpty()) text = "(no users found)";
        user_search_results_->setPlainText(text);
    }

    void set_device_action_enabled(bool enabled) {
        if (revoke_device_) revoke_device_->setEnabled(enabled);
        if (trust_device_) trust_device_->setEnabled(enabled);
        if (untrust_device_) untrust_device_->setEnabled(enabled);
    }

    void set_contact_action_enabled(bool enabled) {
        if (add_contact_) add_contact_->setEnabled(enabled);
        if (remove_contact_) remove_contact_->setEnabled(enabled);
    }

    void set_profile_action_enabled(bool enabled) {
        if (refresh_profile_) refresh_profile_->setEnabled(enabled);
        if (save_profile_) save_profile_->setEnabled(enabled);
    }

    void set_user_search_enabled(bool enabled) {
        if (search_users_) search_users_->setEnabled(enabled);
    }

    void set_group_action_enabled(bool enabled) {
        if (create_group_) create_group_->setEnabled(enabled);
        if (add_member_) add_member_->setEnabled(enabled);
        if (remove_member_) remove_member_->setEnabled(enabled);
    }

    void set_remote_action_enabled(bool enabled) {
        if (remote_invite_) remote_invite_->setEnabled(enabled);
        if (remote_approve_) remote_approve_->setEnabled(enabled);
        if (remote_reject_) remote_reject_->setEnabled(enabled);
        if (remote_cancel_) remote_cancel_->setEnabled(enabled);
        if (remote_terminate_) remote_terminate_->setEnabled(enabled);
        if (remote_rendezvous_) remote_rendezvous_->setEnabled(enabled);
    }

    void set_call_action_enabled(bool enabled) {
        if (call_invite_) call_invite_->setEnabled(enabled);
        if (call_accept_) call_accept_->setEnabled(enabled);
        if (call_decline_) call_decline_->setEnabled(enabled);
        if (call_end_) call_end_->setEnabled(enabled);
    }

    void set_advanced_action_enabled(bool enabled) {
        const std::array<QPushButton*, 24> buttons = {
            advanced_phone_request_, advanced_phone_verify_, advanced_twofa_begin_,
            advanced_twofa_confirm_, advanced_twofa_disable_, advanced_export_,
            advanced_delete_, advanced_block_, advanced_unblock_, advanced_mute_,
            advanced_unmute_, advanced_save_draft_, advanced_clear_draft_,
            advanced_pin_chat_, advanced_unpin_chat_, advanced_archive_chat_,
            advanced_unarchive_chat_, advanced_profile_avatar_, advanced_chat_avatar_,
            advanced_poll_create_, advanced_poll_vote_, advanced_poll_close_,
            nullptr, nullptr,
        };
        for (auto* button : buttons) {
            if (button) button->setEnabled(enabled);
        }
    }

    void set_message_action_enabled(bool enabled) {
        if (reply_) reply_->setEnabled(enabled);
        if (forward_) forward_->setEnabled(enabled);
        if (react_) react_->setEnabled(enabled);
        if (pin_) pin_->setEnabled(enabled);
        if (unpin_) unpin_->setEnabled(enabled);
        if (edit_) edit_->setEnabled(enabled);
        if (delete_) delete_->setEnabled(enabled);
        if (use_match_) use_match_->setEnabled(enabled);
        if (use_latest_) use_latest_->setEnabled(enabled);
    }

    void set_transfer_progress(const std::string& label, int percent) {
        if (transfer_status_) transfer_status_->setText(qstr(label));
        if (transfer_progress_) transfer_progress_->setValue(percent);
    }

    void post_error(std::string message) {
        QMetaObject::invokeMethod(this, [this, message = std::move(message)] {
            if (shutting_down_) return;
            append_line("[error] " + qstr(message));
            connecting_ = false;
            logged_in_ = false;
            last_connection_error_ = qstr("Connection failed: " + message);
            connect_->setEnabled(true);
            register_->setEnabled(true);
            send_->setEnabled(client_ != nullptr);
            attach_->setEnabled(client_ != nullptr);
            load_older_->setEnabled(client_ != nullptr);
            server_search_->setEnabled(client_ != nullptr);
            set_message_action_enabled(client_ != nullptr);
            save_attachment_->setEnabled(client_ != nullptr);
            set_profile_action_enabled(client_ != nullptr);
            refresh_devices_->setEnabled(client_ != nullptr);
            set_device_action_enabled(client_ != nullptr);
            refresh_contacts_->setEnabled(client_ != nullptr);
            set_contact_action_enabled(client_ != nullptr);
            set_user_search_enabled(client_ != nullptr);
            set_group_action_enabled(client_ != nullptr);
            set_advanced_action_enabled(client_ != nullptr);
            if (login_status_) {
                login_status_->setText(qstr("Connection failed: " + message));
            }
            if (login_submit_) login_submit_->setEnabled(true);
            if (login_register_) login_register_->setEnabled(true);
            render_store();
            statusBar()->showMessage(qstr("Connection failed: " + message));
        }, Qt::QueuedConnection);
    }

    void load_cache() {
        if (args_.cache_file.empty()) return;
        std::string error;
        if (!store_.load_from_file(args_.cache_file, &error)) {
            if (error != "open_for_read_failed") {
                append_line("[cache] load failed: " + qstr(error));
            }
            return;
        }
        store_.set_selected_conversation(str(conversation_->text()));
    }

    void save_cache() {
        if (args_.cache_file.empty()) return;
        std::string error;
        if (!store_.save_to_file(args_.cache_file, &error)) {
            append_line("[cache] save failed: " + qstr(error));
        }
    }

    Args args_;
    bool has_remembered_login_ {false};
    bool connecting_ {false};
    bool logged_in_ {false};
    QString last_connection_error_;
    QPointer<QDialog> login_dialog_;
    QPointer<QLabel> login_status_;
    QPointer<QPushButton> login_submit_;
    QPointer<QPushButton> login_register_;
    QLineEdit* host_ {nullptr};
    QSpinBox* port_ {nullptr};
    QCheckBox* tls_ {nullptr};
    QCheckBox* tls_insecure_ {nullptr};
    QLineEdit* conversation_ {nullptr};
    QLineEdit* user_ {nullptr};
    QLineEdit* password_ {nullptr};
    QLineEdit* display_name_ {nullptr};
    QLineEdit* device_ {nullptr};
    QPushButton* connect_ {nullptr};
    QPushButton* register_ {nullptr};
    // M139: Appearance page light/dark radios. Toggling either re-applies
    // the QApplication stylesheet + bubble palette and persists the
    // choice in QSettings.
    QRadioButton* appearance_light_ {nullptr};
    QRadioButton* appearance_dark_ {nullptr};
    QLineEdit* chat_filter_ {nullptr};
    QWidget* search_row_wrap_ {nullptr};
    QLineEdit* message_search_ {nullptr};
    QPushButton* prev_match_ {nullptr};
    QPushButton* next_match_ {nullptr};
    QPushButton* load_older_ {nullptr};
    QPushButton* server_search_ {nullptr};
    QLabel* search_status_ {nullptr};
    QPlainTextEdit* message_search_results_ {nullptr};
    QWidget* connection_notice_ {nullptr};
    QLabel* connection_notice_text_ {nullptr};
    QWidget* reconnect_indicator_ {nullptr};
    QLabel* reconnect_indicator_text_ {nullptr};
    QLineEdit* profile_display_name_ {nullptr};
    QPushButton* refresh_profile_ {nullptr};
    QPushButton* save_profile_ {nullptr};
    QPlainTextEdit* profile_ {nullptr};
    QListWidget* conversations_ {nullptr};
    telegram_like::client::app_desktop::BubbleListView* messages_ {nullptr};
    telegram_like::client::app_desktop::TypingIndicator* typing_indicator_ {nullptr};
    // M144: top strip showing the most-recently pinned message snippet;
    // click jumps to the message in the bubble view.
    QPushButton* pin_bar_ {nullptr};
    QString pin_bar_target_id_;
    // M145: chat info dialog trigger; the dialog itself is constructed
    // on-demand so the QListWidget contents stay in sync with the latest
    // store snapshot.
    QToolButton* chat_info_btn_ {nullptr};
    QToolButton* details_toggle_btn_ {nullptr};
    // M147: client-side TYPING_PULSE state. last_typing_sent_ms_ debounces
    // outgoing pulses to ~one every 2s while the composer is non-empty;
    // typing_decay_timer_ clears the local indicator 5s after the most
    // recent inbound pulse so a missed STOP doesn't leave the dots
    // spinning forever.
    qint64 last_typing_sent_ms_ {0};
    QTimer* typing_decay_timer_ {nullptr};
    // M148: image thumbnail cache keyed by attachment_id. Populated lazily
    // by request_thumbnails_for_visible_messages — render_store iterates
    // image attachments and kicks a worker per cache miss; on success the
    // bytes get decoded into a QPixmap and BubbleListView::setThumbnailCache
    // refreshes. Sized cap is enforced at decode time (240×240).
    QHash<QString, QPixmap> thumbnail_cache_;
    QSet<QString> thumbnail_inflight_;
    QLineEdit* composer_ {nullptr};
    QPushButton* attach_ {nullptr};
    QPushButton* emoji_panel_ {nullptr};
    QLineEdit* message_action_id_ {nullptr};
    QLineEdit* reaction_emoji_ {nullptr};
    QPushButton* reply_ {nullptr};
    QPushButton* forward_ {nullptr};
    QPushButton* react_ {nullptr};
    QPushButton* pin_ {nullptr};
    QPushButton* unpin_ {nullptr};
    QPushButton* edit_ {nullptr};
    QPushButton* delete_ {nullptr};
    QPushButton* use_match_ {nullptr};
    QPushButton* use_latest_ {nullptr};
    QLineEdit* attachment_id_ {nullptr};
    QPushButton* save_attachment_ {nullptr};
    QLabel* transfer_status_ {nullptr};
    QProgressBar* transfer_progress_ {nullptr};
    QPushButton* send_ {nullptr};
    QPushButton* refresh_devices_ {nullptr};
    QPlainTextEdit* devices_ {nullptr};
    QLineEdit* device_action_id_ {nullptr};
    QPushButton* revoke_device_ {nullptr};
    QPushButton* trust_device_ {nullptr};
    QPushButton* untrust_device_ {nullptr};
    QPushButton* refresh_contacts_ {nullptr};
    QPlainTextEdit* contacts_ {nullptr};
    QLineEdit* contact_user_id_ {nullptr};
    QPushButton* add_contact_ {nullptr};
    QPushButton* remove_contact_ {nullptr};
    QLineEdit* user_search_query_ {nullptr};
    QPushButton* search_users_ {nullptr};
    QPlainTextEdit* user_search_results_ {nullptr};
    QLineEdit* group_title_ {nullptr};
    QLineEdit* group_participants_ {nullptr};
    QPushButton* create_group_ {nullptr};
    QLineEdit* member_user_id_ {nullptr};
    QPushButton* add_member_ {nullptr};
    QPushButton* remove_member_ {nullptr};
    QLabel* chat_header_title_ {nullptr};
    QLabel* chat_header_subtitle_ {nullptr};
    QToolButton* hamburger_button_ {nullptr};
    QWidget* sidebar_panel_ {nullptr};
    QPointer<QDialog> account_drawer_;
    QScrollArea* details_panel_ {nullptr};
    QStackedWidget* details_stack_ {nullptr};
    QLabel* detail_avatar_label_ {nullptr};
    QLabel* detail_title_label_ {nullptr};
    QLabel* detail_subtitle_label_ {nullptr};
    QLabel* detail_link_label_ {nullptr};
    QLabel* detail_description_label_ {nullptr};
    QWidget* detail_identity_section_ {nullptr};
    QWidget* detail_media_section_ {nullptr};
    QTabWidget* detail_media_tabs_ {nullptr};
    QListWidget* detail_media_list_ {nullptr};
    QWidget* detail_members_section_ {nullptr};
    QLabel* detail_members_title_ {nullptr};
    QListWidget* detail_members_list_ {nullptr};
    QWidget* detail_danger_section_ {nullptr};
    std::vector<QToolButton*> detail_action_buttons_;
    QPushButton* toggle_details_ {nullptr};
    QListWidget* settings_nav_ {nullptr};
    QStackedWidget* settings_pages_ {nullptr};
    QLabel* avatar_label_ {nullptr};
    QLabel* profile_identity_label_ {nullptr};
    // M108: remote-control widgets
    QLineEdit* remote_target_device_ {nullptr};
    QPushButton* remote_invite_ {nullptr};
    QLineEdit* remote_session_id_input_ {nullptr};
    QPushButton* remote_approve_ {nullptr};
    QPushButton* remote_reject_ {nullptr};
    QPushButton* remote_cancel_ {nullptr};
    QPushButton* remote_terminate_ {nullptr};
    QPushButton* remote_rendezvous_ {nullptr};
    QPlainTextEdit* remote_log_ {nullptr};
    // M128: voice/video call widgets
    QLineEdit* call_callee_user_ {nullptr};
    QLineEdit* call_callee_device_ {nullptr};
    QComboBox* call_kind_ {nullptr};
    QLineEdit* call_id_input_ {nullptr};
    QPushButton* call_invite_ {nullptr};
    QPushButton* call_accept_ {nullptr};
    QPushButton* call_decline_ {nullptr};
    QPushButton* call_end_ {nullptr};
    QPlainTextEdit* call_log_ {nullptr};
    // RC-005: advanced server-backed wrappers
    QLineEdit* advanced_target_user_ {nullptr};
    QLineEdit* advanced_code_ {nullptr};
    QLineEdit* advanced_password_ {nullptr};
    QLineEdit* advanced_draft_ {nullptr};
    QLineEdit* advanced_avatar_id_ {nullptr};
    QLineEdit* advanced_poll_question_ {nullptr};
    QLineEdit* advanced_poll_options_ {nullptr};
    QLineEdit* advanced_poll_message_id_ {nullptr};
    QCheckBox* advanced_poll_multi_ {nullptr};
    QPushButton* advanced_phone_request_ {nullptr};
    QPushButton* advanced_phone_verify_ {nullptr};
    QPushButton* advanced_twofa_begin_ {nullptr};
    QPushButton* advanced_twofa_confirm_ {nullptr};
    QPushButton* advanced_twofa_disable_ {nullptr};
    QPushButton* advanced_export_ {nullptr};
    QPushButton* advanced_delete_ {nullptr};
    QPushButton* advanced_block_ {nullptr};
    QPushButton* advanced_unblock_ {nullptr};
    QPushButton* advanced_mute_ {nullptr};
    QPushButton* advanced_unmute_ {nullptr};
    QPushButton* advanced_save_draft_ {nullptr};
    QPushButton* advanced_clear_draft_ {nullptr};
    QPushButton* advanced_pin_chat_ {nullptr};
    QPushButton* advanced_unpin_chat_ {nullptr};
    QPushButton* advanced_archive_chat_ {nullptr};
    QPushButton* advanced_unarchive_chat_ {nullptr};
    QPushButton* advanced_profile_avatar_ {nullptr};
    QPushButton* advanced_chat_avatar_ {nullptr};
    QPushButton* advanced_poll_create_ {nullptr};
    QPushButton* advanced_poll_vote_ {nullptr};
    QPushButton* advanced_poll_close_ {nullptr};
    QPlainTextEdit* advanced_log_ {nullptr};
    std::shared_ptr<ControlPlaneClient> client_;
    telegram_like::client::app_desktop::DesktopChatStore store_;
    int current_search_index_ {-1};
    std::atomic<bool> shutting_down_ {false};
};

}  // namespace

int main(int argc, char** argv) {
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: app_desktop [--smoke] [--user alice] [--password alice_pw] "
                     "[--display-name Alice] [--device dev_alice_qt] [--host 127.0.0.1] [--port 8787] "
                     "[--conversation conv_alice_bob] [--cache-file path]\n";
        return 2;
    }

    if (args.smoke) {
        return run_smoke(args);
    }

    QApplication app(argc, argv);
    QApplication::setOrganizationName(QStringLiteral("Telegram-like"));
    QApplication::setApplicationName(QStringLiteral("app_desktop"));
    // M139: load the persisted Appearance choice BEFORE the window
    // constructor so the first stylesheet pass picks up the saved theme
    // (env var still wins for the very first run when the setting is
    // absent — see active_theme()'s lazy init).
    {
        QSettings prefs;
        if (prefs.contains(QStringLiteral("appearance/dark_theme"))) {
            telegram_like::client::app_desktop::design::set_active_theme(
                prefs.value(QStringLiteral("appearance/dark_theme")).toBool());
        }
    }
    DesktopWindow window(args);
    window.show();
    return app.exec();
}

#include "app_mobile/mobile_chat_bridge.h"

#include <QByteArray>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QString>
#include <QUrl>
#include <QtQml/qqmlextensionplugin.h>

namespace {
// M136: dark-mode resolver — same TELEGRAM_LIKE_THEME=dark contract as the
// Qt Widgets desktop client. Done in C++ because QML/JS can't read process
// env vars directly. Pushed into the engine as a context property so
// Main.qml's Theme can pick it up at construction.
bool resolve_dark_mode_from_env() {
    const QByteArray raw = qgetenv("TELEGRAM_LIKE_THEME");
    return QString::fromLocal8Bit(raw).trimmed().compare(QStringLiteral("dark"),
                                                          Qt::CaseInsensitive) == 0;
}
}  // namespace

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QQmlApplicationEngine engine;
    MobileChatBridge bridge;
    engine.rootContext()->setContextProperty("ChatBridge", &bridge);
    engine.rootContext()->setContextProperty(
        "themeDarkMode", QVariant(resolve_dark_mode_from_env()));
    // QQmlApplicationEngine::loadFromModule is Qt 6.5+. We use the QRC URL
    // form so the binary builds against Ubuntu's Qt 6.4 too — qt_add_qml_module
    // registers the QML files under /qt/qml/<URI>/ regardless of Qt version.
#if QT_VERSION >= QT_VERSION_CHECK(6, 5, 0)
    engine.loadFromModule("TelegramLikeMobile", "Main");
#else
    engine.load(QUrl("qrc:/qt/qml/TelegramLikeMobile/Main.qml"));
#endif
    if (engine.rootObjects().isEmpty()) {
        return -1;
    }
    return app.exec();
}

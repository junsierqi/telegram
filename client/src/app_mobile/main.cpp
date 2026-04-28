#include "app_mobile/mobile_chat_bridge.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>
#include <QtQml/qqmlextensionplugin.h>

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QQmlApplicationEngine engine;
    MobileChatBridge bridge;
    engine.rootContext()->setContextProperty("ChatBridge", &bridge);
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

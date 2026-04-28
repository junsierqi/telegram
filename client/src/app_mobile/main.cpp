#include "app_mobile/mobile_chat_bridge.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QtQml/qqmlextensionplugin.h>

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QQmlApplicationEngine engine;
    MobileChatBridge bridge;
    engine.rootContext()->setContextProperty("ChatBridge", &bridge);
    engine.loadFromModule("TelegramLikeMobile", "Main");
    if (engine.rootObjects().isEmpty()) {
        return -1;
    }
    return app.exec();
}

add_library(chat_client_core STATIC
    app/application.cpp
    app/app_shell.cpp
    app_desktop/desktop_chat_store.cpp
    remote_control/remote_session_controller.cpp
    net/socket_error.cpp
    net/socket_subsystem.cpp
    net/tcp_line_client.cpp
    transport/control_plane_client.cpp
    transport/json_value.cpp
    transport/request_messages.cpp
    transport/response_messages.cpp
    transport/session_gateway_client.cpp
    transport/udp_media_probe.cpp
    transport/udp_frame_stream.cpp
)

target_include_directories(chat_client_core
    PUBLIC
        ${PROJECT_SOURCE_DIR}/client/src
        ${PROJECT_SOURCE_DIR}/shared/include
)

target_compile_features(chat_client_core PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(chat_client_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(chat_client_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(telegram_like_client
    main.cpp
)

target_link_libraries(telegram_like_client
    PRIVATE
        chat_client_core
)

add_executable(app_chat
    app_chat/main.cpp
)

target_link_libraries(app_chat
    PRIVATE
        chat_client_core
)

find_package(Qt6 QUIET COMPONENTS Widgets Quick QuickControls2 Qml)
if(Qt6_FOUND)
    # Apple platform detection. Qt's iOS toolchain (qt-cmake from a Qt-for-iOS
    # install) sets the IOS variable directly, but a hand-rolled toolchain
    # may only set CMAKE_SYSTEM_NAME=iOS. Accept either so we don't depend
    # on a specific toolchain wrapper. The local TELEGRAM_LIKE_TARGET_IS_IOS
    # boolean is what every Apple guard below switches on.
    set(TELEGRAM_LIKE_TARGET_IS_IOS FALSE)
    if(APPLE)
        if(CMAKE_SYSTEM_NAME STREQUAL "iOS" OR IOS)
            set(TELEGRAM_LIKE_TARGET_IS_IOS TRUE)
        endif()
    endif()
    # qt_add_executable is the modern Qt 6 API that knows how to package the
    # binary differently per platform (plain .exe on Windows, .so wrapped in
    # an APK on Android). Falls back to add_executable on older Qt builds.
    if(COMMAND qt_add_executable)
        qt_add_executable(app_desktop
            app_desktop/main.cpp
        )
    else()
        add_executable(app_desktop
            app_desktop/main.cpp
        )
    endif()

    target_link_libraries(app_desktop
        PRIVATE
            chat_client_core
            Qt6::Widgets
    )

    # Android-specific packaging: point at deploy/android/ so the
    # AndroidManifest.xml lives where Qt for Android expects.
    if(ANDROID)
        set_target_properties(app_desktop PROPERTIES
            QT_ANDROID_PACKAGE_SOURCE_DIR
                "${PROJECT_SOURCE_DIR}/deploy/android"
            QT_ANDROID_MIN_SDK_VERSION 26
            QT_ANDROID_TARGET_SDK_VERSION 33
            QT_ANDROID_VERSION_NAME "0.1.0-dev"
            QT_ANDROID_VERSION_CODE 1
        )
    endif()

    # macOS .app bundle properties — only fires on real macOS, not iOS.
    # Strictly additive: existing target sources / link libraries / Android
    # / Windows blocks above stay untouched. `APPLE AND NOT IOS` is the
    # canonical CMake test for "macOS host build".
    if(APPLE AND NOT TELEGRAM_LIKE_TARGET_IS_IOS)
        set_target_properties(app_desktop PROPERTIES
            MACOSX_BUNDLE TRUE
            MACOSX_BUNDLE_BUNDLE_NAME "Telegram-like"
            MACOSX_BUNDLE_GUI_IDENTIFIER "com.example.telegramlike.desktop"
            MACOSX_BUNDLE_BUNDLE_VERSION "0.1.0-dev"
            MACOSX_BUNDLE_SHORT_VERSION_STRING "0.1.0"
            MACOSX_BUNDLE_COPYRIGHT "Telegram-like Project"
            MACOSX_BUNDLE_INFO_PLIST "${PROJECT_SOURCE_DIR}/deploy/macos/Info.plist.in"
        )
    endif()

    if(MSVC)
        target_compile_options(app_desktop PRIVATE /W4 /permissive-)
    else()
        target_compile_options(app_desktop PRIVATE -Wall -Wextra -Wpedantic)
    endif()

    # Deploy Qt runtime DLLs + platform plugins next to app_desktop.exe so
    # double-click launch works without Qt being on PATH. Disabled with
    # -DTELEGRAM_LIKE_SKIP_WINDEPLOYQT=ON for environments that ship via
    # scripts/package_windows_desktop.ps1 instead.
    if(WIN32 AND NOT TELEGRAM_LIKE_SKIP_WINDEPLOYQT)
        find_program(TELEGRAM_LIKE_WINDEPLOYQT windeployqt
            HINTS "${Qt6_DIR}/../../../bin"
                  "${Qt6_DIR}/../../bin"
        )
        if(TELEGRAM_LIKE_WINDEPLOYQT)
            # windeployqt auto-detects debug vs release from the binary's CRT
            # markers, so we don't pass --debug/--release here — passing the
            # wrong flag set would copy mismatched Qt DLLs.
            add_custom_command(TARGET app_desktop POST_BUILD
                COMMAND "${TELEGRAM_LIKE_WINDEPLOYQT}"
                        --no-translations
                        --no-system-d3d-compiler
                        --no-opengl-sw
                        "$<TARGET_FILE:app_desktop>"
                COMMENT "Deploying Qt runtime next to app_desktop.exe via windeployqt"
                VERBATIM
            )
        else()
            message(STATUS "windeployqt not found; double-click launch will require Qt bin on PATH")
        endif()
    endif()

    # ---- app_mobile (Qt Quick / QML, phone-shaped UI) ----
    if(TARGET Qt6::Quick AND TARGET Qt6::QuickControls2)
        qt_add_executable(app_mobile
            app_mobile/main.cpp
            app_mobile/mobile_chat_bridge.cpp
            app_mobile/mobile_chat_bridge.h
        )
        # AUTOMOC is required for the Q_OBJECT / QML_ELEMENT / Q_INVOKABLE
        # plumbing in mobile_chat_bridge.h; CMake's qt6_extract_metatypes
        # explicitly errors if it's off.
        set_target_properties(app_mobile PROPERTIES
            AUTOMOC ON
            AUTORCC ON
        )
        # qt_policy was added in Qt 6.5. Older Qt (e.g. Ubuntu 24.04 ships 6.4.2)
        # falls back to the default ':/qt/qml/' resource prefix without it.
        if(COMMAND qt_policy)
            qt_policy(SET QTP0001 NEW)
        endif()
        qt_add_qml_module(app_mobile
            URI TelegramLikeMobile
            VERSION 1.0
            QML_FILES
                app_mobile/qml/Main.qml
                app_mobile/qml/LoginPage.qml
                app_mobile/qml/ChatListPage.qml
                app_mobile/qml/ChatPage.qml
        )
        target_link_libraries(app_mobile
            PRIVATE
                chat_client_core
                Qt6::Qml
                Qt6::Quick
                Qt6::QuickControls2
        )
        target_include_directories(app_mobile PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}
            ${CMAKE_CURRENT_SOURCE_DIR}/app_mobile  # so the qmltyperegistrations.cpp autogen finds <mobile_chat_bridge.h>
        )

        if(ANDROID)
            set_target_properties(app_mobile PROPERTIES
                QT_ANDROID_PACKAGE_SOURCE_DIR
                    "${PROJECT_SOURCE_DIR}/deploy/android"
                QT_ANDROID_MIN_SDK_VERSION 26
                QT_ANDROID_TARGET_SDK_VERSION 33
                QT_ANDROID_VERSION_NAME "0.1.0-dev"
                QT_ANDROID_VERSION_CODE 1
            )
        endif()

        # macOS .app for app_mobile (Qt Quick runs as a desktop preview on macOS).
        if(APPLE AND NOT TELEGRAM_LIKE_TARGET_IS_IOS)
            set_target_properties(app_mobile PROPERTIES
                MACOSX_BUNDLE TRUE
                MACOSX_BUNDLE_BUNDLE_NAME "Telegram-like Mobile"
                MACOSX_BUNDLE_GUI_IDENTIFIER "com.example.telegramlike.mobile"
                MACOSX_BUNDLE_BUNDLE_VERSION "0.1.0-dev"
                MACOSX_BUNDLE_SHORT_VERSION_STRING "0.1.0"
                MACOSX_BUNDLE_COPYRIGHT "Telegram-like Project"
                MACOSX_BUNDLE_INFO_PLIST "${PROJECT_SOURCE_DIR}/deploy/macos/Info.plist.in"
            )
        endif()

        # iOS .app bundle. Generated via -G Xcode on macOS using qt-cmake
        # from the Qt-for-iOS install (see deploy/ios/README.md). Block is
        # gated on the local boolean so non-Apple / macOS-only builds never
        # see it regardless of which toolchain wrapper drove configure.
        if(TELEGRAM_LIKE_TARGET_IS_IOS)
            set_target_properties(app_mobile PROPERTIES
                MACOSX_BUNDLE TRUE
                MACOSX_BUNDLE_BUNDLE_NAME "Telegram-like"
                MACOSX_BUNDLE_GUI_IDENTIFIER "com.example.telegramlike.mobile"
                MACOSX_BUNDLE_BUNDLE_VERSION "0.1.0-dev"
                MACOSX_BUNDLE_SHORT_VERSION_STRING "0.1.0"
                MACOSX_BUNDLE_INFO_PLIST "${PROJECT_SOURCE_DIR}/deploy/ios/Info.plist.in"
                XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
                XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "com.example.telegramlike.mobile"
            )
        endif()

        if(WIN32 AND NOT TELEGRAM_LIKE_SKIP_WINDEPLOYQT AND TELEGRAM_LIKE_WINDEPLOYQT)
            add_custom_command(TARGET app_mobile POST_BUILD
                COMMAND "${TELEGRAM_LIKE_WINDEPLOYQT}"
                        --no-translations
                        --no-system-d3d-compiler
                        --no-opengl-sw
                        --qmldir "${CMAKE_CURRENT_SOURCE_DIR}/app_mobile/qml"
                        "$<TARGET_FILE:app_mobile>"
                COMMENT "Deploying Qt Quick runtime next to app_mobile.exe"
                VERBATIM
            )
        endif()
    else()
        message(STATUS "Qt6 Quick / QuickControls2 not found; app_mobile target disabled")
    endif()
else()
    message(STATUS "Qt6 Widgets not found; app_desktop target disabled")
endif()

add_executable(app_desktop_store_test
    app_desktop/store_test.cpp
)

target_link_libraries(app_desktop_store_test
    PRIVATE
        chat_client_core
)

add_executable(json_parser_test
    transport/json_parser_test.cpp
)

target_link_libraries(json_parser_test
    PRIVATE
        chat_client_core
)

add_executable(remote_session_smoke
    remote_control/remote_session_smoke.cpp
)

target_link_libraries(remote_session_smoke
    PRIVATE
        chat_client_core
)

find_package(Threads REQUIRED)
target_link_libraries(chat_client_core PUBLIC Threads::Threads)

if(WIN32)
    target_link_libraries(chat_client_core PUBLIC ws2_32 secur32)
endif()

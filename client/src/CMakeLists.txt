add_library(chat_client_core STATIC
    app/application.cpp
    app/app_shell.cpp
    app_desktop/desktop_chat_store.cpp
    auth/auth_controller.cpp
    chat/chat_controller.cpp
    contacts/contact_controller.cpp
    devices/device_controller.cpp
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

find_package(Qt6 QUIET COMPONENTS Widgets)
if(Qt6_FOUND)
    add_executable(app_desktop
        app_desktop/main.cpp
    )

    target_link_libraries(app_desktop
        PRIVATE
            chat_client_core
            Qt6::Widgets
    )

    if(MSVC)
        target_compile_options(app_desktop PRIVATE /W4 /permissive-)
    else()
        target_compile_options(app_desktop PRIVATE -Wall -Wextra -Wpedantic)
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

find_package(Threads REQUIRED)
target_link_libraries(chat_client_core PUBLIC Threads::Threads)

if(WIN32)
    target_link_libraries(chat_client_core PUBLIC ws2_32)
endif()

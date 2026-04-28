#include "transport/json_value.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

using telegram_like::client::transport::JsonObject;
using telegram_like::client::transport::JsonParser;
using telegram_like::client::transport::JsonValue;
using telegram_like::client::transport::find_member;

namespace {

int g_pass = 0;
int g_fail = 0;

void check_string(const std::string& name, const std::string& json, const std::string& expected) {
    JsonValue value;
    JsonParser parser {json};
    if (!parser.parse(value) || !value.is_object()) {
        std::cerr << "[FAIL] " << name << ": parse failed for " << json << "\n";
        ++g_fail;
        return;
    }
    const JsonValue* member = find_member(*value.as_object(), "v");
    if (member == nullptr || !member->is_string()) {
        std::cerr << "[FAIL] " << name << ": missing string member 'v'\n";
        ++g_fail;
        return;
    }
    const std::string& got = *member->as_string();
    if (got != expected) {
        std::cerr << "[FAIL] " << name << ": expected " << expected.size()
                  << " bytes, got " << got.size() << " bytes\n";
        ++g_fail;
        return;
    }
    std::cout << "[ok ] " << name << "\n";
    ++g_pass;
}

}  // namespace

int main() {
    // ASCII baseline.
    check_string("ascii", R"({"v":"hello"})", "hello");

    // CJK direct UTF-8 (matches ensure_ascii=False server output).
    check_string("cjk_direct", "{\"v\":\"\xe4\xbd\xa0\xe5\xa5\xbd\"}",
                 std::string("\xe4\xbd\xa0\xe5\xa5\xbd", 6));

    // BMP \u escape (legacy ensure_ascii=True clients/servers must also work).
    check_string("u_escape_bmp", R"({"v":"\u4f60\u597d"})",
                 std::string("\xe4\xbd\xa0\xe5\xa5\xbd", 6));

    // Mixed escapes.
    check_string("u_escape_mixed", R"({"v":"a\u00e9b"})",
                 std::string("a\xc3\xa9" "b", 4));

    // ASCII range \u escape (e.g. \u0041 = 'A').
    check_string("u_escape_ascii", R"({"v":"\u0041"})", "A");

    // Surrogate pair: U+1F600 GRINNING FACE = \uD83D\uDE00.
    check_string("u_escape_surrogate", R"({"v":"\ud83d\ude00"})",
                 std::string("\xf0\x9f\x98\x80", 4));

    // Other newly supported escapes.
    check_string("escape_b_f", R"({"v":"a\bb\fc"})", std::string("a\bb\fc", 5));

    // Negative case: unpaired high surrogate must fail to parse.
    {
        JsonValue value;
        JsonParser parser {std::string{R"({"v":"\ud83d"})"}};
        if (parser.parse(value)) {
            std::cerr << "[FAIL] unpaired_high_surrogate parsed but should have failed\n";
            ++g_fail;
        } else {
            std::cout << "[ok ] unpaired_high_surrogate rejected\n";
            ++g_pass;
        }
    }

    // Negative case: unpaired low surrogate.
    {
        JsonValue value;
        JsonParser parser {std::string{R"({"v":"\udc00"})"}};
        if (parser.parse(value)) {
            std::cerr << "[FAIL] unpaired_low_surrogate parsed but should have failed\n";
            ++g_fail;
        } else {
            std::cout << "[ok ] unpaired_low_surrogate rejected\n";
            ++g_pass;
        }
    }

    std::cout << "passed " << g_pass << "/" << (g_pass + g_fail) << "\n";
    return g_fail == 0 ? 0 : 1;
}

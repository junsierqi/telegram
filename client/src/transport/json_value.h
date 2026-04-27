#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <unordered_map>
#include <variant>
#include <vector>

namespace telegram_like::client::transport {

struct JsonValue;

using JsonObject = std::unordered_map<std::string, JsonValue>;
using JsonArray = std::vector<JsonValue>;

struct JsonValue {
    using Storage = std::variant<std::nullptr_t, bool, double, std::string, JsonArray, JsonObject>;

    Storage storage;

    [[nodiscard]] bool is_object() const;
    [[nodiscard]] bool is_array() const;
    [[nodiscard]] bool is_string() const;
    [[nodiscard]] const JsonObject* as_object() const;
    [[nodiscard]] const JsonArray* as_array() const;
    [[nodiscard]] const std::string* as_string() const;
};

class JsonParser {
public:
    explicit JsonParser(std::string_view text);

    [[nodiscard]] bool parse(JsonValue& value);

private:
    [[nodiscard]] bool parse_value(JsonValue& value);
    [[nodiscard]] bool parse_object(JsonValue& value);
    [[nodiscard]] bool parse_array(JsonValue& value);
    [[nodiscard]] bool parse_string(std::string& value);
    [[nodiscard]] bool parse_number(JsonValue& value);
    [[nodiscard]] bool parse_literal(JsonValue& value,
                                     std::string_view literal,
                                     JsonValue::Storage storage);
    void skip_whitespace();
    [[nodiscard]] bool consume(char ch);
    [[nodiscard]] bool eof() const;
    [[nodiscard]] char peek() const;

    std::string_view text_;
    std::size_t pos_ {0};
};

[[nodiscard]] const JsonValue* find_member(const JsonObject& object, std::string_view key);
[[nodiscard]] std::string string_or_empty(const JsonObject& object, std::string_view key);
[[nodiscard]] std::size_t array_size(const JsonObject& object, std::string_view key);

}  // namespace telegram_like::client::transport

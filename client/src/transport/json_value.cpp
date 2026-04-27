#include "transport/json_value.h"

#include <cctype>
#include <cstdlib>

namespace telegram_like::client::transport {

bool JsonValue::is_object() const {
    return std::holds_alternative<JsonObject>(storage);
}

bool JsonValue::is_array() const {
    return std::holds_alternative<JsonArray>(storage);
}

bool JsonValue::is_string() const {
    return std::holds_alternative<std::string>(storage);
}

const JsonObject* JsonValue::as_object() const {
    return std::get_if<JsonObject>(&storage);
}

const JsonArray* JsonValue::as_array() const {
    return std::get_if<JsonArray>(&storage);
}

const std::string* JsonValue::as_string() const {
    return std::get_if<std::string>(&storage);
}

JsonParser::JsonParser(std::string_view text) : text_(text) {}

bool JsonParser::parse(JsonValue& value) {
    skip_whitespace();
    if (!parse_value(value)) {
        return false;
    }
    skip_whitespace();
    return eof();
}

bool JsonParser::parse_value(JsonValue& value) {
    skip_whitespace();
    if (eof()) {
        return false;
    }

    switch (peek()) {
    case '{':
        return parse_object(value);
    case '[':
        return parse_array(value);
    case '"': {
        std::string string_value;
        if (!parse_string(string_value)) {
            return false;
        }
        value.storage = std::move(string_value);
        return true;
    }
    case 't':
        return parse_literal(value, "true", true);
    case 'f':
        return parse_literal(value, "false", false);
    case 'n':
        return parse_literal(value, "null", nullptr);
    default:
        return parse_number(value);
    }
}

bool JsonParser::parse_object(JsonValue& value) {
    if (!consume('{')) {
        return false;
    }

    JsonObject object;
    skip_whitespace();
    if (consume('}')) {
        value.storage = std::move(object);
        return true;
    }

    while (true) {
        std::string key;
        if (!parse_string(key)) {
            return false;
        }
        skip_whitespace();
        if (!consume(':')) {
            return false;
        }
        JsonValue member_value;
        if (!parse_value(member_value)) {
            return false;
        }
        object.emplace(std::move(key), std::move(member_value));
        skip_whitespace();
        if (consume('}')) {
            value.storage = std::move(object);
            return true;
        }
        if (!consume(',')) {
            return false;
        }
        skip_whitespace();
    }
}

bool JsonParser::parse_array(JsonValue& value) {
    if (!consume('[')) {
        return false;
    }

    JsonArray array;
    skip_whitespace();
    if (consume(']')) {
        value.storage = std::move(array);
        return true;
    }

    while (true) {
        JsonValue item;
        if (!parse_value(item)) {
            return false;
        }
        array.push_back(std::move(item));
        skip_whitespace();
        if (consume(']')) {
            value.storage = std::move(array);
            return true;
        }
        if (!consume(',')) {
            return false;
        }
        skip_whitespace();
    }
}

bool JsonParser::parse_string(std::string& value) {
    if (!consume('"')) {
        return false;
    }

    value.clear();
    while (!eof()) {
        const char ch = text_[pos_++];
        if (ch == '"') {
            return true;
        }
        if (ch == '\\') {
            if (eof()) {
                return false;
            }
            const char escaped = text_[pos_++];
            switch (escaped) {
            case '"':
            case '\\':
            case '/':
                value += escaped;
                break;
            case 'n':
                value += '\n';
                break;
            case 'r':
                value += '\r';
                break;
            case 't':
                value += '\t';
                break;
            default:
                return false;
            }
            continue;
        }
        value += ch;
    }
    return false;
}

bool JsonParser::parse_number(JsonValue& value) {
    const std::size_t start = pos_;
    if (peek() == '-') {
        ++pos_;
    }
    while (!eof() && std::isdigit(static_cast<unsigned char>(peek()))) {
        ++pos_;
    }
    if (!eof() && peek() == '.') {
        ++pos_;
        while (!eof() && std::isdigit(static_cast<unsigned char>(peek()))) {
            ++pos_;
        }
    }

    const auto number_text = text_.substr(start, pos_ - start);
    char* parse_end = nullptr;
    const std::string buffer {number_text};
    const double parsed = std::strtod(buffer.c_str(), &parse_end);
    if (parse_end != buffer.c_str() + buffer.size()) {
        return false;
    }

    value.storage = parsed;
    return true;
}

bool JsonParser::parse_literal(JsonValue& value,
                               const std::string_view literal,
                               JsonValue::Storage storage) {
    if (text_.substr(pos_, literal.size()) != literal) {
        return false;
    }
    pos_ += literal.size();
    value.storage = std::move(storage);
    return true;
}

void JsonParser::skip_whitespace() {
    while (!eof() && std::isspace(static_cast<unsigned char>(text_[pos_]))) {
        ++pos_;
    }
}

bool JsonParser::consume(const char ch) {
    skip_whitespace();
    if (eof() || text_[pos_] != ch) {
        return false;
    }
    ++pos_;
    return true;
}

bool JsonParser::eof() const {
    return pos_ >= text_.size();
}

char JsonParser::peek() const {
    return text_[pos_];
}

const JsonValue* find_member(const JsonObject& object, const std::string_view key) {
    const auto it = object.find(std::string(key));
    return it == object.end() ? nullptr : &it->second;
}

std::string string_or_empty(const JsonObject& object, const std::string_view key) {
    const auto* value = find_member(object, key);
    if (value == nullptr) {
        return {};
    }
    const auto* string_value = value->as_string();
    return string_value == nullptr ? std::string {} : *string_value;
}

std::size_t array_size(const JsonObject& object, const std::string_view key) {
    const auto* value = find_member(object, key);
    if (value == nullptr) {
        return 0;
    }
    const auto* array = value->as_array();
    return array == nullptr ? 0 : array->size();
}

}  // namespace telegram_like::client::transport

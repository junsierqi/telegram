"""Static checks for the Linux desktop build path (M89).

Runs locally + in CI to make sure the scaffolding stays coherent. Doesn't
attempt the actual Qt build — that's the linux-desktop CI job's job.

  1. deploy/linux/README.md exists and documents apt deps + cmake invocation.
  2. deploy/linux/telegram-like.desktop is a valid XDG entry.
  3. CMakeLists.txt gates qt_policy on COMMAND existence (Qt 6.4 compat).
  4. app_mobile main.cpp falls back to engine.load on Qt < 6.5.
  5. ci.yml has a linux-desktop job that installs qt6-base-dev/declarative.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINUX_README = REPO / "deploy" / "linux" / "README.md"
DESKTOP_FILE = REPO / "deploy" / "linux" / "telegram-like.desktop"
CMAKE = REPO / "client" / "src" / "CMakeLists.txt"
MOBILE_MAIN = REPO / "client" / "src" / "app_mobile" / "main.cpp"
CI = REPO / ".github" / "workflows" / "ci.yml"

SCENARIOS: list[tuple[str, callable]] = []


def scenario(name):
    def deco(fn):
        SCENARIOS.append((name, fn))
        return fn
    return deco


@scenario("linux_readme_exists_and_documents_build")
def _t1():
    text = LINUX_README.read_text(encoding="utf-8")
    for needle in ("qt6-base-dev", "qt6-declarative-dev", "cmake -S . -B build-linux",
                   "app_desktop app_mobile"):
        assert needle in text, f"Linux README missing: {needle}"


@scenario("desktop_entry_is_valid_xdg")
def _t2():
    text = DESKTOP_FILE.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text, "missing [Desktop Entry]"
    for key in ("Type=Application", "Name=", "Exec=", "Icon=", "Categories="):
        assert key in text, f".desktop file missing: {key}"


@scenario("cmake_qt_policy_is_conditional")
def _t3():
    text = CMAKE.read_text(encoding="utf-8")
    assert "if(COMMAND qt_policy)" in text, \
        "qt_policy must be guarded for Qt 6.4 compatibility"


@scenario("app_mobile_main_has_qt64_fallback")
def _t4():
    text = MOBILE_MAIN.read_text(encoding="utf-8")
    assert "QT_VERSION_CHECK(6, 5, 0)" in text, "app_mobile/main.cpp must compile on Qt 6.4"
    assert 'engine.load(QUrl("qrc:/qt/qml/TelegramLikeMobile/Main.qml"))' in text, \
        "fallback to engine.load on Qt < 6.5"


@scenario("ci_has_linux_desktop_job")
def _t5():
    text = CI.read_text(encoding="utf-8")
    assert "linux-desktop:" in text, "CI workflow missing linux-desktop job"
    assert "qt6-declarative-dev" in text, "CI must install Qt Quick packages"
    for target in ("app_desktop", "app_mobile"):
        assert target in text, f"linux-desktop job should build {target}"


def main() -> int:
    failed = 0
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
    total = len(SCENARIOS)
    print(f"passed {total - failed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

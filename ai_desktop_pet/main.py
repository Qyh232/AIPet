from __future__ import annotations
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="AI Desktop Pet")
    parser.add_argument("--headless", action="store_true", help="无 GUI 模式运行演示")
    parser.add_argument("--no-llm", action="store_true", dest="no_llm", help="禁用 LLM（纯模板模式）")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    from .log import configure
    configure(args.log_level)

    from .crash_handler import install as install_crash_handler
    install_crash_handler()

    from .config import PetConfig
    config = PetConfig()

    # LLM is ON by default; --no-llm disables it
    config.enable_llm = not args.no_llm
    config.enable_memory_manager = not args.no_llm

    if args.headless:
        from .app import PetApp
        PetApp(config).run_headless_demo()
        return

    # GUI mode (default)
    try:
        from PySide6.QtWidgets import QApplication
        from .app import PetApp
        PetApp(config).run_gui()
    except ImportError:
        print("PySide6 未安装。请运行: pip install PySide6")
        print("或使用无界面模式: python -m ai_desktop_pet --headless")
    except Exception as e:
        print(f"GUI 环境不可用 ({e})。")
        print("请运行: python -m ai_desktop_pet --headless")


if __name__ == "__main__":
    main()

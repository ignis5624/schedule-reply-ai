def run_app() -> None:
    """Streamlit本体は画面起動時にだけ読み込む。"""

    from .streamlit_app import run_app as _run_app

    _run_app()

__all__ = ["run_app"]

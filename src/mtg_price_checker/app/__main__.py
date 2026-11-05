import uvicorn

from mtg_price_checker.app.api import create_app


def main() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()

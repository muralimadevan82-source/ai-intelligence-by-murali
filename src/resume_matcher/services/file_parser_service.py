def extract_text_from_bytes(filename: str | None, data: bytes) -> str:
    return data.decode("utf-8", errors="replace")

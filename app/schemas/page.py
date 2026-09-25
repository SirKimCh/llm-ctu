from dataclasses import dataclass


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    page: int
    pages: int
    total: int

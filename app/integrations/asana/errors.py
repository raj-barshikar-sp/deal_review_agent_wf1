"""Asana integration errors."""


class AsanaError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status

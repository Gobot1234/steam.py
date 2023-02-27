"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from typing import TypedDict


class AddPhoneNumber(TypedDict):
    success: bool
    email_confirmation: bool
    error_text: str
    fatal: bool

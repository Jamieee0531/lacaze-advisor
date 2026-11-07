"""Planner and Writer outputs."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from lacaze.domain.models import Contract


class Angle(Contract):
    name: str = Field(min_length=1, description="几个字的角度名，给 CA 看，例如「回应预算」")
    point: str = Field(min_length=1, description="这条消息要让客户记住的一个核心意思，一句平实的话")
    purpose: str = Field(min_length=1, description="这条消息要达成什么、讲到哪里为止；不写具体措辞")
    message_ids: list[str] = Field(description="依据的对话编号，例如 m009")
    fact_ids: list[str] = Field(description="支撑要点、可以告诉客户的事实 ID；不需要时为空")
    next_step: str | None = Field(description="可选的下一步；不需要时为 null")


class Plan(Contract):
    situation: str = Field(min_length=1, description="客户现在的状态，一两句话")
    sub_type: str = Field(description="本场景的子类型，只能从给定列表中选")
    avoid: list[str] = Field(description="这次不能做的事")
    angles: Annotated[list[Angle], Field(min_length=3, max_length=3)]
    missing: list[str] = Field(description="客户问到或需要、但事实中没有的信息")


class Draft(Contract):
    angle: Literal[1, 2, 3]
    text: str = Field(min_length=1, description="发给客户的微信消息正文")
    fact_ids: list[str] = Field(description="正文实际用到的事实 ID")


class Drafts(Contract):
    drafts: Annotated[list[Draft], Field(min_length=3, max_length=3)]

    @field_validator("drafts")
    @classmethod
    def one_per_angle(cls, drafts: list[Draft]) -> list[Draft]:
        if sorted(d.angle for d in drafts) != [1, 2, 3]:
            raise ValueError("Write exactly one draft for each angle 1, 2 and 3")
        texts = [d.text.strip() for d in drafts]
        if len(set(texts)) != 3:
            raise ValueError("The three drafts must be different")
        if any(not re.search(r"[一-鿿]", t) for t in texts):
            raise ValueError("Each draft must be written in Chinese")
        return sorted(drafts, key=lambda d: d.angle)

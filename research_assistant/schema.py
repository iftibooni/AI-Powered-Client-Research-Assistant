from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class DiscoveredPage(BaseModel):
    url: HttpUrl
    label: str = Field(
        default="",
        description="Short label like 'home', 'about', 'services', 'contact', 'pricing', 'blog'.",
    )
    title: str = ""
    meta_description: str = ""
    text_excerpt: str = Field(default="", description="Cleaned visible text excerpt.")


class Competitor(BaseModel):
    name: str = ""
    url: str = ""
    notes: str = ""


class PositioningIdea(BaseModel):
    angle: str = Field(description="A competitor-style positioning angle.")
    who_its_for: str = ""
    key_benefit: str = ""
    proof_points: list[str] = Field(default_factory=list)
    sample_tagline: str = ""


class ContentIdea(BaseModel):
    title: str
    format: Literal[
        "blog",
        "landing_page",
        "comparison",
        "case_study",
        "email",
        "linkedin",
        "twitter",
        "youtube",
        "webinar",
        "lead_magnet",
        "other",
    ] = "blog"
    intent: Literal["awareness", "consideration", "decision"] = "awareness"
    why_it_works: str = ""
    outline_points: list[str] = Field(default_factory=list)


class WebsiteBasics(BaseModel):
    business_name: str = ""
    one_liner: str = ""
    industry: str = ""
    target_customer: str = ""
    locations_served: list[str] = Field(default_factory=list)
    primary_offers: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    call_to_action: str = ""
    contact_emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    social_links: list[str] = Field(default_factory=list)


class ResearchOutput(BaseModel):
    input_url: HttpUrl
    fetched_pages: list[DiscoveredPage] = Field(default_factory=list)
    basics: WebsiteBasics = Field(default_factory=WebsiteBasics)
    summary: str = Field(description="A crisp summary of the business and offering.")
    positioning_ideas: list[PositioningIdea] = Field(default_factory=list)
    competitors: list[Competitor] = Field(default_factory=list)
    content_ideas: list[ContentIdea] = Field(default_factory=list)
    sources: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool/search snippets used to produce the output.",
    )

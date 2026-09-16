from app.shared.schema import CamelModel


class MeResponse(CamelModel):
    name: str
    avatar_url: str | None
    github_linked: bool

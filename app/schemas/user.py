from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    created_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

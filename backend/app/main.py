from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai import assistant
from app.auth import Principal, require
from app.config import get_settings
from app.db import get_db
from app.routers import auth, districts, misc, webfront
from app.routers.entities import cells_router, glaciers_router

app = FastAPI(
    title="NASA Space Monitor API",
    version="0.1.0",
    description="Мониторинг склонов и ледников Кыргызстана на открытых данных NASA. "
                "Статусы показывают отклонение от нормы и необходимость проверки специалистом; это не прогноз.",
)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])

for r in (webfront.router, auth.router, districts.router, cells_router, glaciers_router, misc.router):
    app.include_router(r)


class AskIn(BaseModel):
    question: str = Field(max_length=1000)
    district_id: str | None = None


@app.post("/api/v1/assistant/ask", tags=["assistant"])
def ask(body: AskIn, p: Principal = Depends(require("admin_district", "emercom", "sysadmin")),
        db: Session = Depends(get_db)):
    return assistant.answer(db, p, body.question, body.district_id)

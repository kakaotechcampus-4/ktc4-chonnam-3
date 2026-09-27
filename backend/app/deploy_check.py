"""배포 연결 확인용 앱. 실제 서비스·DB·Redis의 정상 동작을 보증하지 않는다."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "deployment-check"}

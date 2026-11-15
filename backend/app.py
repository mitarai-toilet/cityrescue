from fastapi import FastAPI

app = FastAPI(title="CITYRESCUE AI API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cityrescue-api", "version": "0.1.0"}

from fastapi import FastAPI

app = FastAPI(title="Arbiter")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

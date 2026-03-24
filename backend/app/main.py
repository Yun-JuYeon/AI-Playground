from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import chat, wordchain, idiom
from .core.database import storage_client

app = FastAPI(title="AI Playground API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await storage_client.connect()


@app.on_event("shutdown")
async def on_shutdown():
    await storage_client.close()


# Include routers
app.include_router(chat.router)
app.include_router(wordchain.router)
app.include_router(idiom.router)


@app.get("/")
async def root():
    return {"message": "AI Playground Server Running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

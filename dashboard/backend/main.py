from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import jobs, actions

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(actions.router)
app.include_router(jobs.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

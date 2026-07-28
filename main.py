from services.commons import http
import services
import pkgutil

for _, name, _ in pkgutil.iter_modules(services.__path__):
    __import__(f"services.{name}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(http, host="0.0.0.0", port=14928)
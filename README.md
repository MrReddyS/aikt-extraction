# aikt-extraction

FastAPI app that extracts PDFs to markdown (Docling + EasyOCR). **NGINX Unit** serves the ASGI app on **port 80** (no uvicorn in the container).

There are two images: **`cpu/`** and **`gpu/`** (CUDA torch). Each folder has a `Dockerfile` and Azure Container Registry build scripts (`az acr build`).

## Deploy (Azure CLI)

Run from **`cpu/`** or **`gpu/`** after `az login`.

**Bash** — required flags:

```bash
./deploy.sh --reg <acr-name> --sub <subscription-guid> --rg <resource-group>
```

Optional: `--image <name>` (default `extraction`), `--context <path>` (default `.`). Use `-h` / `--help` for the usage line.

**PowerShell** — same values as named parameters:

```powershell
.\deploy.ps1 -Reg <acr-name> -Sub <subscription-guid> -Rg <resource-group>
```

Optional: `-Image extraction`, `-Context .`.

`deploy.defaults.example.yaml` at the repo root is only a **template for your own notes**. Copy it to **`deploy.defaults.yaml`** if you want a local, gitignored place to store IDs (the scripts **do not** read that file).

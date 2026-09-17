# Self-hosted watermark cleanup + straightening

The new API detects possible watermark overlays using Grounding DINO and restores accepted regions using LaMa. There is no paid inference service, OpenAI key or per-token billing. Server compute/storage and model downloads still consume resources. Straightening remains the user's selected Python 1.1 engine, unchanged.

**Experimental detection:** Grounding DINO is a general-purpose detector, not a specialist watermark classifier. Agreement between two watermark prompts, confidence filtering, duplicate suppression and area limits reduce false detections; they do not eliminate them. Signs/logos can be misclassified, subtle or tiled watermarks missed, and inpainting invents covered detail. Evaluate representative licensed customer images and clean negatives before commercial rollout. The UI labels this experimental. No universal success rate is claimed.

## Run on your Mac / development machine

From the repository root, using Python 3.11 or 3.12:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt
.venv/bin/python api/download_models.py
STRAIGHTLINE_LOCAL_ONLY=1 WATERMARK_ENABLED=1 .venv/bin/uvicorn api.app:create_app --factory --host 127.0.0.1 --port 8080 --workers 1
```

Open http://127.0.0.1:8080. The same batch uploader and slider now have **Remove detected watermarks** enabled when models load successfully. When checked, every image is checked automatically; only accepted regions are inpainted, followed by straightening. There are no manual masks. Disabling the checkbox runs straightening alone. Failed model loading disables the feature and logs the setup error; it never pretends cleanup happened.

The original `python server.py` and browser/Pyodide mode still support straightening only. The existing public Sites page does not host these models. Its watermark control remains disabled until a Python backend is deployed and connected. Merely uploading code to GitHub does not create a running backend.

## Deploy your own API

This is a single-worker service suitable for an initial controlled deployment, not a distributed multi-tenant platform. Host the frontend and API together at the same HTTPS origin. The FastAPI app serves `dist/` itself. Authenticate all requests using HTTP Basic, username `straightline`, password from `STRAIGHTLINE_API_KEY`. Browsers show the native login prompt. Do not embed this key in JavaScript or runtime.json.

Set `PUBLIC_ORIGIN=https://your-app.example` behind an HTTPS reverse proxy so same-origin checks work with TLS termination. Configure proxy upload limits (40 MB), processing timeouts (at least five minutes), authentication/rate limits and resource limits. Run exactly one worker: results and the inference lock are process-local. A busy worker returns 429; the current batch UI reports that per file. Higher-throughput production needs a durable job queue, per-user authorization and shared result storage.

Example container build after downloading models:

```sh
docker build -f api/Dockerfile -t straightline-api .
docker run --rm -p 127.0.0.1:8080:8080 \
  --env-file /secure/path/straightline.env \
  -v "$PWD/models:/app/models:ro" straightline-api
```

The environment file must contain `STRAIGHTLINE_API_KEY` and `PUBLIC_ORIGIN`. Do not set `STRAIGHTLINE_LOCAL_ONLY` for public deployment. Put the HTTPS reverse proxy in front of the loopback port. Container image does not include weights or customer photos. Container execution was not tested here.

Default inference is CPU. `DETECTOR_DEVICE=cuda` can use an appropriately installed PyTorch/CUDA stack for detection; this build keeps ONNX inpainting on CPU. It does not require a GPU or provision a paid server. Benchmark your actual image volume before choosing hardware.

## API contract

- `GET /runtime.json`: frontend capability discovery (`engine: server-python`, `watermarkRemoval`).
- `GET /api/health`: authenticated process/model readiness.
- `POST /api/process`: raw image bytes, `Content-Type: application/octet-stream`, optional `X-Remove-Watermarks: true`. Returns `result` plus base64 preview PNG.
- `GET /api/results/{exportId}`: the exact already-rendered full-resolution PNG; no second inference pass.
- `DELETE /api/results/{exportId}`: delete the stored result.

Results add `watermark` (`disabled`, `no_detection`, `uncertain`, `removed`), `straighteningStatus`, and `exportId`. Overall `cleaned` means watermark pixels were restored without a successful geometry correction. `no_detection` means no confident detection, not proof the image is watermark-free. Errors never report successful removal.

Originals stay in request memory. Processed PNGs are stored in a private temporary directory, with one-hour expiry and a 1 GiB per-worker output quota. Clear batch requests deletion immediately. A background sweep deletes expired files; a process restart discards access to its results. Downloads after expiry return 410 and require reprocessing. Inputs follow the existing 40 MB / 60 MP limits; large images may need substantial RAM. Reverse-proxy upload buffering/logging is operator-controlled and must be configured separately.

## Quality and dimensions

The watermark mask is a padded detected rectangle, not pixel-perfect text segmentation. A context crop is processed at LaMa's fixed 512x512 size and composited only within that mask. Pixels outside the mask are preserved exactly **before straightening**. Geometry correction then resamples/crops as before. Output retains original EXIF-oriented pixel dimensions; that does not guarantee recovered detail or original metadata. RGB 8-bit PNG exports and existing metadata limitations remain unchanged.

## Models and licensing

Pinned identifiers/revisions are in `api/model-lock.json`; downloads are an explicit setup step. Runtime uses local files only, safetensors for the detector and ONNX for inpainting. The download script writes a SHA-256 manifest for deployment auditing; weights are excluded from Git.

- [Grounding DINO tiny](https://huggingface.co/IDEA-Research/grounding-dino-tiny): model card declares Apache-2.0.
- [LaMa ONNX port](https://huggingface.co/Carve/LaMa-ONNX): model card declares Apache-2.0; derived from [original LaMa](https://github.com/advimman/lama), also Apache-2.0.

These licenses permit commercial use subject to their terms and attribution obligations. Preserve model/dependency notices when redistributing. The repository's MIT license covers this application's own code, not third-party weights. Use on imagery you are authorized to edit.

## Validation

```sh
.venv/bin/python -m unittest discover -s api_tests -v
.venv/bin/python -m unittest discover -s python_tests -v
node tests/batch.cjs
```

Eight API/cleanup tests cover authentication, cross-origin rejection, unavailable models, input errors, deterministic cached exports, deletion, no-detection identity, outside-mask identity, dimensions and rejection of excessive/invalid regions. Nine existing geometry/API tests remain passing. Real pinned detector/LaMa inference was exercised on a synthetic SAMPLE overlay on a private photo; detection and removal succeeded and the output was visually inspected. This is a smoke test, not a production-quality benchmark. Private sample photos are not included in the repository.

The clean control photo produced no detections and remained pixel-identical. A later screenshot containing a large PACE REALTY overlay was not reliably detected as a complete watermark. That example remains unsupported by the current conservative detector and needs the original file plus further detector evaluation; the smoke test must not be presented as proof of general watermark removal.

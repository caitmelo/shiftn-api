# Straightline Python test version

The straightening engine and image renderer are implemented in `dist/python/straighten.py` using Python, NumPy and Pillow. HTML/CSS/JavaScript handle upload controls, the vertical comparison slider and downloads. JavaScript does not perform image detection or rendering in this version.

## Test the frontend

The hosted frontend runs the Python module through Pyodide 0.27.7 in a dedicated browser worker. First use downloads the Python runtime, NumPy and Pillow from jsDelivr; subsequent photos reuse the worker. Photos are processed locally and are not uploaded to that CDN. A network connection is required for the initial runtime download. Blocked CDN access produces an explicit error, with no JavaScript-engine fallback.

For native Python execution on a Mac or developer machine, use Python 3.11+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

The server opens `http://127.0.0.1:8080`. Upload one or several photos, select **Straighten all**, inspect the divider, then download individual PNGs or a ZIP. The local server advertises native mode through `/runtime.json`, so the frontend calls the Python API without downloading Pyodide. `--no-browser` prevents automatic opening. Stop with Ctrl+C.

The server is a local development server bound to loopback. It keeps request bytes in memory and does not save uploaded photos. Do not expose this development server directly to the internet. A production backend needs deployment-specific authentication, job isolation, resource limits and lifecycle handling.

## Developer integration

- `straighten.process_bytes(raw)` returns `(result_dict, preview_png_bytes)`.
- `straighten.export_bytes(raw, result_dict['params'])` returns a full-resolution PNG.
- `POST /api/process`: raw JPEG/PNG/WebP request body; JSON response containing `result` and base64 `preview`.
- `POST /api/export`: same raw image body and `X-Correction` JSON header; binary PNG response.
- `dist/python-bridge.js`: chooses native API or browser Python using `runtime.json`.
- `dist/python-worker.js`: initializes Pyodide, passes bytes and invokes Python. It contains no image-processing algorithm.
- `dist/app.js`, `style.css`, `index.html`, `zip.js`: frontend and client-side ZIP generation.

Result status is `corrected`, `unchanged` (no correction detected), or `unresolved`. Technical exceptions are displayed separately as processing failures. Diagnostic evidence is included in batch reports. The comparison is a vertical wipe within a common frame, not geometric registration of every original and transformed pixel.

## Algorithm and limits

Gradient-directed Hough proposals are traced at subpixel precision. Robust camera roll/pitch estimation uses structural line consensus and split-support checks. Lower-contrast retries and continuous-track refinement are compared using shared edge measurements. Supported local corrections are bounded to 0.6% of image width. This is not AI, scene reconstruction, a calibrated lens profile or automatic photographer-position recovery. Yaw is not automatically inferred in this Python version.

This is a Python reimplementation, not a bit-for-bit translation of the JavaScript engine. On the eight supplied unresolved examples, local CPython checks returned 1 corrected, 4 with no correction detected, and 3 unresolved. These outcomes do not establish higher accuracy; no-change outcomes are not proof that an image is correctly aligned. The known remaining examples and broader photographic benchmark still need work. A language switch does not guarantee a better success rate.

Input limits: JPEG/PNG/WebP, 40 MB each, 60 MP and 20,000 px maximum side, 80 px minimum side; batch size 100. Browser requests time out after five minutes, including first runtime load. Batch processing is sequential. Browser and native numerical/library versions can produce small differences.

Exports retain the EXIF-oriented original pixel dimensions and use bicubic sampling from original pixels, with lossless PNG encoding. Perspective correction/cropping can still lose detail. The pipeline is 8-bit RGB; transparency is composited onto white. EXIF orientation is applied; other metadata and original ICC profiles are not preserved. RAW/HDR/16-bit archival processing is not supported. Full-resolution operations may require substantial memory; the app does not silently downsize exports on failure.

## Validation

```sh
python3 -m unittest discover -s python_tests -v
node tests/batch.cjs
```

Six Python tests cover known rotation recovery, level/blank behavior, original-size export, unchanged pixel identity, invalid input, EXIF orientation, and native HTTP frontend/API integration. A JavaScript test covers batch isolation and Python failure handling. Supplied photographs were processed locally and the corrected preview inspected. The original handoff did not exercise Pyodide. See the Python 1.1 update below.

Dependencies in the browser are pinned by the Pyodide 0.27.7 distribution. Native dependency ranges are in `requirements.txt`; pin an exact lockfile for production. Pyodide setup: https://pyodide.org/en/0.27.7/usage/quickstart.html


## Migration from the previous repository

This revision replaces the Node/Express + Wine + Windows ShiftN wrapper with the Python test implementation. The Windows binaries, DLLs, PowerShell scripts, old Node dependencies, Docker/Wine setup and Railway configuration have been removed from the current tree. They remain available in Git history.

This is not a drop-in replacement for the old service: `/correct`, multipart uploads, `X-API-Key`, the old environment variables, Docker/Compose and Railway deployment instructions no longer apply. The included server is for local testing on port 8080; production hosting and authentication must be implemented before exposing a Python API publicly.

Only the required HTML/CSS/JavaScript interface and Pyodide transport remain; image analysis and rendering run in Python. No user photographs, private Site configuration or credentials are included. Use your own test images. The existing repository LICENSE is retained.


## Python 1.1 — browser rejection fix

Reproduced the reported brick-house JPEG rejection in Pyodide 0.27.7 (NumPy 2.0.2, Pillow 10.2.0). Native decoding and browser-runtime decoding differ slightly, which changed edge proposals. The old final all-edge check rejected the agreed pose because conflicting non-upright edges dominated that check.

The fix adds deterministic Hough tie-breaking and a constrained structural-consensus validation fallback: repeated pose agreement, majority count and length support, spatial coverage, improvement on alternating spatial subsets, and a worst-long-edge check. Existing all-edge acceptance thresholds remain unchanged. Analysis evidence includes runtime versions and an analysis-pixel hash. Cache versions and a Python module version assertion prevent stale engine code from being accepted silently.

Validation: 9 native Python tests pass; 8 engine tests also pass in the exact Pyodide runtime using Node. The supplied failing JPEG now returns corrected in that runtime and exports at 1620 × 1080. This validates the processing runtime, not a full browser UI session or a universal success rate. The user photo remains excluded from the public repository.

To reproduce with locally downloaded Pyodide 0.27.7 files and its NumPy/Pillow wheels:

```sh
node tests/wasm-regression.cjs /path/to/pyodide /path/to/expected-correctable.jpg
```

## Optional self-hosted watermark API

See [WATERMARK_API.md](WATERMARK_API.md) for model setup, API deployment, tests and known limitations. The public static test page does not run these models. The straightening engine remains Python 1.1. Watermark detection is experimental and did not reliably cover the PACE REALTY example.

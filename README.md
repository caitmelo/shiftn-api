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

Gradient-directed Hough proposals are traced at subpixel precision. Robust camera roll/pitch estimation uses structural line consensus and split-support checks. Lower-contrast retries and continuous-track refinement are compared using shared edge measurements. Supported local corrections are bounded to 0.6% of image width. This is not AI, scene reconstruction, a calibrated lens profile or automatic photographer-position recovery. A guarded horizontal vanishing-direction estimator rectifies a dominant building face after the upright check. It does not recover calibrated camera yaw or make all faces of a 3D building front-facing.

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


## Python 1.2 — horizontal facade correction

After the existing upright estimator succeeds or finds near-upright edges, a second pass detects near-horizontal tracks. It robustly fits a shared horizontal vanishing direction across multiple heights, requires majority length support, independent height-subset agreement and improvement, and agreement at two or more contrast thresholds. The resulting projective transform preserves the vertical vanishing point. The inverse renderer now uses a general matrix inverse, rather than the transpose used for pure rotations. Exports still sample original pixels once at original dimensions.

New optional parameters `horizontalSlope` and `horizontalPerspective` default to zero. They are validated at export. Evidence reports the supporting horizontal edge count and before/after angular RMS. Existing API callers can continue passing old parameters unchanged. The frontend transports these fields without manual controls.

This is dominant-face rectification, not calibrated 3D reconstruction. It may crop the image and alter apparent proportions; perpendicular walls, sloping roofs and depth lines should not all become horizontal. Ambiguous horizontal evidence leaves the existing upright result intact. Nonlinear local-mesh results are left intact rather than composed with an unvalidated facade transform. This feature does not guarantee success for arbitrary photos.

Validation: 13 native Python tests and 12 engine tests in Pyodide 0.27.7 pass, including known horizontal projectivity recovery, upright preservation, inverse-mapping round trips, original-size rendering, and rejection of sparse/competing directions. The supplied pool/house photo changes from unchanged to corrected in both runtimes; the browser-runtime export is 2048 x 1377. Across 13 available photo fixtures, existing corrected statuses remain corrected; two earlier fixtures additionally receive horizontal correction. Corrected previews were inspected. These are regression checks, not a measured general success rate or full browser UI automation. Private photographs are not included in the public repository.


## Python 1.3 — compression-sensitive horizontal retry

The reported failure was reproduced with JPEG re-encoding and resizing of the pool/house fixture: two of twelve variants returned unresolved in 1.2 because the global upright solver abstained, preventing horizontal analysis. Version 1.3 permits a horizontal retry only when at least six distributed near-vertical edges have majority count/length support and weighted RMS below 0.65 degrees. Both spatial subsets must have coverage. Horizontal consensus checks remain unchanged, and the combined transform must not worsen upright RMS by more than 0.1 degree. A retry does not itself classify an image as corrected or unchanged.

All twelve local compression/size variants now return corrected. The failing re-encoded variant also passes in Pyodide 0.27.7 with original-size export. Fourteen native tests pass, including the new rejection checks for sparse or actually tilted upright support. The thirteen available original photo fixtures retain their 1.2 results. These checks do not identify the exact bytes/runtime used in the user's screenshot, and are not full browser UI automation.

The frontend adds **Download diagnostic report** for a selected result or processing error. Reports include filename, byte count, status, parameters, engine/library versions, rejection evidence and input SHA-256. This allows an exact-input/version comparison without distributing the photograph. Processing and diagnostic downloads remain local. Cache keys and the worker's engine assertion are updated to Python 1.3.

The actual worker process/export handlers can be tested with the pinned runtime through Node adapters:

```sh
node tests/worker-flow.cjs /path/to/pyodide /path/to/expected-correctable.jpg
```

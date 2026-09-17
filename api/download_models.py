"""Explicit one-time download. Runtime inference never downloads or calls paid APIs."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download
ROOT=Path(__file__).resolve().parents[1]
lock=json.loads((ROOT/'api/model-lock.json').read_text())
target=ROOT/'models';target.mkdir(exist_ok=True)
snapshot_download(lock['detector']['repo'],revision=lock['detector']['revision'],local_dir=target/'detector',allow_patterns=['*.json','*.txt','*.safetensors','README.md'])
hf_hub_download(lock['inpainting']['repo'],lock['inpainting']['file'],revision=lock['inpainting']['revision'],local_dir=target/'inpainting')
hf_hub_download(lock['inpainting']['repo'],'README.md',revision=lock['inpainting']['revision'],local_dir=target/'inpainting')
manifest={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and '.cache' not in p.parts and p.name!='manifest.json'}
(target/'manifest.json').write_text(json.dumps({'models':lock,'sha256':manifest},indent=2))
print('Models downloaded to',target)

"""Build QR, chart, parity fixture, and README from measured experiment artifacts."""
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).parent/'.cache/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import qrcode
from qrcode.util import QRData, MODE_8BIT_BYTE
import torch
from train import ROOT, VOCAB, unpack, pack, LM
import base64

r=json.loads((ROOT/'artifacts/results.json').read_text())
w=next(x for x in r['results'] if x['name']==r['winner'])
blob=(ROOT/'artifacts/model.bin').read_bytes()
assert len(blob)==w['bytes']<=2953
qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=8,border=4)
qr.add_data(QRData(blob,mode=MODE_8BIT_BYTE),optimize=0)
qr.make(fit=True)
qr.make_image().save(ROOT/'artifacts/model-qr.png')
model=unpack(blob)
torch.set_num_threads(1)
sequence=('alice was beginning to get very tired of sitting by her sister on the bank. '*4)
state=None; checkpoints=[]
with torch.no_grad():
    for i,c in enumerate(sequence):
        logits,state=model(torch.tensor([[VOCAB.index(c)]]),state)
        if i in [0,1,5,20,60,120,len(sequence)-1]:
            checkpoints.append(dict(position=i,logits=logits[0,0].tolist(),state=state[0,0].tolist()))
(ROOT/'artifacts/parity.json').write_text(json.dumps(dict(sha256=hashlib.sha256(blob).hexdigest(),sequence=sequence,checkpoints=checkpoints),indent=2)+'\n')

torch.manual_seed(1234)
formats=[]
for bits in [4,8,32]:
    payload=pack(LM(4),bits)
    m=unpack(payload)
    with torch.no_grad():
        logits,h=m(torch.tensor([[VOCAB.index(c) for c in 'alice ']]))
    formats.append(dict(bits=bits,payload=base64.b64encode(payload).decode(),logits=logits[0,-1].tolist(),state=h[0,0].tolist()))
(ROOT/'artifacts/format-fixtures.json').write_text(json.dumps(formats,indent=2)+'\n')

fig,ax=plt.subplots(figsize=(10,5.5),layout='constrained')
styles=[('float',32,'#777777','^',':','Float32'),('float',8,'#0072B2','o','-','8-bit'),('float',4,'#D55E00','s','--','4-bit, post-training'),('qat',4,'#009E73','D','-.','4-bit, quantization-aware')]
for stage,bits,color,marker,line,label in styles:
    rows=sorted([x for x in r['results'] if x['stage']==stage and x['bits']==bits and x.get('embedding',8)==8],key=lambda x:x['bytes'])
    x=np.array([x['bytes'] for x in rows]); y=np.array([x['test_bpc'] for x in rows]); ci=np.array([x['test_ci95'] for x in rows])
    ax.errorbar(x,y,yerr=np.maximum(0,np.array([y-ci[:,0],ci[:,1]-y])),color=color,marker=marker,linestyle=line,capsize=2,label=label,linewidth=1.5)
extra=[x for x in r['results'] if x.get('embedding',8)==10 and x['bits']==8]
if extra:
    x=extra[0]
    ax.errorbar([x['bytes']],[x['test_bpc']],yerr=[[x['test_bpc']-x['test_ci95'][0]],[x['test_ci95'][1]-x['test_bpc']]],marker='*',markersize=11,color='#CC79A7',capsize=2,label='8-bit, embedding 10',zorder=4)
ax.axvline(2953,color='#333333',linestyle='--',linewidth=1)
ax.text(2953*1.06,4.13,'One QR: 2,953 bytes',rotation=90,va='top',fontsize=9)
ax.axhline(r['unigram_test_bpc'],color='#777777',linewidth=1,linestyle=':')
ax.text(570,r['unigram_test_bpc']+.025,'Training-unigram reference',fontsize=9,color='#555555')
ax.scatter([w['bytes']],[w['test_bpc']],s=190,facecolors='none',edgecolors='black',linewidths=1.5,zorder=5)
ax.set_xscale('log'); ax.set_xlabel('Complete serialized model (bytes; logarithmic scale)')
ax.set_ylabel('Held-out test loss (bits per character; lower is better)')
ax.set_title('How much language survives a smaller model?',loc='left',pad=16)
ax.spines[['top','right']].set_visible(False)
ax.legend(loc='upper right',frameon=True,facecolor='white',edgecolor='white',framealpha=1,fontsize=9)
ax.grid(axis='y',alpha=.15)
fig.savefig(ROOT/'artifacts/quality.svg')
fig.savefig(ROOT/'artifacts/quality.png',dpi=200)
plt.close(fig)

rows='\n'.join(f"| {x['hidden']} | {x.get('embedding',8)} | {x['bits']} | {x['stage']} | {x['parameters']:,} | {x['bytes']:,} | {x['validation_bpc']:.3f} | {x['test_bpc']:.3f} | {'yes' if x['bytes']<=2953 else 'no'} |" for x in r['results'])
qat=[x for x in r['results'] if x['stage']=='qat']
small=min(qat,key=lambda x:x['bytes'])
float_w=next(x for x in r['results'] if x['hidden']==w['hidden'] and x['bits']==32 and x.get('embedding',8)==w.get('embedding',8))
e8=next(x for x in r['results'] if x['hidden']==20 and x['bits']==8 and x.get('embedding',8)==8)
e10=next(x for x in r['results'] if x['hidden']==20 and x['bits']==8 and x.get('embedding',8)==10)
sha=hashlib.sha256(blob).hexdigest()
report=f'''# A real language model in one QR code

**Yes: a trained neural character language model fits.** The selected model is a
{w['hidden']}-unit GRU with **{w['parameters']:,} learned parameters**, stored in **{w['bytes']:,} bytes**
including all metadata. It scores **{w['test_bpc']:.3f} bits per character** on held-out
Alice text (character perplexity **{w['perplexity']:.2f}**), compared with **{r['unigram_test_bpc']:.3f}** for a
training-frequency unigram reference. It produces spelling-like fragments and recognizable
rhythm, not coherent prose or useful answers. It is a real neural language model, **not a
large language model**, and not a Markov-chain text generator.

## Scan the model straight from this report

![The complete trained neural model encoded as raw binary in one QR code](artifacts/model-qr.png)

[Open the full-resolution QR for printing](artifacts/model-qr.png).
This is **model data, not a URL**. Open the [reader](index.html) in a browser served over
HTTPS or localhost, press **Start camera**, and point it at this code. A phone's ordinary
QR app will not run it; use this project's reader. The image is QR version **{qr.version}-L**,
**{qr.modules_count} × {qr.modules_count} modules**, with a four-module white quiet zone.
Print it at least **15 cm wide**, black on white, without cropping or smoothing the border.
A full-size screen image works too. Dense low-error-correction QR codes need good focus
and lighting; 15 cm is guidance, not a measured physical-print success threshold.

The theoretical limit is **2,953 binary bytes** in a version-40 QR at error-correction
level L, approximately 7% codeword recovery. It is **not** 3 KiB and is smaller at stronger
error correction. We encode one explicit byte-mode segment, with no base64, URL, compression,
or hidden external weights. Selected payload leaves **{2953-len(blob)} bytes** below that limit.
The PNG's file size is unrelated to QR payload capacity.

## Run the offline web reader

From the repository root:

```sh
python -m http.server 8000 --directory qr-code-llm
# Open http://localhost:8000/
```

1. Load the reader once and wait for **Reader saved for offline use**.
2. Disconnect from the network and reload the page.
3. Scan this QR with the camera, or use **choose a QR image** with a downloaded image/photo.
4. Enter a prompt, choose temperature and random seed, then generate 400 characters.

All camera processing and inference stay on your device. A service worker caches the reader,
including the vendored QR decoder. **It does not cache or fetch model weights.** Scanned weights
live only in memory. A reload clears them. Clearing browser site data removes offline support.
The first load must be online or served locally. Camera and service worker APIs require
HTTPS or localhost; opening `index.html` as a `file://` URL is not the supported path.
For a phone, serve this folder over HTTPS; a LAN HTTP address is not a secure camera origin.
The README and linked research artifacts are not part of the offline reader cache.
No server-side inference, CDN calls, WebGPU, or JavaScript ML framework is needed.

## Experiment

Corpus: Lewis Carroll's *Alice's Adventures in Wonderland*, Project Gutenberg ebook 11,
[UTF-8 source]({r['source']}). The original download and normalized text are included under
`data/`, with original Gutenberg license notice retained. The underlying 1865 text is public
domain in the United States; see the source's notice for its distribution terms.

We strip the front matter, table of contents, and Gutenberg footer; lowercase; map smart
quotes to apostrophes; transliterate to ASCII; map `!?;:` to periods; replace unsupported
characters with spaces; collapse repeated spaces and excess blank lines. The fixed
**{len(VOCAB)}-character alphabet** is newline, space, apostrophe, comma, period, and `a`–`z`.
This simplification makes the task easier and limits what the model can emit.

Contiguous 80/10/10 split after normalization:
**{r['split_characters'][0]:,} training / {r['split_characters'][1]:,} validation / {r['split_characters'][2]:,} test characters**.
No training window crosses a split. Validation chooses checkpoints and the winning
serialized model; test loss is not used for selection. Test evaluation predicts each next
character once, with continuous recurrent state within the test split and a fresh zero
state at its beginning. Metrics exclude the first character of each evaluation split.

Architecture: a learned character embedding ({w.get('embedding',8)} dimensions in the selected
model), one GRU layer, and a learned
linear projection to vocabulary logits followed by softmax. The hidden state carries context
across characters. PyTorch's GRU convention is used:

```text
r = sigmoid(W_ir x + b_ir + W_hr h + b_hr)
z = sigmoid(W_iz x + b_iz + W_hz h + b_hz)
n = tanh(W_in x + b_in + r * (W_hn h + b_hn))
h_next = (1 - z) * n + z * h
logits = W_out h_next + b_out
```

We test hidden sizes **8, 12, 16, 20, 24, 33, and 48**, each with an 8-dimensional embedding, plus a 20-unit model with a 10-dimensional
embedding that fits in 2,952 int8 bytes. Each is trained from scratch with seed 1729. Adam, learning rate 0.004, batch size 32, sequence length 64, gradient clipping
at norm 1, **{r['steps']:,} updates** per model. Training windows are sampled uniformly with
replacement, starting with zero hidden state. We check validation loss every 250 steps
and restore the best checkpoint. Every size receives the same update budget.

Each float checkpoint is exported as float32, symmetric per-tensor int8, and symmetric
per-tensor 4-bit. All seven tensors, including biases and embeddings, are quantized.
Scales are `max(abs(weights)) / (2^(bits-1)-1)`. Rounding uses nearest-even. The 4-bit
models receive **{r['qat_steps']:,} additional updates** of quantization-aware training (Adam
0.0008, straight-through gradient, dynamically recomputed detached scales), again choosing
the best validation checkpoint. This costs additional training and is not a controlled
same-compute comparison with the int8 models. We evaluate the actual exported and decoded
bytes, not an unquantized surrogate. `train.py` records every measured candidate, samples,
checkpoint validation history, corpus hashes, and environment version.

**Best means lowest validation BPC among the tested candidates that fit**, not a proof of
optimality over all architectures or training recipes. This is a single training seed;
architecture ranking could change with additional seeds, training, data, or quantization.
A larger 48-unit model supplies an over-budget reference. This is a small research sweep,
not an exhaustive hyperparameter search. An initial shorter sweep motivated adding the
20-unit int8 candidate; byte accounting then motivated its 10-dimensional embedding
variant. The table reports the final equal-budget training run.

## Quality versus size

![Held-out character prediction loss versus complete model size](artifacts/quality.svg)

Each point is one trained model/encoding, with **95% contiguous-block bootstrap intervals**
(512-character blocks, 2,000 resamples, seed 1729) over the held-out test loss. These are
approximate text-block uncertainty intervals, **not** uncertainty across training seeds.
No statistical significance claim is made. Lines connect hidden sizes within each encoding;
they are not an interpolation guarantee. The star is the additional embedding-10
int8 experiment; its other encodings are included in the table. The circled point is selected by validation.
The vertical line is the version-40-L capacity, and the horizontal reference is a unigram
frequency model used only as a baseline, never for generation.

| Hidden units | Embedding | Bits | Training stage | Parameters | Complete bytes | Validation BPC | Test BPC | Fits QR? |
| ---: | ---: | ---: | :--- | ---: | ---: | ---: | ---: | :--- |
{rows}

The {e10['bytes']:,}-byte embedding-10 candidate has validation BPC {e10['validation_bpc']:.3f}
versus {e8['validation_bpc']:.3f} for the {e8['bytes']:,}-byte embedding-8 model. Their test BPC
differs by only {abs(e10['test_bpc']-e8['test_bpc']):.4f}; this single-seed experiment does not
establish a held-out quality gain from the extra {e10['bytes']-e8['bytes']} bytes.
The final model is selected strictly by the stated validation rule.

The smallest quantization-aware model uses {small['bytes']:,} bytes and scores
{small['test_bpc']:.3f} test BPC; the selected model uses {w['bytes']:,} bytes and scores
{w['test_bpc']:.3f}. Shrinking storage loses predictive quality overall, but the relationship
is not perfectly monotonic: bit depth and quantization training matter, not just unit count.
The selected architecture's float32 reference scores {float_w['test_bpc']:.3f} BPC at
{float_w['bytes']:,} bytes. Raw data and every serialized candidate are in
[`artifacts/results.json`](artifacts/results.json) and [`artifacts/models/`](artifacts/models/).

Selected decoded model, prompt `alice `, temperature 0.8, PyTorch sampling seed 123,
320 generated characters (unfiltered):

```text
{w['sample']}
```

All candidate samples are recorded, including failures. The browser uses a documented LCG
sampler rather than PyTorch's RNG, so its samples differ at the same seed; logits agree
within numerical tolerance. Lower temperature sharpens predictions but does not add
understanding, facts, or long-range coherence.

## Exact binary format: QLM1

All multibyte scalars are little-endian. Tensor values are row-major in PyTorch order.
The format includes sufficient information to reconstruct the network with this reader.
The generic architecture interpreter and scanner are supplied by the web app, not encoded
inside the QR — this experiment asks whether **trained model weights** fit on paper.

| Field | Bytes |
| :--- | ---: |
| ASCII `QLM1` magic/version | 4 |
| Bit depth, vocabulary length, embedding width, hidden width (`uint8` each) | 4 |
| ASCII vocabulary in token-index order | {len(VOCAB)} |
| Seven tensors: embedding, GRU input weight, GRU recurrent weight, two GRU biases, output weight, output bias | variable |
| CRC-32 of all preceding bytes (IEEE polynomial) | 4 |

Each quantized tensor has one float32 scale followed by int8 bytes, or packed nibbles.
A 4-bit signed value `q` in -7…7 is stored as `q+8`; first value in the low nibble. Each
tensor pads its odd final nibble with 8 (zero). Float32 tensors omit the scale. GRU gates
are ordered reset, update, new. Parameter count is `V*E + 3*H*E + 3*H*H + 6*H + V*H + V`.
There is no learned initial hidden state. The browser validates magic, CRC, bounds,
vocabulary, exact length, scales, and finite values before allocating inference tensors.
CRC detects accidental corruption; it does not authenticate a model's author.

Selected artifact: `{r['winner']}`. SHA-256 of `artifacts/model.bin`:

```text
{sha}
```

Corpus SHA-256 (original): `{r['source_sha256']}`

Corpus SHA-256 (normalized): `{r['normalized_sha256']}`

## Reproduce

Python 3.12, CPU PyTorch {r['torch_version']}; exact dependency snapshot in
`requirements-lock.txt`. All commands below run inside `qr-code-llm`:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python train.py --steps 8000 --qat-steps 3000 --hidden 8 12 16 20 24 33 48
.venv/bin/python train.py --steps 8000 --qat-steps 3000 --hidden 20 --embedding 10 --append
.venv/bin/python build_report.py
node test_model.cjs
.venv/bin/python test_browser.py
```

Training is CPU-only, single-threaded, with deterministic PyTorch algorithms enabled.
Numerical results may still vary across PyTorch versions and hardware. `requirements.txt`
uses the CPU wheel index for PyTorch. The browser tests use system Chromium by default;
set `CHROMIUM` to its executable path if needed. No dependency installation or corpus fetch
is needed to use the checked-in reader and QR. To rerun the experiment, the corpus is
already included. The vendored scanner is [jsQR 1.4.0](https://github.com/cozmo/jsQR), under
Apache-2.0; its license is in `vendor/jsQR.LICENSE`.

## Verification and limits

`test_model.cjs` checks all three supported bit depths, Python/JavaScript recurrent-state
and logit parity across a
multi-character sequence, deterministic generation, truncation, corrupt bytes, invalid
metadata, invalid scales, and invalid generation settings. `test_browser.py` exercises
image decoding, fake-camera capture of the actual final QR, generation, mobile layout,
and a service-worker-controlled reload with networking disabled followed by rescanning.
It asserts that no model binary is requested and that the service worker cache excludes
model artifacts. Test results and screenshots are in `artifacts/verification.json`,
`artifacts/reader-desktop.png`, and `artifacts/reader-mobile.png`.

**Physical paper, a real phone camera, and Safari/Firefox are not tested in this environment.**
The automated camera test uses an image of the final QR fed through Chromium's camera API.
Successful digital decoding does not guarantee a particular printer, camera, or lighting
setup. A large clean print and a full-resolution image import provide the best chances.
The model is intentionally tiny: it does not reliably retain sentence meaning, follow
instructions, or answer questions. The demonstrated result is a trained recurrent neural
network whose complete serialized parameters can be recovered from one QR and used offline.
'''
(ROOT/'README.md').write_text(report)
print(json.dumps(dict(winner=w['name'],bytes=len(blob),qr_version=qr.version,sha256=sha),indent=2))

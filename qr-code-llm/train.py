"""Train real character GRUs, export every measured model, and select by validation BPC."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import time
import unicodedata
import zlib

os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).parent / '.cache/matplotlib'))
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.func import functional_call

ROOT = Path(__file__).resolve().parent
VOCAB = "\n ',.abcdefghijklmnopqrstuvwxyz"
EMBED = 8
BUDGET = 2953

class LM(nn.Module):
    def __init__(self, hidden, embedding=EMBED):
        super().__init__()
        self.embedding = nn.Embedding(len(VOCAB), embedding)
        self.gru = nn.GRU(embedding, hidden, batch_first=True)
        self.output = nn.Linear(hidden, len(VOCAB))
    def forward(self, x, state=None):
        y, state = self.gru(self.embedding(x), state)
        return self.output(y), state

def corpus():
    raw = (ROOT / 'data/alice-original.txt').read_text()
    # Remove Gutenberg front/back matter, contents, and title page.
    text = raw[raw.index('CHAPTER I.\nDown the Rabbit-Hole'):raw.index('*** END OF THE PROJECT GUTENBERG')]
    text = text.lower().replace('’', "'").replace('‘', "'").replace('“', "'").replace('”', "'")
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub('[!?;:]', '.', text)
    text = ''.join(c if c in VOCAB else ' ' for c in text)
    text = re.sub(' +', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub('\n{3,}', '\n\n', text).strip() + '\n'
    (ROOT / 'data/alice.txt').write_text(text)
    ids = torch.tensor([VOCAB.index(c) for c in text], dtype=torch.long)
    a, b = int(len(ids)*.8), int(len(ids)*.9)
    return text, (ids[:a], ids[a:b], ids[b:])

def quantize(tensor, bits):
    limit = 2**(bits-1)-1
    scale = max(tensor.detach().abs().max().item()/limit, 1e-8)
    q = (tensor.detach()/scale).round().clamp(-limit, limit)
    return q, scale

def fake_weights(model, bits=4):
    result = {}
    for name, p in model.named_parameters():
        q, s = quantize(p, bits)
        result[name] = p + (q*s-p).detach()
    return result

def pack(model, bits):
    h = model.gru.hidden_size
    # Magic, format version, bit depth, vocabulary length, embedding size, hidden size.
    blob = bytearray(b'QLM1' + bytes([bits, len(VOCAB), model.embedding.embedding_dim, h]) + VOCAB.encode('ascii'))
    for p in model.parameters():
        a = p.detach().numpy().ravel()
        if bits == 32:
            blob.extend(a.astype('<f4').tobytes())
        else:
            q, scale = quantize(p, bits)
            blob.extend(struct.pack('<f', scale))
            q = q.numpy().ravel().astype(np.int8)
            if bits == 8:
                blob.extend(q.tobytes())
            else:
                u = (q.astype(np.int16)+8).astype(np.uint8)
                if len(u)%2: u = np.append(u, np.uint8(8))
                blob.extend((u[::2] | (u[1::2]<<4)).tobytes())
    blob.extend(struct.pack('<I', zlib.crc32(blob)))
    return bytes(blob)

def unpack(blob):
    assert blob[:4] == b'QLM1' and zlib.crc32(blob[:-4]) == struct.unpack('<I', blob[-4:])[0]
    bits, v, e, h = blob[4:8]
    assert blob[8:8+v].decode() == VOCAB and 1 <= e <= 64
    model = LM(h, e)
    pos = 8+v
    with torch.no_grad():
        for p in model.parameters():
            n = p.numel()
            if bits == 32:
                values = np.frombuffer(blob, '<f4', n, pos).copy(); pos += n*4
            else:
                scale = struct.unpack_from('<f', blob, pos)[0]; pos += 4
                if bits == 8:
                    values = np.frombuffer(blob, np.int8, n, pos).astype(np.float32)*scale; pos += n
                else:
                    length = (n+1)//2
                    u = np.frombuffer(blob, np.uint8, length, pos); pos += length
                    values = np.stack((u&15, u>>4), axis=1).ravel()[:n].astype(np.float32)
                    values = (values-8)*scale
            p.copy_(torch.tensor(values.reshape(p.shape)))
    assert pos == len(blob)-4
    return model.eval()

@torch.no_grad()
def evaluate(model, ids):
    state = None
    losses = []
    for pos in range(0, len(ids)-1, 256):
        x = ids[pos:min(pos+256,len(ids)-1)][None]
        y = ids[pos+1:pos+1+x.shape[1]]
        logits, state = model(x, state)
        losses.extend((F.cross_entropy(logits[0], y, reduction='none')/math.log(2)).tolist())
    # Contiguous block bootstrap captures some local correlation; not seed uncertainty.
    blocks = np.array([np.mean(losses[i:i+512]) for i in range(0,len(losses),512)])
    rng = np.random.default_rng(1729)
    means = rng.choice(blocks, (2000,len(blocks)), replace=True).mean(axis=1)
    return float(np.mean(losses)), np.quantile(means,[.025,.975]).tolist()

@torch.no_grad()
def sample(model, seed=123, prompt='alice ', count=320):
    torch.manual_seed(seed)
    ids = torch.tensor([[VOCAB.index(c) for c in prompt]])
    logits, state = model(ids)
    out = prompt
    for _ in range(count):
        i = torch.multinomial((logits[0,-1]/.8).softmax(0),1)
        out += VOCAB[i.item()]
        logits, state = model(i.reshape(1,1),state)
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=3000)
    parser.add_argument('--qat-steps', type=int, default=1000)
    parser.add_argument('--hidden', type=int, nargs='+', default=[8,12,16,20,24,33,48])
    parser.add_argument('--embedding', type=int, default=8)
    parser.add_argument('--append', action='store_true', help='Append same-budget experiments to existing results')
    args = parser.parse_args()
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    (ROOT/'artifacts/models').mkdir(parents=True, exist_ok=True)
    text, (train, val, test) = corpus()
    meta = dict(source='https://www.gutenberg.org/files/11/11-0.txt',
                source_sha256=hashlib.sha256((ROOT/'data/alice-original.txt').read_bytes()).hexdigest(),
                normalized_sha256=hashlib.sha256(text.encode()).hexdigest(),
                vocabulary=VOCAB, split_characters=[len(train),len(val),len(test)],
                steps=args.steps, qat_steps=args.qat_steps, batch_size=32, sequence_length=64,
                seed=1729, torch_version=torch.__version__, results=[])
    if args.append:
        meta = json.loads((ROOT/'artifacts/results.json').read_text())
        assert meta['steps'] == args.steps and meta['qat_steps'] == args.qat_steps
    counts = torch.bincount(train,minlength=len(VOCAB)).double()+1
    probs = counts/counts.sum()
    meta['unigram_test_bpc'] = float(-probs[test[1:]].log2().mean())
    for h in args.hidden:
        torch.manual_seed(1729)
        model = LM(h, args.embedding)
        optimizer = torch.optim.Adam(model.parameters(),lr=.004)
        best = float('inf'); best_state = None; history = []
        started = time.time()
        for stage, steps in [('float',args.steps),('qat',args.qat_steps)]:
            if stage == 'qat':
                model.load_state_dict(best_state)
                optimizer = torch.optim.Adam(model.parameters(),lr=.0008)
                best = float('inf')
            for step in range(1,steps+1):
                starts = torch.randint(len(train)-65,(32,))
                ix = starts[:,None]+torch.arange(64)[None]
                x, y = train[ix], train[ix+1]
                optimizer.zero_grad()
                logits,_ = functional_call(model,fake_weights(model),(x,)) if stage == 'qat' else model(x)
                loss = F.cross_entropy(logits.flatten(0,1), y.flatten())
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(),1.)
                optimizer.step()
                if step%250 == 0 or step == steps:
                    evaluated = unpack(pack(model,4)) if stage == 'qat' else model
                    bpc,_ = evaluate(evaluated,val)
                    history.append(dict(stage=stage,step=step,validation_bpc=bpc))
                    if bpc < best:
                        best = bpc; best_state = copy.deepcopy(model.state_dict())
                    print(f'h={h} {stage} {step}/{steps} val={bpc:.4f} elapsed={time.time()-started:.0f}s',flush=True)
            model.load_state_dict(best_state)
            for bits in ([32,8,4] if stage == 'float' else [4]):
                blob = pack(model,bits); decoded = unpack(blob)
                val_bpc,_ = evaluate(decoded,val)
                test_bpc,ci = evaluate(decoded,test)
                prefix = '' if args.embedding == 8 else f'e{args.embedding}-'
                name = f'{prefix}h{h}-{stage}-{bits}bit'
                (ROOT/f'artifacts/models/{name}.bin').write_bytes(blob)
                meta['results'].append(dict(name=name, hidden=h, embedding=args.embedding, bits=bits, stage=stage,
                    parameters=sum(p.numel() for p in model.parameters()), bytes=len(blob),
                    validation_bpc=val_bpc,test_bpc=test_bpc,test_ci95=ci,
                    perplexity=2**test_bpc,sample=sample(decoded)))
        (ROOT/f'artifacts/history-{prefix}h{h}.json').write_text(json.dumps(history,indent=2)+'\n')
        (ROOT/'artifacts/results.json').write_text(json.dumps(meta,indent=2)+'\n')
    winner = min((r for r in meta['results'] if r['bytes']<=BUDGET),key=lambda r:r['validation_bpc'])
    meta['winner'] = winner['name']
    (ROOT/'artifacts/model.bin').write_bytes((ROOT/f"artifacts/models/{winner['name']}.bin").read_bytes())
    (ROOT/'artifacts/results.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('WINNER',winner,flush=True)

if __name__ == '__main__': main()

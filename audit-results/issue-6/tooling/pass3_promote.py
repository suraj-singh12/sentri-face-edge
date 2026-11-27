"""Pass 3 (Linux, source 677bb61): promote reviewed public captures into the existing library.
Run from the repository root after capture processes stop. Copies original bytes unchanged,
appends to capture-register.json and never publishes raw accessibility snapshots.
Captures whose accessibility snapshot shows a filled password/passphrase field stay private,
following the existing credential-bearing-frame rule (reproduce.md, continuation O).
"""
from pathlib import Path
import hashlib, json, re, shutil, struct, sys

ROOT = Path.cwd(); A = ROOT / 'audit-results/issue-6'; P = ROOT / 'qa-fixtures/runs/issue-6-audit'; C = P / 'captures'
SHA = '677bb61e8e9d659db95123871bb2e011cf663a79'
FILLED_SECRET = re.compile(r'textbox "[^"]*(?:[Pp]assword|[Pp]assphrase)[^"]*": \S')
MISCAPTURE = {('J51', 1)}

def ux_for(j, s):
    if j in ('J42', 'J43', 'J44', 'J46'): return 'UX-02'
    if j == 'J45': return 'UX-13'
    if j == 'J48' or j == 'J52': return 'UX-01'
    if j == 'J47':
        if s <= 4 or s >= 19: return 'UX-13'
        if s in (5, 6, 7, 13, 17, 18): return 'UX-01'
        if s == 8: return 'UX-05'
        if s in (15, 16): return 'UX-09'
        return 'UX-06'
    if j == 'J49':
        if s in (1, 9, 16): return 'UX-09'
        if s in (7, 8, 17, 18): return 'UX-05'
        if s == 19: return 'UX-06'
        return 'UX-10'
    if j == 'J50':
        if s in (1, 15, 16): return 'UX-06'
        if s in (4, 14): return 'UX-05'
        if s == 13: return 'UX-09'
        return 'UX-08'
    if j == 'J51': return 'UX-13' if s <= 8 else 'UX-01'
    raise ValueError((j, s))

def png_size(p):
    raw = p.read_bytes(); assert raw.startswith(b'\x89PNG\r\n\x1a\n'), p
    w, h = struct.unpack('>II', raw[16:24]); return {'width': w, 'height': h}

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main(apply):
    reg = json.loads((A / 'capture-register.json').read_text())
    known = {r.get('original_file', r['file']) for r in reg}
    n = max(int(r['capture_id'].split('-')[1]) for r in reg)
    meta = [x for x in json.loads((P / 'capture-metadata.json').read_text()) if x.get('source_sha') == SHA]
    meta.sort(key=lambda x: (x['journey'], x['step']))
    added = withheld = 0
    for x in meta:
        if x['file'] in known: continue
        src = C / x['file']; assert src.exists() and digest(src) == x['sha256'], src
        ux = ux_for(x['journey'], x['step'])
        name = re.sub(r'^UX-\d\d', ux, x['file'])
        snap = (C / (x['file'] + '.txt')).read_text() if (C / (x['file'] + '.txt')).exists() else ''
        rec = {k: v for k, v in x.items() if k not in ('public_candidate', 'sanitized_file', 'sanitized_sha256')}
        n += 1
        rec.update(file=name, original_file=x['file'], ux=ux, kind='synthetic source authority (Linux Pass 3)',
                   fixture_context='Pass 3 disposable synthetic source authority on Linux Chromium; audit-only multi-face detector seam for J42-J44; no operator data.',
                   capture_surface='headless Chromium content viewport; not stitched; OS chrome excluded',
                   capture_id=f'CAP-{n:04d}', raster_pixels=png_size(src), pass_id='Pass 3')
        if x['ux'] != ux: rec['ux_corrected_from'] = x['ux']
        reason = None
        if (x['journey'], x['step']) in MISCAPTURE: reason = 'Withheld: mis-capture superseded by the next step.'; rec['capture_acceptance'] = 'REJECTED as stated state; superseded'
        elif FILLED_SECRET.search(snap): reason = 'Withheld: credential-bearing form with a filled password/passphrase field.'
        elif re.search(r'/home/|/Users/|/private/|/Volumes/|/tmp/', snap): reason = 'Withheld: local path visible.'
        if reason:
            rec['publication'] = 'PRIVATE original only'; rec['publication_reason'] = reason; withheld += 1
        else:
            dest = A / 'screenshots' / ux / name
            rec.update(publication='ORIGINAL unmodified full capture', public_file=str(dest.relative_to(A)), public_sha256=x['sha256'])
            if apply:
                dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dest)
            added += 1
        print(rec['capture_id'], x['journey'], x['step'], ux, rec.get('public_file', reason))
        reg.append(rec)
    if apply: (A / 'capture-register.json').write_text(json.dumps(reg, indent=1) + '\n')
    print(f'public {added}, withheld {withheld}, register {len(reg)}')

if __name__ == '__main__':
    main('--apply' in sys.argv)

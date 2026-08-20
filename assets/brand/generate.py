"""Generate every BILBO brand file from the six base SVGs exported from Figma.

Source of truth: https://www.figma.com/design/9nhbTgYEPDlwRdMEj1VeHP/BILBO-logo-explorations
The base SVGs in _base/ carry exactly two colours: #BA7517 on every mark shape and
#633806 on every word shape. Every file shipped here is a recolour of those.

Requires rsvg-convert and ImageMagick. Run: python3 generate.py
"""
import os, re, shutil, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, '_base')
MARK, WORD = '#BA7517', '#633806'
CREAM, INK = '#FAEEDA', '#1A1206'
GRAY_MARK, GRAY_WORD = '#7A7168', '#2E2A25'

PALETTE = {
    'amber':  ('#633806', '#BA7517', '#FAC775', '#EF9F27'),
    'blue':   ('#0C447C', '#378ADD', '#B5D4F4', None),
    'coral':  ('#993C1D', '#D85A30', '#F5C4B3', None),
    'green':  ('#27500A', '#639922', '#C0DD97', None),
    'purple': ('#3C3489', '#7F77DD', '#CECBF6', None),
    'teal':   ('#0F6E56', '#1D9E75', '#9FE1CB', None),
    'mustard':('#6E5308', '#C9A227', '#F0DFA6', None),
    'gold':   ('#7A4B06', '#EF9F27', '#FBDCA6', None),
    'rust':   ('#7A2E12', '#B4451F', '#E9BBA6', None),
    'olive':  ('#3A4A12', '#6E8B22', '#C9DBA0', None),
    'indigo': ('#2A2E6E', '#4B54C4', '#C3C7EE', None),
    'cyan':   ('#0B4A5E', '#1E8CA8', '#A9DCE9', None),
}
VARIANTS = ['bilayer', 'grid']
FORMS = ['lockup', 'tagline', 'stacked', 'symbol']
TREATMENTS = ['color', 'color-dark', 'black', 'white', 'gray']
LAYOUT = {'bilayer': (6, 3), 'grid': (9, 2)}   # lipids, shapes per lipid

COMBOS = [
    ('duo-amber-teal',          'leaflet',  ['amber', 'teal']),
    ('duo-amber-blue',          'leaflet',  ['amber', 'blue']),
    ('duo-amber-coral',         'leaflet',  ['amber', 'coral']),
    ('duo-teal-purple',         'leaflet',  ['teal', 'purple']),
    ('trio-amber-teal-coral',   'species',  ['amber', 'teal', 'coral']),
    ('trio-amber-purple-green', 'species',  ['amber', 'purple', 'green']),
    ('trio-blue-coral-green',   'species',  ['blue', 'coral', 'green']),
    ('spectrum',                'spectrum', ['amber', 'teal', 'coral', 'blue', 'green', 'purple']),
    ('duo-mustard-teal',        'leaflet',  ['mustard', 'teal']),
    ('duo-mustard-indigo',      'leaflet',  ['mustard', 'indigo']),
    ('duo-mustard-rust',        'leaflet',  ['mustard', 'rust']),
    ('duo-gold-cyan',           'leaflet',  ['gold', 'cyan']),
    ('duo-olive-mustard',       'leaflet',  ['olive', 'mustard']),
    ('trio-mustard-rust-olive', 'species',  ['mustard', 'rust', 'olive']),
    ('trio-mustard-teal-indigo','species',  ['mustard', 'teal', 'indigo']),
    ('trio-gold-coral-cyan',    'species',  ['gold', 'coral', 'cyan']),
    ('spectrum-warm',           'spectrum', ['mustard', 'gold', 'amber', 'rust', 'coral', 'olive']),
    ('spectrum-cool',           'spectrum', ['teal', 'cyan', 'blue', 'indigo', 'purple', 'green']),
]
COMBO_FORMS = ['lockup', 'symbol']
COMBO_PNG = {'spectrum', 'spectrum-warm', 'spectrum-cool', 'duo-amber-teal',
             'duo-mustard-teal', 'trio-mustard-rust-olive', 'trio-amber-teal-coral'}
GRAYS = ['#3F3B35', '#7A7168', '#A99F94']
GRAYS_DARK = ['#D8D2C9', '#A99F94', '#7A7168']


def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    ra, rb = hex2rgb(a), hex2rgb(b)
    return '#%02X%02X%02X' % tuple(int(round(ra[i] + (rb[i] - ra[i]) * t)) for i in range(3))


def tone(name, dark):
    d, mid, light, override = PALETTE[name]
    return (override or mix(mid, light, 0.45)) if dark else mid


def base_svg(form, variant):
    s = open(os.path.join(SRC, 'bilbo-%s-%s.svg' % (form, variant)), encoding='utf-8').read()
    return re.sub(r'<rect width="[0-9.]+" height="[0-9.]+" fill="#E5E5E5"/>', '', s)


def png_of(svg_path, scale=4):
    s = open(svg_path, encoding='utf-8').read()
    w = float(re.search(r'width="([0-9.]+)"', s).group(1))
    out = svg_path[:-4] + '.png'
    subprocess.run(['rsvg-convert', '-w', str(int(round(w * scale))), svg_path, '-o', out], check=True)
    return out


def write(svg, path, mark, word, make_png=True):
    s = svg.replace(MARK, mark).replace(WORD, word)
    open(path, 'w', encoding='utf-8').write(s)
    return [path] + ([png_of(path)] if make_png else [])


def per_lipid(svg, colours, group, word):
    idx = [0]

    def sub(_m):
        k = idx[0]
        idx[0] += 1
        return 'fill="%s"' % colours[min(k // group, len(colours) - 1)]

    return re.sub(r'fill="%s"' % MARK, sub, svg).replace(WORD, word)


def assign(variant, kind, cols):
    n, group = LAYOUT[variant]
    if kind == 'leaflet':
        seq = [cols[i % 2] for i in range(n)] if variant == 'bilayer' else \
              [cols[((i // 3) + i) % 2] for i in range(n)]
    else:
        seq = [cols[i % len(cols)] for i in range(n)]
    return seq, group


def card(src_svg, out_png, cw, ch, bg, inner):
    """Rasterise the SVG straight at the target width, never downscale a 4x PNG."""
    tmp = out_png + '.tmp.png'
    subprocess.run(['rsvg-convert', '-w', str(inner), src_svg, '-o', tmp], check=True)
    subprocess.run(['magick', '-size', '%dx%d' % (cw, ch), 'xc:' + bg,
                    tmp, '-gravity', 'center', '-composite', out_png], check=True)
    os.remove(tmp)


made = []
for variant in VARIANTS:
    vdir = os.path.join(BASE, variant)
    if os.path.isdir(vdir):
        shutil.rmtree(vdir)
    for sub in ('', 'colors', 'combos'):
        os.makedirs(os.path.join(vdir, sub), exist_ok=True)
    dark_word_pairs = {
        'color':      (tone('amber', False), PALETTE['amber'][0]),
        'color-dark': (tone('amber', True), CREAM),
        'black':      (INK, INK),
        'white':      ('#FFFFFF', '#FFFFFF'),
        'gray':       (GRAY_MARK, GRAY_WORD),
    }
    for form in FORMS:
        svg = base_svg(form, variant)
        for t in TREATMENTS:
            m, w = dark_word_pairs[t]
            made += write(svg, os.path.join(vdir, 'bilbo-%s-%s-%s.svg' % (form, variant, t)), m, w)
        if form in ('lockup', 'tagline', 'symbol'):
            for name in PALETTE:
                if name == 'amber':
                    continue
                for dark in (False, True):
                    m = tone(name, dark)
                    w = CREAM if dark else PALETTE[name][0]
                    p = os.path.join(vdir, 'colors', 'bilbo-%s-%s-%s%s.svg'
                                     % (form, variant, name, '-dark' if dark else ''))
                    made += write(svg, p, m, w, make_png=False)
        if form in COMBO_FORMS:
            for cname, kind, names in COMBOS + [('grayscale-multi', 'species', None)]:
                for dark in (False, True):
                    if names is None:
                        cols = GRAYS_DARK if dark else GRAYS
                        word = CREAM if dark else GRAY_WORD
                    else:
                        cols = [tone(n, dark) for n in names]
                        word = CREAM if dark else PALETTE[names[0]][0]
                    seq, group = assign(variant, kind, cols)
                    p = os.path.join(vdir, 'combos', 'bilbo-%s-%s-%s%s.svg'
                                     % (form, variant, cname, '-dark' if dark else ''))
                    open(p, 'w', encoding='utf-8').write(per_lipid(svg, seq, group, word))
                    made.append(p)
                    if cname in COMBO_PNG and not dark:
                        made.append(png_of(p))
    lk = os.path.join(vdir, 'bilbo-lockup-%s-' % variant)
    sy = os.path.join(vdir, 'bilbo-symbol-%s-' % variant)
    amber = tone('amber', False)
    card(lk + 'color.svg', lk + 'on-white.png', 2400, 800, '#FFFFFF', 1560)
    card(lk + 'white.svg', lk + 'on-amber.png', 2400, 800, amber, 1560)
    card(lk + 'color-dark.svg', lk + 'on-ink.png', 2400, 800, INK, 1560)
    card(sy + 'color.svg', os.path.join(vdir, 'bilbo-icon-%s-on-white.png' % variant), 1024, 1024, '#FFFFFF', 520)
    card(sy + 'white.svg', os.path.join(vdir, 'bilbo-icon-%s-on-amber.png' % variant), 1024, 1024, amber, 520)
    card(sy + 'color-dark.svg', os.path.join(vdir, 'bilbo-icon-%s-on-ink.png' % variant), 1024, 1024, INK, 520)
    made += [lk + n for n in ('on-white.png', 'on-amber.png', 'on-ink.png')]

for v in VARIANTS:
    d = os.path.join(BASE, v)
    root = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
    print('%-8s raiz %3d | colors %3d | combos %3d'
          % (v, len(root), len(os.listdir(os.path.join(d, 'colors'))), len(os.listdir(os.path.join(d, 'combos')))))
print('total gerado:', len(made))

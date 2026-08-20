"""Build the contact sheets for each variant.

preview-<variant>-forms.png    every form in every treatment
preview-<variant>-colors.png   every colour, light and dark
preview-<variant>-combos.png   every per-lipid combination, light and dark

Run after generate.py. Requires rsvg-convert and ImageMagick.
"""
import os, subprocess, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
INK, WHITE, PAPER = '#1A1206', '#FFFFFF', '#E8E4DD'
VARIANTS = ['bilayer', 'grid']
FORMS = ['lockup', 'tagline', 'stacked', 'symbol']
COLORS = ['amber', 'mustard', 'gold', 'rust', 'olive', 'coral',
          'green', 'teal', 'cyan', 'blue', 'indigo', 'purple']
COMBOS = ['duo-amber-teal', 'duo-amber-blue', 'duo-amber-coral', 'duo-teal-purple',
          'duo-mustard-teal', 'duo-mustard-indigo', 'duo-mustard-rust', 'duo-gold-cyan',
          'duo-olive-mustard', 'trio-amber-teal-coral', 'trio-amber-purple-green',
          'trio-blue-coral-green', 'trio-mustard-rust-olive', 'trio-mustard-teal-indigo',
          'trio-gold-coral-cyan', 'spectrum', 'spectrum-warm', 'spectrum-cool',
          'grayscale-multi']


def raster(svg, width, out):
    subprocess.run(['rsvg-convert', '-w', str(width), svg, '-o', out], check=True)
    return out


def strip(files, bg, tile, geom, out):
    subprocess.run(['magick', 'montage'] + files +
                   ['-tile', tile, '-geometry', geom, '-background', bg, out], check=True)
    return out


def stack(rows, out, width=1500):
    subprocess.run(['magick'] + rows + ['-background', PAPER, '-gravity', 'center',
                                        '-append', '-resize', '%dx' % width, out], check=True)
    return out


def build(variant, tmp):
    v = os.path.join(BASE, variant)
    n = [0]

    def prep(paths, w=640):
        out = []
        for p in paths:
            n[0] += 1
            out.append(raster(p, w, os.path.join(tmp, '%s-%d.png' % (variant, n[0]))))
        return out

    def f(name):
        return os.path.join(v, name)

    def sub(folder, name):
        return os.path.join(v, folder, name)

    made = []

    # 1. forms and treatments
    rows = []
    for treat, bg in (('color', WHITE), ('black', WHITE), ('gray', WHITE),
                      ('color-dark', INK), ('white', INK)):
        files = [f('bilbo-%s-%s-%s.svg' % (form, variant, treat)) for form in FORMS]
        rows.append(strip(prep(files), bg, '4x', '330x150+14+14',
                          os.path.join(tmp, '%s-forms-%s.png' % (variant, treat))))
    made.append(stack(rows, os.path.join(BASE, 'preview-%s-forms.png' % variant)))

    # 2. colours
    rows = []
    light = [sub('colors', 'bilbo-lockup-%s-%s.svg' % (variant, c)) if c != 'amber'
             else f('bilbo-lockup-%s-color.svg' % variant) for c in COLORS]
    dark = [sub('colors', 'bilbo-lockup-%s-%s-dark.svg' % (variant, c)) if c != 'amber'
            else f('bilbo-lockup-%s-color-dark.svg' % variant) for c in COLORS]
    rows.append(strip(prep(light), WHITE, '4x', '330x130+14+14', os.path.join(tmp, variant + '-cl.png')))
    rows.append(strip(prep(dark), INK, '4x', '330x130+14+14', os.path.join(tmp, variant + '-cd.png')))
    lightsym = [sub('colors', 'bilbo-symbol-%s-%s.svg' % (variant, c)) if c != 'amber'
                else f('bilbo-symbol-%s-color.svg' % variant) for c in COLORS]
    rows.append(strip(prep(lightsym), WHITE, '12x', '110x130+10+10', os.path.join(tmp, variant + '-cs.png')))
    made.append(stack(rows, os.path.join(BASE, 'preview-%s-colors.png' % variant)))

    # 3. combinations
    rows = []
    light = [sub('combos', 'bilbo-lockup-%s-%s.svg' % (variant, c)) for c in COMBOS]
    dark = [sub('combos', 'bilbo-lockup-%s-%s-dark.svg' % (variant, c)) for c in COMBOS]
    rows.append(strip(prep(light), WHITE, '4x', '330x130+14+14', os.path.join(tmp, variant + '-kl.png')))
    rows.append(strip(prep(dark), INK, '4x', '330x130+14+14', os.path.join(tmp, variant + '-kd.png')))
    made.append(stack(rows, os.path.join(BASE, 'preview-%s-combos.png' % variant)))
    return made


with tempfile.TemporaryDirectory() as tmp:
    for variant in VARIANTS:
        for p in build(variant, tmp):
            print('escrito:', os.path.basename(p))
for old in ('preview-bilayer.png', 'preview-grid.png'):
    p = os.path.join(BASE, old)
    if os.path.exists(p):
        os.remove(p)
        print('removido:', old)

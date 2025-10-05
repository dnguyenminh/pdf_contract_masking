import fitz
import sys
p = sys.argv[1] if len(sys.argv)>1 else 'hop_dong_da_che_AI_Final/che_sample1.pdf'
print('Inspecting', p)
doc = fitz.open(p)
for i,page in enumerate(doc):
    print('--- page', i)
    # annotations
    ann = list(page.annots() or [])
    print(' annotations:', len(ann))
    for a in ann:
        print('  annot:', a.type[0], 'rect', a.rect, 'info', dict(a.info))
    # drawings
    try:
        draws = page.get_drawings()
        print(' drawings:', len(draws))
        for idx,d in enumerate(draws):
            print(' draw', idx, 'raw:', d)
            items = d.get('items') if isinstance(d, dict) else None
            if not items:
                # try to print repr
                print('  items repr:', repr(d))
                continue
            for item in items:
                # item can be varied; print repr to inspect
                print('   item repr:', repr(item))
                try:
                    itype = item[0]
                    props = item[1]
                    print('    type', itype)
                    if isinstance(props, dict):
                        print('    props keys', list(props.keys()))
                        print('    stroke', props.get('stroke'), 'fill', props.get('fill'))
                except Exception as e:
                    print('    could not parse item:', e)
    except Exception as e:
        print(' get_drawings error', e)
    # text chars
    try:
        chars = page.get_text('chars')
        print(' chars count', len(chars))
    except Exception as e:
        print(' get chars err', e)
print('done')

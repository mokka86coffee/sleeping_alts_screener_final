import json, re
from render_brief import render_brief
h = open('brief.html', encoding='utf-8').read()
st = json.loads(re.search(r'"stars"\s*:\s*(\[.*?\])\s*,\s*"market"', h, re.S).group(1))
try:
    mk = json.loads(re.search(r'"market"\s*:\s*(\{.*)\}\s*</script>', h, re.S).group(1))
except Exception:
    mk = {}
out = render_brief(st, mk)
doc = '<' + '!doctype html><meta charset=utf-8><body>' + out
open('brief_test.html', 'w', encoding='utf-8').write(doc)
print('brief_test.html записан ·', len(out), 'байт')
print('секция Пойдёт  :', out.count('Пойдёт?'))
print('под наблюдением:', out.count('Под наблюдением'))
print('режим в ленте  :', ('БИТКОИН' in out) or ('regime' in out))

# Подпись на панели: размер под чтение

## файл: `render/podium.py`

Применять ПОСЛЕ `patch-podium-notes.md`.

Подпись осталась в размере старых служебных строк — десять пикселей.
Рядом тикер идёт пятнадцатью, и на цилиндре, где панель ещё и
повёрнута, десятка не читается.

Полоса под графиком освободилась целиком: `.obp-art` кончается за 74
пикселя до низа рамки, и всё это место занимал блок чисел. Подпись
стояла в самом низу, оставляя над собой полсотни пустых пикселей.
Теперь она садится в середину полосы и получает размер, сравнимый с
тикером.

По центру, а не по левому краю: тикер и фигура над ней центрированы,
и подпись, прижатая влево, ломала ось панели.

### было

```python
.obp-note{position:absolute;left:12px;right:12px;bottom:11px;
  font-size:10px;line-height:1.45;letter-spacing:.03em;color:#B9C2CE}
.obp-note b{font-weight:600;color:#E3E8EF}
.obp-note b.up{color:#4FCF8A} .obp-note b.dn{color:#E8705A}
.obp-note b.am{color:#F0B85C}
.obp-note-q{display:block;margin-top:3px;font-size:9px;letter-spacing:.16em;
  text-transform:uppercase;color:#5A6270}
```

### стало

```python
.obp-note{position:absolute;left:10px;right:10px;bottom:24px;
  text-align:center;
  font-size:13px;line-height:1.4;letter-spacing:.02em;color:#D8E0EA;
  /* Тень под текстом: подпись лежит поверх подсветки рамки, и на
     светлом крае панели без неё теряется контраст. */
  text-shadow:0 1px 14px rgba(0,0,0,.75)}
.obp-note b{font-weight:600;color:#FFFFFF}
.obp-note b.up{color:#5FE39C} .obp-note b.dn{color:#FF8A72}
.obp-note b.am{color:#FFC96B}
.obp-note-q{display:block;margin-top:4px;font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:#7C8694}
```

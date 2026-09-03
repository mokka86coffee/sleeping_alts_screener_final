"""Сводка утра — СХЕМА.

ЧТО ЭТО. Вместо колоды страниц с белым листом — одна картина: в центре
светящийся кристалл, от него вниз ствол, от ствола влево-вправо ветви с
короткими мыслями прогона. Мысли не спускаются по стволу: у них три
гнезда в полосе под кристаллом, каждая следующая берёт следующее гнездо
по кругу, а видны всегда две — текущая и предыдущая. Читается за один
взгляд, а не листается.

ПОЧЕМУ ТАК. Прежняя сводка была светлым листом в белой рамке, и переход
в зал читался как переход на другой сайт: там тёмная синь с куполом
света, здесь бумага. Здесь взято поле зала (цвета сняты с его экрана),
его моноширинные подписи вразрядку, его тикеры антиквой. Экраны стали
одним помещением.

СОБЫТИЯ. Не колонка и не отдельная страница: справа всплывают пузыри,
по одному на событие, а под стволом снизу поднимается подпись — день и
название, — проступает на подъёме и тает наверху. Один круг событий
примерно равен показу всех мыслей, поэтому за сводку успевают пройти
все. Полные ноты живут в карточке зала, куда мы идём следом.

ДАННЫЕ. Те же, что у зала и прежней сводки: stars и market. Ничего не
вшито в разметку: изменился прогон — изменились мысли.

КОНТРАКТ С ОБОЛОЧКОЙ НЕ ИЗМЕНИЛСЯ. Документ живёт в кадре, ждёт
сообщения «показан» (иначе при тёплом кэше вся сцена отыгрывает под
лоадером), по окончании шлёт «доиграл» и гаснет; страховочный таймер на
случай, если очередь встанет. Выход досрочно: клик в любом месте, кроме
полосы навигации, и любая клавиша, кроме стрелок.

ИЗОЛЯЦИЯ. Документ несёт в себе ВЕСЬ общий CSS сайта — render_page
кладёт render_css.CSS в каждый экран, а там живут правила прежней
сводки на #obBrief и всём, что под ним. Поэтому разметка и стили схемы
лежат в ТЕНЕВОМ ДЕРЕВЕ на узле #obfHost: внешние правила внутрь не
проходят вовсе. Данные (#obfData) остаются в обычном дереве — их читает
письмо (send_brief_email.load_report_data).

ЗАМЕНА, А НЕ ПРАВКА. Прежний render_brief.py лежит рядом нетронутым:
render_page зовёт либо его, либо этот модуль — одна строка. Если схема
не приживётся, возврат тоже одной строкой.
"""

from __future__ import annotations

import json


def render_scheme(stars: list[dict], market: dict) -> str:
    # Режим по биткоину (31.08, перенос одобрен): REGIME_GATE.md —
    # в нижнюю ленту новостей: вердикт + четыре графы пузырями.
    try:
        import re as _re
        from pathlib import Path as _P
        _p = _P("REGIME_GATE.md")
        if not _p.exists():
            _p = _P(__file__).resolve().parent / "REGIME_GATE.md"
        if _p.exists():
            _md = _p.read_text(encoding="utf-8")
            _v = _re.search(r"ВЕРДИКТ[^:]*:\s*(.+)", _md)
            _rd = _re.search(r"## ЭТАЛОННОЕ ЧТЕНИЕ.*?\n(.*?)(?=\n## )",
                             _md, _re.S)
            # РАЗДЕЛЕНИЕ СЛОЁВ (31.08). Гейт заходил в схему дважды: и
            # ветвью «Биткоин · режим», и восемью пузырями в ленте. Лента
            # — события (что случилось и когда), гейт — фаза (где мы
            # вообще); фазовый текст занимал треть потока пузырей и
            # первым же пунктом подменял «ближайшее событие».
            # Теперь в ленте остаётся ОДИН пузырь — вердикт, как было
            # одобрено изначально; графы живут на своей ветви.
            _new = []
            if _v:
                _new.append({"kind": "regime", "days": 0, "running": True,
                             "title": "БИТКОИН: " +
                                      _v.group(1).strip().rstrip(".")})
            if _new:
                market = dict(market)
                _pp = dict(market.get("predictions") or {})
                _cal = dict(_pp.get("calendar") or {})
                _cal["items"] = _new + list(_cal.get("items") or [])
                _pp["calendar"] = _cal
                market["predictions"] = _pp
                market["regime"] = {
                    "verdict": (_v.group(1).strip().rstrip(".")
                                if _v else ""),
                    "rows": [[_h2.strip(), " ".join(_t2.split())[:150]]
                             for _h2, _t2 in
                             ((c.partition(":")[0], c.partition(":")[2])
                              for c in _re.findall(
                                  r"^\d\.\s+(.+?)(?=^\d\.|\Z)",
                                  _rd.group(1), _re.S | _re.M))][:8]
                    if _rd else []}
    except Exception:
        pass

    """Тело документа сводки-схемы. Данные вшиваются, а не читаются из окна."""
    _wh = {}
    try:
        import json as _j3
        from pathlib import Path as _P3
        _wf = _P3("output") / "whales.json"
        if not _wf.exists():
            _wf = _P3(__file__).resolve().parent / "output" / "whales.json"
        if _wf.exists():
            _wh = _j3.loads(_wf.read_text(encoding="utf-8"))
    except Exception:
        _wh = {}
    # МЕЛОЧЬ · КОГДА ХОДИТ (02.09, одобрено «огонь»): сводка из
    # alts_schedule.py --sync --regime --json. Нет файла — нет циферблата.
    _sc = None
    for _sp in (_P3("output") / "schedule.json",
                _P3(__file__).resolve().parent / "output" / "schedule.json"):
        if _sp.exists():
            try:
                _sc = json.loads(_sp.read_text(encoding="utf-8"))
            except ValueError:
                _sc = None
            break
    blob = json.dumps({"stars": stars, "market": market, "whales": _wh,
                       "sched": _sc},
                      ensure_ascii=False, separators=(",", ":"))
    # Данные идут в <script type="application/json">: внутри такого блока
    # браузер не разбирает разметку, и последовательность вроде </script>
    # в тексте поля не закроет скрипт раньше времени.
    safe = blob.replace("</", "<\\/")
    return (SCHEME_HTML
            + f'<script id="obfData" type="application/json">{safe}</script>'
            + SCHEME_JS)


SCHEME_HTML = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500&display=swap" rel="stylesheet">
<div class="obf-host" id="obfHost"></div>
<template id="obfTpl">
<style>
/* СХЕМА. Как в референсе: тёмная синь, в центре светящийся предмет,
   от него вниз ствол, от ствола влево-вправо выноски с короткими
   подписями. Предмет — кристалл скринера, светящийся бирюзой. Выноски
   — мысли брифа, по одной, появляются одна за другой и остаются:
   к концу весь бриф стоит перед глазами одной схемой. События —
   созвездие: цветные звёзды по полю, цвет по виду, выбранная горит
   ярче, а внизу карточка читает её; карточка сама идёт по звёздам. */
.obs{
  --ink:#e8ecfb; --ink2:#c9d2e8; --mut:#8b93bd; --lab:#98a0cc; --dim:#6c74a6;
  --cy:#7fe3d4; --acc:#ffb266; --up:#5fe39c; --dn:#ff8a72; --blue:#8ab4ff; --amber:#ffd166; --vio:#b07bff;
  --sans:'Inter',system-ui,'Helvetica Neue',Arial,sans-serif; --serif:Georgia,'Iowan Old Style','Times New Roman',serif;
  --mono:ui-monospace,Menlo,Consolas,monospace;
}
.obs{position:fixed;inset:0;overflow:hidden;font-family:var(--sans);font-weight:300;color:var(--ink);z-index:99999;
  /* поле зала, снято с его экрана: верх-центр #2e335c, светлее к куполу
     #3f3f67, углы #262b4e, низ #1b1c34; снизу синий купол и тёплый
     отсвет под волной, как там */
  background:
    radial-gradient(60% 52% at 50% 100%, rgba(60,110,220,.20), transparent 70%),
    radial-gradient(40% 30% at 50% 88%, rgba(120,70,40,.18), transparent 70%),
    radial-gradient(1100px 700px at 50% -5%, #3f3f67, #2b2e51 45%, #1b1c34 100%)}
/* ── КИТЫ · СТАЯ ПО МОНЕТАМ (31.08, вид утверждён): один пузырь —
   одна монета, внутри плавают её киты. Цвет кита = сторона, метка:
   + добрал, ✓ закрыл, пусто — открыл. Размер круга — деньги. ── */
/* ── ЧАСЫ · ЗАРЯД (03.09 вечер, выбран из шести языков) ──
   Сосуд наполняется к ближайшему событию: пусто — двенадцать часов до
   него, полно — оно идёт. Ждём — вода в гамме схемы (рост синий, как
   кристалл; слив роза), цифра главная. Идёт — сосуд включается: рост
   зеленоватый, слив красный, ореол дышит, главным словом «ИДЁТ».
   Под сосудом одной строкой ближайший рост и слив. Волна и дыхание —
   только transform, композитор, дёшево для планшета. */
.fib{position:absolute;left:30px;top:40px;width:150px;z-index:5;font-family:var(--mono)}
.fib svg{display:block;width:150px;height:150px;overflow:visible}
.fib .w1{animation:fibwave 9s linear infinite}
.fib .w2{animation:fibwave 14s linear infinite reverse}
@keyframes fibwave{to{transform:translateX(-92px)}}
.fib .breath{animation:fibbreath 2.4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes fibbreath{0%,100%{opacity:.28;transform:scale(1)}50%{opacity:.42;transform:scale(1.04)}}
.fib .colon{animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* полная таблица при наведении */
.full{position:absolute;left:calc(100% + 14px);top:24px;width:326px;padding:14px 18px 12px;
  border-radius:12px;border:1px solid rgba(232,236,251,.10);background:rgba(8,10,24,.78);
  backdrop-filter:blur(10px);opacity:0;transform:translateX(-8px);pointer-events:none;transition:.25s}
.fib:hover .full{opacity:1;transform:translateX(0);pointer-events:auto}
.full .sub{font-size:7.5px;letter-spacing:.14em;color:#454b6d;margin-bottom:9px;line-height:1.6}
.full table{width:100%;border-collapse:collapse}
.full th{font:600 7.5px Inter;letter-spacing:.24em;color:#454b6d;text-transform:uppercase;text-align:right;padding:0 0 5px 8px}
.full th:first-child{text-align:left;padding-left:0}
.full td{font-size:11px;letter-spacing:.06em;color:var(--lab);text-align:right;padding:4px 0 4px 8px;border-top:1px solid rgba(232,236,251,.05);white-space:nowrap}
.full td:first-child{text-align:left;padding-left:0;font-size:8px;letter-spacing:.22em;text-transform:uppercase;color:#7c88b0}
.full tr.up td{color:var(--cy)}.full tr.up td:first-child{color:rgba(159,240,230,.7)}
.full tr.dead td{color:#5d6488}
.full tr.dn td{color:var(--am)}.full tr.dn td:first-child{color:rgba(255,200,122,.7)}
.full td i{font-style:normal;font-size:8px;color:#454b6d;margin-left:6px}
.full .foot{margin-top:9px;font-size:8px;letter-spacing:.12em;line-height:1.8;color:#5d6488}
.full .foot b{font-weight:400;color:#8b93c4}.full .foot s{text-decoration:none;color:var(--cy)}.full .foot u{text-decoration:none;color:var(--am)}

.pods{position:absolute;right:2.5%;top:7%;width:min(400px,32vw);
  z-index:3;opacity:.92;pointer-events:none}
.pods h5{font:600 8px Inter,Arial;letter-spacing:.34em;color:#57708a;
  margin:0 0 18px;text-align:center}
/* ИМЯ МОНЕТЫ ЖИРНЫМ (02.09). Прежде было тонкое и с разрядкой —
   выглядело подписью. Теперь плотное, тяжёлое, без разрядки:
   имя работает фоном, по которому ходят киты. */
.pod{position:relative;margin:0 auto 8px;display:grid;place-items:center}
.pod .ttl{font:900 var(--fs,64px)/1 Inter,Arial;letter-spacing:-.03em;
  color:rgba(232,236,251,.10);white-space:nowrap;user-select:none;
  text-shadow:0 0 40px rgba(127,227,212,.12)}
.pod.s .ttl{text-shadow:0 0 40px rgba(240,179,86,.12)}
/* ДВЕ ПОЛОСЫ, ПО СТОРОНЕ НА КАЖДУЮ (02.09). Одна общая полоса
   врала по смыслу: «вышли» без стороны ничего не значит — выход из
   лонга и выход из шорта противоположны. Теперь лонги отдельно,
   шорты отдельно, у каждой доля открытых к закрытым. */
.pod .rr{position:absolute;left:50%;bottom:2px;transform:translateX(-50%);
  width:var(--rw,110px);display:grid;gap:5px}
.pod .rr .ln{display:grid;grid-template-columns:26px 1fr 34px;gap:6px;
  align-items:center;
  font:600 7.5px ui-monospace,Menlo,monospace;letter-spacing:.08em}
.pod .rr .nm{color:rgba(93,100,136,.9);text-align:right}
.pod .rr .bar{height:3px;border-radius:2px;overflow:hidden;position:relative;
  background:rgba(232,236,251,.07)}
.pod .rr .bar i{position:absolute;top:0;bottom:0;left:0;border-radius:2px}
.pod .rr .bar u{position:absolute;top:-2px;bottom:-2px;width:1px;
  background:rgba(232,236,251,.45)}
.pod .rr .num{color:rgba(93,100,136,.8);white-space:nowrap}
/* лонги — лайм, шорты — фиолет: те же цвета, что у самих китов */
.pod .rr .l i{background:linear-gradient(90deg,#9fe870,rgba(159,232,112,.4));
  box-shadow:0 0 7px rgba(159,232,112,.38)}
.pod .rr .l .nm{color:rgba(159,232,112,.75)}
.pod .rr .s2 i{background:linear-gradient(90deg,#b98cff,rgba(185,140,255,.4));
  box-shadow:0 0 7px rgba(185,140,255,.38)}
.pod .rr .s2 .nm{color:rgba(185,140,255,.75)}
.pod .rr .off{opacity:.28}
.pod .sub{position:absolute;bottom:-30px;left:0;right:0;text-align:center;
  font:400 7.5px ui-monospace,Menlo,monospace;letter-spacing:.18em;
  color:rgba(93,100,136,.85)}
/* КИТ. Размер уменьшен вдвое против прошлой попытки: огромный силуэт
   закрывал имя и превращался в пятно. Двадцать два на десять —
   читается как кит и не спорит с буквами. */
.pod .w{position:absolute;width:14px;height:6.6px;
  animation:sw 11s ease-in-out infinite}
.pod .w svg{width:100%;height:100%;display:block;overflow:visible}
.pod .w.l svg{color:#9fe870}
.pod .w.s svg{color:#b98cff}
.pod .w.done svg{opacity:.38}
.pod .w.live svg{opacity:1;
  filter:drop-shadow(0 0 3px currentColor) drop-shadow(0 0 8px currentColor)}
/* МЕТКА КОШЕЛЬКА (02.09). Две буквы после 0x — чтобы отличать
   китов друг от друга: один и тот же кошелёк может встретиться в
   нескольких монетах, и это видно только по метке. Держится у хвоста,
   мелко, чтобы не спорить с силуэтом. */
.pod .w b{position:absolute;right:100%;top:50%;margin:-5px 4px 0 0;
  font:600 8px ui-monospace,Menlo,monospace;letter-spacing:.04em;
  color:currentColor;opacity:.62;text-transform:uppercase;
  white-space:nowrap}
.pod .w.l b{color:#b6f096}
.pod .w.s b{color:#cdaaff}
.pod .w.done b{opacity:.34}
/* при зеркальном развороте метка не должна читаться задом наперёд */
/* Метка НИКОГДА не зеркалится (02.09). Прежде зеркалили весь <span>
   вместе с подписью, а её разворачивали обратно правилом по атрибуту
   style — селектор хрупкий, срабатывал не всегда, и часть меток шла
   задом наперёд. Теперь зеркалим ТОЛЬКО силуэт. */
.pod .w.flip svg{transform:scaleX(-1)}
.pod .w.flip b{right:auto;left:100%;margin:-5px 0 0 4px}
@keyframes sw{
  0%,100%{transform:translate(0,0) rotate(0deg)}
  25%{transform:translate(4px,-2px) rotate(-4deg)}
  50%{transform:translate(7px,0) rotate(0deg)}
  75%{transform:translate(4px,2px) rotate(4deg)}}

.top{position:absolute;left:48px;right:48px;top:26px;display:flex;justify-content:flex-end;align-items:center;gap:26px;z-index:5}
/* ЖУРНАЛ ПРОГНОЗОВ (01.09). Вход отсюда, а не из зала: список монет и
   так стоит первым экраном, и сравнивать прогноз с тем, что было,
   удобнее рядом с ним. Кальмар — знак страницы. */
.jrn{position:absolute;left:var(--axis,38%);top:17%;width:0;height:0;
  z-index:7;pointer-events:none;text-decoration:none}
/* Узел идёт слева направо перед кристаллом: по горизонтали — ровно,
   по вертикали — небольшой прогиб вниз посередине, отсюда лёгкая
   дуга. Назад возвращается прозрачным, чтобы не было видно рывка. */
.jrn .sat{position:absolute;left:0;top:0;width:0;height:0;
  pointer-events:none;animation:satX 12s linear infinite}
/* ДЁШЕВО ДЛЯ ПЛАНШЕТА (02.09). Движется только transform и opacity —
   это композитор, без перерисовки. Тень одна вместо двух, и элемент
   поднят на свой слой заранее (will-change), чтобы тень рисовалась
   один раз, а не каждый кадр. Кристалл при этом не трогается вовсе:
   узел на слое выше и за него не уходит. */
.jrn .sat{will-change:transform,opacity}
.jrn .sat i{position:absolute;left:-7px;top:-7px;width:14px;height:14px;
  border-radius:50%;pointer-events:auto;cursor:pointer;
  background:radial-gradient(circle at 50% 50%,#eafcff 0,#7fe3d4 28%,
    rgba(127,227,212,0) 70%);
  box-shadow:0 0 14px rgba(127,227,212,.6);
  will-change:transform;
  animation:satY 12s ease-in-out infinite}
@keyframes satX{
  0%   {transform:translateX(-150px);opacity:0}
  8%   {opacity:1}
  84%  {opacity:1}
  91.6%{transform:translateX(150px);opacity:0}
  91.7%{transform:translateX(-150px)}
  100% {transform:translateX(-150px);opacity:0}}
@keyframes satY{
  0%,91.6%,100%{transform:translateY(0)}
  45.8%{transform:translateY(24px)}}
.jrn .lbl{position:absolute;left:0;top:64px;transform:translateX(-50%);
  white-space:nowrap;font-family:var(--mono);font-size:9px;
  letter-spacing:.3em;text-transform:uppercase;color:#9fb8cc;
  opacity:0;transition:opacity .3s;pointer-events:none}
.jrn:hover .lbl{opacity:.85}
.logo{display:none;align-items:center;gap:12px;font-family:var(--mono);font-size:12.1px;letter-spacing:.34em;color:var(--lab)}
.logo .o{width:22px;height:22px;border-radius:50%;border:1px solid rgba(232,236,251,.35);display:grid;place-items:center;color:var(--cy);font-size:15.4px;box-shadow:0 0 12px rgba(127,227,212,.35)}
.stamp{font-family:var(--mono);font-size:11px;letter-spacing:.3em;text-transform:uppercase;color:var(--dim)}

/* ── КНОПКА ЗВУКА ──
   Браузеры не дают звуку играть сам: без касания или щелчка он
   блокируется, и обойти это нельзя. Поэтому кнопка, а не автозапуск.
   Появляется, только если файл озвучки существует, — на не-macOS его
   не будет вовсе, и кнопки тоже.
   Стоит слева вверху, напротив штампа прогона: два угла заняты
   поровну, и она не спорит с кристаллом по центру. */
.snd{position:absolute;left:48px;top:22px;z-index:6;display:none;
  align-items:center;gap:8px;padding:7px 13px 7px 10px;border-radius:999px;
  border:1px solid rgba(232,236,251,.16);background:rgba(255,255,255,.04);
  font-family:var(--mono);font-size:9px;letter-spacing:.26em;text-transform:uppercase;
  color:var(--lab);cursor:pointer;opacity:.55;transition:opacity .25s,border-color .25s}
.snd.on{display:flex}
.snd:hover{opacity:.9;border-color:rgba(232,236,251,.3)}
.snd i{display:block;width:11px;height:11px;position:relative}
/* Значок динамика: прямоугольник плюс треугольник, без картинок и
   шрифтов — иначе значок ждал бы загрузки вместе со шрифтом. */
.snd i::before{content:'';position:absolute;left:0;top:3px;width:4px;height:5px;
  background:currentColor}
.snd i::after{content:'';position:absolute;left:3px;top:0;width:0;height:0;
  border:5px solid transparent;border-left:6px solid currentColor;border-right:0}
/* Играет — значок пульсирует, чтобы было видно без звука. */
.snd.play i{animation:sndPulse 1.6s ease-in-out infinite}
@keyframes sndPulse{0%,100%{opacity:.5}50%{opacity:1}}

/* звёздная пыль */
.dust{position:absolute;inset:0;pointer-events:none;z-index:0}
/* пыль не мигает и не колется: точки размыты и мягко светятся, а не
   горят пикселем; цветные — крупнее и с ореолом */
/* пыль в цвет поля: серо-синяя, чуть светлее фона, без белого и без
   цветных — только зерно, не конфетти */
/* ПУЗЫРИ. Пыль не стоит, а всплывает: каждая точка идёт снизу вверх
   через весь экран за тридцать — семьдесят секунд, своей скоростью,
   и чуть покачивается вбок. Отрицательная задержка старта раскидывает
   их по высоте с первого кадра, чтобы не было пустого поля в начале.
   Движение только трансформацией, без пересчёта раскладки. */
/* только прямые потомки: точка внутри пузыря-новости — тоже <i>, и
   без «>» она получала бы собственный подъём поверх подъёма родителя,
   уезжая вдвое дальше своей подписи */
.dust > i{position:absolute;width:3px;height:3px;border-radius:50%;background:#a3abd8;opacity:.32;
  filter:blur(.6px);box-shadow:0 0 5px rgba(163,171,216,.45);
  animation:rise var(--t,50s) linear var(--d,0s) infinite, sway var(--w,8s) ease-in-out var(--d,0s) infinite alternate}
@keyframes rise{from{transform:translateY(0)}to{transform:translateY(-118vh)}}
@keyframes sway{from{margin-left:-4px}to{margin-left:4px}}
/* НОВОСТИ — ЭТО ПРАВЫЕ ПУЗЫРИ. Справа всплывают не пустые точки, а
   события: у каждого свой пузырь, чуть крупнее и светлее пыли, с едва
   заметным оттенком вида. Пока пузырь проходит середину экрана, слева
   от него проступает подпись — день и название, тем же тихим шрифтом,
   что на ветвях, — и тает, когда пузырь уходит выше. Пузыри идут
   друг за другом с равным шагом: в середине в каждый момент один-два.
   Никакого блока: новости живут в том же движении, что и поле. */
.news{position:absolute;top:100%;--kc:#8b93bd;
  animation:rise var(--t) linear var(--d) infinite}
/* МЕСТО ПУЗЫРЯ — БЕЗ ОГЛЯДКИ НА BODY. Раньше стояло «body.n1 .news»:
   в прототипе класс висел на body и работало, а здесь схема живёт в
   теневом дереве, куда body не достаёт — правило не совпадало ни разу,
   пузыри теряли left и уезжали в статическую позицию. Найдено 27.08:
   «пузырьки справа вообще пропали». */
.news{left:var(--xr)}
/* пузырь события — того же размера и вида, что пылинка слева; от неё
   отличается только едва заметным ореолом в цвет вида */
.news i{position:absolute;left:0;top:0;width:3px;height:3px;margin:-1.5px 0 0 -1.5px;border-radius:50%;
  background:#a3abd8;opacity:.34;filter:blur(.6px);box-shadow:0 0 6px var(--kc)}
/* НОВОСТЬ ВСПЛЫВАЕТ САМА. Раньше подпись висела на месте и только
   проступала — теперь весь блок поднимается снизу под стволом:
   выходит из-под нижнего края, идёт вверх примерно на треть экрана,
   проступает на подъёме и тает наверху. Рядом с ней всплывают
   несколько своих пузырьков, мельче общей пыли. Слой .tells не
   трансформируется сам, поднимаются его дети, поэтому позиции
   считаются честно. Каждая новость идёт по очереди: время цикла и
   задержка те же, что у пузырей справа. */
.tells{position:absolute;left:var(--axis,38%);bottom:4%;transform:translateX(-50%);width:760px;height:26vh;
  text-align:center;z-index:4;pointer-events:none}
.tells .tl{position:absolute;left:0;right:0;bottom:0;opacity:0;
  animation:tell1 var(--t) linear var(--d) infinite, float1 var(--t) linear var(--d) infinite}
/* три дорожки: соседние новости расходятся вбок и по высоте, поэтому
   их можно показывать разом, не накладывая одну на другую */
/* СТОЛБЕЦ, НО НЕ НИТЬ. Новости идут одной вертикалью под стволом и
   всё же не по одной линии: каждая сдвинута от центра на свою малую
   величину (--x, до сорока пикселей в любую сторону) и всплывает со
   своей скоростью (--sp, от девяноста до ста двадцати процентов
   общей). Разброс намеренно узкий: шире — столбец рассыпается, ровно
   ноль — идёт сплошной нитью.
   Скорость и высота связаны: кто быстрее, тот уходит дальше — путь
   считается как --sp от базовых двадцати шести процентов высоты окна,
   поэтому быстрая новость гаснет выше медленной. */
.tells .tl{width:340px;left:50%;right:auto;bottom:0;
  margin-left:calc(-170px + var(--x, 0px))}
/* всплывание на пятую часть быстрее: тот же путь проходится за
   меньшую долю цикла (было с 18% до 48%, стало с 18% до 42%).
   Дальность у каждой своя — множитель --sp. */
@keyframes float1{
  0%,18%{transform:translateY(0)}
  42%,100%{transform:translateY(calc(-26vh * var(--sp, 1)))}}
/* пузырьки новости — мельче пыли, всплывают вместе с ней */
.tells .tl u{position:absolute;bottom:-10px;width:2px;height:2px;border-radius:50%;display:block;
  background:#a3abd8;opacity:.3;filter:blur(.5px);box-shadow:0 0 4px var(--kc)}
.tells .tl u:nth-of-type(1){left:34%}
.tells .tl u:nth-of-type(2){left:50%;bottom:-24px;width:1.5px;height:1.5px}
.tells .tl u:nth-of-type(3){left:63%;bottom:-4px}
.tells .w{font-family:var(--mono);font-size:8.8px;letter-spacing:.3em;text-transform:uppercase;color:var(--lab);opacity:.8;display:block}
.tells .t{font-family:var(--serif);font-size:14.3px;line-height:1.35;color:#c9d2e8;display:block;margin-top:3px}
/* подпись видна, пока пузырь между сорока двумя и шестьюдесятью пятью
   процентами пути, то есть в середине экрана: в каждый момент видны
   одна-две; вход и выход по пять процентов пути */
/* ДВА МЕСТА ДЛЯ ПОДПИСЕЙ, переключаются классом на body.
   n1 — снизу по центру, под стволом: пузыри событий всплывают в
   центральной полосе, подпись под пузырём, видна, пока пузырь в
   нижней трети экрана, ниже конца ствола.
   n2 — справа вверху: пузыри справа, подпись слева от пузыря, видна
   только когда пузырь выше правой ветви на тридцать пикселей и больше,
   то есть в верхних тридцати процентах экрана. Старт у всех пузырей
   событий ровно с нижнего края, поэтому высота однозначно связана с
   долей пути и окно подписи считается точно. */
/* ОКНО НОВОСТИ: подпись живёт пятую часть цикла — при равном шаге
   между новостями это даёт на экране ровно две, не больше. Раньше
   окно было в треть, и их набиралось три. */
@keyframes tell1{0%,18%{opacity:0}21%,33%{opacity:.55}36%,100%{opacity:0}}
62%,74%{opacity:.5}79%,100%{opacity:0}}

.news.k-delist{--kc:#ff8a72}.news.k-unlock{--kc:#ffd166}.news.k-risk{--kc:#ffb266}.news.k-macro{--kc:#8ab4ff}.news.k-support{--kc:#5fe39c}

/* кристалл */
.orb{position:absolute;left:var(--axis,38%);top:17%;width:0;height:0;z-index:3;transform-style:preserve-3d;perspective:900px;
  animation:spin 44s linear infinite}
@keyframes spin{from{transform:rotateX(-14deg) rotateY(0) scale(var(--gs,1))}to{transform:rotateX(-14deg) rotateY(360deg) scale(var(--gs,1))}}
.orb .half{position:absolute;left:0;top:0;transform-style:preserve-3d}
.orb .half.b{transform:rotateX(180deg)}
/* РАЗМЫТЫЙ КРИСТАЛЛ. Размытие стоит на грани, а обрезка треугольника —
   на её вложенном слое: так размывается уже вырезанный треугольник и
   мягкими становятся сами рёбра. Размытие на всём кристалле нельзя:
   фильтр на родителе сплющил бы объём. */
.orb .f{position:absolute;left:-70px;top:-121px;width:140px;height:121px;transform-origin:50% 100%;
  filter:blur(1.6px);opacity:.9}
.orb .f s{position:absolute;inset:0;display:block;clip-path:polygon(50% 0,100% 100%,0 100%);
  background:linear-gradient(160deg,rgba(125,165,240,.58),rgba(90,125,220,.28) 60%,rgba(110,150,235,.42))}
.orb .f:nth-child(1){transform:rotateY(0deg) translateZ(70px) rotateX(35.26deg)}
.orb .f:nth-child(2){transform:rotateY(90deg) translateZ(70px) rotateX(35.26deg)}
.orb .f:nth-child(3){transform:rotateY(180deg) translateZ(70px) rotateX(35.26deg)}
.orb .f:nth-child(4){transform:rotateY(270deg) translateZ(70px) rotateX(35.26deg)}
.orb .half.b .f{opacity:.5}
.orb .half.b .f s{background:linear-gradient(160deg,rgba(95,130,225,.3),rgba(70,100,195,.1) 60%)}
/* ОРЕОЛ — ГУСТОЙ, как у референса: три отдельных слоя (не
   псевдоэлементы: размытие родителя ломает их положение). Ядро —
   плотный бирюзово-белый свет размером с кристалл, сложен со светом;
   средний — бирюза на полтора кристалла; внешний — широкая синь на три.
   Каждый слой дышит в своём ритме, потому свет живой, а не блин. */
.halo{position:absolute;left:var(--axis,38%);top:17%;border-radius:50%;z-index:2;pointer-events:none;mix-blend-mode:screen}
/* яркость: две трети от самой густой версии (втрое тише было слишком) */
/* СВЕТ — СИНИЙ И ТИХИЙ. Не голубой прожектор, а синева на несколько
   тонов светлее поля: кристалл выделяется, не слепит. Ядро — синь с
   лёгкой голубизной на треть прозрачности, дальше всё глубже в цвет
   поля. Сложение со светом снято: оно и делало белёсое пятно. */
.halo{mix-blend-mode:normal}
.halo.h1{width:340px;height:340px;margin:-170px 0 0 -170px;
  background:radial-gradient(closest-side,rgba(110,150,240,.38),rgba(90,130,225,.24) 30%,rgba(75,110,205,.10) 60%,transparent 100%);
  filter:blur(16px);animation:halo 5s ease-in-out infinite}
.halo.h2{width:600px;height:600px;margin:-300px 0 0 -300px;
  background:radial-gradient(closest-side,rgba(90,130,225,.16),rgba(75,110,205,.06) 50%,transparent 100%);
  filter:blur(26px);animation:halo2 7s ease-in-out infinite}
.halo.h3{width:960px;height:960px;margin:-480px 0 0 -480px;
  background:radial-gradient(closest-side,rgba(75,115,215,.08),rgba(60,90,190,.03) 55%,transparent 100%);
  filter:blur(36px);animation:halo2 9s ease-in-out infinite reverse}
@keyframes halo{0%,100%{transform:scale(.94);opacity:.85}50%{transform:scale(1.06);opacity:1}}
@keyframes halo2{0%,100%{transform:scale(.96);opacity:.8}50%{transform:scale(1.05);opacity:1}}
.orbcap{display:none;position:absolute;left:var(--axis,38%);top:calc(17% + 118px);transform:translateX(-50%);font-family:var(--mono);font-size:9.9px;letter-spacing:.34em;
  text-transform:uppercase;color:var(--cy);text-shadow:0 0 10px rgba(127,227,212,.6);white-space:nowrap;z-index:4}

/* СТВОЛ И ВЕТВИ — ПОЧТИ В ЦВЕТ ПОЛЯ. Линии на полтона светлее фона,
   без свечения: каркас угадывается, а не читается. Узлы — едва видные
   точки. Текст полупрозрачный — как надпись сквозь стекло. */
.trunk{position:absolute;left:var(--axis,38%);top:calc(17% + 140px);bottom:90px;width:1px;background:rgba(232,236,251,.07);
  transform:scaleY(0);transform-origin:top;animation:grow 3.2s cubic-bezier(.22,.61,.36,1) .6s forwards;z-index:3}
@keyframes grow{to{transform:scaleY(1)}}
/* НЕ БОЛЬШЕ ДВУХ РАЗОМ. Появление — медленное, три с половиной
   секунды; уход — ещё медленнее, четыре. Ничего не выскакивает и
   ничего не обрывается: одна мысль тает, пока следующая проступает. */
/* ОСЬ СЦЕНЫ (02.09). Кристалл, ствол, ветви и новости стояли по
   центру и налезали на стаю справа. Ось в переменной, сдвинута
   влево — двигается всё разом. На узком экране возвращается в
   центр: стая там уходит вниз. */
.co{position:absolute;left:var(--axis,38%);width:0;height:0;z-index:4}
.co .node{position:absolute;left:-2.5px;top:-2.5px;width:5px;height:5px;border-radius:50%;background:rgba(232,236,251,.28);
  transform:scale(0);transition:transform 1s cubic-bezier(.22,.61,.36,1)}
.co.on .node{transform:scale(1)}
.co .ln{position:absolute;top:0;height:1px;width:150px;background:rgba(232,236,251,.09);transform:scaleX(0);
  transition:transform 1.5s cubic-bezier(.22,.61,.36,1) .25s}
.co.l .ln{right:0;transform-origin:right}
.co.r .ln{left:0;transform-origin:left}
.co.on .ln{transform:scaleX(1)}
/* ПОТОЛОК ВЕТВИ (правка 01.09). Нота ограничена тремя строками, но
   высота ветви складывается из метки, подписи, значения И ноты — а
   значение с 01.09 несёт тикер и полное имя шаблона и легко идёт в
   две строки. В сумме ветвь перерастала шаг гнёзд и наезжала на
   соседнюю. Потолок привязан к САМОМУ шагу через переменную --slot,
   которую ставит JS: шаг меняется от высоты окна, и потолок обязан
   меняться вместе с ним. */
.co .txt{max-height:calc(var(--slot,124px) - 18px);overflow:hidden;
  position:absolute;top:-10px;width:min(330px,42vw);opacity:0;transform:translateY(6px);
  transition:opacity 2.6s ease .8s,transform 2.6s cubic-bezier(.22,.61,.36,1) .8s}
.co.on .txt{opacity:.7;transform:none}
.co.off .txt{opacity:0;transform:translateY(-4px);transition:opacity 3s ease,transform 3s ease}
.co.off .ln{transform:scaleX(0);transition:transform 3s ease}
.co.off .node{transform:scale(0);transition:transform 3s ease}
.co.l .txt{right:164px;text-align:right}
.co.r .txt{left:164px}
/* текст вдвое мельче и ближе к полю: цифра пятнадцать, подписи семь
   и восемь с половиной, цвета не белые, а серо-синие, как у подписей */
.co .k{font-family:var(--mono);font-size:8.8px;letter-spacing:.3em;text-transform:uppercase;color:var(--lab);opacity:.7}
/* Прогнозы по монетам (31.08): имя монеты белым и крупнее — это
   заголовок мысли, а не служебная метка ветви. */
.co .k.kgo{font-size:13.5px;letter-spacing:.14em;color:#ffffff;opacity:.95;
  font-weight:500}
/* ── МЕТКА ГОРИЗОНТА (31.08) ──
   Одна метка вместо двух: слой не подписан отдельно, он читается из
   горизонта — полгода и недели это фаза (только факты), дни и часы
   это события (машина отвечает «когда»). Точка светится цветом
   горизонта; на левых ветвях порядок зеркалится, чтобы точка смотрела
   в поле, а не в текст. */
.co .hz{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);
  font-size:7.6px;letter-spacing:.3em;text-transform:uppercase;
  color:var(--hz,#cfd8ef);opacity:.7;margin-bottom:5px}
.co .hz::before{content:'';width:4px;height:4px;border-radius:50%;flex:0 0 4px;
  background:var(--hz,#cfd8ef);box-shadow:0 0 8px var(--hz,#cfd8ef)}
.co.l .hz{flex-direction:row-reverse}
/* ЦВЕТА НА ВЕТВЯХ — ТОЛЬКО ХОЛОДНЫЕ. Значение берёт свой оттенок из
   узкой холодной гаммы: бирюза, голубой, васильковый, светлая сталь,
   лавандовый. Тёплого нет вовсе — ни жёлтого, ни красного, — иначе
   рябит; разница между мыслями читается тоном, а не яркостью. */
.co .v{font-weight:200;font-size:19.8px;line-height:1.1;color:var(--vc,#dbe3f7);margin-top:3px}
/* строка целиком: обрезки по двум строкам больше нет, длинные списки
   переносятся; блок шире, чтобы переносов было меньше */
/* ВЫСОТА НОТЫ ОГРАНИЧЕНА. Гнёзда стоят с фиксированным шагом, а нота
   растёт по содержимому: у «ближайшего события» она в четыре строки, и
   хвост залезал на соседнюю ветвь — на кадре 27.08 «разбирают» ушло
   под текст STORJ. Ограничение по числу строк, а не по пикселям:
   шрифт может смениться, строки — нет. Лишнее обрезается многоточием,
   полный текст есть в зале. */
.co .s{font-size:11px;line-height:1.55;color:#aab2cc;margin-top:3px;opacity:.75;
  display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden;-webkit-line-clamp:3}
.co .s b{color:#c9d2e8;font-weight:500}
.co .tkr{font-family:var(--serif);color:#c9d2e8}
/* ИМЯ ШАБЛОНА ВЫДЕЛЕНО (правка 01.09). Значение ветви несёт тикер и
   имя сюжета, и раньше они шли одним весом — глаз не находил, что
   здесь главное. Тикер антиквой, имя плотнее и светлее, разделитель
   приглушён. */
.co .v b{font-weight:500;color:#ffffff;letter-spacing:.005em}
.co .v s{text-decoration:none;opacity:.42;margin:0 .28em;font-weight:200}

/* созвездие событий */
/* имён у звёзд нет: звезда — это только цвет и место, читает её карточка внизу */
.k-delist{--kc:#ff8a72}.k-unlock{--kc:#ffd166}.k-risk{--kc:#ffb266}.k-macro{--kc:#8ab4ff}.k-support{--kc:#5fe39c}

/* управление */
.nav{position:absolute;left:48px;right:48px;bottom:26px;display:flex;align-items:center;gap:16px;z-index:6}
.arrow{width:34px;height:34px;border-radius:50%;border:1px solid rgba(232,236,251,.28);display:grid;place-items:center;cursor:pointer;user-select:none;background:rgba(255,255,255,.04);opacity:.5}
.arrow.off{opacity:.12}
.count{font-family:var(--mono);font-size:11px;letter-spacing:.3em;color:var(--dim)}
.ticks{display:flex;gap:5px;flex:1 1 auto}
/* полоски почти прозрачные: дорожка едва угадывается, пройденное —
   бледная бирюза без свечения; за что кликать, видно, но глаз не цепляет */
.tk{height:2px;flex:1;background:rgba(232,236,251,.04);cursor:pointer;position:relative}
.tk i{position:absolute;inset:0;width:0;background:rgba(127,227,212,.16);display:block}
.tk.done i{width:100%}

/* ── УЗКИЕ ЭКРАНЫ ──
   Слева-справа от ствола на телефоне места нет: выноска в триста
   пикселей уезжает за край. Поэтому на узком мысль встаёт ПОД своим
   узлом по центру, а горизонтальная ветвь убирается — ствол с узлами
   остаётся, читается как нить с бусинами. */
@media (max-width:900px){
  .obs{--axis:50%}
  .co .ln{display:none}
  .co .txt,.co.l .txt,.co.r .txt{left:50%;right:auto;top:14px;width:min(86vw,360px);
    transform:translateX(-50%) translateY(6px);text-align:center}
  .co.on .txt{transform:translateX(-50%)}
  .co.off .txt{transform:translateX(-50%) translateY(-4px)}
  .tells{width:min(92vw,520px)}
  .nav{left:20px;right:20px;bottom:18px}
  }
/* ── НИЗКИЕ ЭКРАНЫ (телефон поперёк) ──
   По высоте всего четыреста точек: кристалл ужимается, ореол вместе с
   ним, полоса новостей ниже. Гнёзда мыслей скрипт считает сам от
   высоты окна — см. SLOT ниже. */
@media (max-height:560px){
  .orb{--gs:.58}
  .halo.h1{width:200px;height:200px;margin:-100px 0 0 -100px}
  .halo.h2{width:360px;height:360px;margin:-180px 0 0 -180px}
  .halo.h3{width:560px;height:560px;margin:-280px 0 0 -280px}
  .tells{height:24vh;bottom:4%}
  .co .v{font-size:17.6px}
  .co .s{font-size:10.5px}
}
</style>
<div class="obs">
  <div class="dust" id="dust"></div>
  <div class="snd" id="snd"><i></i><span id="sndTxt">слушать</span></div>
  <div class="top">
    <div class="stamp" id="stamp"></div><!-- штамп справа от кальмара -->
  </div>
  <div class="halo h3"></div><div class="halo h2"></div><div class="halo h1"></div>
  <!-- ЖУРНАЛ — узел перед кристаллом (02.09). Без SVG-пути и
       пересчётов: обычный элемент с CSS-анимацией. Идёт слева направо
       по слегка выгнутой дуге, всегда ПЕРЕД кристаллом, и уходит
       обратно за кадром. Узел и есть кнопка; подпись при наведении. -->
  <a class="jrn" href="journal.html" title="журнал прогнозов">
    <span class="sat"><i></i></span>
    <span class="lbl">журнал прогнозов</span>
  </a>
  <div class="orb">
    <div class="half"><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i></div>
    <div class="half b"><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i></div>
  </div>
  <div class="trunk"></div>
  <div id="cos"></div>
  <div id="stars" class="dust"></div>
  <!-- ОТРАЖЕНИЕ (референс VIVERA): сцена стоит на мокрой поверхности,
       это даёт кадру опору. Низ был пустым. -->
  <div class="nav">
    <div class="arrow" id="prev">&#8592;</div>
    <div class="arrow" id="next">&#8594;</div>
    <div class="count" id="count"></div>
    <div class="ticks" id="ticks"></div>
  </div>
</div>
</template>
"""


SCHEME_JS = r"""
<script>
(function () {
  var DATA = {};
  try { DATA = JSON.parse(document.getElementById('obfData').textContent); }
  catch (e) { DATA = {}; }
  var ST = DATA.stars || [], M = DATA.market || {};
  var P = M.permission || {}, pp = P.parts || {};

  /* Обёртка от оболочки: класс .on снимает прозрачность. Внутрь неё
     ничего не рисуем — всё в теневом дереве. */
  var wrap = document.getElementById('obBrief')
          || document.querySelector('.ob-brief')
          || document.body;

  /* ТЕНЕВОЕ ДЕРЕВО. Разметка и стили лежат в <template> — там они
     инертны, общий CSS документа их не видит. Клонируем в shadow root
     узла #obfHost: с этого момента внешние правила внутрь не проходят.
     Нет узла или шаблона — это ошибка сборки, и молчать о ней нельзя. */
  var host = document.getElementById('obfHost');
  var tpl  = document.getElementById('obfTpl');
  if (!host || !tpl || !tpl.content) throw new Error('схема: нет #obfHost или #obfTpl');
  var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  root.appendChild(tpl.content.cloneNode(true));
  function q(sel){ return root.querySelector(sel); }
  /* ── мелочь · когда ходит: ЗАРЯД (03.09 вечер, выбран из шести языков; нити сняты) ── */
  (function(){
    if (!DATA.sched || !DATA.sched.pump) return;
    var stage = q('.obs') || root.firstElementChild;
    if (!stage) return;
    stage.insertAdjacentHTML('beforeend', '<div class="fib" id="fib"></div>');
    var pick = q;              /* внутри build() есть свои var q — точки кольца */
    var S = DATA.sched;
    var DN=['пн','вт','ср','чт','пт','сб','вс'], NYZ='America/New_York';
    function nyHourToLocal(h){var now=new Date();
      var p=new Intl.DateTimeFormat('en-US',{timeZone:NYZ,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
      var y=+p.find(x=>x.type==='year').value,m=+p.find(x=>x.type==='month').value,d=+p.find(x=>x.type==='day').value;
      var g=Date.UTC(y,m-1,d,h,0,0);
      for(var k=0;k<3;k++){var f=new Intl.DateTimeFormat('en-US',{timeZone:NYZ,hour:'2-digit',hour12:false,day:'2-digit'}).formatToParts(new Date(g));
        var hh=+f.find(x=>x.type==='hour').value%24,dd=+f.find(x=>x.type==='day').value;var diff=(h-hh)+(d-dd)*24;if(!diff)break;g+=diff*3600000;}
      return new Date(g).getHours();}
    function pad(n){return (n<10?'0':'')+n;}
    
    function len(s){var l=((s[1]+1-s[0])%24+24)%24;return l||24;}

    function build(){
      var now=new Date(), lh=now.getHours()+now.getMinutes()/60;
      var ups=S.pump.map(function(s){return [nyHourToLocal(s[0]),nyHourToLocal(s[1])];});
      var dns=S.dump.map(function(s){return [nyHourToLocal(s[0]),nyHourToLocal(s[1])];});
      var dead=S.dead.map(function(s){return [nyHourToLocal(s[0]),nyHourToLocal(s[1])];});
      /* ВНУТРИ ОКНА (владелец, 03.09): раньше центр считал до начала того
         же окна завтра — «до роста 22 ч» посреди роста. Теперь: если
         «сейчас» внутри окна — показываем, что оно идёт и сколько
         осталось до его конца; иначе — до ближайшего начала. */
      var wins=[];ups.forEach(function(w){wins.push({h:w[0],e:w[0]+len(w),k:'up'});});dns.forEach(function(w){wins.push({h:w[0],e:w[0]+len(w),k:'dn'});});
      var inside=null;
      wins.forEach(function(w){var rel=(lh-w.h+24)%24; if(rel<w.e-w.h){inside={k:w.k,left:w.e-w.h-rel};}});
      /* Ближайшее начало окна ДРУГОГО вида — даже если своё ещё идёт
         (03.09: рост 19-21 и слив 21 пересекались, виджет показывал
         «рост ещё 2 ч» за час до слива). Показываем то, что раньше:
         конец своего окна или начало чужого. */
      var ev=wins.map(function(w){return {h:w.h,k:w.k,dh:(w.h-lh+24)%24};}).sort(function(a,b){return a.dh-b.dh;});
      var nxt, inH, inM, live=false;
      if(inside){
        var other=ev.filter(function(e){return e.k!==inside.k;})[0];
        if(other && other.dh<inside.left){ nxt=other; inH=Math.floor(other.dh); inM=Math.round((other.dh-inH)*60); }
        else { live=true; nxt={k:inside.k}; inH=Math.floor(inside.left); inM=Math.round((inside.left-inH)*60); }
      } else { nxt=ev[0]; inH=Math.floor(nxt.dh); inM=Math.round((nxt.dh-inH)*60); }
    
      /* ЦВЕТ ВОДЫ: ждём — в гамме схемы (рост синий, как кристалл; слив
         приглушённая роза); идёт — сосуд включается: рост зеленоватый,
         слив красный (решение владельца 03.09 вечером). */
      var WATER = {
        'up0': {nc:'#a6bcff', top:'#a6bcff', body:'#6b82e0', deep:'#3a4aa6', halo:'#7f93e8'},
        'up1': {nc:'#b9f5d3', top:'#a8f0c8', body:'#4fc08a', deep:'#1f6e52', halo:'#6fd9a8'},
        'dn0': {nc:'#f1b3e0', top:'#f1b3e0', body:'#b878cc', deep:'#6a3f8c', halo:'#c48ad6'},
        'dn1': {nc:'#ffc4b8', top:'#ffb3a7', body:'#e0605a', deep:'#7a2a30', halo:'#e07a78'}};
      var wtr = WATER[nxt.k+(live?'1':'0')], nc = wtr.nc;
      var LAV='#c3cdf2', DIMT='#8f98c8', INK='#e8ecfb';
      var W=150, H=150, cx=66, cy=70, r=44, L=2*r+4;
      /* ЗАРЯД: доля наполнения. Двенадцать часов до события — пусто,
         событие идёт — полно. */
      var left=inH+inM/60, fill = live ? .97 : Math.max(.05, Math.min(.97, 1-left/12));
      var lvl = cy + r - fill*2*r;
      function nearest(ws){var best=null;ws.forEach(function(w){var d=(w[0]-lh+24)%24;if(best===null||d<best.d)best={d:d,h:w[0]};});return best;}
      var nu=nearest(ups), nd=nearest(dns);
      function hh(x){return pad(Math.round(x)%24)+':00';}
      var s='<svg viewBox="0 0 '+W+' '+H+'"><defs>'+
       '<filter id="fibGlow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.6"/></filter>'+
       '<filter id="fibHalo" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="7"/></filter>'+
       '<linearGradient id="fibNum" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#eef2ff"/><stop offset="1" stop-color="'+nc+'"/></linearGradient>'+
       '<radialGradient id="fibAura" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="'+wtr.halo+'" stop-opacity=".30"/><stop offset=".55" stop-color="'+wtr.halo+'" stop-opacity=".14"/><stop offset="1" stop-color="'+wtr.halo+'" stop-opacity="0"/></radialGradient>'+
       '<radialGradient id="fibDisc" cx="50%" cy="30%" r="75%"><stop offset="0" stop-color="#2a3058"/><stop offset=".7" stop-color="#1a1e40"/><stop offset="1" stop-color="#141733"/></radialGradient>'+
       '<linearGradient id="fibLiq" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="'+wtr.top+'" stop-opacity=".9"/><stop offset=".3" stop-color="'+wtr.body+'" stop-opacity=".82"/><stop offset="1" stop-color="'+wtr.deep+'" stop-opacity=".78"/></linearGradient>'+
       '<linearGradient id="fibRim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".34"/><stop offset=".5" stop-color="#ffffff" stop-opacity=".08"/><stop offset="1" stop-color="#ffffff" stop-opacity=".16"/></linearGradient>'+
       '<clipPath id="fibClip"><circle cx="'+cx+'" cy="'+cy+'" r="'+r+'"/></clipPath>'+
       '</defs>';
      /* ореол как у кристалла (чёрной подложки нет — от неё был резкий переход) */
      s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+(r+22)+'" fill="url(#fibAura)"/>';
      if (live){
        s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+(r+3)+'" fill="none" stroke="'+wtr.halo+'" stroke-width="10" opacity=".28" filter="url(#fibHalo)" class="breath"/>';
        s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+(r+2.5)+'" fill="none" stroke="'+nc+'" stroke-width="1" opacity=".5"/>';
      }
      s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="url(#fibDisc)" opacity=".9"/>';
      /* ЖИДКОСТЬ: две волны, каждая шире диска на два периода, чтобы
         бег по кругу (translateX на длину L) был бесшовным — три
         полных периода на длину L. Обрезаны кругом. */
      s+='<g clip-path="url(#fibClip)">';
      [[2.2,0,.95,'w1'],[1.6,1.9,.6,'w2']].forEach(function(wv){
        var amp=wv[0], ph=wv[1], op=wv[2], x0=cx-r-2;
        var d='M'+(x0-L).toFixed(1)+','+lvl.toFixed(1);
        for(var k=0;k<=180;k++){var x=x0-L+k*(3*L)/180; var y=lvl+Math.sin((x-x0)/L*Math.PI*2*3+ph)*amp; d+=' L'+x.toFixed(1)+','+y.toFixed(1);}
        d+=' L'+(x0+2*L).toFixed(1)+','+(cy+r+2)+' L'+(x0-L).toFixed(1)+','+(cy+r+2)+' Z';
        s+='<g class="'+wv[3]+'"><path d="'+d+'" fill="url(#fibLiq)" opacity="'+op+'"/>'+
           '<path d="'+d+'" fill="none" stroke="#ffffff" stroke-width=".8" opacity="'+(op*.55).toFixed(2)+'" filter="url(#fibGlow)"/></g>';
      });
      s+='<ellipse cx="'+(cx-18)+'" cy="'+(lvl+6).toFixed(1)+'" rx="14" ry="3" fill="#fff" opacity=".10" filter="url(#fibGlow)"/>';
      [[cx-18,lvl+14,1.2],[cx+11,lvl+26,.9],[cx-4,lvl+38,1.4],[cx+22,lvl+9,.7]].forEach(function(b){
        if (b[1] < cy+r) s+='<circle cx="'+b[0].toFixed(1)+'" cy="'+b[1].toFixed(1)+'" r="'+b[2]+'" fill="#fff" opacity=".4"/>';});
      s+='</g>';
      s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="url(#fibRim)" stroke-width="1"/>';
      /* ЦИФРА: свет слоями, градиент к цвету воды */
      function bignum(x,y,size,weight){var t='';
        [[size*.22,.06],[size*.12,.10],[size*.055,.2]].forEach(function(g){
          t+='<text x="'+x+'" y="'+y+'" text-anchor="middle" font-family="Inter,Arial" font-weight="'+weight+'" font-size="'+size+'" fill="none" stroke="'+nc+'" stroke-width="'+g[0].toFixed(2)+'" stroke-linejoin="round" opacity="'+g[1]+'">'+inH+':'+pad(inM)+'</text>';});
        t+='<text x="'+x+'" y="'+y+'" text-anchor="middle" font-family="Inter,Arial" font-weight="'+weight+'" font-size="'+size+'" fill="url(#fibNum)">'+inH+'<tspan class="colon" fill="'+nc+'">:</tspan>'+pad(inM)+'</text>';
        return t;}
      if (!live){
        /* ждём — цифра главная */
        s+=bignum(cx,cy+3,27,200);
        s+='<text x="'+cx+'" y="'+(cy+15)+'" text-anchor="middle" font-family="Inter,Arial" font-weight="400" font-size="5.8" fill="'+LAV+'" letter-spacing=".32em">ДО '+(nxt.k==='up'?'РОСТА':'СЛИВА')+'</text>';
      } else {
        /* идёт — главное слово, цифра ниже и меньше с «ещё» */
        var lab=(nxt.k==='up'?'РОСТ':'СЛИВ')+' ИДЁТ';
        s+='<text x="'+cx+'" y="'+(cy+1)+'" text-anchor="middle" font-family="Inter,Arial" font-weight="500" font-size="9.5" fill="none" stroke="'+nc+'" stroke-width="2.4" opacity=".3" letter-spacing=".3em" filter="url(#fibGlow)">'+lab+'</text>';
        s+='<text x="'+cx+'" y="'+(cy+1)+'" text-anchor="middle" font-family="Inter,Arial" font-weight="500" font-size="9.5" fill="#ffffff" letter-spacing=".3em">'+lab+'</text>';
        s+='<text x="'+cx+'" y="'+(cy+12)+'" text-anchor="middle" font-family="Inter,Arial" font-weight="400" font-size="6" fill="'+LAV+'" letter-spacing=".26em">ЕЩЁ</text>';
        s+=bignum(cx,cy+27,14,300);
      }
      /* ПОДПИСИ ПОД СОСУДОМ: одной строкой, в цветах текста схемы */
      s+='<text x="'+cx+'" y="'+(cy+r+19)+'" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="9" letter-spacing=".14em">'+
         (nu?'<tspan fill="'+DIMT+'">РОСТ </tspan><tspan fill="'+INK+'">'+hh(nu.h)+'</tspan>':'')+
         (nu&&nd?'<tspan fill="'+DIMT+'">  ·  </tspan>':'')+
         (nd?'<tspan fill="'+DIMT+'">СЛИВ </tspan><tspan fill="'+INK+'">'+hh(nd.h)+'</tspan>':'')+'</text>';
      /* сильный день — в правом верхнем углу */
      var dow=(now.getDay()+6)%7, tom=(dow+1)%7;
      var st=S.days_best.indexOf(dow)>=0, stt=S.days_best.indexOf(tom)>=0;
      if (st||stt) s+='<text x="'+(W-6)+'" y="12" text-anchor="end" font-family="ui-monospace,Menlo,monospace" font-size="6" letter-spacing=".26em" fill="'+LAV+'" opacity=".9">'+(st?'СИЛЬНЫЙ ДЕНЬ':'ЗАВТРА СИЛЬНЫЙ ДЕНЬ')+'</text>';
      s+='</svg>';
    
      function tz(h,o){return pad((h+o+24)%24);}function sp(g,o){return g[0]===g[1]?tz(g[0],o):tz(g[0],o)+'–'+tz(g[1],o);}
      function row(c,n,segs,note){return segs.map(function(g,i){return '<tr class="'+c+'"><td>'+(i?'':n)+'</td><td>'+sp(g,0)+'</td><td>'+sp(g,7)+'</td><td>'+sp(g,13)+(i===0&&note?'<i>'+note+'</i>':'')+'</td></tr>';}).join('');}
      var Rg=S.regime;
      var full='<div class="full"><div class="sub">'+S.coins+' монет · полгода · биткоин стоит<br>≥6 монет вверх, ≥10 вниз в один час</div>'+
       '<table><tr><th></th><th>Нью-Йорк</th><th>Москва</th><th>Токио</th></tr>'+
       row('up','пампы',S.pump,tz(S.pump_main,0)+' · '+S.pump_main_n+' соб.')+row('dead','мёртво',S.dead,'')+row('dn','слив',S.dump,'×'+S.dump_main_ratio+' к любому')+
       '</table><div class="foot">лучшие дни: <b>'+S.days_best.map(function(d){return DN[d];}).join(' · ')+'</b><br>'+
       'биткоин стоит <s>'+Rg.flat[0]+'/'+Rg.flat[1]+'</s> · растёт <u>'+Rg.up[0]+'/'+Rg.up[1]+'</u> · падает <s>'+Rg.down[0]+'/'+Rg.down[1]+'</s><br>отскоки на падении — с '+tz(S.bounce_hour,0)+' NY</div></div>';
      var host = pick('#fib'); if (host) host.innerHTML = s + full;
    }

    /* ЖИВОЙ СЧЁТЧИК (03.09). Он считается от часов браузера, прогон ему
       не нужен. Но схема в оболочке живёт в скрытом окне, пока идут
       другие экраны, и браузер там замораживает таймеры — при возврате
       показывалось число с прошлого раза. Поэтому пересчёт: по
       сигналу оболочки «показана», при возврате вкладки, и по таймеру
       раз в 15 секунд. Каждый вызов под защитой — одно падение не
       должно убить таймер. */
    function safeBuild(){ try { build(); } catch (e) {} }
    safeBuild();
    setInterval(safeBuild, 15000);
    try {
      window.addEventListener('message', function(e){
        if (e.data && e.data.type === 'ob:shown') safeBuild();
      });
      document.addEventListener('visibilitychange', function(){
        if (!document.hidden) safeBuild();
      });
      window.addEventListener('focus', safeBuild);
    } catch (e) {}
  })();

  /* ── киты: стая по монетам (31.08) ── */
  (function(){
    var A = (DATA.whales || {}).alerts || [];
    if (!A.length) return;
    function musd(x){ var m = String(x||'').match(/\$([\d.]+)\s*([KMB])/i);
      if (!m) return 0;
      return +m[1] * ({K:1e3, M:1e6, B:1e9})[m[2].toUpperCase()]; }
    var CAP = {};
    for (var ci = 0; ci < ST.length; ci++)
      CAP[String(ST[ci].t || '').replace(/USDT$/, '')] = musd(ST[ci].cap);
    CAP.BTC = CAP.BTC || 2.3e12; CAP.ETH = CAP.ETH || 5.6e11;
    CAP.SOL = CAP.SOL || 1.1e11; CAP.HYPE = CAP.HYPE || 1.5e10;
    /* группируем алерты по монете */
    var G = {}, order = [];
    for (var i = 0; i < A.length; i++) {
      var t = String(A[i].title || '');
      var m = t.match(/([A-Z0-9]{2,10})\s+\$([\d.]+[KMB])/);
      if (!m) continue;
      var sym = m[1], usd = musd('$' + m[2]);
      /* Кошелёк лежит в note: «кошелёк 0x0e989a67… · ликвидация …».
         Четыре знака после 0x — хватает, чтобы различить китов между
         собой; один кошелёк может встретиться в нескольких монетах. */
      var wm = String(A[i].note || '').match(/0x([0-9a-fA-F]{4})/);
      var tag = wm ? wm[1] : '';
      var side = t.indexOf('\u0448\u043e\u0440\u0442') >= 0 ? 's' : 'l';
      var mk = t.indexOf('\u043d\u0430\u0440\u0430\u0441\u0442\u0438\u043b') >= 0 ? '+'
             : t.indexOf('\u0437\u0430\u043a\u0440\u044b\u043b') >= 0 ? '\u2713' : '';
      if (!G[sym]) { G[sym] = {w: [], usd: 0}; order.push(sym); }
      G[sym].w.push([side, mk, tag]);
      G[sym].usd += usd;
    }
    order.sort(function(a, b){ return G[b].usd - G[a].usd; });
    order = order.slice(0, 4);
    if (!order.length) return;
    var UID = 0;
    /* СИЛУЭТ КИТА. Прошлые попытки читались рыбой, потому что тело
       было веретеном. У кита пропорции другие: голова занимает треть
       длины и тупая, спина ровная, к хвосту тело резко сужается,
       хвост — две широкие лопасти горизонтально. Грудной плавник
       снизу и близко к голове, а не посередине. */
    function SVGF(live){
      var id = 'wg' + (UID++);
      return '<svg viewBox="0 0 60 26">' +
        '<defs><linearGradient id="' + id + '" x1="1" y1="0" x2="0" y2="0">' +
          '<stop offset="0" stop-color="currentColor" stop-opacity="1"/>' +
          '<stop offset=".6" stop-color="currentColor" stop-opacity=".78"/>' +
          '<stop offset="1" stop-color="currentColor" stop-opacity=".2"/>' +
        '</linearGradient></defs>' +
        /* тело: тупой нос справа, ровная спина, резкое сужение к хвосту */
        '<path d="M58 13c0 5-6.4 8.4-15.4 8.4-9 0-19-2.6-27.6-6.2' +
          'l-2.4 6.4-1.6-.6 1.4-6.6c-3-1.4-5.6-2.8-7.4-4.2' +
          'C6.8 9.2 9.4 8 12.4 6.8L11 .2l1.6-.6 2.4 6.2' +
          'C23.6 2.4 33.6 0 42.6 0 51.6 0 58 3.4 58 13z" ' +
          'fill="url(#' + id + ')"/>' +
        /* грудной плавник — снизу, ближе к голове */
        '<path d="M40 19.6c3.6 2.6 8.4 3.4 12.4 2-3.4-2.8-8.2-3.6-12.4-2z" ' +
          'fill="currentColor" opacity=".4"/>' +
        /* линия пасти */
        '<path d="M50 17.4c3-.6 5.6-2 7-3.8" stroke="rgba(20,25,46,.5)" ' +
          'stroke-width=".9" fill="none" stroke-linecap="round"/>' +
        '<circle cx="51" cy="10.6" r="1.3" fill="rgba(20,25,46,.9)"/>' +
        '<circle cx="51.4" cy="10.1" r=".45" fill="rgba(255,255,255,.9)"/>' +
        (live ? '<path d="M47 4.2c-.4-2.4.4-4.4 2-5.8M50 4c.6-2.2 2-3.8 3.8-4.6"'
          + ' stroke="currentColor" stroke-width="1.2" fill="none"'
          + ' stroke-linecap="round" opacity=".5"/>' : '') +
      '</svg>';
    }
    var h = '<h5>\u041a\u0418\u0422\u042b \u00b7 ' +
            '\u0421\u0422\u0410\u042f \u041f\u041e \u041c\u041e\u041d\u0415\u0422\u0410\u041c</h5>';
    order.forEach(function(sym, pi){
      var g = G[sym], n = g.w.length;
      var lo = g.w.filter(function(x){ return x[0] === 'l'; }).length;
      var d = Math.max(104, Math.min(178, 78 + n * 21));
      var cp = CAP[sym] || 0, pc = cp ? (g.usd / cp * 100) : null;
      var sub = (pc == null || cp >= 1e11 || pc < 0.05) ? ''
              : pc.toFixed(1) + '% \u043a\u0430\u043f\u044b';
      var fs = Math.max(42, Math.min(82, 34 + n * 2.1));
      /* Считаем ЧЕТЫРЕ числа: у лонгов и у шортов свои открытые и
         закрытые. Открыл и нарастил — в «открыли», закрыл — в
         «закрыли». */
      var lo_o = 0, lo_c = 0, sh_o = 0, sh_c = 0;
      g.w.forEach(function(x){
        var closed = (x[1] === '\u2713');
        if (x[0] === 'l') { closed ? lo_c++ : lo_o++; }
        else              { closed ? sh_c++ : sh_o++; }
      });
      var rw = Math.max(96, Math.min(168, d * 0.74));
      function bar(nm, op, cl, cls){
        var t = op + cl;
        var p = t ? (op / t * 100) : 0;
        return '<div class="ln ' + cls + (t ? '' : ' off') + '">' +
          '<span class="nm">' + nm + '</span>' +
          '<span class="bar"><i style="width:' + p.toFixed(0) + '%"></i>' +
          (t ? '<u style="left:' + p.toFixed(0) + '%"></u>' : '') +
          '</span><span class="num">' + (t ? op + '/' + t : '\u2014') +
          '</span></div>';
      }
      h += '<div class="pod' + (lo >= n / 2 ? '' : ' s') + '" style="width:' +
        d + 'px;height:' + d + 'px;--fs:' + fs.toFixed(0) +
        'px"><span class="ttl">' + esc(sym) + '</span>' +
        '<span class="rr" style="--rw:' + rw.toFixed(0) + 'px">' +
          bar('лонг', lo_o, lo_c, 'l') +
          bar('шорт', sh_o, sh_c, 's2') +
        '</span>' +
        (sub ? '<span class="sub">' + sub + '</span>' : '');
      g.w.forEach(function(w, k){
        /* Ходят по эллипсу вокруг имени: шире, чем выше. Два радиуса
           вперемешку — у стаи появляется глубина. */
        var ang = (k / n) * 6.283 + pi * 1.1;
        var rx = d * (k % 2 ? 0.50 : 0.36);
        var ry = d * (k % 2 ? 0.30 : 0.20);
        var x = d / 2 + Math.cos(ang) * rx - 11;
        var y = d / 2 + Math.sin(ang) * ry - 5;
        var live = (w[1] !== '\u2713');
        var flip = Math.cos(ang) < 0 ? ' flip' : '';
        h += '<span class="w ' + w[0] + ' ' + (live ? 'live' : 'done') +
          flip + '" style="left:' + x.toFixed(0) + 'px;top:' +
          y.toFixed(0) + 'px;animation-duration:' + (10 + (k % 5) * 1.8) +
          's;animation-delay:' + (-k * 1.4).toFixed(1) + 's">' +
          SVGF(live) + (w[2] ? '<b>' + esc(w[2]) + '</b>' : '') +
          '</span>';
      });
      h += '</div>';
    });
    var stage = q('.obs') || root.firstElementChild;
    if (stage)
      stage.insertAdjacentHTML('beforeend',
        '<div class="pods">' + h + '</div>');
  })();
  var reduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion:reduce)').matches;

  /* ── помощники ── */
  function esc(s){ return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function num(v){ var n = +v; return isFinite(n) ? n : null; }
  function pct(v, d){ var n = num(v); if (n === null) return '—';
    return (n > 0 ? '+' : '') + n.toFixed(d === undefined ? 1 : d) + '%'; }
  function money(v){ var n = num(v); if (n === null) return '—';
    var a = Math.abs(n);
    if (a >= 1e9) return '$' + (n/1e9).toFixed(1) + 'B';
    if (a >= 1e6) return '$' + (n/1e6).toFixed(1) + 'M';
    if (a >= 1e3) return '$' + Math.round(n/1e3) + 'K';
    return '$' + Math.round(n); }
  function star(t){ for (var i=0;i<ST.length;i++) if (ST[i].t === t) return ST[i];
    return null; }
  /* СВОЙ ГЕНЕРАТОР СЛУЧАЙНЫХ, а не Math.random: раскладка пыли должна
     быть одинаковой при каждом открытии одного и того же прогона —
     иначе два взгляда на один отчёт выглядят по-разному. */
  var rnd = (function(){ var s = 7; return function(){ s = (s*16807) % 2147483647; return s / 2147483647; }; })();

  var t0 = M.ts ? new Date(M.ts) : new Date();
  function p2(n){ return (n < 10 ? '0' : '') + n; }
  q('#stamp').textContent = 'прогон ' + p2(t0.getDate()) + '.' + p2(t0.getMonth()+1) +
    ' · ' + p2(t0.getHours()) + ':' + p2(t0.getMinutes());

  /* ── пыль: группа пузырей слева ── */
  var dust = q('#dust');
  for (var i = 0; i < 56; i++) {
    var d = document.createElement('i'), t = 30 + rnd()*40;
    var x = 15 + (rnd() + rnd() - 1) * 6;   /* сумма двух случайных даёт горб к центру группы */
    d.style.cssText = 'left:' + x.toFixed(2) + '%;top:' + (100 + rnd()*18).toFixed(2) +
      '%;opacity:' + (0.22 + rnd()*0.26).toFixed(2) +
      ';--t:' + t.toFixed(1) + 's;--d:-' + (rnd()*t).toFixed(1) + 's;--w:' + (6 + rnd()*6).toFixed(1) + 's';
    dust.appendChild(d);
  }

  /* ── мысли прогона ── */
  var reasons = [];
  ['btc','funding','oi','cascade','calendar'].forEach(function(k){
    var p = pp[k] || {}; if (p.warn && p.note) reasons.push(p.note); });
  var md = M.medians || {}, pf = M.portfolios || {}, hold = pf.hold || {}, tr = pf.trade || {};
  var L0 = M.leader || {}, ls = star(L0.t) || {}, lead = M.peakVol || {}, VC = M.volChart || {};
  var take = ST.filter(function(s){ return (s.act||{}).group === 'take' && (s.act||{}).act === 'брать'; });
  var book = ST.filter(function(s){ return (s.book||{}).usd; });
  /* Лидеры трёх суток — по hits_by_day, а не по last_seen: last_seen
     стоит почти у всех и не фильтрует ничего. */
  var rws = ST.map(function(s){ var by = s.byDay || [], n = 0;
    by.slice(-3).forEach(function(v){ n += +v || 0; });
    return n ? { t: s.t, n: n } : null; })
    .filter(Boolean).sort(function(a,b){ return b.n - a.n; }).slice(0, 6);
  var size = (P.warnCount||0) >= 4 ? 'урезанный' : 'полный';

  /* СКОЛЬКО МЫСЛЕЙ. Восьми не хватало: прежняя листалка показывала
     втрое больше за тот же проход. Здесь восемнадцать — весь состав
     старых страниц, разобранный на отдельные ветви: окно, фон,
     медианы, аппетит, доминация, стейблы, портфели, книга, лидер,
     трое суток, объём, фандинг, спящие, разлоки, ближайшее событие,
     брать, в работе, итог. Пустые (нет данных) отсеиваются ниже, так
     что в тихий день ветвей будет меньше — это честнее пустой строки.

     Гамма только холодная: сталь, голубой, васильковый, бирюза,
     лавандовый. Тёплого нет — иначе схема рябит. */
  /* ── НАБЛЮДЕНИЕ ЗА ЛИДЕРСТВОМ (27.08) ──
     Три ветви из журнала: кто держится третьи сутки, кто чаще всех
     брал первое место за сутки, и кто дальше всех ушёл от дна.
     Считает analytics_leaders, здесь только показ. Ключей может не
     быть вовсе — первые трое суток после запуска истории нет, и
     пустая ветвь просто не появится: отбор ниже отсеивает пустые. */
  /* ── ПОТОК СДЕЛОК (29.08). Приходит из Coinglass, считается по
     самим сделкам, а не по свечам: тейкерское отношение, накопленная
     дельта, стороны ликвидаций, приток к капитализации.
     Ключ отличия от всего остального на этом экране: наши датчики
     меряют ИТОГ часа, эти — УСИЛИЕ обеих сторон внутри часа. Цена
     может стоять, пока продавец давит, а покупатель поглощает: по
     свече тихо, по потоку работа. */
  var CG = M.flow2 || {};

  var J = M.journal || {};
  var leadHold = J.leadHold || [], leadDay = J.leadDay || [], leadTop = J.leadTop || null;
  function dmy(iso){
    var d = new Date(String(iso || ''));
    if (isNaN(d)) return '';
    return ('0' + d.getDate()).slice(-2) + '.' + ('0' + (d.getMonth() + 1)).slice(-2);
  }

  var dorm = ST.filter(function(s){ return (s.st || '') === 'dormant'; });
  var fuel = ST.filter(function(s){ return (s.st || '') === 'fuel'; });
  var taker = ST.filter(function(s){ return (s.st || '') === 'taker'; });
  var AS = M.altShare || {}, rs = pp.reservoir || {}, fund = pp.funding || {};
  var oi = pp.oi || {}, casc = pp.cascade || {}, btcp = pp.btc || {};
  /* Вердикт гейта тоже лежит в ленте (kind:'regime'), но событием не
     является: без этого отсева «ближайшее событие» печатало режим
     биткоина вместо ближайшего транша. */
  var cal0 = ((pp.calendar || {}).items || []).filter(function(e){
    return e && e.kind !== 'regime'; })[0] || null;
  var unlocks = ((pp.calendar || {}).items || []).filter(function(e){ return e.kind === 'unlock'; });
  var top = (M.topVol || []).slice(0, 4);
  var cos = (function(){
    /* ПОЙДЁТ? (31.08, перенос одобрен): сюжеты растущего класса —
       одна монета, одна ветвь, до четырёх; нет растущих — ветвей нет.

       ДВЕ ПОЛКИ (правка 01.09). Прежде в один список валились обе
       стадии, и «Пойдёт?» соблазняло тем, что выросло вчера вчетверо:
       акт НА ХОДУ, ИСКРА и подтверждение — это уже идущий ход, вход в
       него дорогой. Растущее семейство осталось одним списком, но
       делится по СТАДИИ: «до движения» идут кандидатами, «в движении»
       — отдельной полкой с честной подписью.
       Стадию считает reputation_cq и кладёт полем rep.stage; поля нет
       (документ старой сборки) — определяем здесь по тем же меткам,
       чтобы правка не гасила полки задним числом. */
    /* Корни, а не полные имена (01.09, вместе с переименованием):
       «крупняк» ловит обе стадии — «тащит вверх» и «начал тащить», —
       а «курок взведён» оба курка. Полные имена после правки друг
       друга не содержат, и список молча опустел бы наполовину. */
    var GROW = ['кит набирает тихо', 'крупняк', 'курок взведён',
                'акт НА ХОДУ', 'ИСКРА', 'подтверждение пришло'];
    var MOVING = ['акт НА ХОДУ', 'ИСКРА', 'подтверждение пришло',
                  'кит ушёл', 'крупняк отпустил', 'раздача после пика',
                  'крупняк тащит вверх'];
    function stageOf(rep) {
      var st = rep && rep.stage;
      if (st === 'before' || st === 'moving') return st;
      var head = String((rep && rep.plot) || '').split(':')[0];
      for (var q = 0; q < MOVING.length; q++)
        if (head.indexOf(MOVING[q]) >= 0) return 'moving';
      return 'before';
    }
    /* ВЕТО ФАЗЫ (правка 01.09). Гейт — фазовый слой, и в режиме
       раздачи сюжет отдельной монеты значения почти не имеет: 31.08
       весь список ушёл в минус при корреляции альтов 0.87. Список не
       прячем — помечаем, решение остаётся за человеком. */
    var rv = String((M.regime || {}).verdict || '').toLowerCase();
    var against = (rv.indexOf('раздача') >= 0 ||
                   rv.indexOf('тянет деньги') >= 0 ||
                   rv.indexOf('сосёт') >= 0);
    var vetoMark = against
      ? '<br><i style="opacity:.62">фон против — режим рынка ' +
        'работает на раздачу</i>' : '';
    var out = [];
    /* Объявлена ЗДЕСЬ, а не в теле цикла (01.09): ветвь лидера ниже
       зовёт её и когда растущих сюжетов не нашлось ни одного, то
       есть когда цикл не выполнялся ни разу. */
    function cut(x, n){ x = String(x).trim();
      if (x.length <= n) return x;
      var z = x.slice(0, n), p = z.lastIndexOf(' ');
      return (p > n * 0.6 ? z.slice(0, p) : z) + '…'; }
    var mov = [];
    for (var gi = 0; gi < ST.length && out.length + mov.length < 6; gi++) {
      var gs = ST[gi], gr = gs.rep || {}, gp = gr.plot || '';
      if (!gp) continue;
      var hit = false;
      for (var gg = 0; gg < GROW.length; gg++)
        if (gp.indexOf(GROW[gg]) >= 0) { hit = true; break; }
      if (!hit) continue;
      var moving = stageOf(gr) === 'moving';
      if (moving ? mov.length >= 2 : out.length >= 4) continue;
      /* КОРОТКО (31.08): сюжет режется по СМЫСЛУ, не по символам.
         Шаблон — в значение ветви; в тело идут две части: чем
         основан (первая часть до точки с запятой) и сторож
         (последняя, где «выход», «пока», «сигнал»). Скобку с
         именем шаблона выбрасываем — она уже в значении. */
      var raw = gp.replace(/\s*\(шаблон[^)]*\)/, '');
      var parts = raw.split(/[;·]\s*/).filter(function(x){
        return x && x.length > 3; });
      var head = (parts[0] || raw).replace(/^[^:]*:\s*/, '');
      var tail = parts.length > 1 ? parts[parts.length - 1] : '';
      /* Имя шаблона кончается ДВОЕТОЧИЕМ, а не скобкой (правка
         01.09). Резали по '(' — и у сюжетов без «(шаблон …)» в
         подпись уезжал весь текст целиком: на экране это выглядело
         сломанной вёрсткой. Двоеточие есть у всех шаблонов без
         исключения, скобка — не у всех. */
      var vname = gp.split(':')[0]
                    .replace(/\s*\([^)]*\)\s*$/, '').trim();
      var body = esc(cut(head, 95)) +
                 (tail ? '<br><i style="opacity:.62">' +
                  esc(cut(tail, 85)) + '</i>' : '');
      var vfull = '<span class="tkr">' + esc(gs.t || '') + '</span>' +
                  '<s>·</s><b>' + esc(vname) + '</b>';
      if (moving) {
        mov.push({ k: 'Уже идёт · ' + (gs.t || ''),
                   v: vfull, c: '#e0b878', moving: 1,
                   s: body + '<br><i style="opacity:.62">вход дорогой ' +
                      '— ход уже состоялся</i>' });
      } else {
        out.push({ k: 'Пойдёт? · ' + (gs.t || ''),
                   v: vfull, c: '#7fe3d4',
                   s: body + vetoMark });
      }
    }
    /* Полка «в движении» идёт ПОСЛЕ кандидатов: она про то, что уже
       ушло, и открывать ею колесо было бы ровно тем соблазном, от
       которого разводили. */
    for (var mi = 0; mi < mov.length; mi++) out.push(mov[mi]);
    /* ЛИДЕР НЕ БЫВАЕТ НЕМЫМ (правка 01.09, случай AIO). Фильтр
       пускает в «Пойдёт?» только растущий класс, и это правильно:
       у «руки над сливом» развязка в обе стороны, кандидатом её
       звать нельзя. Но у ЛИДЕРА прогона молчание читается как
       поломка — AIO вышла в лидеры с самым длинным набором дня,
       тринадцать дней продаж при держащейся цене, и на экране про
       неё не было ни слова.
       Поэтому лидеру сюжет показываем всегда, отдельной ветвью и с
       ЧЕСТНОЙ подписью — именем шаблона, а не «Пойдёт?». Список
       кандидатов от этого не грязнится: ветвь не его. */
    var lt = String(L0.t || '');
    /* РЕПУТАЦИЯ ЛЕЖИТ В ЗВЕЗДЕ, А НЕ В ЛИДЕРЕ (правка 01.09, случай
       монеты «4»). M.leader — облегчённый объект: тикер, кейс,
       капитализация, поля rep у него нет. Полная звезда достаётся
       через star(), она же уже посчитана выше как ls. Из-за этого
       ветвь лидера считала, что сюжета нет, хотя в reputation.json
       он лежал — «крупняк тащит вверх». */
    var lrep0 = (ls && ls.rep) || L0.rep || {};
    var lp = String(lrep0.plot || '');
    var dup = false;
    for (var li = 0; li < out.length; li++)
      if (out[li].k.indexOf(lt) >= 0) { dup = true; break; }
    /* СЮЖЕТА МОЖЕТ НЕ БЫТЬ ВОВСЕ (правка 01.09, случай монеты «4»).
       Прошлая правка показывала сюжет лидера, только если он есть, —
       и лидер без сюжета снова оказывался немым. Молчание на главной
       монете экрана читается как поломка, поэтому говорим ПРИЧИНУ:
       нет монеты в архиве кванта или ни один шаблон не узнан. */
    if (lt && !lp && !dup) {
      var lrep = lrep0;
      var lwhy = (!lrep.line && !lrep.today)
        ? 'в архиве кванта монеты нет — сюжет не строился'
        : 'ни один шаблон не узнан: фигура не похожа на известные';
      out.push({ k: 'Лидер · ' + lt,
                 v: '<span class="tkr">' + esc(lt) + '</span> · ' +
                    esc(L0.case || 'без кейса'),
                 c: '#8b93c4', lead: 1,
                 s: esc(lwhy) +
                    (lrep.line ? '<br><i style="opacity:.62">' +
                     esc(String(lrep.line).slice(0, 90)) + '</i>' : '') });
    }
    if (lt && lp && !dup) {
      var lraw = lp.replace(/\s*\(шаблон[^)]*\)/, '');
      var lname = lraw.split(':')[0].trim();
      var lrest = lraw.split(/[;·]\s*/).filter(function(x){
        return x && x.length > 3; });
      var lhead = (lrest[0] || lraw).replace(/^[^:]*:\s*/, '');
      var ltail = lrest.length > 1 ? lrest[lrest.length - 1] : '';
      out.push({ k: lname.charAt(0).toUpperCase() + lname.slice(1) +
                    ' · ' + lt,
                 v: '<span class="tkr">' + esc(lt) + '</span><s>·</s><b>' +
                    esc(lname) + '</b>',
                 c: '#b3a6e0', lead: 1,
                 s: esc(cut(lhead, 95)) +
                    (ltail ? '<br><i style="opacity:.62">' +
                     esc(cut(ltail, 85)) + '</i>' : '') });
    }
    return out;
  })().concat([
    /* БИТКОИН · РЕЖИМ (31.08): вердикт гейта и его графы прямо
       ветвью схемы — раньше жил только в ленте новостей. */
    { k:'Биткоин · режим',
      v: (M.regime && M.regime.verdict) ?
         esc(M.regime.verdict).replace(/[«»]/g, '') : null,
      c:'#ffcf7a',
      s: (M.regime && M.regime.rows || []).slice(0, 4).map(
           function(r){ return '<b>' + esc(r[0]) + ':</b> ' +
             esc(String(r[1]).slice(0, 110)); }).join('<br>') },
    { k:'Окно рынка', v:(P.warnCount||0) + ' из ' + (P.knownCount||7), c:'#cfd8ef',
      s: esc(reasons[0]||'') + (M.appetite ? '. Аппетит ' + esc(M.appetite).replace('/',' из ') : '') },
    { k:'Фон', v: pct(md.d7,1), c:'#8ab4ff',
      s:'медиана выборки за неделю · сутки ' + pct(md.d1) + ' · месяц ' + pct(md.d30) +
        (M.dom ? ' · доминация ' + M.dom + '%' : '') },
    { k:'Портфели', v: pct(hold.pnlPct,0), c:'#7fe3d4',
      s:'журнал <b>' + (hold.open||0) + '</b> позиций, ' + money(hold.invested) + ' → ' +
        money(hold.value) + ' · книга ' + pct(tr.pnlPct) },
    { k:'Лидер прогона',
      v:'<span class="tkr">' + esc(L0.t||'—') + '</span> · ' + esc(L0.case||''),
      c:'#e6edff',
      s: esc(L0.cap||'') +
        ((ls.rep && ls.rep.plot) ? ' · ' +
          esc(String(ls.rep.plot).split(':')[0]) : '') +
        ((ls.rep && ls.rep.phrase) ? '<br>' +
          esc(String(ls.rep.phrase).slice(0, 140)) : '') +
        (rws.length ? '<br>трое суток держатся: ' + rws.map(function(r){ return r.t + ' ' + r.n; }).join(' · ') : '') },
    /* ── ветви потока сделок ── */

    /* Тейкерское отношение: ниже единицы — продавцы бьют по стакану
       сильнее покупателей. Показываем ХУДШИЕ, потому что раздача на
       растущей позиции опаснее, чем давление на упавшей. */
    { k:'Продавцы давят', v: CG.takerWorst ? CG.takerWorst.t + ' ' + CG.takerWorst.v : null, c:'#ff8a72',
      s: (CG.takerList || []).slice(0, 5).map(function(x){
           return x.t + ' ' + x.v + (x.fall ? ' ↓' : ''); }).join(' · ') },

    /* Накопленная дельта: знак важнее величины. Переворот из плюса в
       минус за сутки означает смену того, кто ведёт торг. */
    { k:'Дельта перевернулась', v: CG.flippedN ? CG.flippedN + ' монет' : null, c:'#ffb266',
      s: (CG.flipped || []).slice(0, 6).join(' · ') },

    /* Ликвидации: не сумма, а СТОРОНА. Вынос лонгов на растущей
       монете — раздача; вынос шортов — топливо вверх. */
    { k:'Кого выносит', v: CG.liqSide || null, c:'#9fb8ff',
      s: (CG.liqList || []).slice(0, 5).map(function(x){
           return x.t + ' ' + x.s; }).join(' · ') },

    /* Приток к капитализации — сравнимая между монетами величина:
       сколько денег привели относительно размера. Абсолютная сумма
       не годится, у монет разный масштаб. */
    { k:'Деньги за сутки', v: CG.flowTop ? CG.flowTop.t + ' ' + (CG.flowTop.v > 0 ? '+' : '') + CG.flowTop.v + '%' : null, c:'#7fe3d4',
      s: (CG.flowList || []).slice(0, 5).map(function(x){
           return x.t + ' ' + (x.v > 0 ? '+' : '') + x.v + '%'; }).join(' · ') },

    { k:'Топ объёма', v:'×' + Math.round(lead.x||0), c:'#9fb8ff',
      s:'<span class="tkr">' + esc(lead.sym||'') + '</span> · ' + esc(VC.cap||'') +
        (VC.funding ? ' · фандинг ' + (+VC.funding).toFixed(2) + '%' : '') },
    { k:'Брать', v: take.length ? take.length + ' монет' : 'нечего', c: take.length ? '#7fe3d4' : '#9aa3c8',
      s: take.length ? take.map(function(s){ return s.t; }).join(' · ')
                     : 'ни одна монета не прошла порог входа' },
    { k:'В работе', v: book.length + ' позиций', c:'#b3c6f2',
      s: book.length ? book.map(function(s){ return s.t; }).join(' · ') : 'книга пуста' },
    { k:'Итог', v: size, c:'#c9c3f0',
      s:'размер по правилу при окне ' + (P.warnCount||0) + ' из ' + (P.knownCount||7) + ' · дальше зал' },

    /* ── добавлено 27.08: состав прежних страниц ── */
    { k:'Аппетит', v: M.appetite ? String(M.appetite).replace('/',' из ') : null, c:'#8ab4ff',
      s:'готовность рынка брать риск' + (M.sector ? ' · сектор дня ' + esc(M.sector) : '') },
    { k:'Доминация BTC', v: M.dom ? M.dom + '%' : null, c:'#b3c6f2',
      s:'доля биткоина в капитализации рынка' + (AS.d7 != null ? ' · обошли биткоин за неделю ' + AS.d7 + '% выборки' : '') },
    { k:'Стейблы к капе', v: rs.share != null ? rs.share + '%' : null, c:'#7fe3d4',
      s:'резервуар покупательной силы' + (rs.ageDays != null ? ' · данным ' + Math.round(rs.ageDays) + ' дн' : '') },
    { k:'Фандинг', v: fund.value != null ? pct(fund.value, 2) : (fund.note ? '—' : null), c:'#9fb8ff',
      s: esc(fund.note || 'плата за плечо: положительный — толпа в лонге') },
    { k:'Плечо', v: oi.value != null ? String(oi.value) : (oi.note ? '—' : null), c:'#cfd8ef',
      s: esc(oi.note || 'открытый интерес против цены') },
    { k:'Каскад', v: casc.value != null ? String(casc.value) : (casc.note ? '—' : null), c:'#b3c6f2',
      s: esc(casc.note || 'перевес ликвидаций') },
    { k:'Биткоин', v: M.btc7d != null ? pct(M.btc7d, 1) : null, c:'#e6edff',
      s:'за неделю' + (btcp.note ? ' · ' + esc(btcp.note) : '') },
    { k:'Спящие', v: dorm.length ? dorm.length + ' монет' : null, c:'#9aa3c8',
      s: dorm.slice(0, 12).map(function(s){ return s.t; }).join(' · ') },
    { k:'Заряжены', v: fuel.length ? fuel.length + ' монет' : null, c:'#7fe3d4',
      s: fuel.slice(0, 12).map(function(s){ return s.t; }).join(' · ') },
    { k:'Разбирают', v: taker.length ? taker.length + ' монет' : null, c:'#9fb8ff',
      s: taker.slice(0, 12).map(function(s){ return s.t; }).join(' · ') },
    { k:'Разлоки впереди', v: unlocks.length ? unlocks.length + ' траншей' : null, c:'#b3c6f2',
      s: unlocks.slice(0, 6).map(function(e){
           var d = num(e.days); return String(e.title).replace(/^разлок */,'') + ' · ' +
             ((e.running || d === 0) ? 'сегодня' : d === 1 ? 'завтра' : 'через ' + d + ' дн'); }).join(' · ') },
    { k:'Ближайшее событие', v: cal0 ? esc(String(cal0.title).slice(0, 22)) : null, c:'#cfd8ef',
      s: cal0 ? esc(String(cal0.note || '').slice(0, 150)) : '' },
    { k:'Следом по объёму', v: top.length ? top.length + ' монет' : null, c:'#9fb8ff',
      s: top.map(function(v){ return v.t + ' ×' + (+v.x).toFixed(1); }).join(' · ') },

    /* ── добавлено 27.08: наблюдение за лидерством ── */

    /* Держатся третьи сутки: лидерство было в КАЖДОМ из трёх суточных
       отрезков последних 72 часов. Пропуск в любом отрезке исключает
       монету — смысл строки не «часто мелькала», а «не отпускает». */
    { k:'Держатся третьи сутки', v: leadHold.length ? leadHold.length + ' монет' : null, c:'#7fe3d4',
      s: leadHold.map(function(x){ return x.t + ' ' + x.n; }).join(' · ') },

    /* Кто чаще брал первое место за последние 24 часа. Окно
       скользящее: календарные сутки дали бы в 00:10 пустое «вчера». */
    { k:'Чаще всех за сутки', v: leadDay.length ? leadDay[0].t + ' ' + leadDay[0].n : null, c:'#9fb8ff',
      s: leadDay.map(function(x){ return x.t + ' — ' + x.n +
           (x.n === 1 ? ' раз' : (x.n < 5 ? ' раза' : ' раз')); }).join(' · ') },

    /* Дальше всех от дна среди лидеров окна. Дно — минимум 60 дней:
       за три года монета могла вырасти четырежды, и рост от
       абсолютного дна ничего не сказал бы о сегодняшнем ходе. */
    { k:'Дальше всех от дна', v: leadTop ? leadTop.t + ' ' + (leadTop.up > 0 ? '+' : '') + leadTop.up + '%' : null, c:'#e6edff',
      s: leadTop ? ('в журнале с ' + dmy(leadTop.first) + ' · последний раз ' + dmy(leadTop.last)) : '' },

  ]).filter(function(c){ return c && c.v != null && c.v !== ''; });

  /* ── ГОРИЗОНТЫ И ПОРЯДОК (31.08) ──────────────────────────────
     Ветви шли одним плоским списком, и три слоя перемешивались:
     после «Пойдёт? · ONG» сразу «Биткоин · режим», за ним «Окно
     рынка» — прогноз, фаза и фон за полминуты, ничем не помечены.

     Метка одна и это ГОРИЗОНТ. Слой из неё читается сам: полгода и
     недели — фаза (там только факты, решает человек), дни и часы —
     события (там машина отвечает «когда»). Счёт — ни то, ни другое.

     Внутри событий порядок по стадиям: подготовка, крючок,
     срабатывание, сторож. Это не выбор оформления, а разбор самого
     события, поэтому стоит одинаково в обоих порядках.

     ПОРЯДОК. 'А' — прогноз прологом (решение 31.08: «Пойдёт?»
     открывает колесо), дальше от быстрого к медленному, экран
     кончается фазой и размером. 'Б' — строго сверху вниз: где мы
     вообще, что вокруг, что сегодня, что сейчас; тогда «Пойдёт?»
     встаёт среди дней и первых страниц не занимает. Смена — одна
     буква здесь. */
  var ORDER = 'А';
  var HZ = {
    'Биткоин · режим':['полгода',0], 'Доминация BTC':['полгода',0],
    'Стейблы к капе':['полгода',0],
    'Окно рынка':['недели',0], 'Фон':['недели',0], 'Аппетит':['недели',0],
    'Биткоин':['недели',0], 'Плечо':['недели',0], 'Каскад':['недели',0],
    'Разлоки впереди':['недели',0],
    'Спящие':['дни',1], 'Заряжены':['дни',1], 'Дальше всех от дна':['дни',1],
    'Лидер прогона':['дни',2], 'Держатся третьи сутки':['дни',2],
    'Разбирают':['дни',3], 'Чаще всех за сутки':['дни',3], 'Брать':['дни',3],
    'Фандинг':['дни',4], 'Ближайшее событие':['дни',4],
    'Топ объёма':['часы',3], 'Дельта перевернулась':['часы',3],
    'Деньги за сутки':['часы',3], 'Следом по объёму':['часы',3],
    'Продавцы давят':['часы',4], 'Кого выносит':['часы',4],
    'Портфели':['счёт',0], 'В работе':['счёт',0], 'Итог':['счёт',0]
  };
  var HZC = {'полгода':'#b07bff', 'недели':'#8ab4ff', 'дни':'#7fe3d4',
             'часы':'#cfd8ef', 'счёт':'#8b93bd'};
  var HZL = {'полгода':'полгода — фаза', 'недели':'недели — фаза',
             'дни':'дни — событие', 'часы':'часы — событие', 'счёт':'счёт'};
  var RANK = (ORDER === 'Б')
    ? {'полгода':0, 'недели':1, 'дни':2, 'часы':3, 'счёт':4}
    : {'полгода':4, 'недели':3, 'дни':2, 'часы':1, 'счёт':5};
  cos.forEach(function(c, i){
    var go = String(c.k).indexOf('\u041f\u043e\u0439\u0434') === 0;
    /* Ветвь лидера идёт прологом рядом с «Пойдёт?» (01.09): она про
       главную монету экрана, а не про фон. Признаком go её не метим —
       иначе оденется в стиль кандидата и снова будет читаться как
       «пойдёт», чего мы и избегали. */
    var lead = !!c.lead || !!c.moving;
    var m = HZ[c.k] || (go ? ['дни', 2] : ['дни', 3]);
    c.h = m[0]; c.g = m[1]; c.go = go; c.i = i;
    /* В порядке А прогноз идёт прологом — раньше всех горизонтов. */
    c.r = ((go || lead) && ORDER !== 'Б') ? -1 : RANK[c.h];
  });
  cos.sort(function(a, b){
    return (a.r - b.r) || (a.g - b.g) || (a.i - b.i); });

  /* ГНЁЗДА СЧИТАЮТСЯ ОТ ОКНА. На широком — три с шагом 96 под
     кристаллом; на узком мысль стоит под узлом и занимает больше
     высоты, на низком высоты нет вовсе — шаг ужимается до того, что
     остаётся между кристаллом и полосой новостей. */
  var wrapCos = q('#cos'), H = window.innerHeight, W = window.innerWidth;
  var narrow = W < 900, low = H < 560;
  var top0 = H*0.17 + (low ? 76 : narrow ? 130 : 168);
  /* Шаг между гнёздами. Нижняя граница — не произвольные 46, а
     высота самой ветви: подпись, значение и три строки ноты. Меньше
     этого гнёзда налезают друг на друга по построению, сколько ни
     сжимай экран. */
  /* +14 к прежним (31.08): метка горизонта — ещё одна строка сверху,
     а этот минимум и есть высота ветви. Не поднять — гнёзда налезут
     друг на друга по построению, сколько ни сжимай экран. */
  var LEAD_MIN = narrow ? 130 : 124;
  var step = Math.max(LEAD_MIN, Math.min(narrow ? 130 : 122,
    (H - top0 - (low ? 120 : narrow ? 250 : 190)) / 2.4));
  var SLOT = [0, step, step*2];
  /* Потолок ветви ходит за шагом (см. .co .txt): иначе на низком
     окне шаг сжимается, а текст остаётся прежним. */
  wrapCos.style.setProperty('--slot', step + 'px');
  wrapCos.innerHTML = cos.map(function(c, i){
    var y = top0 + SLOT[i % 3] + Math.round((rnd() - 0.5) * 36);
    var gate = c.k === '\u0411\u0438\u0442\u043a\u043e\u0438\u043d \u00b7 \u0440\u0435\u0436\u0438\u043c';
    return '<div class="co ' + (i % 2 ? 'r' : 'l') +
        (c.go ? ' cgo' : '') + (gate ? ' cgt' : '') +
        '" style="top:' + y + 'px">' +
      '<i class="node"></i><i class="ln"></i><div class="txt">' +
      '<div class="hz" style="--hz:' + (HZC[c.h] || '#cfd8ef') + '">' +
        esc(HZL[c.h] || c.h) + '</div>' +
      '<div class="k' + (c.go ? ' kgo' : '') + '">' + esc(c.k) + '</div>' +
      '<div class="v" style="--vc:' + (c.c || '#dbe3f7') + '">' + c.v + '</div>' +
      '<div class="s">' + c.s + '</div></div></div>'; }).join('');
  /* ствол — до нижнего гнезда с запасом, а не до низа экрана */
  var trunk = q('.trunk');
  trunk.style.top = Math.round(H*0.17 + (low ? 76 : 110)) + 'px';
  trunk.style.bottom = Math.max(low ? 60 : 90, H - (top0 + SLOT[2] + (narrow ? 86 : 70))) + 'px';

  var els = [].slice.call(wrapCos.children);
  var ticks = q('#ticks'), count = q('#count'), prev = q('#prev'), next = q('#next');
  var nav = q('.nav');
  var cur = -1, timer = null, tks = [];
  els.forEach(function(_, i){
    var t = document.createElement('div'); t.className = 'tk'; t.innerHTML = '<i></i>';
    t.onclick = function(e){ e.stopPropagation(); show(i); }; ticks.appendChild(t); });
  tks = [].slice.call(ticks.children);

  /* На ветвях живут ТРИ: текущая и две предыдущие — по числу гнёзд.
     Было две, при восьми мыслях этого хватало; при восемнадцати экран
     оказывался пустее, чем прежняя листалка. Всё, что старше, тает;
     всё, что моложе, ещё не проступило. Шаг чаще: три с половиной
     секунды вместо пяти, иначе восемнадцать мыслей идут больше
     полутора минут. ПРАВКА 27.08: плюс две секунды на ветвь — при
     трёх с половиной глаз не успевал дочитать вторую строку. */
  var DWELL = 5500;
  function show(i){
    if (i < 0 || i >= els.length) return;
    cur = i; clearTimeout(timer);
    els.forEach(function(e, k){
      var vis = (k === i || k === i - 1 || k === i - 2);
      if (vis) { e.classList.remove('off'); e.classList.add('on'); }
      else if (e.classList.contains('on')) { e.classList.remove('on'); e.classList.add('off'); }
      else { e.classList.remove('on', 'off'); }
    });
    tks.forEach(function(t, k){ t.classList.toggle('done', k <= i); });
    count.textContent = (i + 1) + ' / ' + els.length;
    prev.classList.toggle('off', i === 0);
    next.classList.toggle('off', i === els.length - 1);
    /* Прогнозам по монетам (31.08) +5 секунд: текста много, надо
       вникнуть — остальные ветви идут прежним шагом. */
    /* Гейту (31.08) +3 секунды: восемь граф ушли из ленты пузырей,
       и эта ветвь осталась единственным местом, где состояние
       биткоина вообще читается. */
    var hold = DWELL + (els[i] && els[i].classList.contains('cgo') ? 5000 : 0)
                     + (els[i] && els[i].classList.contains('cgt') ? 3000 : 0);
    if (i < els.length - 1) { timer = setTimeout(function(){ show(cur + 1); }, hold); }
    else { timer = setTimeout(close, hold * 1.4); }   /* последняя мысль постояла — отдаём экран */
  }
  prev.onclick = function(e){ e.stopPropagation(); show(cur - 1); };
  next.onclick = function(e){ e.stopPropagation(); show(cur + 1); };

  /* ── события: пузыри справа, подпись всплывает под стволом ── */
  var items = (pp.calendar || {}).items || [];
  var sw = q('#stars');
  if (items.length) {
    /* Один круг событий примерно равен показу всех мыслей: за сводку
       успевают пройти все, каждое по разу. */
    /* цикл на пятую часть короче прежнего (было 5.5 с на событие):
       поток гуще, при этом окно показа держит на экране две штуки */
    var CYC = Math.max(38, items.length * 4.4);
    /* СКОЛЬКО ИХ. Слева пыли пятьдесят шесть; справа было впятеро
       меньше — около одиннадцати, — и поток вышел редким: правка 27.08
       утраивает их до тридцати трёх. Событий может быть меньше: тогда
       недостающие пузыри идут пустыми, без подписи, чтобы поток не
       редел в тихий день. Больше событий — показываем все.
       Подпись получают ТОЛЬКО пузыри событий; пустые молчат, поэтому
       правило «не больше двух подписей разом» это не трогает. */
    var WANT = Math.round(56 / 5) * 3;
    var bub = '', tel = '';
    items.forEach(function(e, i){
      var d = num(e.days), when = (e.running || d === 0) ? 'сегодня'
        : d === 1 ? 'завтра' : 'через ' + d + ' дн';
      /* по ВСЕЙ ширине, а не в правой половине: от двух до девяноста
         восьми процентов, вразнобой */
      var xr = (2 + rnd()*96).toFixed(2);
      var st = '--t:' + CYC + 's;--d:-' + (i * CYC / items.length).toFixed(1) + 's';
      /* сдвиг от центра и множитель скорости — свои у каждой новости,
         но одинаковые при каждом открытии одного прогона: генератор
         тот же, что у пыли. Разброс узкий намеренно: шире — столбец
         рассыпается, ровно ноль — идёт сплошной нитью. */
      var stt = st + ';--x:' + Math.round((rnd() - 0.5) * 80) + 'px' +
                     ';--sp:' + (0.9 + rnd() * 0.3).toFixed(2);
      bub += '<div class="news k-' + esc(e.kind) + '" style="--xr:' + xr + '%;' + st + '"><i></i></div>';
      tel += '<div class="tl k-' + esc(e.kind) + '" style="' + stt + '">' +
        '<u></u><u></u><u></u><b class="w">' + when + '</b>' +
        '<b class="t">' + esc(e.title) + '</b></div>';
    });
    /* добор до пятой части от левой пыли — пустыми пузырями */
    for (var k = items.length; k < WANT; k++) {
      var t = 30 + rnd()*40;
      bub += '<div class="news" style="--xr:' + (2 + rnd()*96).toFixed(2) + '%;--t:' +
        t.toFixed(1) + 's;--d:-' + (rnd()*t).toFixed(1) + 's"><i></i></div>';
    }
    sw.innerHTML = bub;
    var tells = document.createElement('div');
    tells.className = 'tells'; tells.innerHTML = tel;
    q('.obs').appendChild(tells);
  }

  /* ── ЗВУК ──
     Файл ищем ОДНИМ запросом заголовков: полное чтение потянуло бы
     весь звук ради проверки, что он есть. Нет файла — кнопки нет,
     и это нормальный ответ, а не сбой: на не-macOS озвучка не
     собирается вовсе.
     Клик по кнопке не должен закрывать сводку — она слушает клики
     как «дальше», поэтому событие останавливается здесь же. */
  (function(){
    var snd = q('#snd'), txt = q('#sndTxt'), audio = null;
    fetch('brief_voice.m4a', {method: 'HEAD'}).then(function(r){
      if (r.ok) snd.classList.add('on');
    }).catch(function(){ /* нет файла — молчим */ });

    snd.addEventListener('click', function(e){
      e.stopPropagation();
      if (!audio) {
        audio = new Audio('brief_voice.m4a');
        audio.addEventListener('ended', function(){
          snd.classList.remove('play'); txt.textContent = 'слушать';
        });
      }
      if (audio.paused) {
        audio.play().then(function(){
          snd.classList.add('play'); txt.textContent = 'звук';
        }).catch(function(){ txt.textContent = 'не вышло'; });
      } else {
        audio.pause();
        snd.classList.remove('play'); txt.textContent = 'слушать';
      }
    });

    /* Уходя с экрана, звук останавливаем: иначе сводка читается
       поверх зала, и два экрана говорят разное одновременно. */
    window.addEventListener('pagehide', function(){
      if (audio && !audio.paused) audio.pause();
    });
  })();

  /* ── ВЫХОД: стрелки листают, всё остальное закрывает ──
     Клавиатура: стрелки вправо и вниз — вперёд, влево и вверх — назад;
     любая другая клавиша закрывает. Исключения две, и обе про то, что
     нажатие не было командой сводке: одинокий модификатор и сочетание
     с Ctrl или Cmd (команда браузеру).
     Мышь: клик в любом месте закрывает, кроме полосы навигации внизу.
     Путь события берём составным (composedPath): клик рождается внутри
     теневого дерева, и снаружи его цель видна как узел #obfHost. */
  var MODS = { Shift:1, Control:1, Alt:1, Meta:1, CapsLock:1, NumLock:1,
               ScrollLock:1, Fn:1, FnLock:1, Hyper:1, Super:1, OS:1,
               Dead:1, Unidentified:1 };
  var done = false;
  document.addEventListener('keydown', function(e){
    if (done || cur < 0) return;
    var k = e.key;
    if (k === 'ArrowRight' || k === 'ArrowDown') { e.preventDefault(); show(cur + 1); return; }
    if (k === 'ArrowLeft'  || k === 'ArrowUp')   { e.preventDefault(); show(cur - 1); return; }
    if (MODS[k] || e.ctrlKey || e.metaKey) return;
    close();
  });
  document.addEventListener('click', function(e){
    if (done || cur < 0) return;
    var path = e.composedPath ? e.composedPath() : [], n;
    if (!path.length) for (n = e.target; n; n = n.parentNode) path.push(n);
    var sndBtn = q('#snd');
    /* Кальмар журнала — в тот же белый список (правка 01.09).
       Обработчик висит на ДОКУМЕНТЕ в фазе ПЕРЕХВАТА: он срабатывает
       раньше, чем событие дойдёт до ссылки, поэтому
       event.stopPropagation() на самой кнопке бесполезен — схема
       закрывалась, а переход не успевал. */
    var jrnBtn = q('.jrn');
    for (var i = 0; i < path.length; i++) {
      if (path[i] === nav || path[i] === sndBtn ||
          path[i] === jrnBtn) return;
    }
    close();
  }, true);

  /* Сводка не «закрывается», оставаясь в документе: документ и есть
     сводка. Она сообщает оболочке, что доиграла, и оболочка уничтожает
     документ вместе с таймерами. Класс .on снимается всё равно: между
     сообщением и сменой документа проходит кадр-другой. */
  function close(){
    clearTimeout(timer);
    wrap.classList.remove('on');
    if (done) return;
    done = true;
    try {
      window.parent.postMessage({ type: 'ob:done', screen: 'brief' },
                                window.location.origin);
    } catch (e) { /* открыт вне оболочки — просто гаснем */ }
  }

  /* ПРЕДОХРАНИТЕЛЬ, а не расписание: выход зовёт очередь мыслей выше.
     Таймер оставлен на случай, если она встанет намертво. */
  setTimeout(close, els.length * DWELL + 30000);

  function start(){ if (cur < 0) { show(0); try { window.focus(); } catch (e) {} } }

  wrap.classList.add('on');
  /* Подстраховка от невидимой сводки: класс .on гасит прозрачность из
     общего файла стилей, и если обёртка оказалась другой, экран мог бы
     остаться пустым при полностью рабочем скрипте. */
  setTimeout(function(){
    var ws = getComputedStyle(wrap);
    if (ws.display === 'none') wrap.style.display = 'block';
    if (ws.opacity === '0') { wrap.style.opacity = '1'; wrap.style.pointerEvents = 'auto'; }
  }, 60);

  if (reduce) {
    /* Без движения схема не идёт сама: показываем первую мысль и ждём
       стрелок. Гасим движение, а не смысл. */
    show(0); clearTimeout(timer);
  } else if (window.parent === window) {
    setTimeout(start, 2000);
  } else {
    window.addEventListener('message', function(e){
      if (e.origin !== window.location.origin) return;
      if (e.data && e.data.type === 'ob:shown') setTimeout(start, 2000);
    });
    setTimeout(start, 4500);   /* страховка: сигнал не пришёл */
  }
})();
</script>
"""

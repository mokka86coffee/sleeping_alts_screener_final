"""Карточка монеты · пейзаж. Открывается поверх экрана лидеров.

Модуль заменяет собой только РАСКРЫТУЮ карточку. Сам зал (podium.py)
не тронут: он по-прежнему строит стену панелей, а на клик отдаёт
монету сюда.

Почему пейзаж, а не приборный щиток. У щитка все величины равны:
пятнадцать ячеек одного кегля, и решение о том, что важно, каждый раз
принимает глаз заново. Здесь важность несёт форма — пять величин стоят
столбами света, и высота видна раньше, чем прочитано число. Остальные
десять никуда не делись, они лежат в ящике снизу: сначала впечатление,
потом справка.

Что чем стало:
  глубина от пика жизни   холодный синий, крайний слева
  перевес сторон          красный при продаже, зелёный при покупке
  ход от дна              янтарь, предел шкалы 300%
  объём против рекорда    золото, шкала логарифмическая
  возраст записи          белый, гаснет к четырнадцатому дню
Порядок слева направо — от холода к жару. Он же порядок стадии.

График цены стал грядой на заднем плане: история — это горизонт, на
фоне которого стоят все величины, а не отдельная панель рядом с ними.
Отметка входа в журнал осталась на гряде.

Своих данных у модуля нет: звезду передаёт зал вызовом
window.OBCARD.open(). Значения для нижнего ящика он передаёт уже
свёрстанными — своей вёрсткой тех же чисел модуль бы разошёлся с
залом при первой правке.

ЖИВЁТ В ДОКУМЕНТЕ ЗАЛА, а не дашборда, как было раньше. Вызов идёт
через window, а окно у каждого iframe своё: лежи сцена в соседнем
документе, open() не нашёл бы адресата — молча, без ошибки, потому
что зал проверяет наличие window.OBCARD перед вызовом.

СТИЛИ ЛЕЖАТ ЗДЕСЬ по той же причине, что и у подиума: модуль, который
несёт свою разметку, свой скрипт и свои стили, разойтись сам с собой
не может. Все правила загнаны под #obcRoot, имена анимаций с приставкой
oc — на странице уже живут дашборд, орбита и зал.
"""

from __future__ import annotations


def render_cardscene() -> str:
    return CARDSCENE_CSS + CARDSCENE_HTML + CARDSCENE_JS


CARDSCENE_CSS = """
<style>
/* ── Сцена ───────────────────────────────────────────────────
   Холст и текст живут в одном контейнере с общей системой
   координат: подписи ставятся по x столбов, которые считает JS,
   поэтому рисовать их внутри canvas незачем — DOM-текст резче
   и его можно выделить. */
/* Считаем от высоты, а не от ширины: на широком мониторе кадр
   вылезал за экран сверху и шапка с тикером уходила за край. */
#obcRoot .scene{position:relative;height:min(90vh,calc(96vw*880/1240));
  width:auto;aspect-ratio:1240/880;
  border-radius:3px;overflow:hidden;
  box-shadow:0 40px 120px rgba(0,0,0,.7)}
#obcRoot canvas{position:absolute;inset:0;width:100%;height:100%;display:block}

/* Перспектива нужна слою, а не самим подписям: у каждой из них
   свой поворот, но точка схода на кадр одна — иначе крайние
   столбы уезжали бы в другую сторону, чем центральные. */
#obcRoot .lay{position:absolute;inset:0;pointer-events:none;perspective:1000px}

/* ── Объёмный текст ─────────────────────────────────────────
   Один приём на весь кадр: тёмная фаска вниз даёт толщину,
   ореол currentColor — свет от самой буквы. Меняется только
   сила, чтобы шапка была громче подписей, а нижняя строка тише.
   Отражение вешаем через ::after и data-t: дублировать разметку
   ради зеркальной копии в каждом месте не хочется. */
#obcRoot .d3{position:relative;
  text-shadow:0 1px 0 rgba(0,0,0,.8),0 2px 0 rgba(0,0,0,.55),
    0 4px 6px rgba(0,0,0,.5),0 0 10px currentColor,0 0 30px currentColor}
#obcRoot .d3::after{content:attr(data-t);position:absolute;left:0;top:100%;
  transform:scaleY(-1);opacity:.24;filter:blur(1.4px);text-shadow:none;
  -webkit-mask-image:linear-gradient(#000,transparent 62%);
  mask-image:linear-gradient(#000,transparent 62%)}

/* ── Шапка ─────────────────────────────────────────────────── */
#obcRoot .tick{position:absolute;left:3.4%;top:5.2%;
  font-size:clamp(18px,2.6vw,34px);font-weight:200;letter-spacing:.34em;
  color:#EAF2F8;transform:perspective(800px) rotateX(15deg) rotateY(-9deg);
  transform-origin:0 100%}
#obcRoot .verd{position:absolute;left:3.6%;top:12.4%;
  font-size:clamp(7px,.82vw,10px);letter-spacing:.32em;text-transform:uppercase;
  color:#E8B25A;transform:perspective(800px) rotateX(12deg) rotateY(-7deg);
  transform-origin:0 100%}
/* Класс переименован: `cap` есть и в глобальных стилях дашборда,
   оттуда у капитализации бралась пилюля с рамкой, а все здешние
   правила — переход и уход — до неё не доходили вовсе. */
#obcRoot .obc-cap{position:absolute;right:3.4%;top:5.6%;
  font-size:clamp(9px,1.1vw,14px);font-weight:300;letter-spacing:.12em;color:#8FA3B4;
  transform:perspective(800px) rotateX(12deg) rotateY(9deg);transform-origin:100% 100%}

/* ── Подписи столбов ────────────────────────────────────────
   Текст лежит на воде, а не висит над ней: наклон по X кладёт
   строку в плоскость поверхности, отражение под числом делает
   её частью сцены, а не наклейкой поверх. */
#obcRoot .col{position:absolute;transform-origin:50% 0;text-align:center;
  transition:opacity .4s ease}
#obcRoot .vw{position:relative}
#obcRoot .col .v, #obcRoot .col .rf{font-size:clamp(11px,1.45vw,19px);font-weight:250;
  letter-spacing:.04em;line-height:1;white-space:nowrap}
/* Три тёмных смещения вниз дают букве толщину, два цветных
   ореола — свет от неё же. Свечение берём currentColor, поэтому
   тон подписи и тон столба не могут разойтись. */
#obcRoot .col .v{text-shadow:
    0 1px 0 rgba(0,0,0,.75), 0 2px 0 rgba(0,0,0,.55),
    0 3px 3px rgba(0,0,0,.5),
    0 0 9px currentColor, 0 0 26px currentColor}
#obcRoot .col .rf{position:absolute;left:0;right:0;top:100%;
  transform:scaleY(-1);opacity:.3;filter:blur(1.3px);
  -webkit-mask-image:linear-gradient(#000,transparent 68%);
  mask-image:linear-gradient(#000,transparent 68%)}
#obcRoot .col .n{margin-top:1.15em;font-size:clamp(6px,.72vw,9px);letter-spacing:.3em;
  text-transform:uppercase;color:#B6C8D6;white-space:nowrap;
  text-shadow:0 1px 2px rgba(0,0,0,.9),0 0 14px rgba(150,190,220,.4)}
#obcRoot .col .s{margin-top:.55em;font-size:clamp(6px,.68vw,8.5px);letter-spacing:.16em;
  color:#7C8D9B;white-space:nowrap;text-shadow:0 1px 2px rgba(0,0,0,.9)}

/* Под каждой подписью — размытое пятно, будто свет столба лёг на
   воду именно здесь. Оно и даёт объём: текст перестаёт быть
   наклейкой и получает поверхность, на которой лежит. */
#obcRoot .cin::before{content:'';position:absolute;left:50%;top:-18%;
  width:210%;height:150%;transform:translateX(-50%);pointer-events:none;
  /* Подложка тёмная, а не светлая: подписи лежат на отражении
     столбов, которое само по себе яркое, и светлое пятно съедало
     последний контраст. Тень на воде читается так же естественно,
     как свет, и текст на ней виден. */
  background:radial-gradient(ellipse at 50% 45%,
    rgba(4,10,16,.62),rgba(4,10,16,.34) 46%,transparent 74%);
  filter:blur(4px);z-index:-1}

/* ── Кольцо краткосрока ─────────────────────────────────────
   Полоса внизу ушла целиком. Коридор входа стал КОЛЬЦОМ, стоящим
   на воде: низ обода касается поверхности, верх поднят в небо,
   светящаяся точка цены едет по ободу.

   Почему кольцо, а не шкала. Во-первых, направление: вверх по
   ободу — вверх по цене, и объяснять это не надо. Во-вторых,
   кольцо нарисовано ВНУТРИ сцены, до столбов, — поэтому столбы
   проходят перед ним, а вода отражает его сама, тем же кодом,
   что отражает лодку. Полоса поверх кадра отражаться не умела и
   всегда оставалась наклейкой.

   На холсте живёт только свет: обод, засечки в один ATR, узлы
   опоры и потолка, точка цены. Подписи — HTML поверх: у отчёта
   своя гарнитура и трекинг, текст внутри холста жил бы по своим
   правилам. Слой подписей сквозной для мыши — он ничего не ловит. */
#obcRoot .near{position:absolute;inset:0;pointer-events:none;z-index:3}
/* Ширина подписи ограничена самим ободом и приходит инлайном из
   геометрии: строка, вылезшая за кольцо, попадает на свет столбов
   и становится нечитаемой. Перенос разрешён — лучше две строки
   внутри, чем одна поверх столба. */
#obcRoot .rl{position:absolute;transform:translate(-50%,-50%);
  text-align:center;white-space:normal}
/* Текст в кольце идёт БЕЗ теней. Прежде под буквами лежала
   многослойная подложка, гасившая ореол обода; вблизи она читалась
   грязным пятном вокруг каждой строки. Контраст держат сами цвета:
   кольцо тонкое, фон под ним тёмный, подложка не нужна. */
#obcRoot .rl-k{font-size:clamp(5.5px,.64vw,8px);letter-spacing:.4em;
  text-transform:uppercase;color:#7C8B9A}
#obcRoot .rl-v{margin-top:.3em;font-size:clamp(7.5px,.88vw,11px);
  font-weight:300;letter-spacing:.06em;color:#E4EEF8}
#obcRoot .rl-s{margin-top:.3em;font-size:clamp(5.5px,.66vw,8.5px);
  letter-spacing:.06em;color:#95A6B5}
#obcRoot .rl-s em{font-style:normal;color:#B9C7D3}
#obcRoot .rl-s s{text-decoration:none;color:#63A6E0}
#obcRoot .rl.up .rl-v{color:#FF8A52}
#obcRoot .rl.dn .rl-v{color:#6FE3B4}
#obcRoot .rl.px .rl-k{color:#B9C7D3;letter-spacing:.34em}

/* Центр кольца — как надпись внутри кольца на референсе: тихо,
   разрядкой, по центру. Здесь стоит проверка усилия и исход теста:
   два вывода, которые не привязаны ни к какому уровню. */
#obcRoot .rl-core{position:absolute;transform:translate(-50%,-50%);
  text-align:center;white-space:normal}
#obcRoot .rl-x{font-size:clamp(13px,1.6vw,22px);font-weight:200;
  letter-spacing:.02em;line-height:1;color:#FFC978}
#obcRoot .rl-x.mute{color:#7E8F9D}
#obcRoot .rl-w{margin-top:.55em;font-size:clamp(6.5px,.78vw,9.5px);
  line-height:1.5;color:#B4C5D4}
#obcRoot .rl-w b{font-weight:400;color:#E6ECF3}
#obcRoot .rl-w b.dn{color:#FF8A52} #obcRoot .rl-w b.up{color:#6FE3B4}
#obcRoot .rl-t{margin-top:.9em;font-size:clamp(6px,.72vw,9px);
  letter-spacing:.16em;text-transform:uppercase;color:#95A6B5}
#obcRoot .rl-t b{font-weight:400}
#obcRoot .rl-t b.ok{color:#6FE3B4} #obcRoot .rl-t b.no{color:#FF8A52}

/* ── Переключатель монет ────────────────────────────────────── */
/* ── Значки предложения и инвесторов ────────────────────────
   Пейзаж отвечает «что происходит», значки — «из чего это следует».
   Оба признака уже показаны формой: фонарь горит по весу инвесторов,
   туман стоит по срокам разлока. Но форма даёт впечатление, а не
   имена и не числа, поэтому рядом нужен способ спросить.

   Раскрытие по наведению и по касанию: на планшете наведения нет, а
   значок без ответа хуже отсутствующего. */
/* ── Планка у нижнего края кадра ──
   Не под экраном, а внизу самой картинки: она подпись к кадру и
   должна лежать в нём, на тёмном подножии, где вода уже погасла.
   Слой сквозной для мыши, ловят только сами приборы. */
#obcRoot .obc-bar{position:absolute;left:3.4%;right:3.4%;bottom:7.2%;
  z-index:4;display:flex;align-items:center;
  gap:clamp(12px,1.8vw,26px);pointer-events:none}

/* Раскладка знаков. Правило было потеряно при замене блока ручек, и
   вместе с ним пропало разрешение ловить курсор: слой сцены сквозной
   для мыши (.lay), поэтому каждый интерактивный элемент внутри обязан
   включать pointer-events сам. Без этого знаки вставали столбиком и
   молчали на наведение. */
#obcRoot .obc-marks{display:flex;flex-direction:row;align-items:center;
  gap:clamp(10px,1.2vw,16px);margin-left:auto;pointer-events:auto}

/* ── Знаки ──
   Подложки убраны совсем: купол и фаска делали из двух признаков
   пару кнопок, а нажимать здесь нечего — это показания. Осталось
   то, что и должно было остаться: знак, его свечение и подпись
   при наведении.

   Начертание иероглифическое, и это не украшение. Кадр — вода,
   пагода, сосны, фонари; латинская пиктограмма в нём читалась бы
   как наклейка из другого набора. Знаки выбраны по смыслу:
   «хозяин» — кто стоит за монетой, «дождь» — предложение, которое
   ещё сыплется сверху. Каждый нарисован кистью: концы скруглены,
   толщина черт разная, как в письме. */
#obcRoot .obc-mark{position:relative;width:30px;height:30px;cursor:default;
  transition:transform .25s ease}
#obcRoot .obc-mark:hover{transform:translateY(-2px)}
#obcRoot .obc-mark svg{position:absolute;inset:0;width:100%;height:100%;
  fill:none;stroke:rgba(220,177,118,.62);stroke-width:1.5;
  stroke-linecap:round;stroke-linejoin:round;
  filter:drop-shadow(0 1px 2px rgba(0,0,0,.95))
         drop-shadow(0 0 9px rgba(216,170,106,.3));
  transition:stroke .3s ease,filter .3s ease}
/* Знак всегда одного тона со стратегией: это подписи одного рода, и
   разный цвет заставлял бы искать разницу там, где её нет.
   Состояние несут не черты, а показание внутри знака — точка у
   «хозяина», капли у «дождя», — и сила свечения вокруг. */
#obcRoot .obc-mark svg .dot{fill:rgba(220,177,118,.9);stroke:none}
#obcRoot .obc-mark:hover svg{stroke:rgba(244,214,166,.95);
  filter:drop-shadow(0 1px 2px rgba(0,0,0,.95))
         drop-shadow(0 0 14px rgba(216,170,106,.5))}
#obcRoot .obc-mark.off svg{stroke:rgba(220,177,118,.3);
  filter:drop-shadow(0 1px 2px rgba(0,0,0,.9))}
#obcRoot .obc-mark.off svg .dot{fill:rgba(200,190,178,.34)}
#obcRoot .obc-mark.hot svg{stroke:rgba(220,177,118,.92);
  filter:drop-shadow(0 1px 2px rgba(0,0,0,.95))
         drop-shadow(0 0 14px rgba(255,150,70,.5))}
#obcRoot .obc-mark.hot svg .dot{fill:rgba(255,178,96,.98)}
#obcRoot .obc-mark.free svg{stroke:rgba(220,177,118,.88);
  filter:drop-shadow(0 1px 2px rgba(0,0,0,.95))
         drop-shadow(0 0 13px rgba(110,225,175,.42))}
#obcRoot .obc-mark.free svg .dot{fill:rgba(122,232,186,.95)}

#obcRoot .obc-tip{position:absolute;right:0;bottom:135%;min-width:150px;
  padding:9px 11px;border-radius:3px;pointer-events:none;
  background:rgba(8,13,19,.96);border:1px solid rgba(150,190,225,.22);
  box-shadow:0 12px 32px rgba(0,0,0,.7);
  font-size:10.5px;line-height:1.55;letter-spacing:.04em;color:#A9BCCB;
  text-align:left;text-transform:none;
  opacity:0;transform:translateY(4px);transition:opacity .25s ease,transform .25s ease}
#obcRoot .obc-mark:hover .obc-tip,#obcRoot .obc-mark.open .obc-tip{
  opacity:1;transform:translateY(0)}
#obcRoot .obc-tip b{display:block;color:#E3E9F0;font-weight:400;
  letter-spacing:.16em;text-transform:uppercase;font-size:8.5px;
  margin-bottom:5px}
#obcRoot .obc-tip i{font-style:normal;color:#FF8A52}
#obcRoot .obc-tip u{text-decoration:none;color:#6FE3B4}

/* ── Приборная полоса ───────────────────────────────────────
   Живёт в самом низу, где вода темнее всего, поэтому под ней
   лежит собственная подложка — иначе тонкие светящиеся линии
   тонут в отражении столбов. */
/* Полоса приборов стоит над сценой. Раньше она вставала туда сама,
   потому что селектор писался на #diag, а элемент называется obcDiag,
   и правило до него не доставало. Положение прижилось, поэтому теперь
   оно задано намеренно: высота по своей пропорции, ширина по кадру. */
#obcRoot #obcDiag{position:absolute;left:0;right:0;top:0}
#obcRoot #obcDiag svg{width:100%;height:auto;display:block}
#obcRoot .scrim{position:absolute;left:0;right:0;bottom:0;height:26%;
  background:linear-gradient(transparent,rgba(3,7,11,.86) 62%)}




/* ── Появление текста ───────────────────────────────────────
   Всё, что написано словами, проявляется одинаково: чуть снизу
   и с расширением разрядки. Буквы как будто сходятся к месту,
   а не всплывают готовой плашкой. */
@keyframes ocAppear{
  from{opacity:0;transform:translateY(10px);letter-spacing:.6em;filter:blur(4px)}
  to  {opacity:1;transform:translateY(0);filter:blur(0)}
}
/* Класс появления снят со всех: приход и уход текста делает переход.
   Кадры ocAppear остаются — ими живут подписи столбов, у них своя
   ступенчатая задержка, и переходом её не выразить. */
/* Столбец проявляется сверху вниз и мягко: резкий въезд спорил бы
   с водой, где всё держится на затухании. Тикер приходит первым,
   подпись за ним — тем же порядком, каким их читают. */
/* Своих кадров у столбца тикера больше нет: он приходит и уходит тем
   же переходом, что и остальной текст. */
#obcRoot .cin{position:relative;animation:ocAppear 2.4s cubic-bezier(.16,.84,.3,1) both}
/* Первая половина перехода: старые подписи уезжают вниз, к воде,
   и тонут вместе со своими столбами. */
/* Уходить должно всё, что написано словами, иначе половина кадра
   растворяется, а вторая подменяется рывком — это и читается как
   дефект. Имя, стратегия, фраза и капитализация теперь гаснут вместе
   с подписями и приборной полосой. */
/* Уход и приход — один и тот же переход, в обе стороны. Раньше уход
   делал переход, а приход — отдельная анимация с fill both, и они
   спорили за одни и те же свойства: анимация после проигрывания
   продолжает удерживать конечные значения, поэтому снимать её
   приходилось руками, а снятие давало рывок. Двух механизмов на одно
   движение быть не должно — здесь остаётся один.

   Разрядка и размытие переводятся тем же переходом, поэтому эффект
   схождения букв никуда не делся: он просто перестал быть отдельной
   сущностью со своей жизнью. */
#obcRoot .col, #obcRoot .near, #obcRoot #obcDiag,
#obcRoot .bname, #obcRoot .bstr, #obcRoot .obc-note, #obcRoot .obc-cap,
#obcRoot .obc-marks{
  transition:opacity 1.75s ease, transform 1.75s ease,
             letter-spacing 1.75s ease, filter 1.75s ease}
#obcRoot .lay.out .col, #obcRoot .lay.out #obcDiag,
#obcRoot .lay.out .obc-note, #obcRoot .lay.out .obc-marks{
  opacity:0;transform:translateY(14px)}
/* У нижней строки и капитализации есть собственный наклон, и правило
   ухода его затирало: перспектива слетала в первом же кадре, отчего
   уход читался рывком, а не уходом. Свой поворот переносим сюда
   целиком и добавляем сдвиг к нему, а не вместо него. */
#obcRoot .lay.out .near{opacity:0;letter-spacing:.5em;filter:blur(4px);
  transform:perspective(900px) rotateX(16deg) translateY(14px)}
#obcRoot .lay.out .obc-cap{opacity:0;letter-spacing:.4em;filter:blur(4px);
  transform:perspective(800px) rotateX(12deg) rotateY(9deg) translateY(14px)}
/* Столбец тикера уходит вверх, откуда и пришёл, — вниз ему некуда:
   он стоит вертикально и упирается в край кадра. */
#obcRoot .lay.out .bname, #obcRoot .lay.out .bstr{
  opacity:0;transform:translateY(-12px);filter:blur(5px)}
#obcRoot .lay.out .bname{letter-spacing:.8em}
#obcRoot .lay.out .bstr{letter-spacing:.3em}
/* Подпись приходит следом за тикером, но уходит вместе с ним:
   задержка нужна только на возвращении. */
#obcRoot .bstr{transition-delay:.35s}
#obcRoot .lay.out .bstr{transition-delay:0s}

/* Приборы: линия рисуется слева направо, гребёнка проявляется
   вслед за ней, дуги доезжают до значения, огонёк на конце
   зажигается последним. */
@keyframes ocDraw{to{stroke-dashoffset:0}}
@keyframes ocHin{to{opacity:1}}
#obcRoot .ln{stroke-dasharray:1400;stroke-dashoffset:1400;
  animation:ocDraw 3.45s .75s cubic-bezier(.3,.7,.3,1) forwards}
#obcRoot .hair line{opacity:0;animation:ocHin 1.35s ease forwards}
#obcRoot .val{animation:ocDraw 2.85s 1.5s cubic-bezier(.3,.8,.3,1) forwards}
#obcRoot .tipdot{opacity:0;animation:ocHin 1.5s 3.75s ease forwards}

/* ── Лодка ──────────────────────────────────────────────────
   Имя монеты и стратегия переехали из угла кадра на воду. В углу
   они были подписью к картинке; на лодке они предмет внутри неё —
   и заодно появляется то, чего сцене не хватало: единственное,
   что движется само по себе, а не отвечает на данные.
   Три вложенных слоя, потому что снос, качку и крен нельзя
   сложить в один transform — они разной длительности. */
/* Вдвое меньше и ниже: лодка больше не несёт текст, поэтому ей
   не нужен размер — только присутствие. Ватерлиния по-прежнему
   режет корпус, поэтому при смене размера едет и верх блока. */
#obcRoot .boat{position:absolute;left:17%;top:54%;width:11.5%;pointer-events:none}
/* ── Парус несёт вортекс ────────────────────────────────────
   У лодки был парус, который ничего не значил. Теперь он наполнен в
   ту сторону, куда тянет вортекс, а крен корпуса взят из скорости
   хода. «Вниз двенадцать баров при 1.3 ATR» видно на воде раньше,
   чем прочитано хоть одно число, — и мы не добавили в кадр ни одного
   нового предмета, только объяснили тот, что уже плавал.

   Зеркалим парус относительно мачты: она стоит на x=150, значит
   отражение это x' = 300 − x. */
#obcRoot .boat .sail{transform-origin:0 0}
/* ── Фонарь как признак инвесторов ──────────────────────────
   Кто стоит за монетой — не показание, а свойство: инвестор не
   меняется годами и не говорит «покупай». Он говорит, какого размера
   движение вообще возможно. Отдельного знака под это заводить не
   нужно — на лодке уже горит фонарь, и «под чьим флагом идёт судно»
   выражается его силой, а не второй эмблемой рядом.

   Считается не числом имён, а весом: фонд первого тира тянет втрое
   против третьего. Три безымянных мелких фонда не должны светить
   ярче, чем один DWF. */
#obcRoot .boat .lamp{transform-box:fill-box;transform-origin:50% 50%;
  /* Нижняя граница не ноль и не почти ноль: лодка идёт ночью в любом
     случае, и потухший фонарь читается поломкой, а не отсутствием
     инвесторов. Разницу несёт верхняя половина шкалы. */
  opacity:calc(.62 + var(--inv,0) * .38);
  transform:scale(calc(.88 + var(--inv,0) * .46));
  transition:opacity 1.2s ease, transform 1.2s ease}
#obcRoot .pool{opacity:calc(.55 + var(--inv,0) * .45)}
#obcRoot .boat.wind-l .sail{transform:translateX(300px) scaleX(-1)}
#obcRoot .boat{transform:rotate(var(--heel,0deg));
  transform-origin:50% 68%;transition:transform 1.6s ease}
#obcRoot .boat .drift{animation:ocDrift 26s ease-in-out infinite alternate}
/* Лодку на переходе не трогаем. Смена длительности у идущей анимации
   пересчитывает фазу, и качка прыгает — а лодка и так всё время
   покачивается, этого достаточно. Единственное живое движение в
   кадре не должно спотыкаться ровно там, где на него смотрят. */
#obcRoot .boat .bob{animation:ocBob 5.2s ease-in-out infinite alternate}
#obcRoot .boat .tilt{animation:ocTilt 7.4s ease-in-out infinite alternate;
  transform-origin:50% 90%}
@keyframes ocDrift{from{transform:translateX(-14px)}to{transform:translateX(26px)}}
@keyframes ocBob{from{transform:translateY(0)}    to{transform:translateY(6px)}}
@keyframes ocTilt{from{transform:rotate(-1.5deg)}  to{transform:rotate(1.6deg)}}
#obcRoot .boat svg{width:100%;height:auto;display:block;overflow:visible}

/* ── Шапка ──────────────────────────────────────────────────
   Имя стояло рукописным во весь кадр и занимало его левую
   половину. На таком кегле почерк перестаёт быть почерком и
   становится пятном: места много, прочесть нечем.

   Теперь это вертикальный столбец у правого поля — так, как
   подписывают свиток. Правая сторона кадра пустует, вертикаль
   рифмуется со столбами света, а к берегу с пагодой и соснами
   эта форма подписи принадлежит по праву рождения.

   Тикер набирается прямостоящими буквами: он такая же величина,
   как остальные, и должен читаться сразу. Стратегия остаётся
   росчерком и идёт вдоль поля, как подпись на полях, — она
   единственное в кадре, что не измерено, а названо. */
#obcRoot .bname{position:absolute;right:3.6%;top:22%;
  writing-mode:vertical-rl;text-orientation:upright;
  font-size:clamp(11px,1.35vw,20px);font-weight:200;letter-spacing:.34em;
  color:#E9F1F8;
  text-shadow:0 2px 10px rgba(0,0,0,.85),0 0 24px rgba(150,195,235,.22);
  /* Слой подписей сквозной для мыши (pointer-events:none у .lay) —
     иначе он накрыл бы сцену. Ссылке клики возвращаем точечно: она
     единственное, что здесь нажимается. */
  pointer-events:auto;text-decoration:none;cursor:pointer;
  transition:color .3s,text-shadow .3s}
#obcRoot .bname:hover{color:#fff;
  text-shadow:0 2px 10px rgba(0,0,0,.85),0 0 30px rgba(150,195,235,.5)}
#obcRoot .bname:focus-visible{outline:1px solid rgba(150,195,235,.7);
  outline-offset:6px;border-radius:4px}
/* Волосок между тикером и стратегией: короткий, гаснущий книзу.
   Он не разделяет их, а показывает, что подпись идёт следом. */
#obcRoot .bname::after{content:'';position:absolute;left:50%;top:100%;
  transform:translateX(-50%);margin-top:16px;
  width:1px;height:clamp(18px,3vh,38px);
  background:linear-gradient(rgba(190,215,235,.36),transparent)}
/* Рукописный шрифт здесь не работал: на кегле в полтора десятка
   пикселей почерк перестаёт быть почерком и становится пятном, а
   рядом с гротеском всего остального кадра читается как чужая
   наклейка. Гарнитура теперь общая, а отличие несут разрядка,
   вес и тон — тем же способом, каким различаются подписи столбов.
   Тикер стоит прямыми буквами, стратегия повёрнута: две вертикали
   не сливаются. */
/* Табличка снята: гравировка спорила с кадром и превращала подпись
   в элемент интерфейса. Остались буквы — разрядка и тон делают всё
   остальное. */
/* Развёрнутый ответ занимает остаток полосы. Кегль меньше
   стратегии и цвет холоднее: это пояснение, а не заголовок, и
   спорить с ним за внимание оно не должно. */
#obcRoot .bwhy{flex:1 1 auto;min-width:0;
  display:flex;flex-direction:column;gap:2px;
  font-size:clamp(7px,.78vw,10px);font-weight:300;line-height:1.5;
  letter-spacing:.05em;color:#93A7BC;
  text-shadow:0 1px 2px rgba(0,0,0,.95),0 0 10px rgba(3,7,12,.8)}
#obcRoot .bwhy:empty{display:none}
#obcRoot .bwhy b{font-weight:300;color:#B9CBDD}
/* Условие снятия — единственное светлое пятно в блоке: это то,
   ради чего его читают. */
#obcRoot .bwhy .lift{color:#DCB176;opacity:.82}
#obcRoot .bwhy .lift::before{content:"→ ";opacity:.6}

#obcRoot .bstr{position:relative;
  font-size:clamp(9px,1.02vw,13px);font-weight:300;
  letter-spacing:.4em;text-transform:lowercase;white-space:nowrap;
  color:#DCB176;
  text-shadow:0 1px 2px rgba(0,0,0,.98),0 0 8px rgba(3,7,12,.9),
              0 0 20px rgba(216,170,106,.42)}

/* ── Стая ───────────────────────────────────────────────────
   Дельфины выходят только тогда, когда перевес на стороне покупки.
   Это единственное живое существо в кадре, и появляться оно должно
   не для красоты, а по той же причине, по какой светятся столбы:
   в воде кто-то есть. При перевесе продавца вода пустая, и это
   читается само, без подписи.

   Прыжок разложен на два слоя. Горизонтальный идёт ровно, вертикаль
   выгибается дугой — так и получается парабола; свести их в один
   transform нельзя, у них разный ход времени. Тело доворачивается
   отдельно: на взлёте носом вверх, на входе носом вниз. */
/* Низ стаи стоит ровно на линии воды: 530 из 880 внутренних единиц
   кадра — та же ватерлиния, что у лодки и у столбов. При 52% дельфины
   висели в воздухе на семьдесят пикселей выше воды и не входили в неё. */
#obcRoot .pod{position:absolute;left:26%;top:60.23%;width:23%;
  pointer-events:none;opacity:0;transition:opacity 1.2s ease}
#obcRoot.buyers .pod{opacity:1}
#obcRoot .dol{position:absolute;left:0;bottom:0;width:20%}
/* Один прыгает навстречу. Зеркалим весь блок целиком: разворачивается
   и тело, и направление хода, и наклон на взлёте — три правки одной. */
#obcRoot .dol.b{transform:scaleX(-1)}
#obcRoot .dol svg{width:100%;height:auto;display:block;overflow:visible}
#obcRoot .dx{animation:ocDolX 6s linear infinite}
#obcRoot .dy{animation:ocDolY 6s linear infinite}
#obcRoot .dr{animation:ocDolR 6s linear infinite}

/* Вне прыжка дельфин под водой, поэтому его просто нет: гасим до
   нуля, а не оставляем висеть над поверхностью. */
@keyframes ocDolX{
  0%{transform:translateX(-10%);opacity:0}
  4%{opacity:1}
  32%{opacity:1}
  38%{transform:translateX(190%);opacity:0}
  100%{transform:translateX(190%);opacity:0}
}
/* Высота снята с настоящей параболы по девяти точкам, а шаг между
   ними ровный. Прежде вертикаль шла одной плавной кривой с замедлением
   к верху — от этого дельфин зависал в воздухе, как планирующая птица.
   У брошенного тела скорость падает не плавно, а линейно, и вершина
   проскакивает почти мгновенно. */
@keyframes ocDolY{
  0%     {transform:translateY(14%)}
  4.75%  {transform:translateY(-58%)}
  9.5%   {transform:translateY(-110%)}
  14.25% {transform:translateY(-141%)}
  19%    {transform:translateY(-151%)}
  23.75% {transform:translateY(-141%)}
  28.5%  {transform:translateY(-110%)}
  33.25% {transform:translateY(-58%)}
  38%,100%{transform:translateY(14%)}
}
/* Тело всегда лежит по касательной к дуге, а касательная быстрее
   всего разворачивается как раз на вершине: там вертикальная скорость
   меняет знак. Поэтому у горизонтали дельфин не задерживается —
   проскакивает её за десятую долю прыжка. */
@keyframes ocDolR{
  0%     {transform:rotate(-46deg)}
  9.5%   {transform:rotate(-34deg)}
  15%    {transform:rotate(-19deg)}
  19%    {transform:rotate(0deg)}
  23%    {transform:rotate(19deg)}
  28.5%  {transform:rotate(34deg)}
  38%,100%{transform:rotate(46deg)}
}
/* Второй и третий идут следом с задержкой — стая, а не строй. */
#obcRoot .dol.b{left:44%;width:16%}
#obcRoot .dol.b .dx,#obcRoot .dol.b .dy,#obcRoot .dol.b .dr{animation-delay:.5s}
#obcRoot .dol.c{left:66%;width:13%}
#obcRoot .dol.c .dx,#obcRoot .dol.c .dy,#obcRoot .dol.c .dr{animation-delay:1.05s}

/* След на воде там, где стая вошла: два расходящихся кольца. */
#obcRoot .pod-wake{position:absolute;left:38%;bottom:-2%;width:44%;height:14%;
  border-radius:50%;border:1px solid rgba(190,215,235,.22);
  animation:ocWake 6s ease-out infinite;animation-delay:1.6s}

/* Тёплое пятно на воде от фонаря: свет должен куда-то падать. */
#obcRoot .pool{position:absolute;left:6%;top:66%;width:88%;height:34%;
  background:radial-gradient(ellipse at 46% 50%,rgba(255,150,60,.17),transparent 68%);
  filter:blur(6px)}

/* Отражение лодки — та же разметка вверх ногами. Качается своим
   ритмом, чуть медленнее: вода отзывается с запозданием. */
/* Отражение строится вокруг самой ватерлинии, а не вокруг края
   блока: точка опоры — 66% высоты кадра лодки, там вода. */
#obcRoot .boat.mir{opacity:.24;filter:blur(1.7px);
  transform:scaleY(-1) rotate(var(--heel,0deg));transform-origin:50% 66%;
  -webkit-mask-image:linear-gradient(transparent 10%,#000 58%);
  mask-image:linear-gradient(transparent 10%,#000 58%)}
#obcRoot .boat.mir .bob{animation-duration:5.9s}

/* Расходящиеся круги у борта — единственное, что доказывает, что
   лодка стоит на воде, а не висит над ней. */
#obcRoot .wake{position:absolute;left:50%;top:64%;width:60%;height:12%;
  transform:translateX(-50%);border-radius:50%;
  border:1px solid rgba(190,215,235,.20);
  animation:ocWake 6s linear infinite}
#obcRoot .wake.b{animation-delay:3s}
@keyframes ocWake{
  from{opacity:.5;transform:translateX(-50%) scale(.35)}
  to  {opacity:0; transform:translateX(-50%) scale(1.5)}
}


        #obcRoot .hair{stroke:url(#hg);stroke-width:1.6}
        #obcRoot .ln{fill:none;stroke:#FFD79A;stroke-width:1.8;stroke-linecap:round}
        #obcRoot .ring{fill:none;stroke:rgba(190,215,235,.16);stroke-width:1.2}
        #obcRoot .val{fill:none;stroke:#F0BE6E;stroke-width:2.4;stroke-linecap:round}
        #obcRoot .num{fill:#EEDCBC;font:250 19px 'Helvetica Neue',sans-serif;text-anchor:middle;letter-spacing:.02em}
        #obcRoot .pc{font-size:11px;fill:#8B7B60}
        #obcRoot .cap2{fill:#63717E;font:400 8px 'Helvetica Neue',sans-serif;text-anchor:middle;
              letter-spacing:2.6px;text-transform:uppercase}
        #obcRoot .rule{stroke:rgba(180,205,230,.14);stroke-width:1}
        #obcRoot .tk{stroke:rgba(180,205,230,.26);stroke-width:1}
/* ── Оболочка ───────────────────────────────────────────────
   Карточка занимает весь экран, а не коробку по центру: пейзажу
   нужен горизонт, а в коробке 660 пикселей горизонта нет. */
/* Закрытая карточка не должна ни рисоваться, ни ловить нажатия.
   display:none снимает отрисовку, visibility и pointer-events —
   попадания: на планшете промах по невидимому слою открывал карточку
   поверх дашборда, потому что слой лежал во весь экран. */
#obcRoot{position:fixed;inset:0;z-index:60;display:none;
  visibility:hidden;pointer-events:none;
  align-items:center;justify-content:center;background:#04070B;
  opacity:0;transition:opacity .45s ease;
  font-family:'Helvetica Neue',Inter,system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;color:#E8EEF4}
#obcRoot.on{display:flex;visibility:visible;pointer-events:auto;opacity:1}
#obcRoot *{box-sizing:border-box}

/* ── Листание ───────────────────────────────────────────────
   Стрелки стоят у самых краёв, за пределами кадра: внутри они
   спорили бы со столбами, а вернуться на подиум ради соседней
   монеты — потерять место, на котором стоял. */
#obcRoot .obc-nav{position:absolute;top:50%;transform:translateY(-50%);
  width:56px;height:96px;border:0;background:none;cursor:pointer;
  color:#5E7182;transition:color .25s ease,transform .25s ease;
  display:flex;align-items:center;justify-content:center}
#obcRoot .obc-nav:hover{color:#DCE8F2}
#obcRoot .obc-nav.l{left:6px} #obcRoot .obc-nav.r{right:6px}
#obcRoot .obc-nav.l:hover{transform:translateY(-50%) translateX(-4px)}
#obcRoot .obc-nav.r:hover{transform:translateY(-50%) translateX(4px)}
#obcRoot .obc-nav svg{width:26px;height:26px;fill:none;
  stroke:currentColor;stroke-width:1.2}
#obcRoot .obc-pos{position:absolute;left:50%;bottom:10px;
  transform:translateX(-50%);font-size:8px;letter-spacing:3px;
  text-transform:uppercase;color:#3D4855}
#obcRoot .obc-pos b{color:#93A3B1;font-weight:400}

#obcRoot .obc-close{position:absolute;right:20px;top:18px;z-index:4;
  border:0;background:none;cursor:pointer;font-size:8.5px;
  letter-spacing:3px;text-transform:uppercase;color:#57646F;
  transition:color .25s ease}
#obcRoot .obc-close:hover{color:#DCE8F2}

/* ── Ящик со всеми величинами ───────────────────────────────
   Пейзаж отвечает «что происходит», ящик — «из чего это следует».
   Он закрыт по умолчанию: справка, открытая всегда, перестаёт быть
   справкой и становится фоном. */
#obcRoot .obc-goto{position:absolute;left:20px;bottom:14px;z-index:4;
  border:0;background:none;cursor:pointer;font-size:8.5px;
  letter-spacing:3px;text-transform:uppercase;color:#57646F;
  transition:color .25s ease;display:none}
#obcRoot .obc-goto.on{display:block}
#obcRoot .obc-goto:hover{color:#DCE8F2}
#obcRoot .obc-more{position:absolute;right:20px;bottom:14px;z-index:4;
  border:0;background:none;cursor:pointer;font-size:8.5px;
  letter-spacing:3px;text-transform:uppercase;color:#57646F;
  transition:color .25s ease}
#obcRoot .obc-more:hover{color:#DCE8F2}
#obcRoot .obc-draw{position:absolute;left:0;right:0;bottom:0;z-index:5;
  max-height:74%;overflow-y:auto;transform:translateY(101%);
  transition:transform .5s cubic-bezier(.16,.84,.3,1);
  background:linear-gradient(rgba(6,10,15,.94),rgba(4,7,11,.99));
  border-top:1px solid rgba(150,190,225,.14);
  box-shadow:0 -30px 80px rgba(0,0,0,.8)}
#obcRoot.drawer .obc-draw{transform:translateY(0)}
#obcRoot .obc-draw-x{position:sticky;top:0;text-align:right;
  padding:12px 20px 4px;font-size:8.5px;letter-spacing:3px;
  text-transform:uppercase;color:#57646F;cursor:pointer}

/* Строка наблюдения — единственная фраза словами в кадре. Стоит
   над приборами, потому что она их вывод, а не подпись к ним. */
/* Фраза стояла по центру и попадала ровно под нижний ряд подписей —
   два разных текста в одной точке, оба нечитаемы. Левая треть кадра
   пуста, там её ничто не перекрывает. Ширину ограничиваем, чтобы
   строка не доехала до столбов: пусть лучше ляжет в две строки. */
#obcRoot .obc-note{position:absolute;left:4.5%;right:auto;max-width:27%;
  bottom:22.5%;text-align:left;max-width:30%;
  /* на пятую часть мельче прежнего: два уровня сами по себе заметнее
     одной строки, и прежний кегль стал спорить со столбами */
  font-size:clamp(8px,.92vw,11.2px);line-height:1.6;
  color:#AFC1CF;text-shadow:0 2px 6px rgba(0,0,0,.9)}
/* ── Два уровня ─────────────────────────────────────────────
   Фраза разламывается по смыслу: главное идёт крупно и в цвет,
   остальное уходит в мелкую разрядку. Ломать есть по чему — зал уже
   помечает ключевой кусок наблюдения тегом, и до сих пор эта пометка
   только красила его цветом; теперь она задаёт ещё и размер.

   Это же разводит фразу с приборной строкой внизу: у той один кегль
   на всю длину, здесь два, и разница видна раньше, чем прочитано.
   Печать при этом не нужна — крупное слово само держит блок. */
#obcRoot .obc-note .nq{display:block;font-size:.78em;letter-spacing:.24em;
  text-transform:uppercase;color:#78899A;line-height:1.6}
#obcRoot .obc-note .nq:first-child{position:relative;padding-left:1.5em}
#obcRoot .obc-note .nq:first-child::before{content:'';position:absolute;
  left:0;top:.62em;width:1em;height:1px;background:rgba(190,215,235,.45)}
#obcRoot .obc-note .nk{display:block;font-size:2.7em;font-weight:200;
  letter-spacing:.005em;line-height:1.02;margin:.14em 0 .1em;color:#E6ECF3;
  text-shadow:0 3px 14px rgba(0,0,0,.85),0 0 30px currentColor}
#obcRoot .obc-note .nk.up{color:#6FE3B4}
#obcRoot .obc-note .nk.dn{color:#FF8A52}
#obcRoot .obc-note .nk.am{color:#F0B85F}
#obcRoot .obc-note b{color:#E3E8EF;font-weight:400}
#obcRoot .obc-note b.up{color:#6FE3B4} #obcRoot .obc-note b.dn{color:#FF8A52}
#obcRoot .obc-note b.am{color:#F0B85F}
</style>
"""


CARDSCENE_HTML = """
<div id="obcRoot">
  <button class="obc-close" id="obcClose" type="button">закрыть</button>

  <div class="scene" id="obcScene">
    <canvas id="obcCv"></canvas>
    <div class="lay" id="obcLay">
      <div class="obc-cap" id="obcCap"></div>
      <div class="boat" id="obcBoat">
        <div class="drift"><div class="bob"><div class="tilt">
          <svg viewBox="0 0 340 230">
    <!-- Парус несёт имя, поэтому он и есть главная форма: пять
    реек как на джонке, лёгкий пузырь по ветру, светлая
    кромка по наветренной стороне. -->
    <g class="sail">
    <path d="M150,18 C214,34 246,74 250,132 L150,146 Z"
    fill="rgba(24,32,42,.92)" stroke="rgba(190,215,235,.30)" stroke-width="1.2"/>
    <g stroke="rgba(190,215,235,.16)" stroke-width="1" fill="none">
    <path d="M150,44 C196,54 218,78 224,110"/>
    <path d="M150,70 C186,78 204,96 212,122"/>
    <path d="M150,96 C178,102 194,114 202,130"/>
    <path d="M150,122 C170,126 182,132 190,138"/>
    </g>
    </g>
    <!-- мачта и ванты: без них парус висит в воздухе -->
    <path d="M150,10 L150,164" stroke="#04070A" stroke-width="3.4"/>
    <path d="M150,20 L96,150 M150,20 L206,150"
    stroke="rgba(120,150,180,.22)" stroke-width="1" fill="none"/>
    <!-- Корпус: нос поднят выше кормы, днище провисает. Ровная
    лодка читается доской, весь характер в этой разнице. -->
    <path d="M40,150 C36,138 46,132 62,134 L268,140
    C286,142 292,150 286,158
    C240,182 96,180 40,150 Z" fill="#04070A"/>
    <path d="M40,150 C36,138 46,132 62,134 L268,140"
    fill="none" stroke="rgba(190,215,235,.22)" stroke-width="1.1"/>
    <path d="M62,134 C120,146 210,148 268,140" fill="none"
    stroke="rgba(190,215,235,.10)" stroke-width="1"/>
    <!-- каюта под навесом той же кривой, что крыши пагоды -->
    <path d="M84,128 Q124,110 164,128 Q124,134 84,128 Z" fill="#04070A"/>
    <rect x="96" y="128" width="56" height="12" fill="rgba(255,150,60,.34)"/>
    <!-- фонарь на носу — единственный тёплый огонь на воде -->
    <path d="M52,104 L52,132" stroke="#04070A" stroke-width="2"/>
    <g class="lamp">
    <circle cx="52" cy="112" r="5" fill="rgba(255,178,92,.9)"/>
    <circle cx="52" cy="112" r="15" fill="rgba(255,150,60,.14)"/>
    <circle cx="52" cy="112" r="26" fill="rgba(255,150,60,.10)"/>
    </g>
    </svg>
        </div></div></div>
        <div class="pool"></div>
        <div class="wake"></div><div class="wake b"></div>
      </div>
      <div class="boat mir" id="obcBoatM" aria-hidden="true">
        <div class="drift"><div class="bob"><div class="tilt">
          <svg viewBox="0 0 340 230">
    <!-- Парус несёт имя, поэтому он и есть главная форма: пять
    реек как на джонке, лёгкий пузырь по ветру, светлая
    кромка по наветренной стороне. -->
    <g class="sail">
    <path d="M150,18 C214,34 246,74 250,132 L150,146 Z"
    fill="rgba(24,32,42,.92)" stroke="rgba(190,215,235,.30)" stroke-width="1.2"/>
    <g stroke="rgba(190,215,235,.16)" stroke-width="1" fill="none">
    <path d="M150,44 C196,54 218,78 224,110"/>
    <path d="M150,70 C186,78 204,96 212,122"/>
    <path d="M150,96 C178,102 194,114 202,130"/>
    <path d="M150,122 C170,126 182,132 190,138"/>
    </g>
    </g>
    <!-- мачта и ванты: без них парус висит в воздухе -->
    <path d="M150,10 L150,164" stroke="#04070A" stroke-width="3.4"/>
    <path d="M150,20 L96,150 M150,20 L206,150"
    stroke="rgba(120,150,180,.22)" stroke-width="1" fill="none"/>
    <!-- Корпус: нос поднят выше кормы, днище провисает. Ровная
    лодка читается доской, весь характер в этой разнице. -->
    <path d="M40,150 C36,138 46,132 62,134 L268,140
    C286,142 292,150 286,158
    C240,182 96,180 40,150 Z" fill="#04070A"/>
    <path d="M40,150 C36,138 46,132 62,134 L268,140"
    fill="none" stroke="rgba(190,215,235,.22)" stroke-width="1.1"/>
    <path d="M62,134 C120,146 210,148 268,140" fill="none"
    stroke="rgba(190,215,235,.10)" stroke-width="1"/>
    <!-- каюта под навесом той же кривой, что крыши пагоды -->
    <path d="M84,128 Q124,110 164,128 Q124,134 84,128 Z" fill="#04070A"/>
    <rect x="96" y="128" width="56" height="12" fill="rgba(255,150,60,.34)"/>
    <!-- фонарь на носу — единственный тёплый огонь на воде -->
    <path d="M52,104 L52,132" stroke="#04070A" stroke-width="2"/>
    <g class="lamp">
    <circle cx="52" cy="112" r="5" fill="rgba(255,178,92,.9)"/>
    <circle cx="52" cy="112" r="15" fill="rgba(255,150,60,.14)"/>
    <circle cx="52" cy="112" r="26" fill="rgba(255,150,60,.10)"/>
    </g>
    </svg>
        </div></div></div>
      </div>
      <div class="pod" id="obcPod">
        <div class="dol a"><div class="dx"><div class="dy"><div class="dr">
          <svg viewBox="0 0 140 60">
            <!-- Дельфин узнаётся тремя вещами, и все три должны быть в
                 силуэте: клюв с горбиком лба, серповидный спинной
                 плавник с отогнутым назад концом и хвост на тонком
                 стебле. Без них выходит рыба. -->
            <path d="M137,29 C131,24 126,21 118,19
                     C100,13 76,12 54,18 C40,22 28,26 20,29
                     C30,35 42,40 58,41 C86,42 118,36 132,31 Z"
                  fill="#04070A" stroke="rgba(190,215,235,.26)" stroke-width="1"/>
            <!-- спинной: основание на спине, конец отогнут к хвосту -->
            <path d="M80,15 C77,8 72,3 65,1 C71,7 73,11 74,16 Z" fill="#04070A"/>
            <!-- грудной: уходит вниз и назад -->
            <path d="M86,35 C79,42 73,48 75,52 C83,46 89,40 92,37 Z" fill="#04070A"/>
            <!-- хвост: две лопасти с вырезом между ними -->
            <path d="M20,28 C12,21 3,17 0,21 C5,25 12,28 17,30 Z" fill="#04070A"/>
            <path d="M19,30 C13,34 7,40 8,44 C14,41 18,35 20,31 Z" fill="#04070A"/>
          </svg>
        </div></div></div></div>
        <div class="dol b"><div class="dx"><div class="dy"><div class="dr">
          <svg viewBox="0 0 140 60">
            <!-- Дельфин узнаётся тремя вещами, и все три должны быть в
                 силуэте: клюв с горбиком лба, серповидный спинной
                 плавник с отогнутым назад концом и хвост на тонком
                 стебле. Без них выходит рыба. -->
            <path d="M137,29 C131,24 126,21 118,19
                     C100,13 76,12 54,18 C40,22 28,26 20,29
                     C30,35 42,40 58,41 C86,42 118,36 132,31 Z"
                  fill="#04070A" stroke="rgba(190,215,235,.26)" stroke-width="1"/>
            <!-- спинной: основание на спине, конец отогнут к хвосту -->
            <path d="M80,15 C77,8 72,3 65,1 C71,7 73,11 74,16 Z" fill="#04070A"/>
            <!-- грудной: уходит вниз и назад -->
            <path d="M86,35 C79,42 73,48 75,52 C83,46 89,40 92,37 Z" fill="#04070A"/>
            <!-- хвост: две лопасти с вырезом между ними -->
            <path d="M20,28 C12,21 3,17 0,21 C5,25 12,28 17,30 Z" fill="#04070A"/>
            <path d="M19,30 C13,34 7,40 8,44 C14,41 18,35 20,31 Z" fill="#04070A"/>
          </svg>
        </div></div></div></div>
        <div class="dol c"><div class="dx"><div class="dy"><div class="dr">
          <svg viewBox="0 0 140 60">
            <!-- Дельфин узнаётся тремя вещами, и все три должны быть в
                 силуэте: клюв с горбиком лба, серповидный спинной
                 плавник с отогнутым назад концом и хвост на тонком
                 стебле. Без них выходит рыба. -->
            <path d="M137,29 C131,24 126,21 118,19
                     C100,13 76,12 54,18 C40,22 28,26 20,29
                     C30,35 42,40 58,41 C86,42 118,36 132,31 Z"
                  fill="#04070A" stroke="rgba(190,215,235,.26)" stroke-width="1"/>
            <!-- спинной: основание на спине, конец отогнут к хвосту -->
            <path d="M80,15 C77,8 72,3 65,1 C71,7 73,11 74,16 Z" fill="#04070A"/>
            <!-- грудной: уходит вниз и назад -->
            <path d="M86,35 C79,42 73,48 75,52 C83,46 89,40 92,37 Z" fill="#04070A"/>
            <!-- хвост: две лопасти с вырезом между ними -->
            <path d="M20,28 C12,21 3,17 0,21 C5,25 12,28 17,30 Z" fill="#04070A"/>
            <path d="M19,30 C13,34 7,40 8,44 C14,41 18,35 20,31 Z" fill="#04070A"/>
          </svg>
        </div></div></div></div>
        <div class="pod-wake"></div>
      </div>
      <a class="bname" id="obcName" target="_blank" rel="noopener"
         title="открыть график на TradingView"></a>
      
      <div class="scrim"></div>
      <div id="obcDiag"></div>
      <div class="near" id="obcNear"></div>
      <div class="obc-note" id="obcNote"></div>

      <!-- Планка внизу КАРТИНКИ, а не экрана: она часть кадра и лежит
           на его тёмном подножии, там где вода уже погасла. -->
      <div class="obc-bar">
    <div class="bstr" id="obcStr"></div>
        <!-- Развёрнутый ответ. Наверху карточки стоит короткая запись
             («ждать · книга тонка»), здесь — почему именно, целиком.
             Место выбрано не случайно: полоса читается последней,
             когда приборы уже посмотрены и вопрос «почему нет» уже
             возник. Пусто — узел молчит и не занимает ширины. -->
        <div class="bwhy" id="obcWhy"></div>
      <div class="obc-marks" id="obcMarks">
        <div class="obc-mark" id="obcMarkInv">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <!-- 主 «хозяин»: кто стоит за монетой. Верхняя точка —
                 показание: разгорается на известном организаторе. -->
            <path class="dot" d="M12 2.6a1.35 1.35 0 1 1 0 2.7 1.35 1.35 0 0 1 0-2.7z"/>
            <path d="M7.2 8.1h9.6" stroke-width="1.7"/>
            <path d="M8.6 13.1h6.8" stroke-width="1.4"/>
            <path d="M5.6 18.6h12.8" stroke-width="1.9"/>
            <path d="M12 8.1v10.5" stroke-width="1.6"/>
          </svg>
          <div class="obc-tip"></div>
        </div>
        <div class="obc-mark" id="obcMarkSup">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <!-- 雨 «дождь»: предложение, которое ещё сыплется сверху.
                 Капли внутри — показание: теплеют к близкому траншу. -->
            <path d="M3.8 5.2h16.4" stroke-width="1.7"/>
            <path d="M6.6 8.6h10.8" stroke-width="1.4"/>
            <path d="M6.6 8.6v10.6M17.4 8.6v10.6" stroke-width="1.5"/>
            <path d="M12 5.2v14" stroke-width="1.6"/>
            <path class="dot" d="M9.1 11.2a.85.85 0 1 1 0 1.7.85.85 0 0 1 0-1.7z
                                 M9.1 15.1a.85.85 0 1 1 0 1.7.85.85 0 0 1 0-1.7z
                                 M14.9 11.2a.85.85 0 1 1 0 1.7.85.85 0 0 1 0-1.7z
                                 M14.9 15.1a.85.85 0 1 1 0 1.7.85.85 0 0 1 0-1.7z"/>
          </svg>
          <div class="obc-tip"></div>
        </div>
      </div>
  </div>


    </div>
  </div>

  <button class="obc-nav l" id="obcPrev" type="button" aria-label="предыдущая">
    <svg viewBox="0 0 24 24"><path d="M15 4 L7 12 L15 20"/></svg></button>
  <button class="obc-nav r" id="obcNext" type="button" aria-label="следующая">
    <svg viewBox="0 0 24 24"><path d="M9 4 L17 12 L9 20"/></svg></button>
  <div class="obc-pos" id="obcPos"></div>

  <button class="obc-goto" id="obcGoto" type="button">показать на орбите</button>
  <button class="obc-more" id="obcMore" type="button">все величины</button>
  <div class="obc-draw" id="obcDraw">
    <div class="obc-draw-x" id="obcDrawX">свернуть</div>
    <div id="obcDrawBody"></div>
  </div>
</div>
"""


CARDSCENE_JS = r"""
<script>
(function () {
  var root = document.getElementById('obcRoot');
  if (!root) return;

  /* ════════════════════════════════════════════════════════════
     АДАПТЕР
     Звезда журнала приходит с пятнадцатью полями; сцене нужны пять
     столбов, гряда, часовой ряд и подвал. Всё приведение живёт
     здесь одним куском, чтобы движок не знал про поля журнала, а
     журнал — про столбы.
     ════════════════════════════════════════════════════════════ */
  function num(v) { return (v === undefined || v === null || v === '') ? null : +v; }
  function xf(v) {
    if (!isFinite(v)) return '—';
    return v >= 100 ? Math.round(v) : v >= 10 ? v.toFixed(0) : v.toFixed(1);
  }
  function volNow(c) {
    return Math.max(+c.v1h || 0, +c.v4h || 0, +c.v1d || 0);
  }

  /* Ряды разной длины нельзя смешать поэлементно, а переход между
     монетами именно этим и занят. Поэтому обе кривые приводятся к
     одной сетке и к 0..1: гряда сравнивает форму, не уровни. */
  function resample(src, n) {
    var s = (src || []).map(Number).filter(isFinite);
    if (s.length < 4) { var flat = []; for (var q = 0; q < n; q++) flat.push(0.12); return flat; }
    var lo = Math.min.apply(null, s), hi = Math.max.apply(null, s), rng = (hi - lo) || 1;
    var out = [];
    for (var i = 0; i < n; i++) {
      var t = i / (n - 1) * (s.length - 1), a = Math.floor(t), f = t - a;
      var v = s[a] + ((s[a + 1] === undefined ? s[a] : s[a + 1]) - s[a]) * f;
      out.push(0.06 + (v - lo) / rng * 0.9);
    }
    return out;
  }

  var RIDGE_N = 28, HOURS_N = 24;

  /* Часовой ряд бывает пустым, и это не редкость. Плоская линия из
     подставленных нулей выглядит как показание — «объём весь день
     ровный», — хотя означает «мы ничего не знаем». Порог в шесть
     точек взят тот же, что у панели на стене зала (h48HTML), чтобы
     карточка и панель молчали в одних и тех же случаях. */
  function hoursOf(c) {
    var s = (c.h48 || []).map(Number).filter(function (v) {
      return isFinite(v) && v > 0;
    });
    return s.length < 6 ? null : resample(s, HOURS_N);
  }

  /* ── Два вопроса карточки ────────────────────────────────────
     Каждый прибор отдаёт ОДИН голос, голоса считаются. Складывать
     сами величины нельзя — они разной природы, — а спросить каждого
     и посчитать согласных можно, и это честнее любого взвешенного
     индекса: веса пришлось бы выдумать.

     Молчание прибора не голос: поля может не быть вовсе, и тогда он
     просто не участвует. Поэтому знаменатель — сколько приборов
     ответило, а не сколько их всего. Ноль ответивших — кольцо пустое
     и подписано «нечем мерить», а не нулём. */
  function rings(c) {
    var sq = c.squeeze || {}, ef = c.effort || null, wt = c.wyckoffTest || null;

    /* ВОПРОС ПЕРВЫЙ: кончился ли продавец.

       Голоса «за» и «против» держатся врозь. Раньше список был
       один — согласные, — и при отрицательном вердикте строка
       читалась наоборот: «продавец жив · тест» выглядело так,
       будто это тест утверждает, что продавец жив. Теперь сторона
       подписана словом, и спутать нельзя. */
    var spro = [], scon = [], sn = 0;
    if (wt && wt.note) { sn++; (wt.tested ? spro : scon).push('второй заход'); }
    if (ef && ef.state) {
      sn++; (ef.state === 'absorbing' ? spro : scon).push(
        ef.state === 'spent' ? 'ход отработан'
        : ef.state === 'exhausting' ? 'истощение' : 'поглощение');
    }
    if (sq.negRun !== undefined) { sn++; (sq.charged ? spro : scon).push('заряд'); }
    if (c.press !== undefined && c.press !== null) {
      sn++; (+c.press > 0 ? spro : scon).push('перевес сторон');
    }
    var sell = { n: spro.length, of: sn,
      pro: spro.slice(0, 2).join(' · '), con: scon.slice(0, 2).join(' · '),
      word: !sn ? 'нечем мерить'
        : sn < 3 ? 'мало данных'
        : spro.length >= 3 ? 'иссяк' : spro.length === 2 ? 'сдаёт' : 'жив' };

    /* ВОПРОС ВТОРОЙ: на чьей стороне топливо. Так же врозь: кто
       тянет вверх и кто вниз. */
    var f = 0, fn2 = 0, fup = [], fdn = [];
    if (sq.negRun !== undefined) {
      fn2++; if (sq.charged) { f++; fup.push('шорты платят'); }
    }
    if (c.fund !== undefined && c.fund !== null) {
      fn2++;
      if (+c.fund < 0) { f++; fup.push('фандинг минусовой'); }
      else if (+c.fund > 0.02) { f--; fdn.push('лонги перегреты'); }
    }
    if (c.vxDir) {
      fn2++;
      if (c.vxDir === 'up') { f++; fup.push('вортекс вверх'); }
      else { f--; fdn.push('вортекс вниз'); }
    }
    if (c.oiState) {
      fn2++;
      if (c.oiState === 'held') { f--; fdn.push('плечо застряло'); }
      else if (c.oiState === 'cleared') { f++; fup.push('плечо разгружено'); }
    }
    var fuel = { sign: f > 0 ? 1 : f < 0 ? -1 : 0, n: Math.abs(f), of: fn2,
      pro: fup.slice(0, 2).join(' · '), con: fdn.slice(0, 2).join(' · '),
      word: !fn2 ? 'нечем мерить'
        : f > 0 ? 'вверх' : f < 0 ? 'вниз' : 'ровно' };

    return { sell: sell, fuel: fuel };
  }

  function adapt(c) {
    var up = num(c.up), drop = num(c.lifeDrop), press = num(c.press);
    var vol = volNow(c), rec = num(c.x) || 0, days = num(c.days) || 0;
    var je = c.journalExp || null;
    var price = resample(c.series, RIDGE_N);

    var cols = [
      { n: 'глубина', s: 'от пика жизни', tone: 'cold',
        v: drop === null ? '—' : '−' + Math.round(Math.abs(drop)) + '%',
        h: drop === null ? 0 : Math.min(1, Math.abs(drop) / 100) },
      { n: 'давление', s: 'перевес сторон', tone: press === null ? 'flat' : (press >= 0 ? 'cool' : 'hot'),
        v: press === null ? '—' : (press >= 0 ? 'покупка ' : 'продажа ') + Math.abs(press).toFixed(1),
        h: press === null ? 0 : Math.min(1, Math.abs(press) / 6) },
      { n: 'от дна', s: 'предел 300%', tone: 'amber',
        v: up === null ? '—' : (up >= 0 ? '+' : '') + Math.round(up) + '%',
        h: up === null ? 0 : Math.min(1, up / 300) },
      /* Логарифм, потому что рекорд бывает ×1500 при сегодняшних ×2:
         на линейной шкале не загорелось бы ни одно деление. */
      { n: 'объём', s: rec ? 'рекорд ×' + xf(rec) : 'рекорда нет', tone: 'gold',
        v: vol > 0 ? '×' + xf(vol) : '—',
        h: (rec > 1 && vol > 1) ? Math.min(1, Math.log(vol) / Math.log(rec)) : 0 },
      /* Здесь стоял срок в журнале — «12 из 14 дней до выбытия».
         Это метрика НАШЕЙ системы, а не монеты: рынку всё равно,
         сколько ей осталось лежать в списке. Столб занимал место
         рядом с четырьмя рыночными величинами и читался как пятая
         такая же.

         На его месте — ожидание по прошлым эпизодам: средний ход
         вверх против среднего отката. Реактивная метрика (как часто
         всплывала) не обещает ничего — ALPINE попадала в 97%
         прогонов и была в минусе. Поведенческая отвечает на другой
         вопрос: повторится ли. Высота — по модулю ожидания,
         потолок 20%: выше разница уже не решает. */
      { n: 'ожидание', s: je ? je.n + ' эпизода' : 'эпизодов нет',
        tone: !je ? 'flat' : (je.expPct >= 0 ? 'cool' : 'hot'),
        v: !je ? '—' : (je.expPct >= 0 ? '+' : '') + je.expPct.toFixed(1) + '%',
        h: !je ? 0 : Math.min(1, Math.abs(je.expPct) / 20) }
    ];

    /* ── Краткосрок ──
       Прежний подвал собирался здесь же: восемь строк «что не
       заслужило столба». Все они целы и лежат в ящике «все
       величины» — плечо, вортекс, скорость, дивергенция, позиции,
       упругость, поток против цены. Здесь их больше нет не потому,
       что они не нужны, а потому что полоса теперь отвечает на
       вопрос, а не перечисляет.

       Три источника, все уже посчитаны на стороне Python и ничего
       не стоят экрану: уровни со структурой, реакцией и модельным
       плечом; проверка усилия против результата; тест после
       прокола. Любого может не быть — полоса тогда просто короче,
       а если нет ни одного, она говорит об этом словами. */
    var lv = c.levels || null;
    var ef = c.effort || null;
    var wt = c.wyckoffTest || null;

    /* Давность реакции словами. Ноль — «сегодня»: «0 дн назад»
       читается как ошибка счётчика, а не как сегодня. */
    function agoWord(n) {
      var k = (n === undefined || n === null) ? null : Math.round(n);
      if (k === null) return '';
      if (k <= 0) return 'сегодня';
      var last = k % 10, two = k % 100;
      var word = (last === 1 && two !== 11) ? 'день'
        : (last >= 2 && last <= 4 && (two < 12 || two > 14)) ? 'дня' : 'дней';
      return k + ' ' + word + ' назад';
    }

    function side(d, kind) {
      if (!d) return null;
      var r = d.reaction || null;
      return {
        /* Число, а не строка: раньше процент форматировался здесь и
           ещё раз при отрисовке — вторая попытка получала «+7.3%» и
           давала NaN. Адаптер отдаёт величины, подписи делает
           разметка; смешение и было причиной. */
        pct: (d.pct === undefined || d.pct === null) ? null : +d.pct,
        atr: (d.atr === undefined || d.atr === null) ? null : +d.atr,
        touches: +d.touches || 1,
        /* Реакция — вторая половина уровня: он говорит ГДЕ, она
           КОГДА. Без неё уровень остаётся местом на графике. */
        /* Слова «отдан и удержан» были невнятны: у уровня ПОД ценой
           «приняли» означает, что его пробили ВНИЗ и цена закрывалась
           под ним, а сейчас вернулась выше. Говорим прямо, что
           случилось и когда — без давности реакция читается как
           происходящее сейчас, хотя ей может быть неделя. */
        react: r ? ((r.kind === 'приняли'
                      ? (kind === 'up' ? 'пробит вверх' : 'пробита вниз')
                      : 'сходили и вернулись') + ' ' + agoWord(r.bars_ago)) : null,
        /* Совпадение структуры с модельным плечом. Метка отдельная и
           синяя: два независимых способа указали одно место, но один
           из них — гипотеза. */
        liq: d.liq ? ('плечо ' + (d.liq.side || '') + ' · модель') : null
      };
    }

    var near = {
      up: side(lv && lv.above, 'up'),
      dn: side(lv && lv.below, 'dn'),
      eff: null, test: null
    };

    if (ef) {
      var word = ef.state === 'absorbing' ? 'льют и <b>поглощают</b>'
        : ef.state === 'spent' ? 'усилие <b>отработало</b>'
        : ef.state === 'exhausting' ? '<b>истощение</b> хода'
        : null;
      if (ef.divergence) {
        word = (word ? word + ', ' : '') + 'дельта <b class="dn">гаснет</b> на верхах';
      }
      near.eff = {
        /* Отношение печатается всегда, даже когда состояние не
           сложилось: само число и есть проверка, а состояние —
           её прочтение. */
        x: (ef.ratio === undefined || ef.ratio === null) ? null : +ef.ratio,
        word: word,
        state: ef.state || null
      };
    }

    if (wt && wt.note) {
      near.test = {
        ok: !!wt.tested,
        share: (wt.volRatio === undefined || wt.volRatio === null)
               ? null : Math.round(+wt.volRatio * 100)
      };
    }

    return {
      tick: c.t, verdict: c.pattern || '', cap: c.cap || '',
      /* Пара с биржи, а не склейка из тикера: у монет вроде 1000LUNC
         они не совпадают. Нужна только для адреса графика. */
      pair: c.coin || ((c.t || '') + 'USDT'),
      price: price,
      /* Вход стоит там, где монета попала в журнал: столько дней
         назад, сколько она в нём лежит. */
      entry: Math.max(0, Math.min(1, (RIDGE_N - 1 - days) / (RIDGE_N - 1))),
      cols: cols, near: near,
      hours: hoursOf(c),
      /* Прибор прежний, величина другая. «Объём к рекорду» повторял
         высоту столба объёма слово в слово: log(vol)/log(rec) — то же
         выражение. Положение в диапазоне суток не повторяет ничего,
         и у него есть настоящий потолок, а кольцу без потолка нельзя. */
      /* ── Два кольца наверху ──
         Здесь стояли «в диапазоне» и «дней от дна»: самое видное
         место кадра занимали две служебные величины, которые никто
         не смотрел первыми. Место обязано нести главное, а главное
         у нас — два вопроса, на которые карточка отвечает целиком:
         кончился ли продавец и на чьей стороне топливо. Всё
         остальное в кадре — из чего эти два ответа собраны.

         Кольцо считает СОГЛАСНЫХ, а не величину: приборы разной
         природы нельзя складывать в одно число, но можно спросить
         каждого и посчитать голоса. Заполнение — доля согласия,
         подпись — сам ответ словами. */
      rings: rings(c),

      /* До трёх инвесторов: больше на парусе не помещается, а первые
         три и есть те, кого называют. Тир по умолчанию третий —
         неизвестный тир не должен выглядеть первым. */
      inv: (c.investors || []).slice(0, 3).map(function (v) {
        return { n: v.n || v.name || '', tier: Math.min(3, Math.max(1, +v.tier || 3)) };
      }),

      /* Разлок: дни до него, вес транша в днях оборота, идёт ли
         инсайдерам. Нет дней — нет и объекта: пустой разлок не должен
         превращаться в стену нулевой высоты у самого берега. */
      floatPct: num(c.floatPct),
      /* Размер транша — в токенах, двумя долями. Дни оборота сюда не
         приходят намеренно: их знаменатель берётся из текущего объёма,
         а карточку смотрят на всплеске, когда объём выше нормы в
         десятки раз, и тот же транш выглядит безобидным ровно тогда,
         когда он опаснее всего. */
      unlock: num(c.unlockDays) === null ? null : {
        days: num(c.unlockDays),
        sup: num(c.unlockPctSupply),
        flo: num(c.unlockPctFloat),
        ins: !!c.unlockIns,
        inferred: !!c.unlockInferred,
      },
      /* Перевес на стороне покупки — единственное условие, при котором
         в кадре появляется живое. */
      buyers: press !== null && press > 0,
      raw: c
    };
  }

  var CARDS = [], IDX = 0, DETAIL = null, live = false;

  /* ── Палитра столбов ────────────────────────────────────────
     Пять тонов — те же, что читаются на референсе слева направо.
     core — цвет зерна, glow — цвет свечения у воды. */
  const TONE = {
    cold: {core:'#7FA8C4', glow:'#2E5C7A', txt:'#9FC0D6'},
    hot:  {core:'#FF6A2A', glow:'#C43208', txt:'#FF8A52'},
    cool: {core:'#4FD6A0', glow:'#137A55', txt:'#6FE3B4'},
    amber:{core:'#FFA83C', glow:'#C96A0E', txt:'#FFC06A'},
    gold: {core:'#FFD79A', glow:'#B98A3A', txt:'#FFE1B0'},
    pale: {core:'#E9F0F6', glow:'#7C8B99', txt:'#F1F6FA'},
    flat: {core:'#6E7B87', glow:'#39434D', txt:'#8A96A2'}
  };

  const W = 1240, H = 880, WATER = 530;   // логический кадр
  const cv = document.getElementById('obcCv'), ctx = cv.getContext('2d');
  const lay = document.getElementById('obcLay');

  /* ════════════════════════════════════════════════════════════
     СЛОИ
     Раньше вся верхняя половина рисовалась одним холстом. Для
     перехода этого мало: гряда должна перетекать, столбы расти,
     а берег стоять на месте. Поэтому слоёв три, и меняются они
     с разной частотой — берег рисуется один раз за всё время.
     ════════════════════════════════════════════════════════════ */
  const bgL = mk(W, WATER), fgL = mk(W, WATER), sky = mk(W, WATER);
  function mk(w, h){ const c = document.createElement('canvas');
    c.width = w; c.height = h; return c; }

  let cur = 0, from = 0, to = 0, tp = 1, swapped = true;
  let prep = [], colGeom = [], hover = -1, last = 0;

  const DUR = 4650;                       // весь переход, мс
  const eOut = t => 1 - Math.pow(1 - t, 3);
  const eIn  = t => t * t * t;
  const eIO  = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3)/2;
  const cl   = t => t < 0 ? 0 : t > 1 ? 1 : t;

  /* ════════════════════════════════════════════════════════════
     ГЕОМЕТРИЯ СТОЛБА
     Верх не прямой, а из двух-трёх вытянутых куполов разной
     высоты — на референсе именно это отличает столб света от
     диаграммной колонки. topY(x) возвращает верхнюю границу.
     base — низ в координатах своего холста, а не кадра: каждый
     столб теперь живёт в отдельной картинке и не знает про WATER.
     ════════════════════════════════════════════════════════════ */
  function makeColumn(cx, w, h, seed, base){
    const r = mulberry(seed);
    const x0 = cx - w/2, x1 = cx + w/2, ty = base - h;
    const n = 2 + (r() > .55 ? 1 : 0), lobes = [];
    for (let i = 0; i < n; i++){
      const lw = w * (.30 + r()*.16);
      const lx = x0 + lw + (w - 2*lw) * (n === 1 ? .5 : i/(n-1));
      lobes.push({x:lx, r:lw, top: ty + h * (i === 0 ? 0 : .06 + r()*.22)});
    }
    return {x0, x1, cx, w, h, ty, base, lobes,
      topY(x){
        let best = base;
        for (const L of lobes){
          const d = Math.abs(x - L.x);
          if (d <= L.r){
            // купол вытянут по вертикали в 1.7 раза — иначе верх
            // получается округлым, как у столбика гистограммы
            const y = L.top + (1 - Math.sqrt(1 - (d/L.r)**2)) * L.r * 1.7;
            if (y < best) best = y;
          }
        }
        return best;
      }};
  }

  /* Зерно: плотность падает к вершине, поэтому столб растворяется
     в воздухе, а не обрывается кромкой. */
  function stipple(g, col, tone, dense){
    const N = Math.round(col.w * col.h * .10 * dense);
    g.fillStyle = tone.core;
    for (let i = 0; i < N; i++){
      const x = col.x0 + Math.random() * col.w;
      const yt = col.topY(x);
      if (yt >= col.base - 2) continue;
      const t = Math.random();
      const y = col.base - (col.base - yt) * t;
      const fade = Math.pow(1 - t, .55);
      if (Math.random() > fade * 1.15) continue;
      g.globalAlpha = (.16 + .95 * fade) * (.45 + Math.random()*.55);
      g.fillRect(x, y, t > .7 ? 1.5 : 1.9, t > .7 ? 1.5 : 1.9);
    }
    g.globalAlpha = 1;
  }

  function drawColumn(g, col, tone){
    const gr = g.createLinearGradient(0, col.base, 0, col.ty);
    gr.addColorStop(0,  hex(tone.glow, .80));
    gr.addColorStop(.18,hex(tone.glow, .38));
    gr.addColorStop(.65,hex(tone.glow, .11));
    gr.addColorStop(1,  hex(tone.glow, 0));
    g.fillStyle = gr;
    g.beginPath();
    g.moveTo(col.x0 - 8, col.base);
    for (let x = col.x0 - 8; x <= col.x1 + 8; x += 2) g.lineTo(x, col.topY(x));
    g.lineTo(col.x1 + 8, col.base);
    g.closePath();
    g.fill();
    stipple(g, col, tone, 1.4);
  }

  /* ════════════════════════════════════════════════════════════
     СИЛУЭТЫ
     ════════════════════════════════════════════════════════════ */
  function pagoda(g, x, base, hgt, lamp){
    /* Пагода узнаётся пропорцией и кровлей, а не числом этажей.
       Было три яруса с почти прямыми навесами — выходила башня.
       Стало пять, каждый заметно уже нижнего, и кровля вогнутая:
       от конька она провисает, а у самых концов задирается вверх.
       Этот двойной изгиб и есть подпись дальневосточной крыши;
       без него любой навес читается козырьком.

       Стена по-прежнему ровно во весь промежуток между ярусами,
       поэтому этажи стоят друг на друге, а не висят. */
    const T = 5, band = hgt * .118, y0 = base - hgt * .17;
    g.fillStyle = '#04070A';

    // синбасира — сквозной столб, на нём держится вся постройка
    g.fillRect(x - hgt * .035, base - hgt * .68, hgt * .07, hgt * .68);

    for (let i = 0; i < T; i++){
      const w  = hgt * (.52 - i * .068);   // размах кровли
      const ww = w * .44;                  // стена заметно уже: свес глубокий
      const yt = y0 - i * band;

      g.fillRect(x - ww / 2, yt, ww, band + 2);
      // галерея с перилами — то, что делает ярус этажом, а не полкой
      g.fillRect(x - ww * .78, yt + hgt * .020, ww * 1.56, hgt * .011);

      g.beginPath();
      g.moveTo(x - w / 2, yt - hgt * .030);
      g.bezierCurveTo(x - w * .30, yt - hgt * .004, x - w * .15, yt - hgt * .036,
                      x,           yt - hgt * .050);
      g.bezierCurveTo(x + w * .15, yt - hgt * .036, x + w * .30, yt - hgt * .004,
                      x + w / 2,   yt - hgt * .030);
      g.bezierCurveTo(x + w * .28, yt + hgt * .028, x + w * .12, yt + hgt * .014,
                      x,           yt + hgt * .012);
      g.bezierCurveTo(x - w * .12, yt + hgt * .014, x - w * .28, yt + hgt * .028,
                      x - w / 2,   yt - hgt * .030);
      g.closePath();
      g.fill();
    }

    // сорин: мачта с кольцами и шариком, растёт из столба
    const yTop = y0 - (T - 1) * band;
    g.fillRect(x - hgt * .007, base - hgt * .93, hgt * .014, yTop - (base - hgt * .93));
    for (let k = 0; k < 4; k++){
      const rw = hgt * (.048 - k * .010);
      g.fillRect(x - rw / 2, base - hgt * (.80 + k * .033), rw, hgt * .009);
    }
    g.beginPath(); g.arc(x, base - hgt * .945, hgt * .016, 0, 7); g.fill();

    // каменное основание в две ступени
    g.fillRect(x - hgt * .21, base - hgt * .048, hgt * .42, hgt * .034);
    g.fillRect(x - hgt * .27, base - hgt * .016, hgt * .54, hgt * .020);

    /* Свет только на двух нижних ярусах: наверху пагоды жилья нет,
       и ровный ряд огней до самой макушки выдал бы декорацию. */
    g.fillStyle = 'rgba(255,132,50,' + (.75 * (lamp === undefined ? 1 : lamp)).toFixed(3) + ')';
    for (let i = 0; i < 2; i++){
      const w = hgt * (.52 - i * .068), ww = w * .44;
      const yt = y0 - i * band + hgt * .042;
      /* Три проёма разной ширины: средний уже боковых. Ровный ряд
         одинаковых прямоугольников выдаёт узор, а не постройку.

         Башня круглая, и стена уходит от нас по дуге. Значит,
         крайние окна мы видим не в лоб: они сужаются тем сильнее,
         чем ближе к краю, и разворачиваются вслед за поверхностью.
         Прямой угол у всех трёх сразу выдавал плоскую декорацию —
         рисованный фасад, приклеенный к цилиндру. */
      const wq = [.20, .13, .17], gap = ww * .15;
      let px = x - (ww * (wq[0] + wq[1] + wq[2]) + gap * 2) / 2;
      for (let k = 0; k < 3; k++){
        const w2 = ww * wq[k], cx = px + w2 / 2;
        const u = (cx - x) / (ww / 2);              // −1…1 вдоль стены
        const nar = Math.sqrt(Math.max(.2, 1 - u * u * .8));  // ракурс
        g.save();
        g.translate(cx, yt + hgt * .025);
        g.rotate(-u * .14);                         // разворот по дуге
        g.fillRect(-w2 * nar / 2, -hgt * .025, w2 * nar, hgt * .050);
        g.restore();
        px += w2 + gap;
      }
    }
  }

  /* sw — порыв ветра: добавка к углу, накапливающаяся вглубь ветвей,
     поэтому ствол почти стоит, а концы качаются заметно. */
  function bonsai(g, x, y, len, ang, wid, depth, r, sw){
    if (depth === 0 || len < 4) return;
    const x2 = x + Math.cos(ang) * len, y2 = y + Math.sin(ang) * len;
    g.strokeStyle = '#04070A'; g.lineWidth = wid; g.lineCap = 'round';
    g.beginPath(); g.moveTo(x, y);
    g.quadraticCurveTo(x + Math.cos(ang - .3)*len*.6, y + Math.sin(ang - .3)*len*.6, x2, y2);
    g.stroke();
    if (depth <= 2){
      // крона — облако точек, а не заливка: у сосны на референсе
      // читается силуэт из отдельных хвойных подушек
      g.fillStyle = '#04070A';
      for (let i = 0; i < 90; i++){
        const a = r()*Math.PI*2, rr = Math.pow(r(),.55)*len*.85;
        g.fillRect(x2 + Math.cos(a)*rr, y2 + Math.sin(a)*rr*.42, 1.6, 1.6);
      }
    }
    const br = 2 + (r() > .6 ? 1 : 0);
    for (let i = 0; i < br; i++)
      bonsai(g, x2, y2, len*(.62 + r()*.16), ang + (r()-.5)*1.5 - .1 + (sw || 0), wid*.6, depth-1, r, sw);
  }

  /* ── Пирамидка из камней ────────────────────────────────────
     Четыре плоских камня, каждый меньше нижнего и сдвинут вбок:
     ровная стопка выглядит склеенной, живой её делает именно
     небольшая несоосность. */
  function cairn(g, x, base, h, r){
    g.fillStyle = '#04070A';
    /* Плоская плита под стопкой. Без неё камни лежат горизонтально
       на склоне в сорок пять градусов: нижний одним краем оперт, а
       другим висит в воздухе. В саду такую стопку и ставят на плиту —
       ровное основание тут не украшение, а условие, чтобы она стояла. */
    g.beginPath();
    g.ellipse(x, base, h * .46, h * .085, 0, 0, 7);
    g.fill();
    let y = base - h * .05, w = h * .52;
    for (let i = 0; i < 4; i++){
      const dx = (r() - .5) * w * .22, hh = h * (.20 - i * .022);
      g.beginPath();
      g.ellipse(x + dx, y - hh / 2, w / 2, hh / 2, 0, 0, 7);
      g.fill();
      y -= hh * .96;
      w *= .74;
    }
  }

  /* ── Цапля ──────────────────────────────────────────────────
     Единственная фигура в кадре с вертикалью в рост человека.
     Шея буквой S, а не прямая: прямая шея читается аистом, а
     сложенная — цаплей, которая стоит и ждёт. */
  function heron(g, x, base, h){
    g.fillStyle = '#04070A';
    g.strokeStyle = '#04070A';
    // ноги
    g.lineWidth = h * .022;
    g.beginPath();
    g.moveTo(x - h * .02, base); g.lineTo(x - h * .01, base - h * .34);
    g.moveTo(x + h * .05, base); g.lineTo(x + h * .02, base - h * .34);
    g.stroke();
    // тело каплей, хвост оттянут назад
    g.beginPath();
    g.ellipse(x, base - h * .44, h * .13, h * .10, -.18, 0, 7);
    g.fill();
    g.beginPath();
    g.moveTo(x - h * .10, base - h * .44);
    g.quadraticCurveTo(x - h * .26, base - h * .40, x - h * .30, base - h * .30);
    g.quadraticCurveTo(x - h * .18, base - h * .36, x - h * .08, base - h * .38);
    g.closePath(); g.fill();
    // шея S и клюв
    g.lineWidth = h * .035;
    g.beginPath();
    g.moveTo(x + h * .06, base - h * .50);
    g.bezierCurveTo(x + h * .20, base - h * .60, x - h * .02, base - h * .72,
                    x + h * .08, base - h * .84);
    g.stroke();
    g.lineWidth = h * .018;
    g.beginPath();
    g.moveTo(x + h * .08, base - h * .86);
    g.lineTo(x + h * .30, base - h * .80);
    g.stroke();
  }
  function rock(g, x, y, w, h, r){
    g.fillStyle = '#04070A';
    g.beginPath(); g.moveTo(x - w/2, y);
    for (let i = 0; i <= 8; i++){
      const t = i/8, px = x - w/2 + w*t;
      const py = y - Math.sin(t*Math.PI) * h * (.6 + r()*.7);
      g.lineTo(px, py);
    }
    g.lineTo(x + w/2, y); g.closePath(); g.fill();
  }

  /* Гряда позади — это график цены. История не отдельная панель,
     а горизонт, на фоне которого стоят все величины. */
  function ridge(g, price, entry, rnd){
    const R = rnd || Math.random;
    const x0 = 120, x1 = 1120, base = WATER, top = WATER - 350;
    g.beginPath(); g.moveTo(x0, base);
    const pt = i => [x0 + (x1-x0)*i/(price.length-1), base - (base-top)*price[i]];
    for (let i = 0; i < price.length; i++) g.lineTo(...pt(i));
    g.lineTo(x1, base); g.closePath();
    const gr = g.createLinearGradient(0, top, 0, base);
    gr.addColorStop(0, '#31506B'); gr.addColorStop(1, '#13212D');
    g.fillStyle = gr; g.fill();
    // зерно по верхней кромке — гряда светится изнутри так же,
    // как столбы, иначе она читается как плоская подложка
    g.fillStyle = '#8FB4CC';
    for (let k = 0; k < 2600; k++){
      const i = R()*(price.length-1);
      const a = Math.floor(i), f = i - a;
      const px = x0 + (x1-x0)*i/(price.length-1);
      const h  = price[a] + (price[a+1]-price[a])*f;
      const py = base - (base-top)*h;
      const d  = Math.pow(R(), 2.6) * 120;
      g.globalAlpha = (1 - d/120) * .55;
      g.fillRect(px, py + d, 1.5, 1.5);
    }
    g.globalAlpha = 1;
    // отметка попадания в журнал и её уровень
    const i = entry*(price.length-1), a = Math.floor(i), f = i-a;
    const ex = x0 + (x1-x0)*i/(price.length-1);
    const ey = base - (base-top)*(price[a] + (price[a+1]-price[a])*f);
    g.strokeStyle = 'rgba(217,164,75,.28)'; g.lineWidth = 1;
    g.setLineDash([3,7]); g.beginPath(); g.moveTo(x0, ey); g.lineTo(x1, ey);
    g.stroke(); g.setLineDash([]);
    g.fillStyle = '#F0C070'; g.beginPath(); g.arc(ex, ey, 3.4, 0, 7); g.fill();
    g.strokeStyle = 'rgba(240,192,112,.4)'; g.beginPath(); g.arc(ex, ey, 8, 0, 7); g.stroke();
  }

  /* ════════════════════════════════════════════════════════════
     ПОДГОТОВКА
     Столбы монеты пекутся в отдельные картинки один раз. Во время
     перехода они только растягиваются по высоте и меняют прозрач-
     ность — пересчитывать двадцать тысяч точек каждый кадр нельзя.
     ════════════════════════════════════════════════════════════ */
  const PAD = 26;
  function prepare(k){
    if (prep[k]) return prep[k];
    /* Столбы сдвинуты вправо на ширину одного столба: слева у воды
       теперь стоит кольцо, и прежнее начало ленты упиралось в его
       подписи. Справа места хватало — там был пустой берег. */
    const d = CARDS[k], span = 380, left = 578, set = [];
    d.cols.forEach((c, i) => {
      const cx = left + span * i/(d.cols.length-1) + (i%2 ? 14 : -10);
      const w  = 74 + (i%3)*11;
      const h  = 130 + 330 * Math.min(1, c.h);
      const cw = w + PAD*2, ch = h + PAD;
      const c2 = mk(cw, ch), g = c2.getContext('2d');
      g.globalCompositeOperation = 'lighter';
      drawColumn(g, makeColumn(cw/2, w, h, i*97 + k*13, ch), TONE[c.tone]);
      set.push({cv:c2, x:cx - cw/2, w:cw, h:ch, cx, tone:TONE[c.tone], colw:w});
    });
    prep[k] = set;
    return set;
  }

  /* Берег одинаков для всех монет, и это осознанно: пейзаж — это
     рама, монета — свет в ней. Меняющиеся между переходами камни
     читались бы как другое место, а не как другая монета. */
  function buildFG(sway, lamp){
    const g = fgL.getContext('2d'), r = mulberry(7);
    g.clearRect(0, 0, W, WATER);
    rock(g, 690, WATER, 190, 34, r);
    rock(g, 930, WATER, 150, 28, r);
    rock(g, 205, WATER, 120, 26, r);
    bonsai(g, 700, WATER - 18, 52, -1.5, 6, 4, r, sway || 0);
    // второе дерево качается слабее и с запозданием: одинаковый
    // ход у обоих читался бы качанием кадра, а не ветром
    bonsai(g, 940, WATER - 14, 44, -1.45, 5, 4, r, (sway || 0) * -.7);
    pagoda(g, 118, WATER - 6, 240, lamp === undefined ? 1 : lamp);
    heron(g, 232, WATER - 14, 34);
  }

  /* Гряда перетекает: цены двух монет смешиваются по одной кривой.
     Зерно раскладывается сеяным генератором, поэтому точки стоят
     на месте, пока под ними меняется форма, — иначе гряда мерцала
     бы шумом весь переход. */
  /* Кольцо уходящей монеты не пропадает щелчком: оно сматывается
     обратно в воду тем же ходом, каким рисовалось — ветви бегут
     назад к подножию, искры на их концах живут до самого конца.
     Появление было красивым, а исчезновение рвалось; теперь это
     одно движение в две стороны. */
  var NEAR = null, NEAR_PREV = null, RING_OUT = 0;

  function buildBG(price, entry, unlock, alpha){
    const g = bgL.getContext('2d');
    g.clearRect(0, 0, W, WATER);
    ridge(g, price, entry, mulberry(21));
    const bl = g.createRadialGradient(680, WATER, 10, 680, WATER, 620);
    bl.addColorStop(0,  'rgba(120,150,180,.30)');
    bl.addColorStop(.35,'rgba(80,110,140,.14)');
    bl.addColorStop(1,  'rgba(60,90,120,0)');
    g.globalCompositeOperation = 'lighter';
    g.fillStyle = bl; g.fillRect(0, 0, W, WATER);
    g.globalCompositeOperation = 'source-over';
    /* Туман набирает силу вместе со столбами. Слой гряды строится
       заново каждый кадр перехода, и без множителя стена возникала бы
       целиком в первом же кадре — единственный предмет в кадре,
       появляющийся мгновенно. */
    if (unlock && (alpha === undefined || alpha > .002)) {
      g.globalAlpha = alpha === undefined ? 1 : alpha;
      wall(g, unlock);
      g.globalAlpha = 1;
    }
    /* Кольцо — последним в слое гряды: перед ним пройдут столбы,
       а вода отразит его вместе со всем остальным. */
    if (RING_OUT > .004 && NEAR_PREV) drawRing(g, NEAR_PREV, RING_OUT);
    drawRing(g, NEAR, alpha === undefined ? 1 : alpha);
  }

  /* ── Стена разлока ──────────────────────────────────────────
     Единственное в кадре, что смотрит вперёд. Всё остальное — прошлое
     и настоящее, поэтому и место у неё отдельное: полоса тумана низко
     по воде справа, идущая к берегу.

     Расстояние до берега — дни до разлока. Высота — вес транша в днях
     оборота: рынок переваривает предложение объёмом торгов, и один и
     тот же процент капитализации на разной ликвидности значит разное.
     Тёплая кромка по верху — если транш идёт инсайдерам.

     Стена не доходит до столбов никогда: даже завтрашний разлок
     останавливается правее их. Иначе она читалась бы шестым столбом,
     а это не измерение. */
  function wall(g, u){
    const near = Math.min(1, Math.max(0, (u.days || 0) / 30));
    const x0 = 935 + near * 265;             // ближе разлок — левее стена
    /* Высоту несёт доля от ЦИРКУЛЯЦИИ: продаётся то, что уже
       торгуется, и давление создаёт именно эта часть. Десять процентов
       обращения — потолок шкалы: выше разница между большим и очень
       большим решения уже не меняет. */
    const w = u.flo === null || u.flo === undefined ? 3 : u.flo;
    const h = 26 + Math.min(1, w / 10) * 64;

    /* Туман — это не фигура с контуром, а множество мягких пятен без
       краёв. Прежняя версия строила его одним многоугольником, и
       кромка выдавала треугольник: у тумана кромки нет вовсе, есть
       сгущение и разрежение.

       Пятна кладутся сеяным генератором, поэтому туман не кипит от
       кадра к кадру, и гуще к правому краю: плотность падает по мере
       удаления от источника, то есть влево, к берегу. */
    const r = mulberry(97);
    const N = 46;
    for (let i = 0; i < N; i++){
      const t = Math.pow(r(), .6);           // гуще справа
      const x = x0 - 30 + t * (W + 90 - x0);
      const y = WATER - h * (.15 + r() * .75) + r() * 10;
      const rx = 40 + r() * 90, ry = rx * (.28 + r() * .22);
      const dens = Math.min(1, (x - x0 + 60) / 180);   // к берегу редеет
      const a = (.030 + r() * .045) * Math.max(0, dens);
      if (a <= .001) continue;
      const gr = g.createRadialGradient(x, y, 0, x, y, rx);
      gr.addColorStop(0, 'rgba(176,198,220,' + a.toFixed(3) + ')');
      gr.addColorStop(.55, 'rgba(160,184,210,' + (a * .45).toFixed(3) + ')');
      gr.addColorStop(1, 'rgba(150,175,200,0)');
      g.save();
      g.translate(x, y); g.scale(1, ry / rx);
      g.fillStyle = gr;
      g.beginPath(); g.arc(0, 0, rx, 0, 7); g.fill();
      g.restore();
    }

    /* Подошва: у самой воды туман всегда плотнее, потому что там он и
       рождается. Без неё полоса висит над поверхностью. */
    const base = g.createLinearGradient(0, WATER - h * .35, 0, WATER + 4);
    base.addColorStop(0, 'rgba(150,175,200,0)');
    base.addColorStop(1, 'rgba(140,166,194,.20)');
    g.fillStyle = base;
    g.fillRect(x0 - 20, WATER - h * .35, W - x0 + 20, h * .35 + 4);

    if (u.ins){
      /* Транш идёт инсайдерам — по верхней кромке проходит тёплый
         отсвет. Не линия: линия вернула бы туману контур. */
      for (let i = 0; i < 14; i++){
        const x = x0 + (r() * (W + 40 - x0));
        const y = WATER - h * (.55 + r() * .35);
        const rr = 30 + r() * 60;
        const gr = g.createRadialGradient(x, y, 0, x, y, rr);
        gr.addColorStop(0, 'rgba(255,150,70,.10)');
        gr.addColorStop(1, 'rgba(255,150,70,0)');
        g.fillStyle = gr;
        g.beginPath(); g.arc(x, y, rr, 0, 7); g.fill();
      }
    }
  }


  /* Столбы уходят справа налево, а поднимаются слева направо: у
     перехода появляется направление, и он читается как смена, а
     не как мигание. */
  function riseF(set, p){ return set.map((_, i) =>
    eOut(cl((p - i * .10) / .62))); }
  function sinkF(set, p){ return set.map((_, i) =>
    1 - eIn(cl((p - (set.length-1-i) * .07) / .70))); }

  function drawSet(g, set, fs, mul){
    set.forEach((c, i) => {
      const f = fs[i];
      if (f <= .002) return;
      g.globalAlpha = Math.min(1, f * 1.5) * (mul === undefined ? 1 : mul);
      g.drawImage(c.cv, c.x, WATER - c.h * f, c.w, c.h * f);
    });
    g.globalAlpha = 1;
  }

  function compose(){
    const g = sky.getContext('2d');
    g.clearRect(0, 0, W, WATER);
    g.drawImage(bgL, 0, 0);
    g.globalCompositeOperation = 'lighter';
    if (tp < 1){
      const out = cl(tp / .46), inn = cl((tp - .42) / .58);
      if (from !== to && out < 1) drawSet(g, prepare(from), sinkF(prepare(from), out));
      /* След набирает силу вместе с подъёмом. Раньше он появлялся
         только в самом последнем кадре перехода — и это читалось как
         вспышка яркости у столбов, уже закончивших расти. */
      if (from !== to) drawSet(g, prepare(from), prepare(from).map(() => 1), .13 * inn);
      drawSet(g, prepare(to), riseF(prepare(to), inn));
    } else {
      /* След предыдущей монеты. Столбы у всех монет стоят на одних и
         тех же местах, поэтому слабая копия старой видна ровно там,
         где та была ВЫШЕ новой, и нигде больше. Получается не вторая
         картинка, а разница между двумя — то самое «выше или ниже»,
         которое иначе приходится держать в памяти при листании. */
      if (from !== to) drawSet(g, prepare(from), prepare(from).map(() => 1), .13);
      drawSet(g, prepare(to), prepare(to).map(() => 1));
    }
    g.globalCompositeOperation = 'source-over';
    g.drawImage(fgL, 0, 0);
    colGeom = prepare(to).map(c => ({cx:c.cx, w:c.colw, tone:c.tone}));
  }

  /* ── Смена монеты ───────────────────────────────────────────── */
  function go(k){
    if (tp < 1) return;            // не перебиваем идущий переход
    from = cur; to = k; cur = k; tp = 0; swapped = false; hover = -1;
    NEAR_PREV = (CARDS[from] || {}).near || null;
    lay.querySelectorAll('.col').forEach(el => el.style.opacity = '');

    /* Класс появления здесь больше не снимается: у текстов его нет.
       Приход и уход делает один переход, снимать нечего — и именно
       это снятие раньше давало рывок. */

    lay.classList.add('out');
    root.classList.add('moving');
  }

  /* ── Вода ───────────────────────────────────────────────────── */
  /* Отражение — самая дорогая часть кадра: по строке drawImage на
     каждый пиксель высоты воды, триста пятьдесят вызовов за кадр.
     На слабой машине это и есть тормоз. Шаг увеличиваем вдвое —
     строки рисуются вдвое толще, на глаз разница в размытой воде не
     видна, а вызовов вдвое меньше. */
  const STEP = (navigator.hardwareConcurrency || 4) <= 4 ||
               matchMedia('(hover: none)').matches ? 2 : 1;

  function water(t){
    const hgt = H - WATER;
    for (let j = 0; j < hgt; j += STEP){
      const src = WATER - 1 - j * (WATER/hgt) * .82;
      if (src < 0) break;
      const k = j/hgt;
      const dx = Math.sin(j*.055 + t*.0009) * (2 + k*11) * (.4 + k);
      ctx.globalAlpha = (1 - k) * .62;
      ctx.drawImage(sky, 0, Math.floor(src), W, 1, dx, WATER + j, W, STEP + .2);
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = 'rgba(200,225,245,.10)';
    for (let j = 0; j < 34; j++){
      const y = WATER + Math.pow(j/34, 1.7) * hgt;
      ctx.fillRect(Math.sin(j*2.7 + t*.0004)*380 + 500, y, 60 + Math.random()*300, 1);
    }
  }

  /* ── Ближний план ───────────────────────────────────────────
     Камни и полумесяц стоят ближе зрителя, чем острова, поэтому
     рисуются ПОСЛЕ воды, а не в слое берега: предмет между зрителем
     и отражением закрывает его собой, а не отражается сам. Размер не
     меняем — глубину здесь несёт только положение ниже линии воды,
     и этого достаточно, чтобы они вышли из общего ряда островов.

     Генератор сеяный: форма камней должна быть одна и та же в каждом
     кадре, иначе они закипят.  */
  function nearProps(){
    const r = mulberry(211);
    // отмель под каждой фигурой: без неё они висят над водой
    ctx.fillStyle = 'rgba(4,7,10,.55)';
    ctx.beginPath(); ctx.ellipse(602, WATER + 16, 44, 4, 0, 0, 7); ctx.fill();

    /* Камни отодвинуты назад: на сорока шести пикселях они лезли к
       зрителю в упор. Шестнадцати хватает, чтобы выйти из линии
       островов и не более того — задача была не приблизить, а сбить
       строй. */
    cairn(ctx, 602, WATER + 16, 52, r);

  }


  const LANTERNS = [
      {
        x: 328,
        y: 58,
        sp: -.000068,
        amp: 22,
        r: 7.6
      },
      {
        x: 368,
        y: 106,
        sp: -.00008,
        amp: 22,
        r: 8.6
      },
      {
        x: 611,
        y: 76,
        sp: .000076,
        amp: 26,
        r: 9
      },
      {
        x: 810,
        y: 52,
        sp: .000072,
        amp: 28,
        r: 6.8
      },
  ];

  function lanterns(t){
    LANTERNS.forEach(L => {
      const x = L.x + Math.sin(t * L.sp * 6) * L.amp;
      const y = WATER + L.y + Math.sin(t * .0007 + L.x) * 1.6;

      // ореол
      const halo = ctx.createRadialGradient(x, y, 0, x, y, L.r * 4.2);
      halo.addColorStop(0, 'rgba(255,168,80,.42)');
      halo.addColorStop(.45, 'rgba(255,140,60,.12)');
      halo.addColorStop(1, 'rgba(255,130,50,0)');
      ctx.fillStyle = halo;
      ctx.fillRect(x - L.r * 4.2, y - L.r * 4.2, L.r * 8.4, L.r * 8.4);

      // хвост блика вниз: он и сажает огонь на воду
      const tail = ctx.createLinearGradient(0, y, 0, y + L.r * 9);
      tail.addColorStop(0, 'rgba(255,170,86,.34)');
      tail.addColorStop(1, 'rgba(255,150,60,0)');
      ctx.fillStyle = tail;
      ctx.fillRect(x - L.r * .42, y, L.r * .84, L.r * 9);

      // сам фонарь
      ctx.fillStyle = 'rgba(255,196,120,.95)';
      ctx.beginPath();
      ctx.ellipse(x, y, L.r * .52, L.r * .40, 0, 0, 7);
      ctx.fill();
      ctx.fillStyle = 'rgba(20,12,6,.8)';
      ctx.fillRect(x - L.r * .52, y + L.r * .30, L.r * 1.04, L.r * .14);
    });
  }
  function frame(t){
    /* Проверка стоит первой, а не в конце: закрытая карточка не должна
       дорисовать даже один лишний кадр — на планшете он заметен. */
    if (!live) return;
    const dt = last ? Math.min(64, t - last) : 16; last = t;

    if (tp < 1){
      tp = Math.min(1, tp + dt/DUR);
      /* Обратный ход занимает первую часть перехода — ровно ту, где
         тонут столбы уходящей монеты. */
      RING_OUT = from !== to ? Math.max(0, 1 - tp / .42) : 0;
      const a = CARDS[from].price, b = CARDS[to].price, m = eIO(tp);
      buildBG(a.map((v, i) => v + (b[i] - v) * m),
              CARDS[from].entry + (CARDS[to].entry - CARDS[from].entry) * m,
              CARDS[to].unlock, cl((tp - .42) / .58));

      /* Берег на переходе не стоит истуканом: по деревьям проходит
         порыв, а свет в окнах приседает и разгорается обратно. Сильнее
         всего в середине, где меняются данные, — env как раз и есть
         половина синусоиды от начала к концу. Пересчёт слоя идёт
         только пока идёт переход; в покое он печётся один раз. */
      const env = Math.sin(Math.PI * tp);
      /* Порыв на треть градуса у концов веток: заметно, что воздух
         шевельнулся, и не заметно, что кто-то качает деревья. */
      buildFG(Math.sin(t * .0032) * .018 * env, 1 - .72 * env);
      if (tp === 1) { RING_OUT = 0; buildFG(0, 1); root.classList.remove('moving'); }
      // подписи меняем в момент, когда старые столбы уже утонули,
      // а новые ещё не поднялись: провал в середине перехода
      if (!swapped && tp >= .42){ swapped = true; applyCard(CARDS[to]); }
      compose();
    }

    ctx.clearRect(0, 0, W, H);
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#16242F'); bg.addColorStop(.55, '#1D3241');
    bg.addColorStop(.62, '#152634'); bg.addColorStop(1, '#080F16');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
    ctx.drawImage(sky, 0, 0);
    water(t);
    ctx.fillStyle = 'rgba(170,205,230,.26)';
    ctx.fillRect(0, WATER - .5, W, 1);
    nearProps();
    lanterns(t);
    // цикл живёт только пока карточка открыта: за ней стоит зал
    // со своей 3D-сценой, и два кадра одновременно ей дорого
    requestAnimationFrame(frame);
  }

  /* ── Строка решения ─────────────────────────────────────────
     Здесь была сводка из двух вопросов и положения цены — и она
     дублировала всё сразу: шапку повторяли кольца наверху, крупную
     строку и хвост повторяли подписи внутри обода. Повтор в кадре
     хуже пустоты: глаз читает дважды и оба раза не находит нового.

     Осталось единственное, чего картинка не показывает и показать
     не может: ЧТО ДЕЛАТЬ и почему. Действие приходит готовым из
     слоя решений (тот же act, что печатает зал), поэтому карточка
     ничего не решает сама — она лишь перестаёт молчать о решении.

     Причина обязательна: «ждать» без причины — это приказ, а с
     причиной — довод, который можно оспорить. Ниже — ближайший
     срок, если он есть: событие, которое сделает решение
     несвоевременным. */
  function verdictHTML(card){
    const c = (card && card.raw) || {};
    const act = c.act || null;
    if (!act || !act.act) return '<span class="nq">решение не посчитано</span>';

    const TONE = { 'брать': 'up', 'добрать': 'up', 'держать': 'am',
                   'ждать': 'am', 'хеджировать': 'am',
                   'сократить': 'dn', 'выйти': 'dn', 'мимо': 'dn' };
    const tone = TONE[act.act] || 'am';

    const why = (act.why || '').trim();
    const soon = (c.exitWhy || [])[0] || '';

    return '<span class="nq">решение</span>' +
      '<span class="nk ' + tone + '">' + act.act + '</span>' +
      (why ? '<span class="nq">' + why + '</span>' : '') +
      (soon ? '<span class="nq">' + soon + '</span>' : '');
  }

  /* ── Кольцо краткосрока ─────────────────────────────────────
     Одна геометрия на два слоя: свет рисует холст, подписи ставит
     HTML. Считается она здесь и ровно один раз, поэтому засечки и
     подписи не могут разъехаться.

     Устройство обода: низ — опора, верх — потолок, точка цены едет
     по правой половине. Доля пути от опоры к потолку меряется в
     ATR: проценты у спокойной монеты и у дёрганой несравнимы, а
     ATR сравним, и та же мера уже стоит в усилии и в буфере стопа.

     Кольца нет, когда мерить нечего: ни одного измеренного уровня
     — ни обода, ни подписей. Пустой круг был бы прибором со
     сломанной стрелкой. */
  /* Кольцо стоит слева от столбов и ниже: в середине кадра оно
     спорило с ними за внимание и накрывало гряду. Слева у воды
     пусто — там ему и место, а низ обода по-прежнему лежит ровно
     на линии воды. */
  var RING_CX = 300, RING_R = 145;

  function ringGeom(n){
    if (!n) return null;
    const up = n.up, dn = n.dn;
    const haveU = up && up.atr !== null, haveD = dn && dn.atr !== null;
    if (!haveU && !haveD) return null;

    const total = (haveU ? up.atr : 0) + (haveD ? dn.atr : 0);
    /* Односторонний уровень — обычное дело: у монеты на дне нет
       опоры под ней, у вершины нет потолка над ней. Тогда шкала
       идёт от точки цены к единственному известному концу. */
    const t = !total ? 0.5
      : haveU && haveD ? dn.atr / total
      : haveD ? 0.92 : 0.08;

    const CY = WATER - RING_R;
    const at = f => {                       // f: 0 — низ, 1 — верх
      const a = Math.PI * f;
      return [RING_CX + Math.sin(a) * RING_R, CY + Math.cos(a) * RING_R];
    };
    /* Две параметризации кольца существовали одновременно, и это
       был баг: обод рисовался по ПОЛНОЙ окружности (f: 0 — низ,
       .5 — верх, 1 — снова низ), а точки считались по ПОЛОВИНЕ
       (f: 0 — низ, 1 — верх). Головы прорисовки, посчитанные не той
       формулой, уезжали куда угодно — отсюда и «одна снизу, другая
       сверху». Теперь обе формулы объявлены рядом и названы: at —
       по правой половине (там живут уровни и цена), atFull — по
       всему ободу (там идёт прорисовка). */
    const atFull = f => {
      const a = Math.PI / 2 + f * 2 * Math.PI;
      return [RING_CX + Math.cos(a) * RING_R, CY + Math.sin(a) * RING_R];
    };
    return { cx: RING_CX, cy: CY, r: RING_R, t: t, total: total,
             at: at, atFull: atFull, px: at(t),
             up: haveU ? up : null, dn: haveD ? dn : null };
  }

  /* ── Свет кольца на холсте ──
     Рисуется в слой гряды, ДО столбов: столбы проходят перед
     кольцом, а вода отражает его сама — тем же кодом, что отражает
     лодку и пагоду. Ради этого кольцо и живёт на холсте. */
  /* Кольцо не ПОЯВЛЯЕТСЯ, а РИСУЕТСЯ: свет выходит из воды в двух
     точках у подножия и растёт по ободу навстречу самому себе,
     смыкаясь наверху. Проявление прозрачностью выдавало картинку,
     наложенную на кадр; прорисовка читается как событие внутри
     него — тем более что низ обода лежит ровно на воде, откуда
     свет и поднимается.

     Ход берётся из того же счётчика перехода, что ведёт всю
     сцену, поэтому кольцо строится ровно тогда, когда встают
     столбы, и отдельной синхронизации не нужно. */
  function drawRing(g, n, prog){
    const R = ringGeom(n);
    if (!R) return;
    const pr = prog === undefined ? 1 : Math.max(0, Math.min(1, prog));
    if (pr <= 0.004) return;
    const a = 1;
    const half = pr / 2;                    // докуда доросли обе ветви
    const drawn = f => f <= half || f >= 1 - half;
    g.save();
    g.globalAlpha = a;
    g.globalCompositeOperation = 'lighter';

    /* ── Шлейф ──
       Голое кольцо выглядело наклейкой: свет обязан во что-то
       упираться. Поэтому вокруг него три слоя воздуха и один на
       воде.

       Первый — широкое дальнее зарево: оно даёт кольцу объём и
       съедает резкую границу с небом. Второй — ближний ореол у
       самого обода. Третий — дымка у подножия, там где свет
       встречает воду: у любого источника над водой есть такая
       полоса. И, наконец, световая дорожка по воде вниз от
       кольца — та же, что тянется от фонарей на воде. */
    const bloom = g.createRadialGradient(R.cx, R.cy, R.r * .35,
                                         R.cx, R.cy, R.r * 2.35);
    bloom.addColorStop(0, 'rgba(126,186,222,' + (.055 * pr).toFixed(3) + ')');
    bloom.addColorStop(.42, 'rgba(126,186,222,' + (.032 * pr).toFixed(3) + ')');
    bloom.addColorStop(1, 'rgba(126,186,222,0)');
    g.fillStyle = bloom;
    g.beginPath(); g.arc(R.cx, R.cy, R.r * 2.35, 0, 7); g.fill();

    const halo = g.createRadialGradient(R.cx, R.cy, R.r * 0.78,
                                        R.cx, R.cy, R.r * 1.3);
    halo.addColorStop(0, 'rgba(150,205,235,0)');
    halo.addColorStop(.46, 'rgba(150,205,235,' + (.13 * pr).toFixed(3) + ')');
    halo.addColorStop(1, 'rgba(150,205,235,0)');
    g.fillStyle = halo;
    g.beginPath(); g.arc(R.cx, R.cy, R.r * 1.3, 0, 7); g.fill();

    // дымка у подножия: свет встречает воду
    const mist = g.createRadialGradient(R.cx, WATER - 6, 0,
                                        R.cx, WATER - 6, R.r * 1.15);
    mist.addColorStop(0, 'rgba(176,214,240,' + (.16 * pr).toFixed(3) + ')');
    mist.addColorStop(.55, 'rgba(176,214,240,' + (.055 * pr).toFixed(3) + ')');
    mist.addColorStop(1, 'rgba(176,214,240,0)');
    g.save();
    g.translate(R.cx, WATER - 6); g.scale(1, .32); g.translate(-R.cx, -(WATER - 6));
    g.fillStyle = mist;
    g.beginPath(); g.arc(R.cx, WATER - 6, R.r * 1.15, 0, 7); g.fill();
    g.restore();

    // дорожка по воде — прямо под кольцом, как от фонаря
    const track = g.createLinearGradient(0, WATER - 4, 0, WATER + 120);
    track.addColorStop(0, 'rgba(190,225,248,' + (.2 * pr).toFixed(3) + ')');
    track.addColorStop(1, 'rgba(190,225,248,0)');
    g.fillStyle = track;
    g.fillRect(R.cx - R.r * .16, WATER - 4, R.r * .32, 124);

    /* ── Переливы обода ──
       Ровная линия читается чертежом. На референсе обод живой:
       вверху почти белый, к бокам уходит в холодную синь, местами
       вспыхивает. Собирается посегментно — цвет и яркость зависят
       от места на окружности, — и тремя проходами: мягкое гало,
       средний слой, острая нить. Одна дуга одним цветом такого не
       даёт ни при какой толщине. */
    const SEG = 96;
    const tone = f => {                      // f: 0 низ, .5 верх, 1 низ
      const k = Math.sin(Math.PI * f);       // 0 у воды, 1 наверху
      const r = Math.round(120 + 118 * k), gg = Math.round(178 + 70 * k),
            b = Math.round(206 + 46 * k);
      return [r, gg, b, .30 + .68 * k];
    };
    /* Две вспышки: наверху, где на референсе обод пересекает свет,
       и на самой точке цены — там, где сейчас происходит дело. */
    const flare = f => {
      const dTop = Math.abs(f - .5);
      const dPx = Math.min(Math.abs(f - R.t / 2), Math.abs(f - (1 - R.t / 2)));
      return Math.max(0, 1 - dTop / .07) * .55 + Math.max(0, 1 - dPx / .05) * .75;
    };
    [[8, .10, 0], [3.2, .30, 0], [1.25, 1, 1]].forEach(([w, mul, sharp]) => {
      for (let i = 0; i < SEG; i++){
        const f0 = i / SEG, f1 = (i + 1.02) / SEG;
        if (!drawn(f0)) continue;           // ветви ещё не дошли сюда
        const [rr, gg, bb, al] = tone(f0);
        /* Живая неровность яркости: идеально ровная окружность
           выдаёт вектор. Волна медленная и слабая — глаз не ловит
           её как узор, но перестаёт видеть штамп. */
        const wob = 1 + Math.sin(f0 * Math.PI * 6 + 1.1) * .10
                      + Math.sin(f0 * Math.PI * 14 + .4) * .05;
        const fl = flare(f0) * wob;
        const A = Math.min(1, (al * wob + fl) * mul);
        if (A <= .004) continue;
        g.lineWidth = w + (sharp ? fl * 1.1 : fl * 2.2);
        g.strokeStyle = 'rgba(' + Math.min(255, rr + fl * 90) + ',' +
          Math.min(255, gg + fl * 60) + ',' + Math.min(255, bb + fl * 30) + ',' +
          A.toFixed(3) + ')';
        g.beginPath();
        g.arc(R.cx, R.cy, R.r, Math.PI / 2 + f0 * 2 * Math.PI,
              Math.PI / 2 + f1 * 2 * Math.PI);
        g.stroke();
      }
    });

    /* Пылинки в свете обода — те же боке, что на референсе. Сеяный
       генератор: они должны стоять на месте, а не кипеть. */
    let sd = 4177;
    const rnd2 = () => (sd = (sd * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < 26; i++){
      const a = rnd2() * Math.PI * 2, rr = R.r * (.42 + rnd2() * .56);
      const x = R.cx + Math.cos(a) * rr, y = R.cy + Math.sin(a) * rr;
      g.fillStyle = 'rgba(214,238,252,' + (.03 + rnd2() * .10).toFixed(3) + ')';
      g.beginPath(); g.arc(x, y, .8 + rnd2() * 2.6, 0, 7); g.fill();
    }

    // засечки через один ATR по рабочей половине обода
    if (R.total > 0){
      for (let k = 0; k <= Math.floor(R.total + 0.001); k++){
        const f = k / R.total;
        if (f > 1) break;
        if (!drawn(f / 2) && !drawn(1 - f / 2)) continue;
        const big = k % 5 === 0, p = R.at(f);
        const inn = [R.cx + (p[0] - R.cx) * (1 - (big ? .052 : .032)),
                     R.cy + (p[1] - R.cy) * (1 - (big ? .052 : .032))];
        g.lineWidth = big ? 1.4 : .9;
        g.strokeStyle = big ? 'rgba(200,225,245,.55)' : 'rgba(200,225,245,.3)';
        g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(inn[0], inn[1]); g.stroke();
      }
    }

    // узлы уровней: опора внизу, потолок вверху; плита модели —
    // мягкое синее пятно на ободе, без кромки
    const node = (f, col, liq) => {
      const p = R.at(f);
      if (liq){
        const gl = g.createRadialGradient(p[0], p[1], 0, p[0], p[1], 54);
        gl.addColorStop(0, 'rgba(99,166,224,.42)');
        gl.addColorStop(1, 'rgba(99,166,224,0)');
        g.fillStyle = gl;
        g.beginPath(); g.arc(p[0], p[1], 54, 0, 7); g.fill();
      }
      /* Узлу — свой ореол: точка без свечения на светящемся ободе
         читается как грязь на стекле. */
      g.save(); g.globalAlpha = a * .5; g.fillStyle = col; g.filter = 'blur(6px)';
      g.beginPath(); g.arc(p[0], p[1], 8, 0, 7); g.fill(); g.restore();
      g.fillStyle = col;
      g.beginPath(); g.arc(p[0], p[1], 3.4, 0, 7); g.fill();
      g.lineWidth = 1; g.strokeStyle = col;
      g.globalAlpha = a * .5;
      g.beginPath(); g.arc(p[0], p[1], 9, 0, 7); g.stroke();
      g.globalAlpha = a;
    };
    if (R.dn) node(0, '#6FE3B4', R.dn.liq);            // с ним свет и начинается
    if (R.up && pr > .985) node(1, '#FF8A52', R.up.liq); // ветви сомкнулись

    // точка цены: единственное по-настоящему яркое пятно кадра
    const p = R.px;
    if (drawn(R.t / 2)) {
    /* Короткий шлейф по ободу вокруг точки: свет не обрывается
       ступенькой, а стекает по кольцу в обе стороны. */
    g.save();
    g.globalAlpha = a * .55;
    g.strokeStyle = 'rgba(255,240,205,.75)';
    g.lineWidth = 3.4;
    g.filter = 'blur(4px)';
    g.beginPath();
    g.arc(R.cx, R.cy, R.r, Math.PI / 2 + (R.t / 2) * 2 * Math.PI - .13,
          Math.PI / 2 + (R.t / 2) * 2 * Math.PI + .13);
    g.stroke();
    g.restore();
    const hot = g.createRadialGradient(p[0], p[1], 0, p[0], p[1], 34);
    hot.addColorStop(0, 'rgba(255,238,200,.55)');
    hot.addColorStop(1, 'rgba(255,238,200,0)');
    g.fillStyle = hot;
    g.beginPath(); g.arc(p[0], p[1], 34, 0, 7); g.fill();
    g.fillStyle = '#FFF6E2';
    g.beginPath(); g.arc(p[0], p[1], 4.2, 0, 7); g.fill();
    }

    /* Головы ветвей: пока кольцо строится, на концах горят искры —
       по ним и видно, что это рисование, а не проявление.

       Обе идут ОТ НИЗА в разные стороны, по той же формуле, что и
       обод, и гаснут не щелчком: последнюю пятую часть пути они
       плавно тускнеют и мельчают, а у самого начала так же плавно
       разгораются. Резкое исчезновение искры читается как сбой
       отрисовки, а не как конец движения. */
    const headFade = Math.min(1, pr / .06) * Math.min(1, (1 - pr) / .2);
    if (headFade > .01){
      [half, 1 - half].forEach(f => {
        const q = R.atFull(f);
        const rad = 12 + 16 * headFade;
        g.globalAlpha = a * headFade;
        const hg = g.createRadialGradient(q[0], q[1], 0, q[0], q[1], rad);
        hg.addColorStop(0, 'rgba(226,244,255,.8)');
        hg.addColorStop(1, 'rgba(226,244,255,0)');
        g.fillStyle = hg;
        g.beginPath(); g.arc(q[0], q[1], rad, 0, 7); g.fill();
        g.fillStyle = '#F2FAFF';
        g.beginPath(); g.arc(q[0], q[1], 1.4 + 1.6 * headFade, 0, 7); g.fill();
        g.globalAlpha = a;
      });
    }
    g.restore();
  }

  /* ── Подписи вокруг кольца ──
     Три места: потолок над верхом, опора у воды, цена рядом со
     своей точкой. Внутри кольца — проверка усилия и исход теста:
     это выводы, не привязанные ни к одному уровню, и место в
     центре им по смыслу. */
  function nearBand(n){
    const host = document.getElementById('obcNear');
    if (!host) return;
    const R = ringGeom(n);
    n = n || {};
    if (!R){ host.innerHTML = ''; return; }

    /* Весь текст ушёл ВНУТРЬ обода. Снаружи он расползался по кадру
       и спорил со столбами; внутри кольцо само работает рамкой, и
       читать его нужно сверху вниз — ровно в том порядке, в каком
       стоят уровни: потолок, цена между ними, опора. */
    /* Ширина считается по ХОРДЕ на высоте подписи, а не по диаметру:
       у верхней и нижней строк места меньше, чем у середины, и
       единая ширина вылезала бы за обод сверху и снизу. */
    const pc = (x, y, wf) => {
      const dy = Math.abs(y - R.cy) / R.r;
      const chord = 2 * R.r * Math.sqrt(Math.max(0.08, 1 - dy * dy)) * .82;
      return 'left:' + (x / W * 100).toFixed(2) + '%;top:' +
        (y / H * 100).toFixed(2) + '%;max-width:' +
        ((wf === undefined ? chord : wf) / W * 100).toFixed(2) + '%';
    };
    const dist = d => (d.pct === null ? '—'
      : (d.pct >= 0 ? '+' : '') + d.pct.toFixed(1) + '%') +
      (d.atr === null ? '' : ' · ' + d.atr.toFixed(1) + ' ATR');
    const sub = d => [
      d.touches > 1 ? 'касаний ' + d.touches : 'одно касание',
      d.react ? '<em>' + d.react + '</em>' : null,
      d.liq ? '<s>' + d.liq + '</s>' : null
    ].filter(Boolean).join(' · ');

    let html = '';

    if (R.up){
      html += '<div class="rl up" style="' + pc(R.cx, R.cy - R.r * .56) + '">' +
        '<div class="rl-k">потолок</div><div class="rl-v">' + dist(R.up) +
        '</div><div class="rl-s">' + sub(R.up) + '</div></div>';
    }
    if (R.dn){
      html += '<div class="rl dn" style="' + pc(R.cx, R.cy + R.r * .58) + '">' +
        '<div class="rl-k">опора</div><div class="rl-v">' + dist(R.dn) +
        '</div><div class="rl-s">' + sub(R.dn) + '</div></div>';
    }

    /* Слова «цена» здесь нет намеренно. Оно вылезало правее обода
       на свет столба и почти ложилось на подпись опоры. И оно
       ничего не добавляло: точка цены — единственное тёплое пятно
       кадра, с ореолом, и едет между зелёным узлом опоры и ржавым
       узлом потолка. Что это цена, видно без подписи.

       */

    const ef = n.eff, ts = n.test;
    if (ef || ts){
      html += '<div class="rl-core" style="' + pc(R.cx, R.cy + 2) + '">';
      if (ef){
        html += '<div class="rl-x' + (ef.x === null ? ' mute' : '') + '">' +
            (ef.x === null ? '—' : '×' + (ef.x >= 10 ? Math.round(ef.x) : ef.x.toFixed(1))) +
          '</div>' + (ef.word ? '<div class="rl-w">' + ef.word + '</div>' : '');
      }
      if (ts){
        /* Было просто «тест» — слово ни о чём не говорит. Теперь
           названо действие: цена во второй раз сходила к минимуму,
           и вопрос в том, тише ли прошёл этот заход. */
        html += '<div class="rl-t">второй заход к дну <b class="' +
          (ts.ok ? 'ok' : 'no') + '">' + (ts.ok ? 'тише' : 'так же шумно') +
          '</b>' + (ts.share === null ? '' : ' · ' + ts.share +
          '% объёма прокола') + '</div>';
      }
      html += '</div>';
    }

    host.innerHTML = html;
  }

  /* ── Подписи ────────────────────────────────────────────────── */
  function labels(d){
    lay.querySelectorAll('.col').forEach(e => e.remove());
    ['obcName','obcStr'].forEach((id, k) => {
      const el = document.getElementById(id), t = [d.tick, d.verdict][k];
      el.textContent = t; el.dataset.t = t;
    });
    /* Развёрнутый ответ приходит готовым из слоя решений — карточка
       ничего не досочиняет. Первое возражение выделено: по нему
       принято решение, остальные объясняют, почему оно не одиноко. */
    const whyEl = document.getElementById('obcWhy');
    const act = (d.raw && d.raw.act) || {};
    const full = act.whyFull || [];
    whyEl.innerHTML = !full.length ? '' :
      full.map(function (t, i) {
        return '<span>' + (i ? '' : '<b>') + t + (i ? '' : '</b>') + '</span>';
      }).join('') +
      (act.whyLift ? '<span class="lift">' + act.whyLift + '</span>' : '');

    /* Тот же вид адреса, что у ссылок кандидата: BINANCE:<пара>.P */
    const nameEl = document.getElementById('obcName');
    nameEl.href = 'https://www.tradingview.com/chart/?symbol=BINANCE:' +
      encodeURIComponent(d.pair || '') + '.P';
    const capEl = document.getElementById('obcCap');
    capEl.textContent = d.cap; capEl.dataset.t = d.cap; capEl.classList.add('d3');
    nearBand(d.near);
    diagram(d);

    d.cols.forEach((c, i) => {
      const gm = colGeom[i] || {cx:620, tone:TONE.pale};
      const el = document.createElement('div');
      el.className = 'col';
      el.style.left = (gm.cx / W * 100) + '%';
      const far = i % 2 === 0;
      /* Ближний ряд поднят на 20: он уходил в самый низ воды, где под
         ним уже стоит приборная полоса, и пара «давление · объём»
         читалась впритык к ней. */
      el.style.top    = ((WATER + (far ? 34 : 102)) / H * 100) + '%';
      el.style.zIndex = far ? 1 : 2;
      const yaw = ((gm.cx - 680) / 240) * 15;
      el.style.transform = `translateX(-50%) perspective(760px)
        rotateX(${far ? 26 : 19}deg) rotateY(${yaw.toFixed(1)}deg)`;
      el.style.fontSize = far ? '.88em' : '1em';
      // задержка по номеру столба — подписи проявляются вслед за
      // своим столбом, а не все разом
      el.innerHTML = `<div class="cin" style="animation-delay:${(.90 + i*.30).toFixed(2)}s">
                        <div class="vw">
                          <div class="v"  style="color:${gm.tone.txt}">${c.v}</div>
                          <div class="rf" style="color:${gm.tone.txt}">${c.v}</div>
                        </div>
                        <div class="n">${c.n}</div><div class="s">${c.s}</div>
                      </div>`;
      lay.appendChild(el);
    });
  }

  /* ════════════════════════════════════════════════════════════
     ПРИБОРНАЯ ПОЛОСА
     Часовой ход объёма линией со свечением, под ней вертикальные
     волоски до базы — именно они на референсе превращают график в
     прибор, без них это обычный спарклайн. По краям две дуги.
     ════════════════════════════════════════════════════════════ */
  function diagram(d){
    const VW = 1240, VH = 200, base = 152, top = 26, x0 = 300, x1 = 940;
    /* Ряда за сутки может не быть вовсе, и это не редкость. Плоская
       линия из подставленных нулей читалась бы как показание — «объём
       весь день ровный», — хотя означает «мы ничего не знаем». Поэтому
       при пустом ряде линия и гребёнка не рисуются, а подпись прямо
       говорит, чего нет. Приборы по краям остаются: они на этот ряд
       не опираются. */
    const H = d.hours || [], has = H.length > 1;
    const px = i => x0 + (x1 - x0) * i / Math.max(1, H.length - 1);
    const py = v => base - (base - top) * v;

    let hair = '', hn = 0, path = '', lx = x1, ly = base;
    const dly = () => `style="animation-delay:${(.84 + hn++ * .024).toFixed(3)}s"`;
    if (has) H.forEach((v, i) => {
      hair += `<line ${dly()} x1="${px(i).toFixed(1)}" y1="${py(v).toFixed(1)}"
               x2="${px(i).toFixed(1)}" y2="${base}"/>`;
      // между узлами ещё по два волоска — частая гребёнка читается
      // как заливка светом, редкая как столбики
      if (i < H.length - 1)
        for (let k = 1; k < 3; k++){
          const t = (i + k/3), a = Math.floor(t), f = t - a;
          const vv = H[a] + (H[a+1] - H[a]) * f;
          hair += `<line ${dly()} x1="${px(t).toFixed(1)}" y1="${py(vv).toFixed(1)}"
                   x2="${px(t).toFixed(1)}" y2="${base}" stroke-opacity=".45"/>`;
        }
    });

    if (has) {
      H.forEach((v, i) => {
        const x = px(i), y = py(v);
        if (!i) path = `M${x.toFixed(1)},${y.toFixed(1)}`;
        else {
          const xp = px(i-1), yp = py(H[i-1]), cx = (xp + x)/2;
          path += ` C${cx.toFixed(1)},${yp.toFixed(1)} ${cx.toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
        }
      });
      lx = px(H.length-1); ly = py(H[H.length-1]);
    }

    // Дуга: незамкнутое кольцо, значение — длина штриха. Обод и
    // цифра внутри, подпись под ним, как на приборе.
    /* Дни — счёт, а не доля, поэтому дугу заполнения кольцо не несёт:
       у доли есть предел, у счёта его нет, и любой предел был бы нашей
       выдумкой. Но обод остаётся — как циферблат без стрелки. Пара
       приборов по краям держит полосу, а пустой обод честнее ложной
       шкалы. */
    const tally = (cx, n) => `<g transform="translate(${cx},${base-46})">
        <circle r="30" class="ring"/>
        <text class="num" y="5">${n === null || n === undefined ? '—' : n}<tspan class="pc"> дн</tspan></text>
        <text class="cap2" y="46">дней от дна</text></g>`;

    /* Кольцо вопроса. Заполнение — доля согласных приборов, в
       центре их счёт, под кольцом — ответ словами. У топлива дуга
       БИПОЛЯРНАЯ: от верхней точки вправо, когда заряжено вверх, и
       влево, когда вниз. Одинаковая дуга на оба знака заставила бы
       читать подпись, чтобы понять сторону, — а кольцо на то и
       кольцо, чтобы отвечать раньше слов. */
    const qring = (cx, q, name, bipolar) => {
      const r = 30, cc = 2 * Math.PI * r;
      /* Подпись стороны. Показываем тех, кто держит ВЕРДИКТ: при
         «иссяк» это голоса за, при «жив» — против. Иначе строка
         объясняет не то, что написано над ней. */
      const pos = bipolar ? q.sign > 0 : (q.n >= Math.ceil(q.of / 2));
      const list = pos ? q.pro : q.con;
      const label = bipolar ? (pos ? 'за рост' : 'за спад') : (pos ? 'за' : 'против');
      const side = list ? label + ': ' + list : '';
      const frac = q.of ? Math.min(1, q.n / q.of) : 0;
      const sweep = cc * frac * (bipolar ? 0.42 : 0.75);
      const rot = bipolar ? (q.sign < 0 ? 90 : -90) : -215;
      const dir = bipolar && q.sign < 0 ? ' transform="scale(-1,1)"' : '';
      const center = !q.of ? '—'
        : (bipolar ? (q.sign > 0 ? '↑' : q.sign < 0 ? '↓' : '·') + q.n
                   : q.n + '<tspan class="pc">/' + q.of + '</tspan>');
      return `<g transform="translate(${cx},${base-46})">
        <circle r="${r}" class="ring"/>
        ${frac > 0.01 ? `<g${dir}><circle r="${r}" class="val"
            stroke-dasharray="${sweep.toFixed(1)} ${cc}"
            style="stroke-dashoffset:${sweep.toFixed(1)}"
            transform="rotate(${rot})"/></g>` : ''}
        <text class="num" y="5">${center}</text>
        <text class="cap2" y="46">${name} · ${q.word}</text>
        ${side ? `<text class="cap2" y="60" opacity=".62">${side}</text>` : ''}
      </g>`;
    };

    const arc = (cx, [name, frac]) => {
      const r = 30, c = 2 * Math.PI * r;
      return `<g transform="translate(${cx},${base-46})">
        <circle r="${r}" class="ring"/>
        <circle r="${r}" class="val" stroke-dasharray="${(c*frac*.75).toFixed(1)} ${c}"
                style="stroke-dashoffset:${(c*frac*.75).toFixed(1)}"
                transform="rotate(-215)"/>
        <text class="num" y="5">${Math.round(frac*100)}<tspan class="pc">%</tspan></text>
        <text class="cap2" y="46">${name}</text></g>`;
    };

    document.getElementById('obcDiag').innerHTML = `
    <svg viewBox="0 0 ${VW} ${VH}" preserveAspectRatio="xMidYMax meet">
      <defs>
        <filter id="gl" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="b"/>
                   <feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <linearGradient id="hg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#FFC978" stop-opacity=".55"/>
          <stop offset="1" stop-color="#FFC978" stop-opacity="0"/>
        </linearGradient>
        <style>
          .hair{stroke:url(#hg);stroke-width:1.6}
          .ln{fill:none;stroke:#FFD79A;stroke-width:1.8;stroke-linecap:round}
          .ring{fill:none;stroke:rgba(190,215,235,.16);stroke-width:1.2}
          .val{fill:none;stroke:#F0BE6E;stroke-width:2.4;stroke-linecap:round}
          .num{fill:#EEDCBC;font:250 19px 'Helvetica Neue',sans-serif;text-anchor:middle;letter-spacing:.02em}
          .pc{font-size:11px;fill:#8B7B60}
          .cap2{fill:#63717E;font:400 8px 'Helvetica Neue',sans-serif;text-anchor:middle;
                letter-spacing:2.6px;text-transform:uppercase}
          .rule{stroke:rgba(180,205,230,.14);stroke-width:1}
          .tk{stroke:rgba(180,205,230,.26);stroke-width:1}
        </style>
      </defs>
      <g class="hair">${hair}</g>
      <line class="rule" x1="60" y1="${base}" x2="1180" y2="${base}"/>
      ${has ? [0,6,12,18,23].map(i => `<line class="tk" x1="${px(i).toFixed(1)}" y1="${base}"
          x2="${px(i).toFixed(1)}" y2="${base+7}"/>`).join('') : ''}
      ${has ? `<path class="ln" d="${path}" filter="url(#gl)"/>
      <circle class="tipdot" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.6"
              fill="#FFE7BE" filter="url(#gl)"/>` : ''}
      <text x="${x0}" y="${base+22}" class="cap2" text-anchor="start">${
        has ? '24 часа · объём' : '24 часа · ряда нет'}</text>
      <g filter="url(#gl)">${qring(150, d.rings.sell, 'продавец')}${
        qring(1090, d.rings.fuel, 'топливо', true)}</g>
    </svg>`;
  }

  /* Гашение соседей при наведении снято: подписи и так на пределе
     читаемости поверх отражения, и любое приглушение делало их
     нечитаемыми совсем. Все пять величин видны всегда. */


  function mulberry(a){ return function(){
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function hex(h, a){
    const n = parseInt(h.slice(1), 16);
    return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`; }

  /* ════════════════════════════════════════════════════════════
     УПРАВЛЕНИЕ
     ════════════════════════════════════════════════════════════ */
  var note = document.getElementById('obcNote');

  /* Ключевой кусок зал помечает тегом b. Всё до него и после — мелкой
     разрядкой, сам он — крупно. Если пометки нет, фраза остаётся
     одной строкой: выдумывать, что в ней главное, мы не станем. */
  function levels(html) {
    if (!html) return '';
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    var b = tmp.querySelector('b');
    if (!b) return html;
    var before = '', after = '', seen = false;
    [].forEach.call(tmp.childNodes, function (n) {
      if (n === b) { seen = true; return; }
      if (seen) after += n.textContent; else before += n.textContent;
    });
    before = before.trim().replace(/[:,]\s*$/, '');
    after = after.trim();
    return (before ? '<span class="nq">' + before + '</span>' : '') +
           '<span class="nk ' + (b.className || '') + '">' + b.textContent + '</span>' +
           (after ? '<span class="nq">' + after + '</span>' : '');
  }
  var pos  = document.getElementById('obcPos');
  var draw = document.getElementById('obcDrawBody');

  /* Подстановка содержимого. Раньше текст, ящик и счётчик менялись в
     тот же миг, когда начинался переход: старая фраза ещё висела на
     экране и вдруг становилась новой. Отсюда и ощущение скачка —
     столбы плавно тонули, а слова подменялись рывком.

     Теперь всё содержимое ставится одним куском в провале посередине,
     когда старое уже утонуло, а новое ещё не поднялось. */
  /* ── Значки ─────────────────────────────────────────────────
     Три состояния у предложения, и они разные по смыслу, а не по
     степени: разлок впереди, весь объём уже в обращении, данных нет.
     Средний случай — не «ноль дней до разлока», а его отсутствие как
     свойство: давить сверху больше нечему. Красить его тем же цветом,
     что и близкий разлок, значит спутать угрозу с её отсутствием. */
  function marks(card) {
    const mi = document.getElementById('obcMarkInv');
    const ms = document.getElementById('obcMarkSup');
    const inv = card.inv || [];

    /* Знак «хозяин» и фонарь на лодке говорят одно и то же и потому
       зажигаются от одного правила: известный организатор. Прочие
       инвесторы остаются в подсказке — знать их полезно, но масштаб
       возможного движения меняют не они. */
    var org = organizerOf(card);
    mi.className = 'obc-mark' + (org ? ' hot' : (inv.length ? '' : ' off'));
    mi.querySelector('.obc-tip').innerHTML = (org
      ? '<b>организатор</b><i>' + org + '</i>'
      : '<b>инвесторы</b>') + (inv.length
      ? (org ? '<br>' : '') + inv.map(function (v) {
          return v.n + ' · тир ' + v.tier;
        }).join('<br>')
      : (org ? '' : 'не известны'));

    const u = card.unlock, fp = card.floatPct;
    let cls = ' off', tip = '<b>предложение</b>данных нет';

    if (u) {
      /* Горячо, если транш весит больше пяти процентов обращения ИЛИ
         идёт инсайдерам. Не вердикт, а выделение того, что стоит
         посмотреть. */
      const hot = (u.flo !== null && u.flo >= 5) || u.ins;
      cls = hot ? ' hot' : '';
      tip = '<b>предложение</b>разлок через ' +
            (u.days === 0 ? '<i>сегодня</i>' : '<i>' + u.days + ' дн</i>') +
            (u.sup !== null ? '<br>' + u.sup + '% всей эмиссии' : '') +
            (u.flo !== null ? '<br>' + u.flo + '% того, что в обращении' : '') +
            (u.ins ? '<br><i>идёт инсайдерам</i>' : '') +
            (u.inferred ? '<br>срок оценочный' : '') +
            (fp !== null ? '<br>сейчас в обращении ' + Math.round(fp) + '%' : '');
    } else if (fp !== null && fp >= 99) {
      /* Весь объём в обращении — состояние, а не пропуск: сверху
         больше не сыплется, и это единственный случай, когда у
         предложения хорошие новости. Отсюда и свой цвет. */
      cls = ' free';
      tip = '<b>предложение</b><u>весь объём в обращении</u>' +
            '<br>разлоков впереди нет';
    } else if (fp !== null) {
      cls = '';
      tip = '<b>предложение</b>в обращении ' + Math.round(fp) + '%' +
            '<br>сроки разлока не известны';
    }
    ms.className = 'obc-mark' + cls;
    ms.querySelector('.obc-tip').innerHTML = tip;
  }

  /* ── Известные организаторы ──
     Список короткий и именной сознательно: «фонарь» отмечает не
     наличие инвестора, а присутствие тех, кто способен вести
     монету сам. Имена набраны по расследованиям, лежащим в основе
     техдолга схем; список пополняется руками, как и должен —
     автоматически такое не выводится.

     Сверка по нормализованной подстроке: в данных встречаются и
     «YZi Labs», и «Binance Labs (YZi)», и «DWF». */
  var ORGANIZERS = ['yzi', 'binance labs', 'dwf', 'hsbg'];

  function organizerOf(card) {
    var c = (card && card.raw) || {};
    var names = [];
    if (c.organizer) names.push(String(c.organizer));
    (c.investors || []).forEach(function (v) {
      names.push(String(v.n || v.name || ''));
    });
    for (var i = 0; i < names.length; i++) {
      var low = names[i].toLowerCase();
      for (var k = 0; k < ORGANIZERS.length; k++) {
        if (low.indexOf(ORGANIZERS[k]) >= 0) return names[i];
      }
    }
    return null;
  }

  function applyCard(card) {
    var det = DETAIL ? DETAIL(card.raw) : null;
    /* Здесь была фраза про частоту попаданий — «сегодня 29 против
       17». Это реактивная метрика нашей же системы, ровно та, от
       которой мы отказались: частота ничего не обещает (ALPINE
       попадала в 97% прогонов и была в минусе). И она конкурировала
       с полосой внизу за роль вывода.

       Сводка в кадре должна быть ОДНА. Теперь она собирается из тех
       же двух вопросов, что и кольца наверху, и заканчивается тем,
       что решается сегодня. Крупная строка — положение цены
       относительно ближайшего уровня: это и есть ответ «где мы
       сейчас», ради которого карточку открывают. */
    note.innerHTML = verdictHTML(card);
    draw.innerHTML = (det && det.body) || '';
    pos.innerHTML = '<b>' + (IDX + 1) + '</b> из ' + CARDS.length;
    root.classList.toggle('buyers', !!card.buyers);

    /* ── Лодка несёт ОДИН смысл ──
       Было три: парус показывал сторону вортекса, крен — скорость
       хода, фонарь — сумму тиров инвесторов. Первые два никто не
       различал: наклон в пару градусов и зеркальный парус не
       читаются, а обе величины уже сказаны в другом месте —
       направление вортекса голосует в кольце топлива, скорость
       лежит в ящике. Третий был мёртв: поля инвесторов в пейлоаде
       нет, и фонарь всегда горел вполсилы.

       Осталось одно: фонарь разгорается, когда за монетой стоит
       ИЗВЕСТНЫЙ организатор. Не «инвестор вообще» и не сумма тиров
       — именно имя из короткого списка тех, чьё присутствие само по
       себе меняет масштаб возможного движения. Парус и крен замерли:
       лодка просто идёт, покачиваясь на волне. */
    var org = organizerOf(card);
    [document.getElementById('obcBoat'), document.getElementById('obcBoatM')]
      .forEach(function (b) {
        b.style.setProperty('--heel', '0deg');
        b.style.setProperty('--inv', org ? '1' : '0');
        b.classList.remove('wind-l');
      });

    NEAR = card.near;
    marks(card);
    labels(card);
    lay.classList.remove('out');
  }

  function show(i, animated) {
    IDX = (i + CARDS.length) % CARDS.length;
    root.classList.remove('drawer');
    if (animated) { go(IDX); return; }

    /* Первый заход из зала идёт тем же переходом, но начинается сразу
       со второй половины. Первая половина — это утопление предыдущей
       монеты, а на входе тонуть нечему: при tp = 0 зритель просто
       две секунды смотрел на пустую воду. Ставим время на точку
       подмены, содержимое даём сразу, и остаётся один подъём. */
    cur = from = to = IDX; tp = .42; swapped = true;
    root.classList.add('moving');
    /* Сначала гряда и композиция, только потом содержимое: подписи
       столбов встают по colGeom, а его заполняет compose. Вызвав
       applyCard раньше, мы получаем пустой colGeom — и все пять
       подписей садятся в одну точку по запасному значению. */
    /* На входе туман тоже начинается с нуля: время уже стоит на точке
       подмены, и первый же кадр цикла продолжит его проявление. */
    NEAR = CARDS[IDX].near;
    buildBG(CARDS[IDX].price, CARDS[IDX].entry, CARDS[IDX].unlock, 0);
    compose();
    applyCard(CARDS[IDX]);
  }

  function step(d) { if (tp >= 1) show(IDX + d, true); }

  document.getElementById('obcPrev').onclick = function () { step(-1); };
  document.getElementById('obcNext').onclick = function () { step(1); };
  document.getElementById('obcMore').onclick = function () { root.classList.toggle('drawer'); };
  document.getElementById('obcDrawX').onclick = function () { root.classList.remove('drawer'); };
  /* На планшете наведения нет: значок открывается касанием и
     закрывается касанием мимо. Второе важнее первого — подсказка,
     которую нечем убрать, закрывает собой кадр. */
  document.getElementById('obcMarks').addEventListener('click', function (e) {
    const m = e.target.closest('.obc-mark');
    [].forEach.call(this.children, function (c) {
      c.classList.toggle('open', c === m && !c.classList.contains('open'));
    });
    e.stopPropagation();
  });
  document.getElementById('obcScene').addEventListener('click', function () {
    [].forEach.call(document.getElementById('obcMarks').children, function (c) {
      c.classList.remove('open');
    });
  });

  document.getElementById('obcClose').onclick = close;

  /* Экран лидеров отвечает «что происходит», карточка на орбите —
     «почему». Пара сохранена: кнопка есть, если зал дал переход. */
  var gotoBtn = document.getElementById('obcGoto'), GOTO = null;
  gotoBtn.onclick = function () {
    if (!GOTO) return;
    var t = CARDS[IDX].tick;
    close();
    GOTO(t);
  };

  function close() {
    live = false;                 /* кадр остановится сам на ближайшем тике */
    root.classList.remove('on', 'drawer');
    /* Холст и разметку чистим: закрытая карточка не держит в памяти
       последнюю монету и не показывает её на долю секунды при
       следующем открытии, до первого кадра. */
    ctx.clearRect(0, 0, W, H);
    document.getElementById('obcDiag').innerHTML = '';
    lay.querySelectorAll('.col').forEach(function (e) { e.remove(); });
  }

  /* Стрелки листают, esc закрывает — но сначала ящик, если он открыт:
     иначе одно нажатие уносит сразу из справки на подиум. */
  document.addEventListener('keydown', function (e) {
    if (!live) return;
    if (e.key === 'ArrowLeft')  { step(-1); e.preventDefault(); }
    if (e.key === 'ArrowRight') { step(1);  e.preventDefault(); }
    if (e.key === 'Escape') {
      if (root.classList.contains('drawer')) root.classList.remove('drawer');
      else close();
      e.stopPropagation();
    }
  }, true);

  /* ════════════════════════════════════════════════════════════
     ВНЕШНИЙ ВЫЗОВ
     podium.py отдаёт весь список журнала и номер открытой монеты —
     иначе листать было бы нечего. detail(c) возвращает готовую
     вёрстку нижнего ящика: числа форматирует зал, картинку рисуем мы.
     ════════════════════════════════════════════════════════════ */
  window.OBCARD = {
    open: function (list, index, detail, goto) {
      if (!list || !list.length) return;
      CARDS = list.map(adapt);
      DETAIL = detail || null;
      GOTO = goto || null;
      gotoBtn.classList.toggle('on', !!GOTO);
      prep = [];                  /* столбы пекутся заново под новый список */
      root.classList.add('on');
      live = true; last = 0;
      cv.width = W; cv.height = H;
      buildFG();
      show(index || 0, false);
      requestAnimationFrame(frame);
    },
    close: close,
    isOpen: function () { return live; }
  };
})();
</script>
"""

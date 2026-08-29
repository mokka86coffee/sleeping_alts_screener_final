"""Лидеры прогона · САМОСТОЯТЕЛЬНЫЙ ДОКУМЕНТ.

Был экраном поверх дашборда, в одном с ним документе. Стал отдельным
файлом podium.html, который оболочка грузит вторым — после сводки.

Сетка карточек заменена круглым залом. Причина не в оформлении: в сетке
стадия сделки была подписью над группой, то есть требовала прочитать
заголовок и запомнить его. Здесь стадию несёт ВЫСОТА яруса — вверху
то, что ещё не началось, посередине то, что идёт, внизу отработавшее.
Положение в пространстве запоминается само, подпись только называет.

Второе следствие зала: у монеты появляется место. В ленте место есть
только у первой и последней карточки, остальные различаются лишь
порядком; в комнате монета остаётся там, где её оставили, и к ней
возвращаются поворотом головы.

Цена решения названа прямо: зал показывает пять-шесть карточек разом
против двух десятков в сетке. Для «пробежать глазами» это хуже, для
«разглядеть, что с монетой» — лучше. Экран лидеров заведён ради
второго.

Данных своих у модуля нет и теперь: они приходят АРГУМЕНТОМ и
вшиваются в документ при сборке. Второй источник тех же чисел
разошёлся бы с орбитой при первой правке, и монета показывала бы на
двух экранах разное — поэтому build_stars() зовётся один раз в
render_page, а результат уходит во все экраны сразу.

ОЧЕРЕДЬ ЭКРАНОВ ЗДЕСЬ БОЛЬШЕ НЕ ЖИВЁТ. Раньше зал сам дожидался
сводки: вешал MutationObserver на её узел, ловил снятие класса .on и
запускался через 560 мс, плюс держал сторожевой таймер на случай, если
сводка не откроется вовсе. Всё это ушло в оболочку (SEQUENCE в
render_shell.py) — вместе со знанием о том, что сводка вообще
существует и каким классом отмечает своё состояние.

СТИЛИ ЛЕЖАТ ЗДЕСЬ, а не в css.py — намеренно. Блок подиума в css.py
трижды дублировался от повторного применения патчей, и каждый раз это
чинилось отдельным скриптом. Модуль, который несёт свою разметку, свой
скрипт и свои стили, разойтись сам с собой не может.
"""

from __future__ import annotations

import json

# Сцена карточки живёт в этом же документе, потому что открывает её
# только зал — вызовом window.OBCARD.open() при клике по карточке.
# В разных документах этот вызов не дошёл бы до адресата: у каждого
# iframe своё окно. Раньше сцену вставлял дашборд, и это работало лишь
# потому, что все три экрана лежали на одной странице.
from render_cardscene import render_cardscene


def render_podium(stars: list[dict], market: dict) -> str:
    """Тело документа зала. Данные вшиваются, а не читаются из окна."""
    blob = json.dumps({"stars": stars, "market": market},
                      ensure_ascii=False, separators=(",", ":"))
    safe = blob.replace("</", "<\\/")
    return (PODIUM_CSS + PODIUM_HTML
            + render_cardscene()
            + f'<script id="obpData" type="application/json">{safe}</script>'
            + PODIUM_JS)


PODIUM_CSS = """
<style>
/* ── Зал ─────────────────────────────────────────────────────
   Третий экран в очереди: сводка → лидеры → дашборд. Подложка та
   же, что у сводки: переход должен читаться как смена содержимого,
   а не как другое приложение. */
/* Закрытый зал должен исчезать из страницы, а не становиться
   прозрачным. На узком экране он превращается в прокручиваемый слой
   во весь экран (см. ветку max-width:900px), а такой слой на
   планшете продолжает ловить касания даже с pointer-events:none —
   инерция прокрутки живёт своей жизнью и съедает первые нажатия.
   Отсюда и мёртвый блок FLOW на дашборде после закрытия.

   visibility снимает попадания надёжно и для прокрутки тоже, но
   гасить её надо ПОСЛЕ затухания: с нулевой задержкой зал пропадал
   бы мгновенно, без перехода. */
.ob-podium{position:fixed;inset:0;z-index:41;overflow:hidden;
  background:radial-gradient(1100px 700px at 50% -5%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;visibility:hidden;
  transition:opacity .5s ease, visibility 0s linear .5s;
  cursor:grab;perspective:1200px;perspective-origin:50% 46%}
.ob-podium.on{opacity:1;pointer-events:auto;visibility:visible;
  transition:opacity .5s ease, visibility 0s}


/* Купол: свет по краю, звёзды к центру. Он и сообщает, что мы
   внутри помещения, а не смотрим на ленту карточек. */
.obp-dome{position:absolute;left:-10%;right:-10%;top:-42%;height:96%;
  border-radius:50%;pointer-events:none;
  background:
    radial-gradient(60% 52% at 50% 100%, rgba(60,110,220,.22), transparent 70%),
    radial-gradient(90% 70% at 50% 108%, rgba(20,50,140,.16), transparent 72%)}

/* Пол: отражения нижнего яруса лежат на нём, поэтому не просто
   градиент, а поверхность с бликом от центра. */
.obp-floor{position:absolute;left:-20%;right:-20%;bottom:0;height:46%;
  pointer-events:none;
  background:
    radial-gradient(46% 78% at 50% 0%, rgba(255,190,90,.09), transparent 66%),
    linear-gradient(180deg, rgba(10,14,26,0), rgba(6,9,18,.85) 42%, #050406)}

.obp-sky{position:absolute;inset:0;pointer-events:none}

.obp-top{position:absolute;left:26px;right:26px;top:20px;z-index:6;
  display:flex;align-items:baseline;justify-content:space-between;gap:20px}
.obp-h{font-family:ui-monospace,Menlo,monospace;font-size:11px;
  letter-spacing:.34em;text-transform:uppercase;color:#8E96A2}
.obp-stamp{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#454C57}

/* Сводка портфеля в шапке. Занимает середину строки: слева заголовок,
   справа кнопка выхода, и обе уже прижаты к краям. */
.obp-port{position:absolute;left:210px;right:210px;top:16px;z-index:7;
  text-align:center;font-family:ui-monospace,Menlo,monospace;
  font-size:11px;letter-spacing:.04em;color:#8D97A6;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.obp-port b{font-weight:600;color:#E3E8EF}
.obp-port b.up{color:#5FE39C} .obp-port b.dn{color:#FF8A72}
.obp-port .sep{color:#3A414C;padding:0 8px}
.obp-port .loss{color:#B9C2CE}
.obp-port .loss i{font-style:normal;color:#5A6270}
@media (max-width:1100px){ .obp-port{display:none} }

/* Выход. Не крестик: значок пришлось бы объяснять, а слово говорит
   само. Рамка тонкая и холодная — кнопка обязана быть найдена, но
   не обязана спорить за внимание с карточками. */
.obp-exit{position:absolute;right:26px;top:14px;z-index:8;
  font-family:ui-monospace,Menlo,monospace;font-size:9px;
  letter-spacing:.3em;text-transform:uppercase;color:#6E7684;
  padding:7px 14px;border:1px solid rgba(255,255,255,.10);
  border-radius:999px;cursor:pointer;background:rgba(8,10,16,.55);
  transition:color .2s ease,border-color .2s ease,background .2s ease}
.obp-exit:hover{color:#D6DCE6;border-color:rgba(255,255,255,.24);
  background:rgba(18,22,32,.8)}
.obp-exit:focus-visible{outline:2px solid #7FE3D4;outline-offset:2px}

/* ── Сцена ───────────────────────────────────────────────────
   Панели стоят по цилиндру, наблюдатель внутри. Без CSS-перехода:
   угол доводится покадрово, и переход поверх дал бы двойное
   сглаживание — зал отставал бы от жеста рывками. */



/* Панели вне поля обзора не только прозрачны, но и не ловят курсор:
   иначе невидимая карточка перехватывала бы клик по видимой. */


/* ── Рама ────────────────────────────────────────────────────
   Матовая плита, а не залитый цветом прямоугольник: сквозь неё
   виден фон зала. */



/* Техническая сетка: даёт поверхности фактуру и почти не видна. */


/* Световая полоса делит раму на зону заголовка и зону графика.
   Свет здесь не украшение, а разделитель. */
.obp-beam{position:absolute;left:-8%;right:-8%;top:58px;height:2px;
  pointer-events:none;
  background:linear-gradient(90deg,
    transparent, rgba(var(--c),.85) 32%, #fff 50%,
    rgba(var(--c),.85) 68%, transparent)}
.obp-beam::before{content:'';position:absolute;left:0;right:0;top:-26px;
  height:54px;filter:blur(7px);
  background:radial-gradient(58% 100% at 50% 50%,
    rgba(var(--c),.55), transparent 72%)}

/* Уголковые скобы: рамка намечена, а не замкнута — панель читается
   как элемент интерфейса, а не картина в багете. */
.obp-br{position:absolute;width:13px;height:13px;pointer-events:none;
  border:1px solid rgba(var(--c),.55)}
.obp-br.tl{left:7px;top:7px;border-right:0;border-bottom:0}
.obp-br.tr{right:7px;top:7px;border-left:0;border-bottom:0}
.obp-br.bl{left:7px;bottom:7px;border-right:0;border-top:0}
.obp-br.brr{right:7px;bottom:7px;border-left:0;border-top:0}

.obp-tick{position:absolute;left:0;right:0;top:16px;text-align:center;
  font-family:ui-monospace,Menlo,monospace;
  font-size:15px;font-weight:300;letter-spacing:3.8px;color:#E8EEF4;
  text-shadow:0 0 18px rgba(var(--c),.6)}
.obp-state{position:absolute;left:0;right:0;top:38px;text-align:center;
  font-size:8.5px;font-weight:400;letter-spacing:2.6px;
  text-transform:uppercase;color:rgba(var(--c),.85);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 10px}




/* ── Приборы ─────────────────────────────────────────────────
   Три величины — три формы, а не четыре одинаковых числа в строку.
   В приборной панели так не бывает: там скорость это дуга, заряд —
   полоса, и различить их можно не читая. */
.obp-nums{position:absolute;left:0;right:0;bottom:0;height:74px;
  padding:9px 12px 10px;display:flex;align-items:center;gap:10px;
  background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.46) 38%);
  border-top:1px solid rgba(255,255,255,.05)}



.obp-gau-v{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;padding-top:2px}
.obp-gau-v b{font-family:ui-monospace,Menlo,monospace;
  font-size:13px;font-weight:400;color:#7FD9A6}
.obp-gau-v i{font-size:6px;font-style:normal;letter-spacing:1.4px;
  text-transform:uppercase;color:#454C57;margin-top:1px}

.obp-rows{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px}
.obp-row{display:flex;align-items:center;gap:7px}
.obp-row i{font-size:6.5px;font-style:normal;letter-spacing:1.3px;
  text-transform:uppercase;color:#454C57;width:34px;flex:none}
.obp-row b{font-family:ui-monospace,Menlo,monospace;font-size:11px;
  font-weight:400;color:#c9ccd2;margin-left:auto;flex:none}

/* Сегменты: тусклые — рекорд за наблюдение, светлые — сегодня.
   Полоса отвечает на вопрос, которого голое число не задаёт:
   далеко ли сегодня до собственного максимума. */
.obp-seg{display:flex;gap:2px;flex:1;min-width:0}
.obp-seg u{flex:1;height:7px;border-radius:1px;text-decoration:none;
  background:rgba(var(--c),.13)}
.obp-seg u.on{background:rgba(var(--c),.85);
  box-shadow:0 0 7px rgba(var(--c),.55)}
.obp-seg u.rec{background:rgba(var(--c),.30)}

/* Насечки дней: всего четырнадцать — столько живёт запись.
   Видно и сколько прошло, и сколько осталось. */
.obp-tk{display:flex;gap:1.5px;flex:1;min-width:0;align-items:flex-end}
.obp-tk u{flex:1;height:5px;border-radius:.5px;text-decoration:none;
  background:rgba(255,255,255,.10)}
.obp-tk u.on{height:10px;background:rgba(var(--c),.75)}

/* Отражение только у нижнего яруса: пол один, и картины верхних
   этажей на нём отражаться не могут. */





/* ── Переключатель групп ─────────────────────────────────────
   Стоит по центру сверху: это первое, что видно при входе, и оно же
   объясняет, что зал показывает не всё сразу. Счётчик на кнопке
   обязателен — иначе переключение вслепую, и пустая группа выглядит
   как поломка. */
/* ── Переключатель групп ─────────────────────────────────────
   Была коробка с жёсткими перегородками: рамка, разделители в
   пиксель и залитая плашка у активной вкладки. Плашка спорила с
   залом по весу, «в работе» ломалось на две строки, а счётчики
   читались наравне с названиями.

   Теперь это стеклянная планка с бликом по верхней кромке — тот
   же материал, что у капсулы дашборда и рамок панелей. Активная
   вкладка не заливается, а подсвечивается снизу тонкой чертой в
   цвет своей группы: подчёркивание указывает, заливка загораживает.
   Счётчик стоит тише названия — он уточняет, а не называет. */

/* Блик по верхней кромке — как у капсулы дашборда */


.obp-gb{position:relative;--a:#C8D2DE;
  font:400 10px/1 var(--mono,ui-monospace,monospace);letter-spacing:.2em;
  text-transform:uppercase;color:#6B717C;background:transparent;border:0;
  padding:10px 20px 11px;border-radius:999px;cursor:pointer;
  white-space:nowrap;                      /* «в работе» больше не ломается */
  transition:color .22s ease,background .22s ease}
.obp-gb[data-g="take"]{--a:#9EDCF5}
.obp-gb[data-g="trade"]{--a:#7FE3D4}
.obp-gb[data-g="exit"]{--a:#FFB4A0}
.obp-gb b{font-weight:400;margin-left:9px;color:#454A54;
  transition:color .22s ease}
.obp-gb:hover{color:#A2AAB6;background:rgba(200,220,232,.045)}
.obp-gb:hover b{color:#6B717C}
.obp-gb:focus-visible{outline:2px solid var(--a);outline-offset:2px}

/* Черта под активной: короткая, светящаяся, в цвет группы */
.obp-gb::after{content:'';position:absolute;left:50%;bottom:5px;
  width:0;height:1.5px;border-radius:1px;transform:translateX(-50%);
  background:var(--a);box-shadow:0 0 10px var(--a);opacity:0;
  transition:width .28s cubic-bezier(.2,.8,.3,1),opacity .22s ease}
.obp-gb.on::after{width:calc(100% - 34px);opacity:.95}
.obp-gb.on{color:var(--a);text-shadow:0 0 16px color-mix(in srgb,var(--a) 45%,transparent)}
.obp-gb.on b{color:color-mix(in srgb,var(--a) 62%,#6B717C)}
/* Пустая группа не притворяется живой: счётчик в нуле гаснет */
.obp-gb b:empty{display:none}

/* ── Подписи ярусов ──────────────────────────────────────────
   Высота несёт стадию, и это надо назвать словом, а не оставить
   угадывать по цвету. */

.obp-tl{position:absolute;left:0;transform:translateY(-50%)}
.obp-tl-n{font-size:8.5px;font-weight:500;letter-spacing:3.2px;
  text-transform:uppercase;color:rgba(var(--c),.9)}
.obp-tl-c{font-family:ui-monospace,Menlo,monospace;font-size:20px;
  font-weight:300;color:#8b8a92;margin-top:4px}
.obp-tl-c small{font-size:9px;color:#454C57;margin-left:5px}
.obp-tl::before{content:'';position:absolute;left:-14px;top:4px;
  width:2px;height:26px;border-radius:2px;background:rgba(var(--c),.55)}

/* ── Интрадей на панели и в карточке ── */
.obp-today{display:flex;justify-content:space-between;align-items:center;
  margin-top:6px;padding-top:5px;border-top:1px solid rgba(255,255,255,.07);
  font-size:9px;letter-spacing:.06em;color:#8D97A6}
.obp-today b{font-weight:600}
.obp-today b.up{color:#4FCF8A} .obp-today b.dn{color:#E8705A}

/* Наблюдение словами вместо блока чисел. Прижато к низу рамки:
   график остаётся главным, подпись читается под ним, а не спорит
   с ним за верх карточки. */
.obp-note{position:absolute;left:10px;right:10px;bottom:24px;
  text-align:center;
  font-size:18px;line-height:1.4;letter-spacing:.02em;color:#D8E0EA;
  /* Тень под текстом: подпись лежит поверх подсветки рамки, и на
     светлом крае панели без неё теряется контраст. */
  text-shadow:0 1px 14px rgba(0,0,0,.75)}
.obp-note b{font-weight:600;color:#FFFFFF}
.obp-note b.up{color:#5FE39C} .obp-note b.dn{color:#FF8A72}
.obp-note b.am{color:#FFC96B}
/* Место в текущем прогоне. Стоит в углу рамы и набрано тише тикера:
   это не имя монеты, а её номер в очереди, и спорить с именем он не
   должен. Score под номером ещё тише — он объясняет номер, а не
   существует сам по себе. */
.obp-rank{position:absolute;right:9px;top:8px;text-align:right;
  font-size:12px;font-weight:300;letter-spacing:.04em;color:#93A4B3}
.obp-rank i{display:block;font-style:normal;font-size:8.5px;
  letter-spacing:.14em;color:#5E6E7C;margin-top:1px}
.obp-note-q{display:block;margin-top:4px;font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:#7C8694}

/* Пробелы. Нейтральный серый и рамка пунктиром: это не ошибка, а
   место под ручную работу. Красным было бы неправдой — расчёт
   исправен, данных нет у биржи. */
.obz-gaps{margin-top:14px;padding:9px 11px;border-radius:6px;
  border:1px dashed rgba(255,255,255,.13);font-size:11px;line-height:1.6;
  color:#8D97A6}
.obz-gaps b{color:#B9C2CE;font-weight:600}
.obz-gaps i{font-style:normal;color:#5A6270;letter-spacing:.24em;
  text-transform:uppercase;font-size:9px;display:block;margin-bottom:4px}

.obp-port .gaps{color:#6E7684}
.obp-port .gaps b{color:#9AA6B5}

.obz-sum{padding:12px 20px;font-size:13px;line-height:1.6;color:#E3E8EF;
  background:rgba(127,227,212,.05);
  border-top:1px solid rgba(255,255,255,.08)}
.obz-sum b{font-weight:600;color:#7FE3D4}
.obz-sum b.up{color:#4FCF8A} .obz-sum b.dn{color:#E8705A}
.obz-sum b.am{color:#F0B85C}

.obz-blocks{display:block}
.obz-blk{padding:14px 20px 16px;border-top:1px solid rgba(255,255,255,.08)}
.obz-blk-k{font-size:9px;letter-spacing:.4em;text-transform:uppercase;
  color:#5A6270}
.obz-blk-h{font-size:11px;color:#5A6270;margin:2px 0 10px}
.obz-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));
  gap:12px 16px;margin-top:12px}
.obz-cell i{display:block;font-size:9px;letter-spacing:.28em;
  text-transform:uppercase;color:#5A6270;font-style:normal;margin-bottom:3px}
.obz-cell b{font-size:14px;font-weight:400;color:#E3E8EF}
.obz-cell b.up{color:#4FCF8A} .obz-cell b.dn{color:#E8705A}
.obz-cell b.am{color:#F0B85C}
.obz-h48{background:#0b0d12;border:1px solid rgba(255,255,255,.08);
  border-radius:6px;padding:5px}
.obz-days{display:flex;gap:3px;align-items:flex-end;height:26px;margin-top:5px}
.obz-days i{width:11px;background:#7FE3D4;opacity:.75;border-radius:1px}
.obz-days i.z{background:rgba(255,255,255,.09)}
.obz-chip{display:inline-block;font-size:10px;padding:3px 8px;margin:5px 5px 0 0;
  border:1px solid rgba(255,255,255,.08);border-radius:20px;color:#8D97A6}
.obz-chip.best{border-color:rgba(127,227,212,.5);color:#7FE3D4}

.obp-hint{position:absolute;left:0;right:0;bottom:16px;text-align:center;
  font-size:8px;letter-spacing:3px;text-transform:uppercase;
  color:#2E2A24;pointer-events:none}
.obp-empty{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  max-width:46ch;text-align:center;font-size:12px;line-height:1.7;
  color:#5E564A}

/* ── Раскрытая карточка ──────────────────────────────────────
   Форма другая, чем у панелей на стене, и намеренно: там плитка в
   ряду, здесь она одна. Одинаковая форма означала бы, что мы
   просто увеличили плитку. */
.obz{position:absolute;inset:0;z-index:9;display:none;
  align-items:center;justify-content:center;
  background:radial-gradient(60% 60% at 50% 50%,
    rgba(3,4,7,.74), rgba(3,4,7,.95));
  opacity:0;transition:opacity .3s ease}
.obz.on{display:flex;opacity:1}

/* Перспектива на самой коробке: внутри две плоскости, и без неё
   поворот второй дал бы просто сплющенный прямоугольник.
   overflow не ставим — наклонённая панель выходит за нижнюю
   границу, и обрезка съела бы ровно её. */
.obz-box{width:660px;max-width:92vw;border-radius:16px;position:relative;
  padding-bottom:8px;perspective:1500px;perspective-origin:50% 24%;
  background:
    radial-gradient(120% 90% at 50% 118%, rgba(var(--c),.16), transparent 62%),
    linear-gradient(180deg, rgba(255,255,255,.05), rgba(4,6,12,.96) 46%);
  box-shadow:
    inset 0 0 0 1px rgba(var(--c),.34),
    inset 0 1px 0 rgba(255,255,255,.13),
    0 0 120px -18px rgba(var(--c),.7);
  transform:scale(.94);transition:transform .34s cubic-bezier(.22,.61,.36,1)}
.obz.on .obz-box{transform:scale(1)}

.obz-head{padding:22px 26px 0;display:flex;align-items:baseline;gap:13px}
.obz-t{font-family:ui-monospace,Menlo,monospace;font-size:30px;
  font-weight:300;letter-spacing:5px;color:#E8EEF4;
  text-shadow:0 0 30px rgba(var(--c),.65)}
.obz-s{font-size:8.5px;font-weight:400;letter-spacing:3px;
  text-transform:uppercase;color:rgba(var(--c),.9)}
.obz-cap{margin-left:auto;font-family:ui-monospace,Menlo,monospace;
  font-size:12px;color:#565E6A}

.obz-stack{transform-style:preserve-3d}

/* Экран с графиком: вертикальная плоскость, чуть вынесенная на
   зрителя — иначе две плоскости смыкаются в одну. */
.obz-art{height:196px;margin-top:12px;transform:translateZ(26px);
  transform-style:preserve-3d}
.obz-art svg{display:block;width:100%;height:100%}

/* Световой шов на ребре между экраном и консолью. */
.obz-seam{position:relative;height:1px;margin:0 26px;
  background:linear-gradient(90deg,
    transparent, rgba(var(--c),.7) 22%, #fff 50%,
    rgba(var(--c),.7) 78%, transparent)}
.obz-seam::after{content:'';position:absolute;left:0;right:0;top:-9px;
  height:20px;filter:blur(6px);
  background:radial-gradient(50% 100% at 50% 50%,
    rgba(var(--c),.5), transparent 70%)}

/* Приборная панель лежит под 32°, точка поворота у верхнего края:
   уходит ВНИЗ от линии графика, а не проваливается серединой.
   Угол выбран по читаемости — на 32° вертикальное сжатие около
   0.85, цифры ещё читаются без усилия. */
.obz-dash{position:relative;margin-top:14px;padding:22px 26px 30px;
  display:flex;align-items:center;justify-content:space-between;gap:18px;
  transform:rotateX(32deg);transform-origin:50% 0%;
  transform-style:preserve-3d;
  background:linear-gradient(180deg,
    rgba(255,255,255,.045), rgba(0,0,0,.35) 78%);
  border-top:1px solid rgba(var(--c),.28);
  border-radius:0 0 14px 14px;
  box-shadow:0 -14px 40px -22px rgba(var(--c),.6)}
/* Дальний край темнее ближнего: на наклонной поверхности свет
   падает неравномерно, и ровная заливка выдаёт подделку. */
.obz-dash::after{content:'';position:absolute;inset:0;pointer-events:none;
  border-radius:0 0 14px 14px;
  background:linear-gradient(180deg, transparent 30%, rgba(0,0,0,.45))}

.obz-met{width:150px;flex:none}
.obz-met.r{text-align:right}
.obz-met-k{font-size:7.5px;font-weight:500;letter-spacing:2.4px;
  text-transform:uppercase;color:#454C57;margin-bottom:7px}
.obz-met-v{font-family:ui-monospace,Menlo,monospace;font-size:19px;
  font-weight:300;color:#d8dde4}
.obz-met-v small{font-size:9px;color:#454C57;margin-left:4px}
.obz-met .obp-seg,.obz-met .obp-tk{margin-top:9px}
.obz-met .obp-seg u{height:8px}
.obz-met .obp-tk u{height:6px}
.obz-met .obp-tk u.on{height:12px}

/* Циферблат развёрнут ОТДЕЛЬНО от панели, на которой лежит: он
   смотрит мимо зрителя и от этого читается как деталь корпуса, а
   не круг, нарисованный на поверхности. Вбок меньше, чем панель
   вниз — два сильных разворота подряд превращают шкалу в щель. */
.obz-gau{position:relative;width:200px;height:200px;flex:none;
  transform:rotateY(-26deg);transform-style:preserve-3d}
.obz-gau svg{display:block;width:100%;height:100%}
/* Веер виден только с той стороны, куда прибор отвёрнут: не ореол
   вокруг, а отдельная деталь позади. */
.obz-fan{position:absolute;inset:-26px;transform:translateZ(-42px);
  pointer-events:none}
.obz-gau-c{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;transform:translateZ(10px)}
.obz-gau-c b{font-family:ui-monospace,Menlo,monospace;font-size:34px;
  font-weight:300;color:#fff;text-shadow:0 0 26px rgba(var(--c),.6)}
.obz-gau-c i{font-size:8px;font-style:normal;letter-spacing:3px;
  text-transform:uppercase;color:#454C57;margin-top:3px}

.obz-verdict{padding:2px 26px 0;font-size:11px;line-height:1.5;
  color:#6C7480;max-width:62ch}
.obz-close{position:absolute;right:18px;top:14px;font-size:9px;
  letter-spacing:2.4px;text-transform:uppercase;color:#454C57;
  cursor:pointer;z-index:2}
.obz-close:hover{color:#E8EEF4}
.obz-goto{position:absolute;left:26px;bottom:-30px;font-size:9px;
  letter-spacing:2.4px;text-transform:uppercase;
  color:rgba(var(--c),.75);cursor:pointer}
.obz-goto:hover{color:#fff}

@media (prefers-reduced-motion:reduce){
  .obp-pan,.obz,.obz-box{transition:none}
}

/* ── Узкий экран ─────────────────────────────────────────────
   Зал разбирается: те же рамы ложатся обычной сеткой. Разметка не
   меняется, меняется только раскладка — иначе пришлось бы держать
   две версии карточки и чинить обе. */
@media (max-width:900px){
  /* display:block вместо флекса — обязателен, а не косметика.
     Флекс с центрированием по обеим осям давал одну колонку (дочерний
     элемент сжимался по содержимому) и убивал прокрутку (верх
     переполнения уезжал выше точки старта и становился недоступен). */
  .ob-podium{display:block;overflow-y:auto;-webkit-overflow-scrolling:touch;
    perspective:none;cursor:auto}
  .obp-dome,.obp-floor,.obp-sky,.obp-tiers,.obp-hint{display:none}
  .obp-stage{position:static;transform:none!important;width:100%;height:auto;
    display:grid;gap:9px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
    padding:64px 14px 40px}
  .obp-pan{position:static;transform:none!important;margin:0;
    width:auto;height:300px;opacity:1!important}
  .obp-pan.obp-off{opacity:1!important;pointer-events:auto}
  .obp-refl{display:none!important}
  .obz-box{perspective:none}
  .obz-dash{transform:none;padding:18px 20px 22px}
  .obz-art{transform:none}
  .obz-gau{transform:none;width:150px;height:150px}
  .obz-fan{display:none}
}
/* ── Ворота зала ─────────────────────────────────────────────
   Первый экран после бриза и постоянный дом зала. Слева сцена
   (волна прогона, ядро с числом выбранной группы, спутники),
   справа сам зал — список монет вместо стены карточек: он всегда
   перед глазами, и сцена не уходит.

   Все классы с приставкой obg-/obr-: экран лежит поверх подиума,
   и общие имена вроде .row или .panel столкнулись бы с его
   стилями.

   Палитра индиго — своя у ворот. Ярусы стены сохраняют прежние
   цвета STAGE, здесь же группам назначен индиго-набор, чтобы
   сцена читалась как один предмет. */
.obp-gate{position:absolute;inset:0;z-index:46;display:none;
  align-items:center;justify-content:center;padding:28px 20px;overflow:hidden;
  background:
    radial-gradient(90% 70% at 50% 22%,#333a6b 0%,transparent 62%),
    radial-gradient(80% 60% at 50% 96%,rgba(236,111,94,.10) 0%,transparent 66%),
    linear-gradient(180deg,#2a2f59 0%,#232748 46%,#1a1e3a 100%)}
.obp-gate::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(120% 90% at 50% 50%,transparent 44%,rgba(14,17,34,.55) 100%)}
.obp-gate.on{display:flex}

/* Выход из зала. Тихая, но всегда на месте: экран без видимого
   выхода — ловушка на любом устройстве без клавиатуры. */
.obg-out{position:absolute;top:14px;right:16px;z-index:9;
  padding:7px 15px;border-radius:999px;cursor:pointer;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);
  color:#98a0cc;font:inherit;font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;transition:color .3s,border-color .3s,background .3s}
.obg-out:hover{color:#e8ecfb;border-color:rgba(255,255,255,.22);
  background:rgba(255,255,255,.09)}
.obg-out:active{transform:translateY(1px)}

.obg-stage{position:relative;z-index:3;display:flex;align-items:center;
  gap:44px;width:min(1560px,96vw);height:100%}
.obg-inner{position:relative;flex:1;min-width:0;display:flex;flex-direction:column;
  align-items:center;gap:30px;
  animation:obgRise 2.1s cubic-bezier(.2,.75,.3,1) both}

/* ── Карточка монеты ──
   Встаёт РОВНО туда, где стояло ядро с кнопками, и только после того,
   как они уехали: до переезда центр занят, и вставать некуда.

   Лежит вне потока и место не занимает — иначе появление карточки
   раздвигало бы сцену, а исчезновение схлопывало. */
.obg-card{position:absolute;left:0;right:0;z-index:5;
  display:flex;flex-direction:column;align-items:flex-start;gap:13px;
  padding:0 4px;opacity:0;pointer-events:none;transition:opacity .5s ease}
.obg-card.obg-on{opacity:1}
/* Выходит СТРОКА ЗА СТРОКОЙ, а не блоками. Разница не косметическая:
   когда пять фактов появляются разом, они читаются как одно пятно и
   разбирать их приходится заново, глазами. Появляясь по очереди, они
   сами задают порядок чтения — и к последней строке первая уже
   прочитана.

   Шаг между строками почти две секунды, сама строка проступает за
   шесть с половиной: столько нужно, чтобы строку успели ПРОЧЕСТЬ до
   прихода следующей, а не только заметить.

   Тринадцать строк разворачиваются около двадцати восьми секунд — и
   это примерно срок отрисовки линии. Совпадение вышло случайно, но
   держать его стоит: текст и график заканчиваются вместе, а не так,
   что один давно готов и ждёт другого. */
.obg-card.obg-on .obc-anim{animation:obgCardIn 6.6s cubic-bezier(.2,.75,.3,1) both;
  animation-delay:calc(var(--nd,0) * 1.8s)}
@keyframes obgCardIn{from{opacity:0;transform:translateY(10px)}
  to{opacity:1;transform:none}}

.obc-head{display:flex;align-items:baseline;gap:22px;width:100%}
.obc-tk{font-size:52px;font-weight:200;letter-spacing:.03em;color:#eef2fa;
  line-height:1;text-decoration:none;cursor:pointer;
  transition:color .25s ease,text-shadow .25s ease}
.obc-tk:hover{color:#fff;text-shadow:0 0 26px rgba(200,214,255,.5)}
.obc-cs{font-size:11px;letter-spacing:.3em;text-transform:uppercase;color:var(--c)}
/* Приписка «ход отработан» рядом с фигурой. Янтарная рамка, а не
   цвет фигуры: это не свойство монеты, а состояние момента. */
.obc-spent{font-style:normal;margin-left:10px;padding:1px 6px;
  border-radius:3px;font-size:7.5px;letter-spacing:.12em;color:#ffb266;
  border:1px solid rgba(255,178,102,.45);background:rgba(255,178,102,.09)}
.obc-act{margin-left:auto;text-align:right;font-size:24px;font-weight:300;
  letter-spacing:.06em;text-transform:uppercase;color:var(--ac)}
/* Подпись строчными, а не капсом: капс у длинной причины съедает
   полстроки и всё равно упирается в край. */
.obc-act s{display:block;text-decoration:none;font-size:11px;letter-spacing:.04em;
  text-transform:none;color:#7b83b8;margin-top:9px;font-weight:400;
  max-width:420px;margin-left:auto}
/* Проза — главный текст карточки, а не подпись. Числа в ней подсвечены:
   глаз цепляется за них первым, а слова объясняют уже подцепленное. */
.obc-why{font-size:15px;line-height:1.7;color:#b3bcd8;max-width:1020px}
.obc-why em{font-style:normal;color:#f0b85c}

.obc-facts{display:flex;flex-direction:column;gap:7px;width:100%;max-width:820px}
.obc-fact{display:flex;gap:14px;align-items:baseline;font-size:11.5px;
  line-height:1.55;color:#8f98be}
.obc-fact em{font-style:normal;color:#c9d2e8}
/* Ярлык прижат вправо и одной ширины у всех: так значения выстраиваются
   в столбец и читаются как таблица, без линий. */
.obc-fact b{flex:0 0 92px;text-align:right;font-size:8px;letter-spacing:.2em;
  text-transform:uppercase;font-weight:500;color:var(--fc,#6b7391)}
.obc-fact span{flex:1;min-width:0}

.obc-nums{display:flex;gap:42px;flex-wrap:wrap;margin-top:4px}
.obc-num b{display:block;font-size:8.5px;letter-spacing:.22em;text-transform:uppercase;
  color:#5d6488;font-weight:400;margin-bottom:8px}
.obc-num i{font-style:normal;font-size:30px;font-weight:200;color:#dfe6f2;
  font-variant-numeric:tabular-nums;line-height:1}
.obc-num.up i{color:#4fc98a}
.obc-num.dn i{color:#ec6f5e}

.obc-calc{width:100%;max-width:820px;padding-top:10px;
  border-top:1px solid rgba(255,255,255,.07);
  font-size:12px;line-height:1.6;color:#767ea8}
.obc-calc em{font-style:normal;color:#c9d2e8}
@keyframes obgRise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}

/* ── Волна прогона ── */
.obg-wave{position:relative;width:100%;min-height:300px;isolation:isolate}
.obg-wave svg{position:relative;z-index:1;display:block;width:100%;height:auto;
  max-height:34vh}
/* Призрачное число — нижний слой: лента и сетка идут поверх и режут его. */
/* ── Частокол: точки событий и шкала времени ──
   Волна кончается СЕГОДНЯ — вертикалью. Всё, что правее, ещё не
   случилось, и линии там нет: сплошная линия вперёд читалась бы как
   знание. Там стоят только сроки.

   Цвет точки — по источнику, а не по тяжести: делистинг красный,
   разлок синеватый, событие календаря янтарный, наблюдение зелёное.
   Тяжесть скажет подсказка, а цвет должен отвечать «откуда это». */
.obg-pins{position:absolute;inset:0;z-index:4;pointer-events:none}
.obg-pin{position:absolute;width:13px;height:13px;
  transform:translate(-50%,-50%);pointer-events:auto;
  animation:obgPinIn 1.1s cubic-bezier(.2,.8,.3,1) both;
  animation-delay:calc(1.2s + var(--pd,0) * .34s)}
@keyframes obgPinIn{from{opacity:0;transform:translate(-50%,-50%) scale(.3)}
  to{opacity:1;transform:translate(-50%,-50%) scale(1)}}
.obg-pin i{position:absolute;inset:0;border-radius:50%;
  border:1.5px solid var(--pc);background:#1b1f3a;
  box-shadow:0 0 12px var(--pg);transition:transform .25s ease}
.obg-pin:hover i{transform:scale(1.45)}
/* Стойка вниз — чтобы точку можно было отнести к сроку на шкале.
   Гаснет, не доходя: доведи её до шкалы, и кадр расчертится в клетку. */
.obg-pin s{position:absolute;left:50%;top:11px;width:1px;
  height:var(--ph,46px);text-decoration:none;
  background:linear-gradient(180deg,var(--pc),transparent);opacity:.5}
/* Текст подсказки лежит в точке, но НЕ показывается из неё: точки
   стоят друг над другом ярусами, и всплывающая подсказка накрывала
   соседей — до нижних было не добраться. Здесь только хранилище. */
.obg-pin u{display:none}

/* Показывается подсказка в ОДНОМ постоянном месте — в свободном поле
   под частоколом, правее «сегодня». Там ничего нет по построению:
   линия кончается сегодня, а точки висят выше. Постоянное место ещё и
   удобнее: глаз не ищет, куда выскочило, он уже знает куда смотреть. */
.obg-tip{position:absolute;z-index:8;top:54%;width:33%;
  padding:12px 14px;border-radius:6px;pointer-events:none;
  background:rgba(20,24,48,.94);border:1px solid rgba(150,190,225,.18);
  box-shadow:0 18px 44px rgba(8,10,24,.8);
  font-size:10.5px;line-height:1.55;color:#a9bccb;text-align:left;
  opacity:0;transform:translateY(6px);
  transition:opacity .28s ease,transform .28s ease}
.obg-tip.obg-on{opacity:1;transform:none}
.obg-tip b{display:block;font-size:8px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--pc,#8b93c4);margin-bottom:5px}
.obg-tip em{font-style:normal;color:#e8ecfb}

.obg-now{position:absolute;z-index:2;top:8%;bottom:0;width:1px;
  background:linear-gradient(180deg,transparent,rgba(255,210,172,.38) 16%,
    rgba(255,210,172,.38) 88%,transparent);pointer-events:none;
  animation:obgFade 1.4s ease .6s both}

.obg-axis{position:relative;width:100%;height:34px;flex:0 0 auto;
  margin-top:-16px;border-top:1px solid rgba(255,255,255,.06);
  animation:obgFade 1.6s ease .5s both}
.obg-tick{position:absolute;top:0;transform:translateX(-50%);text-align:center}
.obg-tick s{display:block;width:1px;height:5px;margin:0 auto;
  text-decoration:none;background:rgba(255,255,255,.13)}
.obg-tick b{display:block;margin-top:6px;font-size:8.5px;letter-spacing:.16em;
  color:#6b7391;font-weight:400;white-space:nowrap}
.obg-tick.obg-tnow s{height:9px;background:rgba(255,210,172,.7)}
.obg-tick.obg-tnow b{color:#ffd2ac;letter-spacing:.2em}

.obg-ghost{position:absolute;z-index:0;left:50%;top:62%;
  transform:translate(-50%,-50%);font-size:230px;font-weight:700;
  letter-spacing:-.05em;line-height:1;color:rgba(255,255,255,.055);
  pointer-events:none;user-select:none;
  text-shadow:0 0 60px rgba(255,255,255,.04)}

/* ── Ядро и спутники ── */
.obg-hero{display:flex;align-items:center;justify-content:center;gap:56px;
  width:100%;flex-wrap:wrap;min-height:288px}
#obgHero{width:100%;display:flex;flex-direction:column;align-items:center;
  gap:30px;min-height:456px;justify-content:flex-start}
/* Высоты и ширины ЗАКРЕПЛЕНЫ: подписи групп разной длины, и без этого
   при переключении прыгал весь экран. */
/* Ядро — показание, не кнопка: ни указателя, ни отклика на наведение.
   Внутренний слой держит переменные цвета группы. */
.obg-core{position:relative;min-height:284px;width:300px}
.obg-core-in{display:flex;flex-direction:column;align-items:center;gap:18px}
.obg-ring{position:relative;width:196px;height:196px;display:grid;
  place-items:center}
.obg-ring svg{position:absolute;inset:0;width:100%;height:100%}
.obg-disc{position:absolute;inset:26px;border-radius:50%;
  background:
    radial-gradient(circle at 50% 32%,rgba(255,255,255,.14) 0%,transparent 40%),
    radial-gradient(circle at 50% 60%,rgba(var(--rgb),.24) 0%,rgba(38,43,80,.6) 66%);
  box-shadow:inset 0 2px 2px rgba(255,255,255,.16),
             inset 0 -18px 34px -18px rgba(10,12,26,.9),
             0 0 44px rgba(var(--rgb),.28)}
.obg-num{position:relative;z-index:2;font-size:51px;font-weight:200;
  letter-spacing:-.04em;color:#fff;text-shadow:0 0 30px rgba(var(--rgb),.75)}
/* Строка списка — единственная дверь в карточку монеты, поэтому
   отклик на наведение остался только у неё. */
.obg-mark{display:flex;align-items:center;gap:14px}
.obg-mark i{display:block;width:46px;height:1px;position:relative;
  background:linear-gradient(90deg,transparent,rgba(var(--rgb),.55))}
.obg-mark i:last-child{background:linear-gradient(90deg,rgba(var(--rgb),.55),transparent)}
.obg-mark i::after{content:"";position:absolute;top:-2px;width:1px;height:5px;
  background:rgba(var(--rgb),.7)}
.obg-mark i:first-child::after{right:0}
.obg-mark i:last-child::after{left:0}
.obg-cap{font-size:12px;letter-spacing:.52em;text-transform:uppercase;
  font-weight:600;color:var(--c);text-indent:.52em;
  text-shadow:0 0 22px rgba(var(--rgb),.55),0 0 46px rgba(var(--rgb),.25)}
.obg-sub{margin-top:9px;font-size:8px;letter-spacing:.22em;text-transform:uppercase;
  color:#6c74a6;font-weight:500}
.obg-sub b{color:#98a0cc;font-weight:600}

.obg-side{display:flex;flex-direction:column;gap:12px;width:236px}
/* Выбранная группа на десктопе не дублируется: её называет ядро.
   Кнопка при этом существует — она нужна узким экранам. */
.obg-sat.obg-cur{display:none}
.obg-sat{display:flex;align-items:center;gap:14px;width:236px;
  background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);
  padding:8px 18px 8px 8px;border-radius:999px;cursor:pointer;font:inherit;
  transition:background .6s,transform .6s,border-color .6s}
.obg-sat:hover{background:rgba(255,255,255,.05);
  border-color:rgba(var(--rgb),.35);transform:translateX(3px)}
.obg-pill{flex:0 0 auto;width:54px;height:54px;border-radius:50%;display:grid;
  place-items:center;font-size:18px;font-weight:300;color:var(--c);
  background:
    linear-gradient(180deg,rgba(255,255,255,.08),transparent 34%),
    radial-gradient(circle at 50% 118%,rgba(var(--rgb),.2),rgba(30,34,64,.5) 74%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.16),
             0 0 0 1px rgba(var(--rgb),.3),0 0 20px rgba(var(--rgb),.14)}
.obg-sat .obg-scap{flex:1;text-align:left;font-size:10px;letter-spacing:.28em;
  text-transform:uppercase;color:var(--c);opacity:.8;font-weight:500}
.obg-sat.obg-zero{opacity:.45}

/* ── Подсказка и панель чисел ── */
.obg-hint{margin:0;text-align:center;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:9px;min-height:74px}
.obg-say{font-size:22px;font-weight:200;letter-spacing:-.01em;color:#e8ecfb}
.obg-say b{font-weight:400;color:#4fc98a;text-shadow:0 0 26px rgba(79,201,138,.6)}
.obg-tail{position:relative;font-size:10px;letter-spacing:.12em;
  text-transform:lowercase;color:#8f97c6;padding-top:11px}
.obg-tail::before{content:"";position:absolute;top:0;left:50%;
  transform:translateX(-50%);width:54px;height:1px;
  background:linear-gradient(90deg,transparent,rgba(143,151,198,.5),transparent)}
.obg-panel{display:flex;border-radius:16px;overflow:hidden;
  background:linear-gradient(180deg,rgba(63,70,124,.5),rgba(38,43,80,.5));
  border:1px solid rgba(255,255,255,.06);
  box-shadow:0 24px 50px -30px rgba(8,10,24,.9)}
.obg-panel div{position:relative;padding:10px 20px;text-align:center;
  border-right:1px solid rgba(255,255,255,.05);transition:background .6s}
.obg-panel div:last-child{border-right:0}
.obg-panel div:hover{background:rgba(255,255,255,.03)}
.obg-panel div.obg-up::before{content:"";position:absolute;top:0;left:26%;right:26%;
  height:1px;opacity:.6;
  background:linear-gradient(90deg,transparent,#4fc98a,transparent)}
.obg-panel span{display:block;font-size:5.8px;letter-spacing:.28em;
  text-transform:uppercase;color:#6c74a6;font-weight:600}
.obg-panel b{display:block;margin-top:5px;font-size:12.8px;font-weight:200;
  letter-spacing:-.02em;color:#eef1fb;font-variant-numeric:tabular-nums}
.obg-panel b i{font-style:normal;font-size:8.2px;font-weight:400;margin-left:7px;
  color:#4fc98a}
.obg-panel b.obg-up{color:#4fc98a;text-shadow:0 0 20px rgba(79,201,138,.35)}

/* ── Зал колонкой ─────────────────────────────────────────────
   Высота колонки постоянна, список внутри тянется, место под полосу
   прокрутки зарезервировано: иначе при переходе к пустой группе блок
   схлопывался и весь экран дёргался. */
/* Ширина вдвое меньше прежних трёхсот девяноста двух. В строке одна
   точка и одно имя — остальное было воздухом, а воздух в колонке
   отнимает его у центра, где стоит карточка монеты. */
.obr{width:196px;flex:0 0 auto;height:100%;display:flex;flex-direction:column;
  gap:10px;padding:66px 0 18px}
.obr-head{display:flex;align-items:baseline;justify-content:space-between;
  padding:0 4px 10px;border-bottom:1px solid rgba(255,255,255,.07);
  animation:obgFade 1.2s ease both}
.obr-head b{font-size:11px;letter-spacing:.34em;text-transform:uppercase;
  font-weight:600;color:var(--c)}
.obr-head span{font-size:9px;letter-spacing:.2em;text-transform:uppercase;
  color:#6c74a6}
/* Поиск по списку. Фильтрует УЖЕ отрисованные строки, а не
   перерисовывает список: перерисовка на каждой букве заново
   проигрывала бы отрисовку линий и мигала. */
.obr-find{position:relative;flex:0 0 auto}
.obr-find input{width:100%;padding:8px 30px 8px 30px;border-radius:9px;
  background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);
  color:#e8ecfb;font:inherit;font-size:11px;letter-spacing:.08em;
  outline:none;transition:border-color .3s,background .3s}
.obr-find input::placeholder{color:#6c74a6;letter-spacing:.16em;
  text-transform:uppercase;font-size:9.5px}
.obr-find input:focus{border-color:rgba(255,255,255,.2);
  background:rgba(255,255,255,.055)}
.obr-find .obr-mag{position:absolute;left:11px;top:50%;width:9px;height:9px;
  margin-top:-6px;border:1.4px solid #6c74a6;border-radius:50%;
  pointer-events:none}
.obr-find .obr-mag::after{content:"";position:absolute;right:-4px;bottom:-3px;
  width:5px;height:1.4px;background:#6c74a6;transform:rotate(45deg)}
.obr-find .obr-clr{position:absolute;right:8px;top:50%;transform:translateY(-50%);
  width:18px;height:18px;border:0;border-radius:50%;cursor:pointer;
  background:rgba(255,255,255,.06);color:#98a0cc;font:inherit;font-size:11px;
  line-height:1;display:none}
.obr-find.obr-has .obr-clr{display:block}
.obr-row.obr-hide{display:none}

/* ── Подпись группы ──
   Без неё порядок был бы невидим: читатель решил бы, что список
   перемешан. Подпись говорит, ПОЧЕМУ монета здесь. */
.obr-grp{display:flex;align-items:center;gap:9px;padding:15px 4px 7px;
  font-size:7.6px;letter-spacing:.24em;text-transform:uppercase;
  color:#575e82;animation:obgFade 1.2s ease both}
.obr-grp:first-child{padding-top:0}
.obr-grp s{flex:1;height:1px;background:rgba(255,255,255,.07);
  text-decoration:none}
.obr-grp.obr-hide{display:none}
/* Метка делистинга. Янтарь — предупреждение биржи, красный — решение
   принято. Мигание только у срочного: если мигает всё, не мигает
   ничего. */
/* Минимально читаемый размер: шесть с половиной пунктов, разрядка
   узкая, рамка в полпикселя. Метка обязана быть заметна и не обязана
   спорить с именем — она приписка, а не второе название. */
.obr-row > div{display:flex;align-items:center;gap:9px;min-width:0}
.obr-dl{display:inline-block;margin-left:0;padding:0 4px;border-radius:3px;
  font-size:6.5px;letter-spacing:.1em;text-transform:uppercase;vertical-align:2px;
  line-height:1.6;
  border:1px solid rgba(255,178,102,.5);color:#ffb266;background:rgba(255,178,102,.09)}
.obr-dl-w{border-color:rgba(255,214,120,.42);color:#ffd678;
  background:rgba(255,214,120,.07)}
.obr-dl-x{border-color:rgba(255,110,110,.62);color:#ff7d7d;
  background:rgba(255,110,110,.13);animation:obrDl 1.9s ease-in-out infinite}
@keyframes obrDl{0%,100%{opacity:1}50%{opacity:.45}}
.obr-none{padding:22px 6px;text-align:center;font-size:10.5px;
  letter-spacing:.14em;color:#6c74a6;display:none}
.obr-none.obr-on{display:block}

.obr-list{flex:1;min-height:0;display:flex;flex-direction:column;gap:5px;
  overflow-y:auto;padding-right:4px;scrollbar-gutter:stable;
  scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.12) transparent}
.obr-list::-webkit-scrollbar{width:5px}
.obr-list::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);
  border-radius:3px}
.obr-empty{flex:1;min-height:0;display:grid;place-items:center;text-align:center;
  font-size:11px;letter-spacing:.14em;color:#6c74a6;
  animation:obgFade 1.2s ease both}

/* ── Строка монеты ──
   Карточка убрана. Она занимала всю ширину колонки под два слова и
   строила из списка стопку плашек: много места, мало сказанного.
   Осталась волосяная линия снизу — она разделяет, ничего не огораживая.

   Набор антиквой: на тёмном фоне засечки дают воздух, которого у
   гротеска нет, и список читается оглавлением, а не таблицей. */
.obr-row{position:relative;display:flex;align-items:center;
  gap:8px;padding:8px 2px 7px;cursor:pointer;
  border-bottom:1px solid rgba(255,255,255,.05);
  transition:border-color .42s ease;
  animation:obrRowIn 1.26s cubic-bezier(.2,.75,.3,1) both}
/* Наведение красит саму линию и добавляет имени света СВОИМ цветом.
   Выбеливать имя нельзя: белое оно теряет стратегию, а она теперь
   только в цвете. Геометрия не двигается — строка обязана остаться
   под курсором. */
.obr-row:hover{border-color:rgba(var(--rgb) / .55)}
.obr-row:hover .obr-tk{color:#fff}
.obr-row:hover .obr-dot{box-shadow:0 0 16px rgba(var(--rgb) / 1)}
/* цвет стратегии — полоса слева */

/* Слово стратегии из строки убрано, и цвет перешёл на САМО ИМЯ —
   иначе стратегию нести стало бы нечем. Имя остаётся единственным
   текстом строки и говорит две вещи разом: что за монета и что она
   такое.

   Кегль на треть меньше прежнего: двадцать один пункт был крупен для
   строки, из которой ушла вторая половина.

   Цифры принудительно прописные: у антиквы они по умолчанию
   старостильные, и 1000LUNC получал болтающиеся нули вразнобой. */
.obr-tk{font-family:Georgia,"Iowan Old Style","Times New Roman",serif;
  font-size:15px;font-weight:400;letter-spacing:.015em;line-height:1.1;
  color:#e2e8f6;text-decoration:none;cursor:pointer;
  font-feature-settings:"lnum" 1;font-variant-numeric:lining-nums;
  transition:color .3s ease}

/* ── Цвет стратегии несёт ТОЧКА ──
   Наследница прежней полоски: цвет вынесен из слова и стоит столбцом,
   по которому список ведут взглядом сверху вниз, не читая имён. Имена
   при этом все одного света, и тусклые стратегии не проваливаются.

   Первая буква вынесена в разметке отдельно, но не красится: пробовали
   красить её — красиво в отдельной строке и рассыпается в столбце из
   полусотни. Разметку оставил на случай возврата, цвета там нет. */
.obr-tk b{font-weight:400;color:inherit}
.obr-dot{flex:0 0 auto;width:6px;height:6px;border-radius:50%;
  background:var(--c);box-shadow:0 0 9px rgba(var(--rgb) / .75);
  transition:box-shadow .3s ease}
.obr-tk:hover{color:var(--c);text-decoration:underline;
  text-underline-offset:3px;text-decoration-thickness:1px}
.obr-tk:focus-visible{outline:1px solid var(--c);outline-offset:3px;
  border-radius:3px}
/* Стратегия ушла из-под тикера вправо: место освободилось, а строка
   теперь читается в одну линию — что за монета и что она такое. */
/* Стратегия курсивом той же антиквы и её цветом. Капса нет намеренно:
   он спорит с засечками и тянет на себя больше внимания, чем имя. */

.obr-row:hover .obr-cs{opacity:1}
.obr-row svg{display:block;width:100%;height:34px}
.obr-pnl{text-align:right;font-size:13px;font-weight:300;
  font-variant-numeric:tabular-nums}
.obr-pnl.obg-up{color:#4fc98a} .obr-pnl.obg-dn{color:#ec6f5e}
.obr-pnl em{display:block;font-style:normal;margin-top:2px;font-size:7.4px;
  letter-spacing:.16em;text-transform:uppercase;color:#6c74a6}

/* ── Движение ─────────────────────────────────────────────────
   Отрисовка нарочно медленная: сначала проступает сетка, по ней
   рисуется линия, СЛЕДОМ наливается тело. Тело показывалось сразу —
   и волна выглядела готовой, сколько бы линия ни рисовалась. */
@keyframes obgFade{from{opacity:0}to{opacity:1}}
@keyframes obgTextIn{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
@keyframes obrRowIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
@keyframes obrDraw{to{stroke-dashoffset:0}}
@keyframes obgWaveDraw{to{stroke-dashoffset:0}}
@keyframes obgSpin{to{transform:rotate(360deg)}}
/* Вступление играет ТОЛЬКО на входе в зал — отсюда класс.
   Раньше правило висело без него, и при каждой смене группы ряд
   собирался заново и проигрывал появление сызнова: вся связка «ядро
   плюс кнопки» дёргалась вниз и проявлялась. Это и был рывок до
   переезда; после переезда кнопки из ряда вынуты, потому там и чисто. */
#obgHero.obg-enter .obg-hero{animation:obgTextIn 1.32s cubic-bezier(.2,.75,.3,1) both}
#obgHero.obg-enter .obg-hint{animation:obgTextIn 1.32s cubic-bezier(.2,.75,.3,1) both .27s}
#obgHero.obg-enter .obg-panel{animation:obgTextIn 1.32s cubic-bezier(.2,.75,.3,1) both .48s}

/* Смена группы — не вход. Ядро меняет число, цвет и подпись разом, и
   без единой мягкой подсветки эта подмена читается щелчком. Поэтому
   ему одному дана короткая проявка, БЕЗ сдвига: двигаться ему некуда,
   оно стоит на месте. Правило нарочно выше правил гашения — иначе оно
   вернуло бы ядро на экран после переезда. */
@keyframes obgSoftIn{from{opacity:0}to{opacity:1}}
#obgHero.obg-swap .obg-core,
#obgHero.obg-swap .obg-hint,
#obgHero.obg-swap .obg-panel{animation:obgSoftIn 2.2s ease both}

/* ── Смена группы: сначала гаснет старое ──
   Раньше содержимое подменялось в одном кадре: старое исчезало ровно
   тогда, когда появлялось новое, и это читалось щелчком.

   Гасим АНИМАЦИЕЙ, а не переходом прозрачности. Причина техническая:
   у всего здесь есть вступительная анимация с удержанием конечного
   кадра, и она продолжает диктовать прозрачность даже после того, как
   отыграла. Перекрыть её может только другая анимация.

   Правило стоит ПОСЛЕ проявки и ДО правил переезда: вес у них
   одинаковый, решает очерёдность. Иначе после переезда погашенное
   ядро на миг проступило бы. */
/* Имя obg-out НЕ брать: оно занято кнопкой «закрыть», а та абсолютная.
   Повесив его на центральный блок, я выдернул его из потока — сцена
   схлопывалась в комок ровно на время гашения. */
@keyframes obgSoftOut{from{opacity:1}to{opacity:0}}
#obgHero.obg-swapout .obg-core,
#obgHero.obg-swapout .obg-hint,
#obgHero.obg-swapout .obg-panel{animation:obgSoftOut .88s ease both}

/* Волна и призрачное число живут ВНЕ центрального блока, поэтому у них
   своя метка — на общем контейнере сцены. Без неё число подменялось
   в одном кадре: остальное плавно уходило, а оно щёлкало.
   Гаснут они вместе с центром, тем же сроком.
   Проявление у числа своё: волна приходит собственной отрисовкой. */
#obgInner.obg-swapout .obg-wave{animation:obgSoftOut .88s ease both}

/* ── Нажатая кнопка уходит, а не пропадает ──
   Она становится выбранной группой, а выбранная из ряда прячется — и
   пряталась разом, в кадр пересборки. Гасим её ЗАРАНЕЕ, с самого
   клика, ровно за то же время, что идёт до пересборки: к моменту,
   когда её уберут из разметки, она уже невидима. Место при этом
   держит до конца, поэтому соседи не дёргаются раньше времени —
   они сомкнутся переездом, когда ряд соберётся заново. */
@keyframes obgSatOut{from{opacity:1;transform:none}
  to{opacity:0;transform:scale(.86)}}
.obg-side .obg-sat.obg-sat-out{animation:obgSatOut .88s ease both;
  pointer-events:none}
#obgInner.obg-swap .obg-ghost{animation:obgSoftIn 2.2s ease both}

/* ── Нижний блок гаснет через десять секунд ──
   Подсказка и деньги отвечают на вопрос «как дела у журнала целиком».
   Ответ нужен на входе и один раз; дальше он только занимает низ кадра.

   Гаснет ОПАЦИТИ, а не выносится из потока: у сцены вертикальное
   центрирование, и убери мы блок совсем — всё остальное подскочило бы
   вверх на его высоту. Пустое место внизу дешевле прыжка.

   Уходит подсказка, следом деньги: тем же порядком, каким читались. */
@keyframes obgTextOut{from{opacity:1;transform:none}
  to{opacity:0;transform:translateY(9px)}}
#obgHero.obg-faded .obg-hint{animation:obgTextOut 1.6s ease both;
  pointer-events:none}
#obgHero.obg-faded .obg-panel{animation:obgTextOut 1.6s ease both .2s;
  pointer-events:none}
/* Ядро уходит вместе с ними: открытая группа названа в шапке списка,
   и держать её ещё и кольцом в центре — повтор. Место остаётся
   занятым по той же причине, что и у блока ниже. */
#obgHero.obg-faded .obg-core{animation:obgTextOut 1.6s ease both;
  pointer-events:none}
/* Погашенное состояние держится отдельным классом: без него смена
   группы перерисовала бы блок и вернула его во весь свет. */
#obgHero.obg-gone .obg-hint,#obgHero.obg-gone .obg-panel,
#obgHero.obg-gone .obg-core{animation:none;opacity:0;pointer-events:none}

/* ── Вкладки над списком ──
   Те же кнопки, что стояли в центре: они не создаются заново, а
   переезжают — подмену копией глаз читает как мигание.
   Пока не переехали, место пустое и спрятано: иначе колонка
   начиналась бы с зазора в десять пикселей. */
/* Место под вкладки держится с самого начала, пустым. Иначе в момент
   прилёта колонка получала бы новую строку разом — шапка, поиск и
   список ныряли бы вниз ступенькой, пока кнопки ещё в полёте.
   Высота равна росту вкладки: кружок 32 плюс отступы 5 и рамка. */
.obr-tabs{flex:0 0 auto;min-height:40px}

/* Слой всего меняющегося. Гасим не его целиком, а перечисленных детей —
   ПОИМЁННО. Причина: поле поиска у всех групп одинаковое, и мигать ему
   не с чего. Погаси мы слой, оно уходило бы вместе со всеми, а потом
   возвращалось разом — оно единственное здесь без проявления, и этот
   рывок и было видно перед плавным приходом остального.

   Правило то же, что у вкладок: что не меняется, то не анимируем. */
.obr-body{flex:1;min-height:0;display:flex;flex-direction:column;gap:10px}
/* Гашение анимацией, а не прозрачностью: у шапки своя вступительная
   анимация с удержанием кадра, перекрыть её может только анимация. */
.obr-body.obr-out .obr-head,
.obr-body.obr-out .obr-list,
.obr-body.obr-out .obr-empty{animation:obgSoftOut .44s ease both}
.obg-side.obg-tucked{flex-direction:row;width:auto;gap:7px}
/* Счёт НАД подписью, а не рядом. В строку они не влезают: на вкладку
   в узкой колонке приходится шестьдесят с небольшим пикселей, из них
   число забирает половину, и «выходить» обрезалось. Столбиком каждому
   достаётся вся ширина, и подпись читается целиком.
   Заодно это повторяет устройство центра: число, под ним имя группы. */
.obg-side.obg-tucked .obg-sat{width:auto;flex:1 1 0;min-width:0;
  flex-direction:column;align-items:center;gap:1px;padding:4px 3px}
/* Кружок счёта в переехавшем ряду — просто число. Коробка в тридцать
   два пикселя под ним осталась от вида с диском, а диска здесь нет: в
   узкой колонке она съедала половину вкладки, и подпись обрезалась. */
.obg-side.obg-tucked .obg-pill{width:auto;height:auto;font-size:13px;
  line-height:1.2}
.obg-side.obg-tucked .obg-scap{flex:0 0 auto;font-size:7px;
  letter-spacing:.08em;white-space:nowrap;text-align:center}
.obg-wave .obg-wv{stroke-dasharray:2600;stroke-dashoffset:2600;
  animation:obgWaveDraw 5.7s cubic-bezier(.3,.75,.35,1) .45s both}
/* Отрисовка при наведении. Была вчетверо короче входной — и от этого
   читалась мельканием: линия успевала лечь раньше, чем глаз находил
   её начало. Сейчас медленнее входной: смотреть на монету можно
   столько, сколько нужно, а торопиться некуда. */
.obg-wave.obg-quick .obg-wv{animation-duration:25.2s;animation-delay:.9s}
.obg-wave.obg-quick .obg-mesh{animation-duration:16.2s;animation-delay:.9s}
.obg-wave.obg-quick .obg-body{animation-duration:14.4s;animation-delay:7.2s}
.obg-wave.obg-quick .obg-head{animation-duration:7.2s;animation-delay:24.3s}
.obg-wave.obg-quick .obg-node{animation-duration:9s;animation-delay:18s}
.obg-wave .obg-mesh{animation:obgFade 3.6s ease .3s both}
/* Тело волны — два размытия по 16 пикселей. Просим отдельный слой:
   иначе движок пересчитывает их вместе с каждым кадром линии. */
.obg-wave .obg-body{animation:obgFade 3.2s ease 1.6s both;
  will-change:opacity;transform:translateZ(0)}
.obg-wave .obg-head{animation:obgFade 1.5s ease 5.6s both}
.obg-wave .obg-node{animation:obgFade 1.8s ease 4.2s both}
.obr-row svg .obr-ln{stroke-dasharray:420;stroke-dashoffset:420;
  animation:obrDraw 2.4s cubic-bezier(.25,.8,.3,1) both}
.obr-row svg .obr-mk,.obr-row svg .obr-lvl{animation:obgFade 1.5s ease both}
.obg-spin{transform-origin:50% 50%;animation:obgSpin 78s linear infinite}
.obg-spin.obg-rev{animation:obgSpin 102s linear infinite reverse}

/* Пока ворота открыты, верхний ряд групп и «заново» молчат. */
.ob-podium.obp-gated .obp-groups,
.ob-podium.obp-gated .obp-hint,
.ob-podium.obp-gated .obp-again{opacity:0;pointer-events:none}
.obp-again{right:auto;left:26px;color:#8a6a3f;
  border-color:rgba(232,165,85,.22);background:rgba(14,11,8,.6)}
.obp-again:hover{color:#ffcb7d;border-color:rgba(232,165,85,.45);
  background:rgba(28,20,12,.85)}

/* ═══════════════════════════════════════════════════════════════
   ПЛАНШЕТ И ТЕЛЕФОН · отдельная раскладка, а не сжатый десктоп

   Что было не так. Сцена вставала над списком со своими жёсткими
   минимумами (волна 300, ядро со спутниками 456, подсказка 74 —
   больше 800px в сумме). Она съедала почти весь экран, призрачное
   число уезжало за верхний край, а списку оставалась полоска в
   две-три строки ниже сгиба.

   Что сделано. Сцена превращается в ГОРИЗОНТ: волна сжимается в
   ленту во всю ширину, по которой едет счёт выбранной группы.
   Ядро с кольцами и призрачное число уходят совсем — их работу
   берут на себя вкладки: четыре кнопки, в каждой свой счёт.
   Панель из четырёх плиток становится одной строкой. Всё, что
   осталось по высоте, забирает список и прокручивается сам.
   ═══════════════════════════════════════════════════════════════ */
/* ── ПЛАНШЕТ ВШИРЬ: раскладка как на компьютере, только уже ──
   От 900 до 1180 сцена и список стоят рядом, как на большом экране:
   волна во всю ширину сцены, под ней ядро с группами и деньги, справа
   список. Раньше эта полоса попадала в узкую ветку, и на планшете
   поперёк список занимал весь экран, а волна сжималась в ленту в
   пятьдесят шесть пикселей — читать было нечего.
   Уже, чем на компьютере: сцена ужимается, список сто семьдесят,
   отступы меньше; частокол и карточка монеты остаются на месте. */
/* Блок «возврат к десктопной раскладке» (900–1180) ВЫРЕЗАН 29.08.
   Он был написан против копии узкой ветки в render_css.py, которой
   там нет (проверено 26.08): стили зала живут одним экземпляром в
   этом файле. Дубль перебивал тип-селекторами любые новые классы
   карточки — на этом ловились пилюли свода. Если планшет 900–1180
   когда-нибудь поедет — искать настоящую вторую копию, а не
   возвращать этот блок. */

@media (max-width:900px){
  .obp-gate{padding:0;align-items:stretch;justify-content:flex-start}
  .obg-stage{flex-direction:column;gap:0;height:100%;width:100%;
    align-items:stretch;justify-content:flex-start}

  /* Сцена — не блок с содержимым, а система координат для горизонта.
     Высота её частей задаётся здесь и только здесь. */
  .obg-inner{position:relative;flex:0 0 auto;gap:0;animation:none}

  /* ── Горизонт ──
     Была лента в пятьдесят шесть пикселей: волна не читалась вовсе, а
     список занимал весь экран. Теперь график держит четверть высоты
     окна (но не меньше ста сорока и не больше двухсот двадцати) —
     столько же, сколько на компьютере занимает верх сцены. */
  .obg-wave{position:relative;height:clamp(140px,26vh,220px);min-height:0;overflow:hidden}
  .obg-wave svg{position:absolute;inset:0;width:100%;height:100%;
    max-height:none}
  .obg-ghost{display:none}          /* именно оно уезжало за край */

  /* Счёт едет ПО горизонту: ядро вынимается из потока и ложится
     на ленту. От него остаются число и название группы. */
  #obgHero{position:static;min-height:0;gap:0}
  .obg-hero{position:static;min-height:0;gap:0;display:block}
  /* Счёт группы стоит В УГЛУ волны, но волна теперь высокая — если
     тянуть ядро на всю её высоту, число повисает посреди графика.
     Даём ему полосу в сорок четыре пикселя сверху. */
  .obg-core{position:absolute;left:0;top:0;z-index:4;
    width:auto;min-height:0;height:44px;
    display:flex;align-items:center;padding:0 0 0 16px}
  .obg-core-in{display:flex;align-items:baseline;gap:9px}
  .obg-ring{width:auto;height:auto;position:static;display:contents}
  .obg-ring svg,.obg-disc,.obg-sub{display:none}
  .obg-num{position:static;font-size:26px;line-height:1}
  .obg-mark{display:flex;align-items:center;gap:0}
  .obg-mark i{display:none}
  .obg-cap{font-size:9px;letter-spacing:.28em}

  /* ── Вкладки групп ── */
  .obg-side{display:flex;flex-direction:row;gap:6px;width:auto;
    padding:10px 12px 0}
  .obg-sat,.obg-sat.obg-cur{display:flex;flex:1 1 0;width:auto;min-width:0;
    flex-direction:column;align-items:center;gap:2px;
    padding:7px 4px 8px;border-radius:10px;
    background:rgba(255,255,255,.025);border:1px solid transparent}
  .obg-sat.obg-cur{background:rgba(255,255,255,.075);
    border-color:rgba(255,255,255,.14)}
  .obg-pill{width:auto;height:auto;border:0;background:none;
    font-size:17px;font-weight:200;line-height:1.1;color:var(--c)}
  /* Селектор ДВУМЯ классами, как в базовом правиле. Одним он весит
     меньше и не срабатывал вовсе: подпись всё это время стояла по
     базовому левому краю, а число слипалось с ней — «56HOLD». */
  .obg-sat .obg-scap{font-size:7.5px;letter-spacing:.2em;text-align:center;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
  .obg-sat.obg-zero{opacity:.42}
  .obg-sat.obg-zero.obg-cur{opacity:.8}

  /* Подсказка молчит: на узком экране каждая строка — это строка
     списка, которой не хватило. */
  .obg-hint{display:none}

  /* ── КАРТОЧКА МОНЕТЫ ЖИВЁТ И ЗДЕСЬ ──
     Раньше её прятали: она вставала на место ядра, а ядра в узкой
     раскладке нет. Но именно в ней весь текст прогона — фигура, довод,
     цена, — и без неё экран превращался в один список. Теперь карточка
     стоит в потоке между волной и списком: клик по строке открывает
     её здесь же, второй клик по той же строке — закрывает. */
  /* ВЫСОТУ ДЕЛЯТ ТРОЕ: волна, карточка, список — и все внутри окна.
     Раньше карточка росла по содержимому, и список уезжал за нижний
     край: на телефоне от него оставалась одна строка. Теперь карточка
     занимает не больше трети окна и прокручивается внутри себя. */
  .obg-gate{height:100%;max-height:100%;overflow:hidden}
  .obg-stage{height:100%;min-height:0}
  .obg-card{position:static;opacity:1;pointer-events:auto;
    flex:0 1 auto;min-height:0;padding:10px 14px 2px;gap:8px;
    max-height:32vh;overflow-y:auto;-webkit-overflow-scrolling:touch}
  .obg-card:empty{display:none}
  /* Цена и капитализация в карточке набраны огромными: на компьютере
     они занимают освободившийся центр, на телефоне — пол-экрана. */
  .obg-card .obc-nums{gap:18px}
  .obg-card .obc-nums b{font-size:22px}

  /* ── Частокол на узких экранах не живёт ──
     Волна здесь сжата в полосу в пятьдесят шесть пикселей. Частоколу
     нужна высота: точки стоят ярусами и держат стойки вниз, а шкала
     подписывает три недели вперёд. В полосе они не помещаются — метки
     вылезали поверх вкладок, а шкала налезала на саму волну.

     Карточка монеты по той же причине: она встаёт на место ядра, а
     ядра здесь нет. И наведения на касании тоже нет — вместо него
     работает клик по строке, он открывает карточку целиком. */
  .obg-axis,.obg-pins,.obg-now,.obg-tip{display:none}

  /* Место под вкладки не резервируем: переезжать им некуда, ряд и так
     стоит вверху своей раскладкой. Сорок четыре пикселя пустоты на
     телефоне — это полторы строки списка. */
  .obr-tabs{min-height:0;display:none}

  /* ── Деньги гаснут ВЕЗДЕ (владелец перерешал 29.08) ──
     Прежнее «не гаснут на узких» защищало от 88px пустоты после
     гашения. Теперь obgBlockOut схлопывает высоту в ноль вместе с
     прозрачностью — пустоты нет, и блок живёт свои десять секунд
     на любой ширине одинаково. */

  /* Подпись вкладки прижимается вправо. */
  .obg-sat .obg-scap{text-align:right}

  /* ── Панель денег во всю ширину ──
     Сцена центрирует детей, и панель вставала по своему содержимому:
     сто сорок шесть пикселей посреди пустой строки. Растягиваем. */
  .obg-panel{align-self:stretch}

  /* ── Запас под кнопки ──
     «Закрыть» лежит поверх списка у нижнего края, и последняя строка
     пряталась под ней. Пятьдесят два пикселя — высота кнопки с полями. */
  .obr-list{padding-bottom:52px}

  /* ── Сводка одной строкой ── */
  .obg-panel{display:flex;margin:10px 12px 0;border-radius:0;
    background:none;border-top:1px solid rgba(255,255,255,.07);
    border-bottom:1px solid rgba(255,255,255,.07);flex-wrap:nowrap}
  .obg-panel > div{flex:1 1 0;min-width:0;padding:7px 4px;text-align:center;
    border-right:1px solid rgba(255,255,255,.07);border-left:0}
  .obg-panel > div:last-child{border-right:0}
  .obg-panel span{font-size:6.5px;letter-spacing:.16em}
  .obg-panel b{font-size:11px;margin-top:2px}
  .obg-panel i{font-size:8px}

  /* ── Список идёт ПОД графиком и текстом, а не вместо них ──
     Он берёт остаток высоты, но не больше половины окна: сверху должны
     помещаться волна, счёт по группам, деньги и карточка монеты. Если
     монет много — прокручивается внутри себя. */
  .obr{width:100%;flex:1 1 auto;min-height:0;height:auto;max-height:none;
    padding:10px 12px 12px}
  .obr-list{max-height:none;flex:1 1 auto;min-height:0;overflow-y:auto}
  .obr-row{min-height:46px}          /* палец, а не курсор */
  .obg-out{top:auto;bottom:14px;right:14px;
    background:rgba(20,22,44,.82);backdrop-filter:blur(6px)}
}

/* Планшет лёжа: ширина вернулась — горизонт, вкладки и сводка уходят
   в левую колонку, список занимает всю правую. */
@media (max-width:900px) and (min-width:781px) and (orientation:landscape){
  .obg-stage{flex-direction:row}
  .obg-inner{flex:0 0 300px;border-right:1px solid rgba(255,255,255,.07);
    display:flex;flex-direction:column}
  .obg-wave{height:72px}
  .obg-core{height:72px}
  .obg-side{flex-direction:column;padding:12px 12px 0}
  .obg-sat,.obg-sat.obg-cur{flex-direction:row;justify-content:space-between;
    align-items:baseline;padding:8px 11px}
  /* Вправо, как в двух других раскладках: подпись растянута на всю
     оставшуюся ширину, и при выравнивании влево она встаёт вплотную к
     числу — «56HOLD». Число слева, название справа, между ними воздух. */
  .obg-sat .obg-scap{text-align:right}
  .obg-panel{flex-direction:column;margin:12px 12px 0;border:0}
  .obg-panel > div{display:flex;align-items:baseline;justify-content:space-between;
    text-align:left;border-right:0;padding:6px 2px;
    border-bottom:1px solid rgba(255,255,255,.07)}
  .obg-panel b{margin-top:0}
  .obr{flex:1 1 auto;padding:12px}
}

/* ── Телефон ──
   Четыре вкладки в ряд не помещаются: подписи «выходить» и
   «держать» слипаются. Раскладываем сеткой два на два, сводку
   тоже, и урезаем горизонт — на телефоне дорога каждая строка. */
@media (max-width:560px){
  /* На телефоне волна не лента: те же четверть высоты, что на планшете,
     но не выше ста восьмидесяти — иначе списку не остаётся места. */
  .obg-wave{height:clamp(130px,24vh,180px)}
  .obg-core{height:clamp(130px,24vh,180px);padding-left:12px;align-items:flex-start;padding-top:10px}
  .obg-num{font-size:21px}
  .obg-cap{font-size:8px;letter-spacing:.22em}
  .obg-side{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:9px 10px 0}
  .obg-sat,.obg-sat.obg-cur{flex-direction:row;justify-content:space-between;
    align-items:baseline;padding:7px 10px}
  .obg-pill{font-size:15px}
  .obg-sat .obg-scap{text-align:right;font-size:7px}
  .obg-panel{display:grid;grid-template-columns:1fr 1fr;margin:9px 10px 0;
    border:1px solid rgba(255,255,255,.07);border-radius:10px;overflow:hidden}
  .obg-panel > div{border-right:1px solid rgba(255,255,255,.07);
    border-bottom:1px solid rgba(255,255,255,.07)}
  .obg-panel > div:nth-child(2n){border-right:0}
  .obg-panel > div:nth-child(n+3){border-bottom:0}
  .obr{padding:9px 10px 10px}
  .obr-row{grid-template-columns:1fr auto;min-height:44px}
  .obr-find input{font-size:12px}   /* меньше 12px — iOS зумит поле */
}

@media (prefers-reduced-motion:reduce){
  .obg-inner,.obr-row,.obr-row svg .obr-ln,.obr-row svg .obr-mk,
  .obr-row svg .obr-lvl,.obr-head,.obr-empty,.obg-spin,
  #obgHero .obg-hero,#obgHero .obg-hint,#obgHero .obg-panel,
  .obg-wave .obg-wv,.obg-wave .obg-mesh,.obg-wave .obg-body,
  .obg-wave .obg-head,.obg-wave .obg-node{animation:none}
  .obr-row svg .obr-ln,.obg-wave .obg-wv{stroke-dashoffset:0}
  .obg-ring{transition:none}

  /* Всё, добавленное залом сегодня, слушается того же запрета.
     Причина не только в вежливости: половина новых движений идёт
     десятками секунд, и для того, кто просил не двигать экран, это
     было бы не медленно, а мучительно. Содержимое при этом остаётся
     на месте целиком — гасим движение, а не смысл. */
  #obgHero.obg-swap .obg-core,#obgHero.obg-swap .obg-hint,
  #obgHero.obg-swap .obg-panel,#obgHero.obg-swapout .obg-core,
  #obgHero.obg-swapout .obg-hint,#obgHero.obg-swapout .obg-panel,
  #obgInner.obg-swapout .obg-wave,#obgInner.obg-swap .obg-ghost,
  .obg-side .obg-sat.obg-sat-out,
  .obg-card.obg-on .obc-anim,.obg-pin,.obg-now,.obg-axis,
  .obg-wave.obg-quick .obg-wv,.obg-wave.obg-quick .obg-mesh,
  .obg-wave.obg-quick .obg-body,.obg-wave.obg-quick .obg-head,
  .obg-wave.obg-quick .obg-node{animation:none}
  .obg-wave.obg-quick .obg-wv{stroke-dashoffset:0}
  .obg-body{will-change:auto}
  .obr-body .obr-head,.obr-body .obr-list,.obg-tip,
  .obg-card,.obg-sat{transition:none}
}

/* ── Метки монеты на волне (29.08) ──
   Цена, «от дна» и «от пика» переехали ИЗ полосы чисел СЮДА, в пустое
   поле будущего справа: линия кончается сегодня, правее рисовать
   нечего — место отдано подписям, каждая на высоте своей линии. */
.obg-mk{position:absolute;font:600 8.5px/1.2 Georgia,serif;letter-spacing:.13em;
  text-transform:uppercase;color:#9aa3c9;white-space:nowrap;opacity:0;
  transform:translateY(-50%);animation:obgMkIn .9s ease .7s both;
  pointer-events:none}
.obg-mk b{font-size:11.5px;letter-spacing:.02em;color:#dfe4f4;margin-right:5px}
.obg-mk-px{color:var(--mkc,#ffd2ac)}
.obg-mk-px b{font-size:14px;color:var(--mkc,#ffd2ac);
  text-shadow:0 0 12px rgba(232,236,248,.2)}
.obg-mk-dim b{color:#c6cde6}
@keyframes obgMkIn{from{opacity:0;transform:translateY(-50%) translateX(8px)}
  to{opacity:1;transform:translateY(-50%) translateX(0)}}
.obg-mkln{opacity:0;animation:obgMkLn 1.1s ease .55s both}
@keyframes obgMkLn{from{opacity:0}to{opacity:1}}
@media (max-width:900px){
  .obg-mk{font-size:8px}
  .obg-mk b{font-size:10.5px}
  .obg-mk-px b{font-size:12px}
  .obg-mkx{display:none}
}

/* ── Э-7: свод пометок пилюлями (одобрен 29.08) ──
   Собственные теги x-*: их не достают тип-селекторы чужих правил —
   урок боя с каскадом на прототипе. */
x-dg{display:flex;flex-wrap:wrap;gap:6px 8px;margin:2px 0 10px;
  animation:obgMkLn .9s ease .8s both}
x-pill{display:inline-flex;flex:0 0 auto;white-space:nowrap;
  align-items:center;gap:6px;padding:0 10px 0 8px;height:22px;
  box-sizing:border-box;
  border:1px solid rgba(170,179,216,.13);border-radius:18px;
  font:600 8.5px/1.2 Georgia,serif;letter-spacing:.12em;
  text-transform:uppercase;color:#9aa3c9;background:transparent}
x-i{display:inline-block;width:5px;height:5px;border-radius:50%;
  background:var(--pc,#aab3d8);box-shadow:0 0 6px var(--pc,#aab3d8);
  opacity:.8;flex:none}
x-b{display:inline;font-size:10px;letter-spacing:.03em;font-weight:600;
  color:#d3daed;margin:0 1px}
x-pill.hot{border-color:rgba(255,150,140,.25)}
x-pill.hot x-b{color:#f0b3a9}
@media (max-width:900px){x-dg{gap:5px}
  x-pill{padding:3px 8px 3px 6px;font-size:8px}x-b{font-size:9.5px}}

/* ── Полоса тремя группами (правка владельца 29.08): разделитель —
   чёрточка на ПЕРВОЙ плитке группы; отдельный элемент ломал счёт
   детей узкой ветки. ── */
.obc-num.gsep{margin-left:26px;position:relative}
.obc-num.gsep::before{content:'';position:absolute;left:-14px;top:18%;
  bottom:14%;width:1px;
  background:linear-gradient(180deg,transparent,rgba(170,179,216,.22),transparent)}
@media (max-width:900px){
  .obc-num.gsep{margin-left:0}
  .obc-num.gsep::before{display:none}
}

/* ── «Журнал держит всё» и панель портфеля (правка владельца 29.08):
   парадный шрифт; ВЕСЬ блок живёт десять секунд на любой ширине и
   схлопывается — раньше на телефоне жил вечно. Минимум высоты
   отпускается после полной прозрачности, чтобы сцена не мигнула. ── */
.obg-say{font:600 34px/1.15 Georgia,serif;letter-spacing:.015em;
  background:linear-gradient(180deg,#f6f8ff 20%,#c3cdec);
  -webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 2px 16px rgba(214,224,255,.16))}
@media (max-width:900px){.obg-say{font-size:25px}}
.obg-hint,.obg-panel,
#obgHero .obg-hint,#obgHero .obg-panel,
.obg-gate .obg-hint,.obg-gate .obg-panel{overflow:hidden;
  animation:obgBlockOut 12s ease both}
#obgHero.obg-gone .obg-hint,#obgHero.obg-gone .obg-panel{
  max-height:0;min-height:0;height:0;margin:0;padding:0;border:0}
@keyframes obgBlockOut{
  0%{opacity:0;max-height:360px}
  7%{opacity:1}
  80%{opacity:1;max-height:360px}
  93%{opacity:0;max-height:360px}
  100%{opacity:0;max-height:0;min-height:0;height:0;
       margin:0;padding:0;border:0;visibility:hidden}}

/* ── Э-8 (одобрено 29.08): формы суток и зоны ликвидаций ── */
.obg-spk{vertical-align:-3px;margin-right:4px}
.obg-spk polyline{fill:none;stroke:#aab3d8;stroke-width:1.2;opacity:.8}
.obg-liqz{fill:rgba(240,168,120,.07);stroke:rgba(240,168,120,.18);
  stroke-width:.5}

/* ── Э-9: подписи горизонтов ── */
.obc-hz{font:600 8px/1 Georgia,serif;letter-spacing:.3em;
  text-transform:uppercase;color:#5d6488;margin:14px 0 2px;
  display:flex;align-items:center;gap:10px}
.obc-hz::after{content:'';flex:1;height:1px;max-width:150px;
  background:linear-gradient(90deg,rgba(170,179,216,.18),transparent)}

/* ── Г-15: метки строк ── */
x-rm{display:inline-block;margin-left:7px;font-size:10px;line-height:1;
  vertical-align:1px;opacity:.75;font-style:normal}
x-rm.up{color:#8fd6b8;text-shadow:0 0 7px rgba(143,214,184,.35)}
x-rm.dn{color:#f0a89b;text-shadow:0 0 7px rgba(240,168,155,.35)}
@media (max-width:900px){x-rm{font-size:9px;margin-left:5px}}
</style>
"""

PODIUM_HTML = """
<div class="ob-podium" id="obPodium">
  <div class="obp-dome"></div>
  <svg class="obp-sky" id="obpSky"></svg>
  <div class="obp-floor"></div>

  <div class="obp-top">
    <div class="obp-h">лидеры прогона</div>
    <div class="obp-port" id="obpPort"></div>
    <div class="obp-stamp" id="obPodStamp"></div>
  </div>
  <button class="obp-exit" id="obpExit" type="button">к дашборду</button>
  <button class="obp-exit obp-again" id="obpAgain" type="button">заново</button>


  <!-- Ворота зала: первый экран после бриза и постоянный дом зала.
       Слева сцена — волна прогона, ядро выбранной группы и спутники;
       справа зал списком вместо стены карточек, он всегда на виду.
       Стена по-прежнему живёт своей жизнью и открывается кликом. -->
  <div class="obp-gate" id="obpGate">
    <!-- Выход был только на клавиатуре: на планшете и телефоне
         клавиатуры нет, и уйти из зала было НЕЧЕМ. Кнопка стоит
         поверх сцены, у верхнего края, и не отнимает высоты у
         списка (position:absolute). -->
    <button class="obg-out" id="obgOut" type="button"
            aria-label="закрыть зал">закрыть</button>
    <div class="obg-stage">
      <div class="obg-inner" id="obgInner"></div>
      <aside class="obr" id="obgRail"></aside>
    </div>
  </div>

  <div class="obz" id="obpZoom"><div class="obz-box" id="obpZbox"></div></div>

  <div class="obp-hint">колесо — список · клик по строке — карточка · esc — выход</div>
</div>
"""

PODIUM_JS = """
<script>
(function () {
  var pod = document.getElementById('obPodium');
  /* Узел стены снят вместе со стеной; зал живёт в воротах. */
  if (!pod) return;

  /* Молчаливый выход опаснее отказа: пустой экран неотличим от
     сломанного модуля. Все ранние выходы называют причину. */
  /* Сообщение о пустоте — ОДИН узел на весь зал, а не новый каждый
     раз. Стена пересобирается при каждой смене группы, и добавление
     узла оставляло на экране все прежние сообщения разом: «выходить не
     из чего» поверх «открытых позиций нет». */
  var emptyEl = null;
  function bail(why) {
    if (!emptyEl) {
      emptyEl = document.createElement('div');
      emptyEl.className = 'obp-empty';
      pod.appendChild(emptyEl);
    }
    emptyEl.textContent = why;
    emptyEl.style.display = why ? '' : 'none';
  }

  /* Данные вшиты в документ при сборке — см. render_podium() выше. */
  var O = {};
  try { O = JSON.parse(document.getElementById('obpData').textContent); }
  catch (e) { O = {}; }
  var STARS = (O.stars || []).slice();

  /* Палитра и стадии — те же, что у звёзд на орбите. Берём из ORB,
     свой список только запасной: третий набор цветов на третьем
     экране гарантированно разойдётся с первыми двумя.

     На сегодня ORB.strat не выставляется, и работает запасной —
     это безобидно ровно до первой правки цветов в orbit.py. */
  /* Таблица приходит со словарём рынка (render_common.CASE_STRAT);
     O.strat оставлен в цепочке на случай старых сборок. Встроенная
     копия — запасная. */
  var MAXD = +((O.market || {}).maxAge) || 14;
  var STRAT = (O.market && O.market.strat) || O.strat || {
    dormant:  { c: '#7E9AB5', stage: 0 }, hidden:   { c: '#7FE3D4', stage: 0 },
    spring:   { c: '#6FC9E8', stage: 0 }, churn:    { c: '#F0B85C', stage: 1 },
    taker:    { c: '#FFD98A', stage: 1 }, leverage: { c: '#E89AB0', stage: 1 },
    fuel:     { c: '#C4703A', stage: 2 }
  };
  var NONE = { c: '#8D97A6', stage: 1 };
  /* ═══ Группы зала (Р-27) ═══
     Ярусы больше не «у дна / движется». Фигура есть почти у всей
     выборки — стадия перестала различать монеты, и вопрос сместился
     на «что с ней делать сегодня». Три яруса — три вопроса:
     БРАТЬ (позиции нет, окно открыто), ДЕРЖАТЬ (позиция есть, повода
     трогать нет), ВЫХОДИТЬ (срок или истощение).
     Порядок сверху вниз — по срочности: ближе к полу то, что решается
     сегодня. */
  /* ═══ Четыре вкладки: один журнал, два подхода ═══
     HOLD — инвестирование: попал в лидеры, взял на $1000, держу.
     Правила к нему не применяются, там всегда весь журнал.
     Остальные три — состояние ТОРГОВОЙ книги: что правила предлагают
     взять сейчас, что ведут и из чего выходят.

     Одна монета может стоять и в HOLD, и в торговой группе. Это не
     дублирование, а ровно то, что сравнивается: инвестиционный подход
     монету просто держит, торговый мог вчера сократить её вдвое перед
     траншем.

     Вкладки, а не ярусы: ярусы делили экран на три, и каждой группе
     доставалась треть высоты — при сорока с лишним монетах это
     заставляло мельчить карточки. Одна группа за раз возвращает
     панелям полный размер; цена — нужно переключаться, и поэтому
     счётчики стоят прямо на кнопках. */
  var STAGE = [
    { n: 'hold',     c: '#8A8F99', key: 'hold' },
    { n: 'брать',    c: '#6FC9E8', key: 'take' },
    { n: 'держать',  c: '#7FE3D4', key: 'trade' },
    { n: 'выходить', c: '#FF6B35', key: 'exit' }
  ];

  /* Граница ярусов — доля пройденного пути от дна к пику ЖИЗНИ.
     Проценты, не кратность.

     Кратность от дна на эту роль не годится: она не знает, из какой
     ямы монета выбирается. HEMI на ×2.16 прошла 2.5% своего пути,
     BULLA на ×4.59 — 2.9%, а BTW на ×1.21 уже 76%, потому что
     падала всего на 21%. По кратности первые две «движутся», а
     третья стоит «у дна» — порядок обратный правильному.

     Граница по разбросу пробы 16 августа (61 монета): мин 0.07,
     q25 1.04, медиана 3.50, q75 14.82, макс 79.6. Двадцать стоит
     выше q75, и за ней начинается видимо другая популяция. */
  var TIER_MOVE_PCT = 20.0;

  /* Восстановленный путь из двух полей звезды, без новых величин в
     ядре. Вывод: цена = дно × upX, пик = дно / (1 − lifeDrop),
     отсюда доля = (upX − 1)·(1 − lifeDrop) / lifeDrop. Дно
     сокращается, поэтому сама цена не нужна.

     Ноль означает «не мерили»: величины нет, а не «монета на дне».
     Отправляем в нижний ярус — там она хотя бы попадётся на глаза,
     тогда как в «движется» утверждала бы то, чего мы не знаем.
     Падение ровно на сто процентов делит на ноль и означает, что
     пик жизни неизвестен, — тот же случай. */
  function pathPct(ux, dropPct) {
    var ld = Math.abs(+dropPct || 0) / 100;
    if (!(ux > 1) || ld <= 0 || ld >= 1) return 0;
    return (ux - 1) * (1 - ld) / ld * 100;
  }

  function recoveredPct(s) {
    /* Основной источник — пейлоад FLOW: оба конца из одного окна
       цикла, величина точная. */
    var main = pathPct(+s.upX || 0, s.lifeDrop);
    if (main > 0) return main;

    /* Запасной — метрики, которые считаются для каждой монеты
       выборки. up это рост от минимума ОКНА в 60 дней, ath —
       падение от исторической вершины, то есть концы из разных
       окон: при дне цикла заметно ниже двухмесячного минимума доля
       выйдет завышенной. Мириться с этим лучше, чем с нулём:
       ноль означал «у дна» и отправлял туда монету, которая сходила
       на десять концов и вернулась (TUT). */
    return pathPct(1 + (+s.up || 0) / 100, s.ath);
  }

  /* ═══ ТОРГОВАЯ ГРУППА МОНЕТЫ — ОТ КНИГИ, НЕ ОТ НАСТРОЕНИЯ ═══
     Ошибка, с которой начался этот блок: группы раздавались по
     ДЕЙСТВИЮ (act.group), а действие считалось от состояния рынка.
     При пустой книге зал показывал «в работе 32» — тридцать две
     позиции, которых никто не открывал. После Р-30 «в работе» и
     «выходить» — это состояние КНИГИ (журнала предположений), и
     источником группы обязана быть сама книга:

       позиция ЕСТЬ (s.book)  → «в работе»; «выходить», если
                                 действие зовёт выйти;
       позиции НЕТ            → «брать», только если правило
                                 предлагает вход (событие, Р-30);
                                 иначе монета живёт ТОЛЬКО в HOLD.

     Действие при этом не игнорируется — оно решает, КОТОРАЯ из
     групп книги (спокойная или выходная) и есть ли предложение
     входа. Оно лишь не может объявить позицией то, чего в книге
     нет. */
  function tradeGroupOf(s) {
    var inBook = !!(s.book && (s.book.usd || s.book.px));
    if (inBook) {
      return (s.act && s.act.group) === 'exit' ? 'exit' : 'trade';
    }
    /* «Брать» — только ЗАЯВКА на вход (действие «брать»). Группу
       take слой действия ставит и на «ждать»/«мимо» — это адрес
       стены, а не предложение, и в счётчик заявок им нельзя:
       «БРАТЬ 45» при нуле реальных входов — то же враньё, что
       «в работе 32» при пустой книге. Монеты без заявки живут в
       HOLD — он показывает весь журнал. */
    return (s.act && s.act.act) === 'брать' ? 'take' : null;
  }

  /* Ярус карточки — свечение группы. Монета без торговой группы
     красится как HOLD: другого места у неё нет. */
  var GROUP_INDEX = { hold: 0, take: 1, trade: 2, exit: 3 };

  function tierOf(s) {
    var i = GROUP_INDEX[tradeGroupOf(s) || 'hold'];
    return i === undefined ? 0 : i;
  }

  function stratOf(s) { return STRAT[s.st] || NONE; }
  function volNow(s) { return Math.max(+s.v1h || 0, +s.v4h || 0, +s.v1d || 0); }
  function xfmt(v) {
    if (!v) return '—';
    return v >= 10 ? '×' + Math.round(v) : '×' + v.toFixed(1);
  }
  /* Цвет приходит как #rrggbb, а в CSS-переменную нужен «r,g,b»:
     тени и заливки строятся через rgba(var(--c),.5). */
  function rgbOf(hex) {
    var h = String(hex || '').replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    if (isNaN(n)) return '141,151,166';
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(',');
  }

  /* ── Геометрия зала ──────────────────────────────────────────
     Радиус 1400 при перспективе 1200 даёт масштаб дальней стены
     0.46 и около одиннадцати панелей в кадре. Шаг выводится из
     радиуса, а не задаётся числом: хорда между соседними равна
     ширине панели с зазором. Вплотную рамы читались бы как одно
     сплошное полотно. */
  var NS = 'http://www.w3.org/2000/svg';

  /* ── Ряд цены ──
     Заливка под линией: у половины монет линия почти плоская, и
     одна линия там не читается как форма.

     Сглаживание рисует значения МЕЖДУ днями, которых не было. Для
     иллюстрации это допустимо; если график начнут использовать для
     разбора уровней — сглаживание снимать. */
  function smooth(pts) {
    if (pts.length < 2) return '';
    var d = 'M' + pts[0][0].toFixed(1) + ' ' + pts[0][1].toFixed(1);
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i > 0 ? i - 1 : 0], p1 = pts[i],
          p2 = pts[i + 1], p3 = pts[i + 2 < pts.length ? i + 2 : i + 1];
      d += ' C' + (p1[0] + (p2[0] - p0[0]) / 12).toFixed(1) + ' ' +
                  (p1[1] + (p2[1] - p0[1]) / 12).toFixed(1) + ', ' +
                  (p2[0] - (p3[0] - p1[0]) / 12).toFixed(1) + ' ' +
                  (p2[1] - (p3[1] - p1[1]) / 12).toFixed(1) + ', ' +
                  p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
    }
    return d;
  }

  function art(c, col, W, H) {
    var ser = (c.series || []).slice(-21).map(Number).filter(function (v) {
      return isFinite(v);
    });
    if (ser.length < 4) return '<svg viewBox="0 0 ' + W + ' ' + H + '"></svg>';

    var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
    var rng = (hi - lo) || 1;
    var pts = ser.map(function (v, i) {
      return [i * W / (ser.length - 1), H - 10 - (v - lo) / rng * (H - 38)];
    });
    var d = smooth(pts), last = pts[pts.length - 1];

    /* Узел входа в журнал: бар, на котором монета попала под
       наблюдение. Без него график показывает «что было», с ним —
       «что было ПОСЛЕ входа», а это и есть вопрос, ради которого
       журнал ведётся. */
    var ei = Math.max(0, Math.min(pts.length - 1,
      pts.length - 1 - (+c.days || 0)));
    var e = pts[ei];

    var id = 'z' + Math.random().toString(36).slice(2, 8);
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' +
      '<defs>' +
        '<linearGradient id="s' + id + '" x1="0" y1="0" x2="1" y2="0">' +
          '<stop offset="0" stop-color="' + col + '" stop-opacity=".28"/>' +
          '<stop offset="0.6" stop-color="' + col + '"/>' +
          '<stop offset="1" stop-color="#ffffff"/></linearGradient>' +
        '<linearGradient id="f' + id + '" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0" stop-color="' + col + '" stop-opacity=".42"/>' +
          '<stop offset="1" stop-color="' + col + '" stop-opacity="0"/>' +
        '</linearGradient>' +
        '<radialGradient id="n' + id + '">' +
          '<stop offset="0" stop-color="#fff" stop-opacity=".9"/>' +
          '<stop offset="0.35" stop-color="' + col + '" stop-opacity=".5"/>' +
          '<stop offset="1" stop-color="' + col + '" stop-opacity="0"/>' +
        '</radialGradient>' +
        '<filter id="b' + id + '" x="-30%" y="-60%" width="160%" height="220%">' +
          '<feGaussianBlur stdDeviation="3"/></filter>' +
      '</defs>' +
      '<path d="' + d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z" ' +
        'fill="url(#f' + id + ')"/>' +
      '<line x1="0" y1="' + e[1].toFixed(1) + '" x2="' + W + '" y2="' +
        e[1].toFixed(1) + '" stroke="' + col + '" stroke-width=".7" ' +
        'stroke-dasharray="2 4" opacity=".38"/>' +
      '<path d="' + d + '" fill="none" stroke="url(#s' + id + ')" ' +
        'stroke-width="4" stroke-linecap="round" opacity=".45" ' +
        'filter="url(#b' + id + ')"/>' +
      '<path d="' + d + '" fill="none" stroke="url(#s' + id + ')" ' +
        'stroke-width="1.6" stroke-linecap="round"/>' +
      '<circle cx="' + e[0].toFixed(1) + '" cy="' + e[1].toFixed(1) +
        '" r="9" fill="url(#n' + id + ')"/>' +
      '<circle cx="' + e[0].toFixed(1) + '" cy="' + e[1].toFixed(1) +
        '" r="2.6" fill="none" stroke="#fff" stroke-width="1" opacity=".85"/>' +
      '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) +
        '" r="2.6" fill="#FFE9B8"/>' +
    '</svg>';
  }

  /* ── Дуга со шкалой ──
     Диапазон 0..300%: выше начинается редкий хвост, и растягивать
     шкалу под него значит прижать к нулю всё остальное. Что вышло
     за предел — упирается в конец дуги, и это честнее сжатой шкалы. */
  function segs(now, rec, n) {
    n = n || 10;
    var L = function (v) { return Math.log10(Math.max(v, 0) + 1); };
    var top = Math.max(L(rec), L(now)) || 1;
    var kn = Math.round(L(now) / top * n), kr = Math.round(L(rec) / top * n);
    var out = '';
    for (var i = 0; i < n; i++) {
      out += '<u class="' + (i < kn ? 'on' : (i < kr ? 'rec' : '')) + '"></u>';
    }
    return '<span class="obp-seg">' + out + '</span>';
  }

  function ticksDays(d, max) {
    max = max || 14;
    var out = '';
    for (var i = 0; i < max; i++) {
      out += '<u class="' + (i < d ? 'on' : '') + '"></u>';
    }
    return '<span class="obp-tk">' + out + '</span>';
  }

  /* ── Метки крупных заявок на линии ──
     Позиции в bigMarks отсчитаны от начала хвоста в 48 часов, тем же
     хвостом рисуется h48. Ряд и метки обязаны ехать вместе: если
     когда-нибудь длина хвоста изменится в одном месте, метки
     разъедутся молча.

     Белая точка — покупка, красная — продажа, нейтральные не
     рисуются вовсе: бар, где стороны погасили друг друга, ничего не
     сообщает, а точка на графике выглядит утверждением. */
  function markDots(marks, pts) {
    if (!marks || !marks.length || !pts.length) return '';
    var n = pts.length, out = '';
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      if (m.s !== 'buy' && m.s !== 'sell') continue;
      var idx = Math.round(m.i / 47 * (n - 1));
      if (idx < 0 || idx >= n) continue;
      var p = pts[idx];
      var r = Math.min(6, 2.2 + (+m.x || 0) * 0.35);
      out += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) +
        '" r="' + r.toFixed(1) + '" fill="' +
        (m.s === 'buy' ? '#ffffff' : '#E8705A') + '" opacity=".9"/>';
    }
    return out;
  }

  /* Линия за 48 часов. Отдельно от art(): та рисует недели и знает
     про узел входа в журнал, здесь же вопрос другой — что было за
     двое суток. Общая функция обслуживала бы оба плохо. */
  function h48HTML(c, col, W, H) {
    var ser = (c.h48 || []).map(Number).filter(function (v) {
      return isFinite(v) && v > 0;
    });
    if (ser.length < 6) return '';
    var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
    var rng = (hi - lo) || 1;
    var pts = ser.map(function (v, i) {
      return [i * W / (ser.length - 1), H - 8 - (v - lo) / rng * (H - 22)];
    });
    var d = smooth(pts);
    return '<div class="obz-h48"><svg viewBox="0 0 ' + W + ' ' + H +
      '" preserveAspectRatio="none" width="100%" height="' + H + '">' +
      '<path d="' + d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z" fill="' +
        col + '" opacity=".12"/>' +
      '<path d="' + d + '" fill="none" stroke="' + col +
        '" stroke-width="1.5"/>' +
      markDots(c.bigMarks, pts) +
      '</svg></div>';
  }

  /* Строка «сегодня» на панели. Три коротких факта, каждый — ответ
     на отдельный вопрос: куда наклонён поток, откупали ли на
     проливе, жива ли монета в эти сутки. */
  function notes(c) {
    var out = [];
    function add(w, span, short, full) {
      if (w > 0) out.push({ w: w, span: span, short: short, full: full });
    }

    var vol = volNow(c), bg = c.volBg;

    if (vol >= 5 && bg !== undefined && bg < 1) {
      add(vol / 5, 'day',
        'всплеск первый час, ×' + xfmtRaw(vol),
        'всплеск первый час: <b class="am">×' + xfmtRaw(vol) +
        '</b> при фоне ×' + xfmtRaw(bg));
    } else if (bg !== undefined && bg >= 1.3) {
      add(bg / 1.3, 'day',
        'интерес держится сутки',
        'интерес держится сутки, фон <b class="am">×' + xfmtRaw(bg) + '</b>');
    } else if (vol < 0.5 && bg !== undefined && bg < 0.5) {
      add(0.5 / Math.max(vol, 0.05), 'day',
        'тихо в обоих измерениях',
        'тихо в обоих измерениях: ×' + xfmtRaw(vol) + ' при фоне ×' +
        xfmtRaw(bg));
    }

    if (c.press !== undefined && Math.abs(+c.press) >= 3) {
      var upside = +c.press >= 0;
      add(Math.abs(+c.press) / 3, 'day',
        upside ? 'покупатель усиливается' : 'продавец прибавил',
        (upside ? 'покупатель усиливается' : 'продавец прибавил') +
        ' на <b class="' + (upside ? 'up' : 'dn') + '">' +
        Math.abs(+c.press).toFixed(1) + ' п.п.</b> за последние часы');
    }

    if (c.bigBuys && c.rangePos !== undefined && c.rangePos <= 35) {
      add(c.bigBuys + (+c.bigMax || 0) / 4, 'day',
        'откупали у низа: ' + c.bigBuys,
        'откупали у низа: <b>' + c.bigBuys + '</b>, крупнейший ×' +
        (c.bigMax || 0));
    }
    if (c.bigSells && c.rangePos !== undefined && c.rangePos >= 65) {
      add(c.bigSells + (+c.bigMax || 0) / 4, 'day',
        'крупные продажи у верха',
        'крупные продажи у верха диапазона: <b>' + c.bigSells + '</b>');
    }

    /* Что было за последние часы. Условие составное: крупные заявки
       ОДНОЙ стороны при цене, которая не пошла в её сторону. Покупки
       на растущих барах — догоняющие, и говорить о них нечего;
       смысл появляется, когда покупают на сползании, а продают на
       стоящей цене. Порога «стоит» здесь нет, есть знак хода: где
       именно проходит граница, мы ещё не мерили.

       Шкала печатается рядом с числами: пятнадцатиминутки берутся
       только для монет журнала, у остальных ответ часовой, и без
       подписи две одинаковые фразы означали бы разное. */
    if (c.shakeBuys > (c.shakeSells || 0) && c.shakeMove <= 0) {
      add(c.shakeBuys + (+c.shakeMax || 0) / 4, 'day',
        'откупали на сползании: ' + c.shakeBuys,
        'откупали на сползании, ' + (c.shakeHours || 4) + ' ч: <b>' +
        c.shakeBuys + '</b> заявок, крупнейшая ×' +
        xfmtRaw(c.shakeMax) + ' при цене ' + (+c.shakeMove).toFixed(1) +
        '% <small>' + (c.shakeScale || '') + '</small>');
    } else if (c.shakeSells > (c.shakeBuys || 0) && c.shakeMove >= 0) {
      add(c.shakeSells + (+c.shakeMax || 0) / 4, 'day',
        'продавали в рост: ' + c.shakeSells,
        'крупные продажи при растущей цене, ' + (c.shakeHours || 4) +
        ' ч: <b>' + c.shakeSells + '</b>, крупнейшая ×' +
        xfmtRaw(c.shakeMax) + ' <small>' + (c.shakeScale || '') +
        '</small>');
    }

    /* Последние часы против суток. Условие составное: поток
       сместился в одну сторону, а цена в эту сторону НЕ пошла.
       Покупки на растущих барах — догоняющие, говорить о них
       нечего; смысл появляется, когда покупают на сползании, а
       продают на стоящей цене.

       Вес складывается из двух безразмерных частей: во сколько раз
       крупнейшая сделка окна перекрыла обычный для суток разброс, и
       насколько сместился поток. Так он сравним с весами остальных
       наблюдений, которые тоже меряются в «во сколько раз перекрыт
       порог».

       Отсечка в один пункт отсеивает дрожание доли: перекос меньше
       процентного пункта — это шум округления, а не смена стороны. */
    var shPP = +c.shakePP || 0, shX = +c.shakeX || 0, shP = +c.shakeP90 || 0;
    var shW = (shP > 1 ? shX / shP : shX) + Math.abs(shPP) / 5;
    var shTail = ' <small>' + (c.shakeScale || '') + '</small>';
    var shMid = 'сделки ×' + xfmtRaw(shX) + ' к суточной норме' +
      (shP > 0 ? ' (обычно ×' + xfmtRaw(shP) + ')' : '') +
      ', цена ' + (+c.shakeMove).toFixed(1) + '%' +
      (c.shakeLow ? ', низ окна пробит' : '');

    if (shPP >= 1 && c.shakeMove <= 0) {
      add(shW, 'day',
        'откупали на сползании: +' + shPP.toFixed(1) + ' п.п.',
        'за ' + (c.shakeHours || 4) + ' ч поток сместился в покупку на <b>' +
        shPP.toFixed(1) + ' п.п.</b>, ' + shMid + shTail);
    } else if (shPP <= -1 && c.shakeMove >= 0) {
      add(shW, 'day',
        'продавали в рост: ' + shPP.toFixed(1) + ' п.п.',
        'за ' + (c.shakeHours || 4) + ' ч поток сместился в продажу на <b>' +
        Math.abs(shPP).toFixed(1) + ' п.п.</b>, ' + shMid + shTail);
    }

    if (c.vxDir === 'up' && c.vxAgo >= 0 && c.vxAgo <= 12) {
      add((13 - c.vxAgo) / 6, 'day',
        'развернулся ' + c.vxAgo + ' ч назад',
        'развернулся вверх <b class="up">' + c.vxAgo + ' часов назад</b>');
    }

    if (c.byDay && c.byDay.length >= 3) {
      var today = c.byDay[c.byDay.length - 1];
      var past = c.byDay.slice(0, -1).filter(function (n) { return n > 0; });
      if (today >= 2 && past.length) {
        var mid = past.slice().sort(function (a, b) { return a - b; })[
          Math.floor(past.length / 2)];
        if (mid > 0 && today > mid) {
          add(today / mid, 'day',
            'попадает чаще: ' + today,
            'попадает чаще обычного: сегодня <b>' + today +
            '</b> против ' + mid);
        }
      }
    }

    if ((+c.heldRallies || 0) >= 3) {
      add(c.heldRallies / 3, 'weeks',
        'дно выдержало ' + c.heldRallies,
        'дно выдержало <b>' + c.heldRallies + '</b> отскоков из ' +
        (c.rallies || c.heldRallies));
    }

    /* Состояние плеча — готовая метка analytics_momentum.oi_state(),
       а не свой порог: то же слово, что уже показывает карточка.
       held — самое настороженное (GPS перед обвалом стоял здесь,
       cycles=0 — цикл ни разу не закрывался), repeat — уже сдувался
       в этом окне (BLESS), cleared показывать не нужно — это
       позитивное состояние, не наблюдение-предупреждение. */
    if (c.oiState === 'held' || c.oiState === 'repeat') {
      var oiW = (c.oiRise - 1) + c.oiHeld / 100;
      add(oiW, 'day',
        'плечо ×' + xfmtRaw(c.oiRise) + (c.oiState === 'held' ? ', не проверено' : ', уже сдувалось'),
        'плечо выросло <b class="' + (c.oiState === 'held' ? 'dn' : 'am') + '">×' +
        xfmtRaw(c.oiRise) + '</b> и держит ' + Math.round(c.oiHeld) + '%' +
        (c.oiState === 'held' ? ' — этот цикл ещё ни разу не закрывался'
          : ', цикл ' + ((c.oiCycles || 0) + 1)));
    }

    /* Флаг диспетчера: победивший подкейс сам себя пометил поздним
       (flow_fuel, growth_load) — фигура собралась, но описывает уже
       состоявшееся движение. Вес фиксированный и высокий: это не
       наблюдение о рынке, а предупреждение о самом сигнале. */
    if (c.late) {
      add(2, 'day', 'фигура уже отыграна',
        'фигура <b class="dn">уже отыграна</b> — движение состоялось ' +
        'раньше входа');
    }

    /* Ход уже отдан, независимо от гейта выбытия из журнала (Ч-11):
       cycle_done() не поймает giveback ниже вершины ×10, а карточка
       уже предупреждает об этом отдельной строкой. */
    if (c.cycleGivenPct !== undefined && c.cycleGivenPct) {
      add(c.cycleGivenPct / 40, 'weeks',
        'отдано ' + Math.round(c.cycleGivenPct) + '% хода',
        'от вершины ×' + xfmtRaw(c.cyclePeakX) + ' отдано <b class="dn">' +
        Math.round(c.cycleGivenPct) + '%</b> хода');
    }

    /* Дивергенция цены и OBV: второй пик цены не ниже первого, поток
       слабее — тот же вопрос, что показал Klinger Oscillator на
       BLESS, только на уже посчитанном OBV. */
    if (c.divShare !== undefined && c.divShare) {
      add(1.5 + c.divShare, 'day',
        'поток слабее на повторном пике',
        'цена ' + (c.divPricePct >= 0 ? '+' : '') + c.divPricePct.toFixed(1) +
        '% ко второму пику, а поток <b class="dn">слабее</b> первого');
    }

    out.sort(function (a, b) { return b.w - a.w; });
    return out;
  }

  /* Кратность без знака умножения — фраза его ставит сама. */
  function xfmtRaw(v) {
    var n = +v || 0;
    return n >= 10 ? Math.round(n) : n.toFixed(1);
  }

  function fan(col) {
    var CX = 126, CY = 126, out = '';
    var id = 'F' + Math.random().toString(36).slice(2, 7);
    for (var i = 0; i < 13; i++) {
      var a0 = -104 + i * 15.6, a1 = a0 + 11.4;
      var t0 = (a0 - 90) * Math.PI / 180, t1 = (a1 - 90) * Math.PI / 180;
      var p = [
        [CX + Math.cos(t0) * 62, CY + Math.sin(t0) * 62],
        [CX + Math.cos(t0) * 118, CY + Math.sin(t0) * 118],
        [CX + Math.cos(t1) * 118, CY + Math.sin(t1) * 118],
        [CX + Math.cos(t1) * 62, CY + Math.sin(t1) * 62]
      ];
      var k = 1 - Math.abs(i - 6) / 7;
      out += '<path d="M' + p.map(function (q) {
          return q[0].toFixed(1) + ' ' + q[1].toFixed(1);
        }).join(' L') + ' Z" fill="url(#' + id + ')" opacity="' +
        (0.18 + 0.62 * k).toFixed(2) + '"/>';
    }
    return '<svg viewBox="0 0 252 252">' +
      '<defs><radialGradient id="' + id + '" cx="50%" cy="50%" r="50%">' +
        '<stop offset="0.45" stop-color="' + col + '" stop-opacity="0"/>' +
        '<stop offset="0.72" stop-color="' + col + '" stop-opacity=".85"/>' +
        '<stop offset="1" stop-color="#FFF0CE" stop-opacity=".95"/>' +
      '</radialGradient>' +
      '<filter id="b' + id + '" x="-30%" y="-30%" width="160%" height="160%">' +
        '<feGaussianBlur stdDeviation="4"/></filter></defs>' +
      '<g filter="url(#b' + id + ')">' + out + '</g></svg>';
  }

  /* ── Большой прибор ──
     Три концентрических пояса разной частоты: точечный обод, пояс
     насечек и сама шкала. Один пояс читается как круговая
     диаграмма, три — как прибор. */
  function bigGauge(pct, col) {
    var CX = 100, CY = 100, RR = 62, A0 = -134, A1 = 134;
    var f = Math.max(0, Math.min(1, pct / 300));

    function pt(a, r) {
      var t = (a - 90) * Math.PI / 180;
      return [CX + Math.cos(t) * r, CY + Math.sin(t) * r];
    }
    function arc(a0, a1, r) {
      var s = pt(a0, r), e = pt(a1, r);
      return 'M' + s[0].toFixed(1) + ' ' + s[1].toFixed(1) +
        ' A' + r + ' ' + r + ' 0 ' + (a1 - a0 > 180 ? 1 : 0) + ' 1 ' +
        e[0].toFixed(1) + ' ' + e[1].toFixed(1);
    }

    var dots = '';
    for (var i = 0; i <= 72; i++) {
      var q = pt(A0 + (A1 - A0) * i / 72, RR + 22);
      dots += '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) +
        '" r=".9" fill="' + col + '" opacity="' + (i % 6 === 0 ? .5 : .18) + '"/>';
    }
    var ticks = '';
    for (var j = 0; j <= 40; j++) {
      var b = A0 + (A1 - A0) * j / 40, big = j % 4 === 0;
      var p1 = pt(b, RR + 6), p2 = pt(b, RR + (big ? 15 : 10.5));
      ticks += '<line x1="' + p1[0].toFixed(1) + '" y1="' + p1[1].toFixed(1) +
        '" x2="' + p2[0].toFixed(1) + '" y2="' + p2[1].toFixed(1) +
        '" stroke="' + col + '" stroke-width="' + (big ? 1.5 : .8) +
        '" opacity="' + (big ? .6 : .26) + '"/>';
    }

    var id = 'B' + Math.random().toString(36).slice(2, 7);
    return '<svg viewBox="0 0 200 200">' +
      '<defs>' +
        '<pattern id="p' + id + '" width="3.2" height="3.2" ' +
          'patternUnits="userSpaceOnUse">' +
          '<circle cx="1.6" cy="1.6" r=".55" fill="' + col + '" opacity=".16"/>' +
        '</pattern>' +
        '<linearGradient id="z' + id + '" x1="0" y1="0" x2="1" y2="1">' +
          '<stop offset="0" stop-color="#2b3038"/>' +
          '<stop offset="0.5" stop-color="#0a0d13"/>' +
          '<stop offset="1" stop-color="#23272f"/></linearGradient>' +
        '<linearGradient id="a' + id + '" x1="0" y1="1" x2="1" y2="0">' +
          '<stop offset="0" stop-color="' + col + '" stop-opacity=".35"/>' +
          '<stop offset="0.7" stop-color="' + col + '"/>' +
          '<stop offset="1" stop-color="#fff"/></linearGradient>' +
        '<radialGradient id="d' + id + '" cx="50%" cy="38%" r="62%">' +
          '<stop offset="0" stop-color="#12161f"/>' +
          '<stop offset="1" stop-color="#05070c"/></radialGradient>' +
        '<filter id="g' + id + '" x="-40%" y="-40%" width="180%" height="180%">' +
          '<feGaussianBlur stdDeviation="5"/></filter>' +
      '</defs>' + dots + ticks +
      '<path d="' + arc(A0, A1, RR) + '" fill="none" ' +
        'stroke="rgba(255,255,255,.07)" stroke-width="4" stroke-linecap="round"/>' +
      (f > 0.01
        ? '<path d="' + arc(A0, A0 + (A1 - A0) * f, RR) + '" fill="none" ' +
            'stroke="url(#a' + id + ')" stroke-width="4" stroke-linecap="round" ' +
            'opacity=".55" filter="url(#g' + id + ')"/>' +
          '<path d="' + arc(A0, A0 + (A1 - A0) * f, RR) + '" fill="none" ' +
            'stroke="url(#a' + id + ')" stroke-width="4" stroke-linecap="round"/>'
        : '') +
      '<circle cx="100" cy="100" r="48" fill="url(#d' + id + ')"/>' +
      '<circle cx="100" cy="100" r="48" fill="url(#p' + id + ')"/>' +
      '<circle cx="100" cy="100" r="48" fill="none" stroke="' + col + '" ' +
        'stroke-width="1" opacity=".45"/>' +
      '<circle cx="100" cy="100" r="48" fill="none" stroke="' + col + '" ' +
        'stroke-width="3" opacity=".22" filter="url(#g' + id + ')"/>' +
      '<path d="M59 81 A48 48 0 0 1 141 81" fill="none" stroke="#fff" ' +
        'stroke-width="1.6" opacity=".17" stroke-linecap="round"/>' +
      '<ellipse cx="100" cy="73" rx="36" ry="13" fill="#fff" opacity=".05"/>' +
      '<circle cx="100" cy="100" r="92" fill="none" ' +
        'stroke="url(#z' + id + ')" stroke-width="11"/>' +
      '<circle cx="100" cy="100" r="97" fill="none" ' +
        'stroke="rgba(255,255,255,.09)" stroke-width="1"/>' +
      '<path d="M38 42 A92 92 0 0 0 24 128" fill="none" stroke="#fff" ' +
        'stroke-width="2.4" opacity=".30" stroke-linecap="round"/>' +
    '</svg>';
  }

  /* ── Небо ──
     Детерминированное: зал должен выглядеть одинаково при каждом
     заходе, иначе глаз не запоминает место. */
  var seed = 20260812;
  function rnd() {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  }
  function sky() {
    var svg = document.getElementById('obpSky');
    if (!svg) return;
    var W = window.innerWidth, H = window.innerHeight;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var out = '';
    for (var i = 0; i < 240; i++) {
      out += '<circle cx="' + (rnd() * W).toFixed(0) + '" cy="' +
        (rnd() * H * 0.62).toFixed(0) + '" r="' +
        (0.3 + Math.pow(rnd(), 2.6) * 1.5).toFixed(2) +
        '" fill="#dfe8f5" opacity="' + (0.12 + rnd() * 0.55).toFixed(2) + '"/>';
    }
    svg.innerHTML = out;
  }

  /* ── Раскрытая карточка ── */
  var zoom = document.getElementById('obpZoom');
  var zbox = document.getElementById('obpZbox');

  /* Фраза наблюдения для сцены: те же два наблюдения, что и в старой
     сводке, но без обёртки — в пейзаже у неё своё место и свой стиль. */
  function noteText(c) {
    var all = notes(c);
    var day = all.filter(function (n) { return n.span === 'day'; })[0];
    var wk = all.filter(function (n) { return n.span === 'weeks'; })[0];
    var parts = [];
    if (day) parts.push(day.full);
    if (wk) parts.push(wk.full);
    return parts.join(' · ');
  }

  function openZoom(c, zi) {
    /* Без открытого зала карточки быть не может. Проверка нужна на
       планшете: там промах по панели проходил сквозь закрытый зал и
       карточка вылезала поверх дашборда. Зал — единственная дверь в
       неё, и дверь должна быть открыта. */
    if (!pod.classList.contains('on')) return;

    /* Карточка-пейзаж живёт в render/cardscene.py и берёт на себя весь
       показ. Если модуль не подключён, работает прежняя карточка ниже —
       это и есть способ сравнить обе, не откатывая правку. */
    if (window.OBCARD && ZLIST.length) {
      window.OBCARD.open(ZLIST, zi || 0,
        function (s) {
          return { note: noteText(s), body: blocksHTML(s, stratOf(s).c) };
        },
        function (t) {
          pod.classList.remove('on');
          if (typeof window.obShowStar === 'function') window.obShowStar(t);
        });
      return;
    }

    var sc = stratOf(c), col = sc.c, up = Math.round(+c.up || 0);
    zbox.style.setProperty('--c', rgbOf(col));
    zbox.innerHTML =
      '<div class="obz-close" id="obpZclose">закрыть</div>' +
      '<div class="obz-head">' +
        '<span class="obz-t">' + c.t + '</span>' +
        '<span class="obz-s">' + (c.pattern || '—') + '</span>' +
        '<span class="obz-cap">' + (c.cap || '') + '</span>' +
      '</div>' +
      '<div class="obz-stack">' +
        '<div class="obz-art">' + art(c, col, 610, 196) + '</div>' +
        '<div class="obz-seam"></div>' +
        /* Прибор по центру, шкалы по краям. Симметрия не ради
           красоты: боковые величины сравниваются между собой, а
           центральная ни с чем — она итог. */
        '<div class="obz-dash">' +
          '<span class="obz-met">' +
            '<span class="obz-met-k">объём сейчас</span>' +
            '<span class="obz-met-v">' + xfmt(volNow(c)) +
              '<small>рекорд ' + xfmt(+c.x || 0) + '</small></span>' +
            segs(volNow(c), +c.x || 0, 14) +
          '</span>' +
          '<span class="obz-gau">' +
            '<span class="obz-fan">' + fan(col) + '</span>' +
            bigGauge(up, col) +
            '<span class="obz-gau-c"><b>' + up + '%</b><i>от дна</i></span>' +
          '</span>' +
          '<span class="obz-met r">' +
            '<span class="obz-met-k">в журнале</span>' +
            /* MAXD, не литерал: хендофф заменял зашитые «14» через
               ORB.maxAge, канал умер с переездом на документы, и
               подпись врала при сроке журнала 26. */
            '<span class="obz-met-v">' + (+c.days || 0) +
              '<small>из ' + MAXD + ' дней</small></span>' +
            ticksDays(+c.days || 0, MAXD) +
          '</span>' +
          /* Р-25: жива ли фигура — различение «ожидание повода»
             против «держим труп». aliveGapDays == null означает
             «поле ещё не копилось» (записи старше 22.08) и НЕ
             показывается: нет данных — нет строки, ноль здесь
             соврал бы. Порог трёх дней — прикидка: детектор
             пересчитывается каждый прогон, три дня тишины при
             восьми прогонах в сутки — это не пропуск, а распад. */
          /* Р-4/Р-15: ступень размера. Показывается ТОЛЬКО когда она
             понижена: полная ступень — это база, о которой нечего
             сообщать, и строка «полный» у сорока монет была бы шумом.
             Причины уходят в подвал карточки орбиты, здесь число. */
          (!(c.size || {}).steps ? '' :
            '<span class="obz-met r">' +
              '<span class="obz-met-k">размер</span>' +
              '<span class="obz-met-v dn">' + c.size.tier +
                '<small>$' + c.size.usd + '</small></span>' +
            '</span>') +
          /* Р-31: структурный спрос. Единственная отметка карточки,
             которая говорит В ПОЛЬЗУ монеты, поэтому и тон у неё
             тёплый, а не тревожный. Размер стоит первым: «выкуп 4.6%
             капы в год» читается, «активный выкуп» — нет. */
          (!c.demandNote ? '' :
            '<span class="obz-met r">' +
              '<span class="obz-met-k">спрос</span>' +
              '<span class="obz-met-v up">' + c.demandNote + '</span>' +
            '</span>') +
          /* Р-11/Р-17: правило выхода. Отдельной строкой и первым
             среди отметок: если оно сработало, остальное читается уже
             в его свете. Формулировка «пора смотреть», а не «выходи»
             — решение за человеком, как и со входом. */
          (!(c.exitWhy || []).length ? '' :
            '<span class="obz-met r">' +
              '<span class="obz-met-k">пора смотреть</span>' +
              '<span class="obz-met-v dn">' +
                (c.exitDeadline !== undefined && c.exitDeadline !== null
                  ? c.exitDeadline + '<small>дн до даты</small>'
                  : 'поток<small>' + c.exitWhy.length + ' причины</small>') +
              '</span>' +
            '</span>') +
          /* Р-12: связка плеча и транша. Отметка, не вердикт — числа
             и никакого «опасно»: решение за человеком (нулевой раздел).
             Строки нет, если нет любой из половин. */
          (!c.linkNote ? '' :
            '<span class="obz-met r">' +
              '<span class="obz-met-k">связка</span>' +
              '<span class="obz-met-v dn">плечо+транш<small>' +
                c.linkDays + ' дн</small></span>' +
            '</span>') +
          /* Р-5: опережение выборки. Стоит рядом с изменением цены и
             отвечает на другой вопрос: не «сколько прошла», а
             «сколько из этого своё». Нет ключа — монеты нет в текущей
             выборке, и строка не рисуется вовсе: ноль здесь читался
             бы как «шла вровень», а это утверждение, которого данные
             не делают. */
          ((c.rel || {}).d7 === undefined ? '' :
            '<span class="obz-met r">' +
              '<span class="obz-met-k">к рынку</span>' +
              '<span class="obz-met-v ' + (c.rel.d7 >= 0 ? 'up' : 'dn') +
                '">' + (c.rel.d7 >= 0 ? '+' : '') + c.rel.d7 +
                '<small>п.п. за 7д</small></span>' +
            '</span>') +
          (c.aliveGapDays === null || c.aliveGapDays === undefined ? '' :
            '<span class="obz-met r">' +
              '<span class="obz-met-k">фигура</span>' +
              (c.aliveGapDays <= 3
                ? '<span class="obz-met-v up">жива<small>признаки держатся</small></span>'
                : '<span class="obz-met-v dn">распалась<small>' +
                  Math.round(c.aliveGapDays) + ' дн без сигнала</small></span>') +
            '</span>') +
        '</div>' +
      '</div>' +
      (c.verdict ? '<div class="obz-verdict">' + c.verdict + '</div>' : '') +
      summaryHTML(c) +
      blocksHTML(c, col) +
      '<div class="obz-goto" id="obpZgoto">показать на орбите</div>';

    zoom.classList.add('on');
    document.getElementById('obpZclose').onclick = closeZoom;

    /* Экран лидеров отвечает «что происходит», карточка на орбите —
       «почему»; разрывать эту пару отдельной навигацией незачем. */
    document.getElementById('obpZgoto').onclick = function () {
      closeZoom();
      pod.classList.remove('on');
      if (typeof window.obShowStar === 'function') window.obShowStar(c.t);
    };
  }
  /* ── Два блока карточки ──
     Горизонты разные и намеренно разведены: «за недели» отвечает на
     вопрос цикла, «сегодня» — на вопрос ближайших суток. Одна
     таблица на оба заставляла бы сравнивать несравнимое. */
  function cell(k, v, cls) {
    if (v === null || v === undefined || v === '') return '';
    return '<span class="obz-cell"><i>' + k + '</i><b' +
      (cls ? ' class="' + cls + '"' : '') + '>' + v + '</b></span>';
  }

  function pct(v, digits) {
    if (v === undefined || v === null) return null;
    var n = +v;
    return (n >= 0 ? '+' : '') + n.toFixed(digits === undefined ? 0 : digits) + '%';
  }

  /* Сводка карточки: по одному наблюдению с каждого горизонта.
     Оба с одного означали бы две фразы про один и тот же всплеск,
     а вопрос у горизонтов разный. */
  function summaryHTML(c) {
    var all = notes(c);
    var day = all.filter(function (n) { return n.span === 'day'; })[0];
    var wk = all.filter(function (n) { return n.span === 'weeks'; })[0];
    var parts = [];
    if (day) parts.push(day.full);
    if (wk) parts.push(wk.full);
    if (!parts.length) return '';
    return '<div class="obz-sum">' + parts.join(' · ') + '</div>';
  }

  function blocksHTML(c, col) {
    var weeks =
      cell('от дна', pct(c.up), 'up') +
      cell('от пика жизни', c.lifeDrop ? '−' + Math.round(Math.abs(c.lifeDrop)) + '%' : null, 'dn') +
      cell('вершина хода', c.peakX ? '×' + c.peakX : null) +
      cell('отскоки', c.rallies ? (c.heldRallies || 0) + ' из ' + c.rallies : null) +
      cell('в лидерах', c.runsSeen ? (c.hitCount || 0) + ' из ' + c.runsSeen : null) +
      cell('в журнале', (+c.days || 0) + 'д · тишина ' + (+c.quiet || 0)) +
      cell('плечо', c.oiState
        ? '×' + xfmt(c.oiRise) + ' · ' + Math.round(c.oiHeld || 0) + '%' +
          (c.oiState === 'cleared' ? ' · разгружено'
            : c.oiState === 'repeat' ? ' · цикл ' + ((c.oiCycles || 0) + 1)
            : ' · не проверено')
        : null, c.oiState === 'held' ? 'dn' : null) +
      cell('ход', (c.cycleGivenPct !== undefined && c.cycleGivenPct)
        ? 'отдано ' + Math.round(c.cycleGivenPct) + '%' : null, 'dn');

    var today =
      cell('объём сейчас', xfmt(volNow(c))) +
      cell('фон суток', c.volBg !== undefined ? xfmt(c.volBg) : null, 'am') +
      cell('перевес сторон', c.press !== undefined
        ? (+c.press >= 0 ? 'покупка ' : 'продажа ') +
          Math.abs(+c.press).toFixed(1) + ' п.п.' : null,
        (+c.press >= 0 ? 'up' : 'dn')) +
      cell('вортекс', c.vxDir
        ? (c.vxDir === 'up' ? 'вверх' : 'вниз') +
          (c.vxAgo >= 0 ? ' · ' + c.vxAgo + ' бар' : ' · держится')
        : null, c.vxDir === 'up' ? 'up' : 'dn') +
      cell('в диапазоне', c.rangePos !== undefined
        ? Math.round(c.rangePos) + '% снизу' : null) +
      cell('откупы за сутки', c.bigCount
        ? c.bigCount + ' · макс ×' + (c.bigMax || 0) : null) +
      cell('скорость хода', c.speedV ? c.speedV + ' ATR/бар' : null) +
      cell('заметность', c.q ? 'q ' + c.q + ' · ' + (c.qScale || '') : null);

    /* ── ТРЕТИЙ БЛОК: ДЕНЬГИ ──
       Из разбора 26.08. Денег на споте нет — ход оплачен чужим
       плечом, и вопрос не «сколько его», а откуда оно и держится ли.
       Всё, что отвечает на этот вопрос, собрано в одном месте:
       порознь эти величины лежали в разных блоках и не читались
       вместе, а смысл у них общий.

       Порядок внутри блока — от факта к оценке: сначала наблюдаемое
       (спот, ликвидации, киты), потом модельное (плиты плеча). Так
       читатель не примет оценку за измерение. */
    var money = '';
    if (c.spotShare !== undefined && c.spotShare !== null) {
      var sp = +c.spotShare * 100;
      money += cell('доля спота', (sp <= 0 ? 'спота нет вовсе'
        : sp < 1 ? sp.toFixed(2) + '%' : Math.round(sp) + '%'),
        sp <= 0 ? 'dn' : null);
    }
    if (c.liq24h) {
      money += cell('ликвидации за сутки',
        'лонгов ' + money9(c.liq24h.long) + ' · шортов ' + money9(c.liq24h.short),
        (+(c.liq24h.long || 0) > +(c.liq24h.short || 0)) ? 'dn' : 'up');
    }
    if (c.hlWhales && c.hlWhales.n) {
      money += cell('киты Hyperliquid',
        'в лонге ' + (c.hlWhales.long || 0) + ' · в шорте ' + (c.hlWhales.short || 0) +
        ' из ' + c.hlWhales.n);
    }
    if (c.liqFuel) {
      var bl = +c.liqFuel.below || 0, ab = +c.liqFuel.above || 0;
      money += cell('плечо под ценой', bl > 0 ? fuelPct(bl) + ' капитализации' : null, 'dn');
      money += cell('плечо над ценой', ab > 0 ? fuelPct(ab) + ' капитализации' : null, 'up');
      if (c.liqFuel.below_usd || c.liqFuel.above_usd) {
        money += cell('в деньгах',
          money9(c.liqFuel.below_usd) + ' снизу · ' + money9(c.liqFuel.above_usd) + ' сверху');
      }
    }
    if (c.stopInPlate) {
      money += cell('наш стоп', 'стоит в плите' +
        (c.stopInPlate.dist_atr !== undefined
          ? ' (' + c.stopInPlate.dist_atr + ' ATR)' : ''), 'dn');
    }
    if (c.liqFresh && c.liqFresh.length) {
      var nz = c.liqFresh[0];
      money += cell('крупнейшая плита',
        px4(nz.price) + ' · ' + (nz.side || '') +
        (nz.pct !== undefined ? ' · ' + pct(nz.pct) : ''));
    }
    /* Профиль инструмента: С-7, С-8, С-9. Не движение, а свойства —
       кто за монетой, в какой сети, давно ли листинг. */
    /* Дверь для плеча — первым в блоке: по разбору 26.08 это ПЕРВОЕ
       звено механизма, а не подробность. Свежая дверь важнее старой:
       контракт есть у всей выборки, а открыли его недавно — у
       немногих. */
    if (c.perpAt || c.perpVenue) {
      money += cell('плечо открыли',
        (c.perpVenue || '') +
        (c.perpLev ? ' ×' + (+c.perpLev) : '') +
        (c.perpDays !== undefined && c.perpDays !== null
          ? ' · ' + (+c.perpDays === 0 ? 'сегодня' : (+c.perpDays) + ' дн назад')
          : ''),
        (c.perpDays !== undefined && c.perpDays !== null && +c.perpDays <= 14)
          ? 'am' : null);
    }
    if (c.organizer) money += cell('организатор', c.organizer, 'dn');
    if (c.chain) money += cell('сеть', c.chain);
    if (c.listingDays !== undefined && c.listingDays !== null) {
      money += cell('листинг', (+c.listingDays) + ' дн назад',
        (+c.listingDays) < 60 ? 'dn' : null);
    }
    if (c.unlockShift && +c.unlockShift.days > 0) {
      money += cell('дату транша двигали', 'на ' + (+c.unlockShift.days) + ' дн', 'dn');
    }
    if (c.aligned && c.aligned.dir) {
      money += cell('три окна', c.aligned.dir === 'up' ? 'согласны вверх' : 'согласны вниз',
        c.aligned.dir === 'up' ? 'up' : 'dn');
    }
    if (c.flowFired && +c.flowFired > 1) {
      money += cell('детекторов согласно', String(+c.flowFired));
    }

    var days = '';
    if (c.byDay && c.byDay.length) {
      var mx = Math.max.apply(null, c.byDay) || 1;
      days = '<span class="obz-cell"><i>попадания по дням</i>' +
        '<span class="obz-days">' +
        c.byDay.map(function (n) {
          var h = Math.max(3, Math.round(n / mx * 26));
          return '<i class="' + (n ? '' : 'z') + '" style="height:' + h +
            'px"></i>';
        }).join('') + '</span></span>';
    }

    /* Список пробелов конкретной монеты. Идёт последним: сначала то,
       что известно, потом то, что предстоит дописать. */
    var gaps = '';
    if (c.gaps && c.gaps.length) {
      gaps = '<div class="obz-gaps"><i>заполнить руками</i>' +
        c.gaps.map(function (t) { return '<b>' + t + '</b>'; }).join(' · ') +
        '</div>';
    }

    var out = '<div class="obz-blocks">';
    if (weeks) {
      out += '<div class="obz-blk"><div class="obz-blk-k">за недели</div>' +
        '<div class="obz-blk-h">форма цикла и место в нём</div>' +
        '<div class="obz-grid">' + weeks + '</div></div>';
    }
    if (today || days) {
      out += '<div class="obz-blk"><div class="obz-blk-k">сегодня</div>' +
        '<div class="obz-blk-h">горизонт сутки-двое · часовая шкала</div>' +
        h48HTML(c, col, 610, 84) +
        '<div class="obz-grid">' + today + days + '</div></div>';
    }
    if (money) {
      out += '<div class="obz-blk"><div class="obz-blk-k">деньги</div>' +
        '<div class="obz-blk-h">чем оплачен ход · факт, затем оценка</div>' +
        '<div class="obz-grid">' + money + '</div></div>';
    }
    return out + gaps + '</div>';
  }

  function closeZoom() { zoom.classList.remove('on'); }
  zoom.addEventListener('click', function (e) {
    if (e.target === zoom) closeZoom();
  });

  /* ── Сборка ──
     Стена карточек на цилиндре снята 25.08: её место занял зал
     списком в воротах. Вместе с ней ушли сборка панелей, вращение,
     перетаскивание, ярусы и верхний ряд групп.

     Порядок, в котором монеты идут в списке зала. Стрелки в раскрытой
     карточке листают именно по нему, поэтому «следующая» означает
     «соседняя в списке». Наполняет его paintRail. */
  var ZLIST = [];
  /* Есть ли вообще открытые позиции. Если журнал решений пуст, две из
     трёх групп будут пусты не «сегодня», а всегда — и открывать зал на
     пустой вкладке значит показывать поломку вместо работы. Поэтому в
     такой день вход идёт сразу на «брать». */
  var TRADE_ANY = STARS.some(function (s) {
    var g = tradeGroupOf(s);
    return g === 'trade' || g === 'exit';
  });
  /* Зал открывается на HOLD ВСЕГДА. Раньше вход переезжал на
     «выходить», как только в книге появлялась хоть одна позиция, — и
     экран начинался с того, чего чаще всего нет: «выходить не из
     чего». Журнал держим всегда, выход бывает изредка; открываться
     нужно на первом, а не на втором.
     Выбранную группу держит GATE_KEY ниже. */

  /* Монеты группы. «Брать» — ПОРЯДОК, а не отбор: лидер прогона встаёт
     в центр дуги, места со второго по пятое — вплотную по бокам,
     остальной журнал продолжает ту же дугу наружу. Раньше здесь стоял
     фильтр по местам, и монеты вне пятёрки не попадали НИКУДА: журнал
     из сорока четырёх показывал четыре карточки. Зал обязан вмещать
     весь журнал — вопрос «кто первый» решается положением, а не
     выбрасыванием остальных. */
  var TAKE_PLACES = 5;

  /* ═══ ИНВАРИАНТ ЗАЛА (сменился вместе с Р-30) ═══
     Прежний — «сумма трёх групп равна журналу» — был верен, пока
     торговые группы были раскладкой ЖУРНАЛА. Теперь «в работе» и
     «выходить» — раскладка КНИГИ, и старая сумма стала бы ложью:
     она требовала бы записать в группы позиции, которых нет.

     Новый инвариант: «в работе» + «выходить» = открытые позиции
     книги. «Брать» — предложения входа, счёт ЗАЯВОК, не позиций,
     и в равенство не входит. Монета не потеряется от того, что не
     попала ни в одну торговую группу: HOLD показывает журнал
     целиком, дыры между группами больше нет по построению. */
  var GROUPS_ALL = { hold: [], take: [], trade: [], exit: [] };
  (function () {
    var inBook = 0;
    STARS.forEach(function (s) {
      /* HOLD — весь журнал: инвестиционный подход не выбирает. Монета
         попадает сюда И, параллельно, в свою торговую группу. */
      if (s.hold) GROUPS_ALL.hold.push(s);
      if (s.book && (s.book.usd || s.book.px)) inBook++;
      var g = tradeGroupOf(s);
      if (g) GROUPS_ALL[g].push(s);
    });
    var sum = GROUPS_ALL.trade.length + GROUPS_ALL.exit.length;
    if (sum !== inBook && window.console) {
      console.warn('зал: в группах книги ' + sum +
        ' при открытых позициях ' + inBook);
    }
  })();

  function groupList(key) {
    var list = (GROUPS_ALL[key] || []).slice();
    if (key !== 'take' && key !== 'hold') return list;

    /* Ранжированные — те, у кого есть место в СЕГОДНЯШНЕЙ выборке
       FLOW. Монета журнала, выпавшая из выборки, места не имеет: она
       идёт следом по своему правилу «какая живее», а не притворяется
       шестой. */
    var ranked = [], rest = [];
    list.forEach(function (s) {
      var p = +s.fpos || 0;
      (p >= 1 ? ranked : rest).push(s);
    });
    ranked.sort(function (a, b) { return (+a.fpos || 99) - (+b.fpos || 99); });
    rest.sort(function (a, b) {
      var d = (+b.heldRallies || 0) - (+a.heldRallies || 0);
      return d || recoveredPct(a) - recoveredPct(b);
    });
    return ranked.concat(rest);
  }

  /* Пустая группа — законный ответ, а не сбой, и текст обязан это
     говорить: «нечего» читается иначе, чем «сломалось». */
  var EMPTY = {
    hold: 'журнал лидеров пуст — держать нечего',
    take: 'правила сегодня входов не предлагают',
    trade: (TRADE_ANY
      ? 'спокойных позиций в торговой книге нет'
      : 'торговая книга пуста: правила ещё не сделали ни одного входа'),
    exit: (TRADE_ANY
      ? 'выходить не из чего — сроков и истощения нет'
      : 'торговая книга пуста, выходить не из чего')
  };

  /* Колесом раньше крутилась стена. Стены нет: внутри списка зала
     прокрутка отдаётся браузеру, мимо него — гасится, чтобы страница
     под экраном не ехала. */
  pod.addEventListener('wheel', function (e) {
    if (zoom.classList.contains('on')) return;
    if (inRail(e.target)) return;
    e.preventDefault();
  }, { passive: false });

  /* Событие приходит от самой глубокой ячейки строки, поэтому идём
     вверх по родителям и ищем список. */
  function inRail(el) {
    while (el && el !== pod) {
      if (el.classList && el.classList.contains('obr-list')) return true;
      el = el.parentNode;
    }
    return false;
  }

  /* Очередь экранов (сводка → лидеры → дашборд) теперь ведёт
     оболочка. Здесь остался только флаг «уже показались»: show()
     зовётся из одного места, но перестраховка дешевле разбора того,
     почему сцена построилась дважды. */
  var opened = false;

  /* ── Сводка портфеля в шапке ──
     Две части. Итог отвечает «чего стоят находки», список просадок —
     «что разбирать руками». Второе без первого выглядело бы
     жалобой, первое без второго — отчётом без работы над ошибками.

     Просадка идёт с фигурой и датой входа: при разборе вопрос не
     «сколько потеряли», а «какая стратегия и когда сюда завела». */
  function portLine() {
    var host = document.getElementById('obpPort');
    if (!host) return;
    var j = (O.market && O.market.journal) || {};
    /* Один источник про деньги — analytics_portfolio. Прежний
       j.port (второй расчёт в журнале лидеров) снят 23.08. */
    var PF = (O.market && O.market.portfolios) || {};
    var H = PF.hold || {}, T = PF.trade || {};
    if (!H.invested && !T.trades) { host.innerHTML = ''; return; }

    var money = function (v) {
      var n = +v || 0, a = Math.abs(n), t = n < 0 ? '−$' : '$';
      return t + (a >= 10000 ? (a / 1000).toFixed(1) + 'K' : Math.round(a));
    };
    var sign = function (v) {
      var n = +v || 0;
      return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
    };
    var tone = function (v) { return (+v || 0) >= 0 ? 'up' : 'dn'; };

    /* HOLD — чего стоят находки, если просто держать. */
    var out = 'HOLD ' + money(H.value) + ' <b class="' + tone(H.pnlPct) +
      '">' + sign(H.pnlPct) + '</b>';

    /* Трейдинг — та же лента, но по правилам. Пустая книга — не
       умолчание, а состояние, и подписана словами: тишина здесь
       читалась бы как поломка. */
    out += ' <span class="sep">·</span> по правилам ';
    if (T.open) {
      out += '<b class="' + tone(T.pnlPct) + '">' + sign(T.pnlPct) +
        '</b> <i>(' + money(T.invested) + ' в работе)</i>';
    } else if (T.trades) {
      out += '<b class="' + tone(T.realized) + '">' + money(T.realized) +
        '</b> <i>зафиксировано, позиций нет</i>';
    } else {
      out += '<span class="gaps">книга пуста</span>';
    }

    /* Потолок находок — цена отсутствующего правила выхода: разрыв
       между «держали до сих пор» и «вышли в лучшей точке каждой». */
    if (PF.peakPct !== undefined && PF.peakPct !== null) {
      out += ' <span class="sep">·</span> потолок <b class="up">' +
        sign(PF.peakPct) + '</b>';
    }

    // Пробелы в данных — рядом с деньгами, но отдельной частью: это
    // не результат, а работа, которую предстоит сделать руками.
    var g = j.gaps;
    if (g && g.gaps) {
      out += ' <span class="sep">·</span> <span class="gaps">заполнить <b>' +
        g.gaps + '</b>';
      if (g.worst && g.worst.n) {
        out += ', чаще всего <b>' + g.worst.label + '</b> (' +
          g.worst.n + ' из ' + g.coins + ')';
      }
      out += '</span>';
    }

    var L = PF.losers || [];
    if (L.length) {
      out += ' <span class="sep">·</span> <span class="loss">разобрать: ' +
        L.map(function (d) {
          return d.t + ' <b class="dn">' + sign(d.chg) + '</b> <i>' +
            (d.case || '?') + ', ' + (d.at || '').slice(5) + '</i>';
        }).join(', ');
      if (PF.losersAll > L.length) {
        out += ' <i>и ещё ' + (PF.losersAll - L.length) + '</i>';
      }
      out += '</span>';
    }
    host.innerHTML = out;
  }


  /* ── Ворота зала ───────────────────────────────────────────────
     Зал открывался сразу стеной выбранной группы: человек попадал
     внутрь списка, не выбрав его. Теперь после бриза стоит сцена —
     волна прогона, ядро с числом группы, спутники — а справа сам
     зал списком. Стена никуда не делась: клик по строке или по
     ядру открывает её. */
  var GATE = document.getElementById('obpGate');
  var GATE_KEY = 'hold';

  /* Цвета ворот СВОИ. Ярусы стены сохраняют прежние STAGE-цвета —
     их менять нельзя, на них завязано свечение карточек, — а сцена
     живёт в индиго, чтобы читаться одним предметом. */
  var GATE_C = {
    hold: { c: '#8b93c4', rgb: '139 147 196' },
    take: { c: '#6b7ae0', rgb: '107 122 224' },
    trade: { c: '#4fc98a', rgb: '79 201 138' },
    exit: { c: '#ec6f5e', rgb: '236 111 94' }
  };
  /* Кейс FLOW лежит в поле st. Цвет кейса — цвет СТРАТЕГИИ в строке
     зала: по нему видно, почему монета вообще в списке. */
  /* ВНИМАНИЕ, НЕ «ЧИНИТЬ». Составляющие цвета записаны через ПРОБЕЛ, а
     в стилях зала они вызываются старой записью через запятую. Такая
     пара недействительна, и правило браузер отбрасывает: ни заливки
     диска в ядре, ни кружка вокруг счёта в кнопках групп, ни свечений.

     ИМЕННО ЭТОТ ВИД И УТВЕРЖДЁН. Я однажды принял это за поломку и
     перевёл вызовы на действующую запись — в центре тут же вылезли
     шары под числами и подсвеченные кружки в кнопках, чего в задуманном
     виде не было. Правки откачены. Хотите включить — включайте по
     одному правилу и смотрите, а не разом. */
  var GATE_CASE = {
    hidden:   { n: 'скрытый спрос',   c: '#d9b96e', rgb: '217 185 110' },
    spring:   { n: 'пружина',         c: '#6b7ae0', rgb: '107 122 224' },
    churn:    { n: 'перемол',         c: '#8b93c4', rgb: '139 147 196' },
    fuel:     { n: 'топливо',         c: '#f0a878', rgb: '240 168 120' },
    dormant:  { n: 'спячка',          c: '#5c6598', rgb: '92 101 152' },
    taker:    { n: 'смена агрессора', c: '#c98ce0', rgb: '201 140 224' },
    leverage: { n: 'плечо',           c: '#ec6f5e', rgb: '236 111 94' }
  };
  function caseOf(s) {
    return GATE_CASE[s && s.st] ||
      { n: 'без кейса', c: '#7b83b8', rgb: '123 131 184' };
  }
  function gcol(key) { return GATE_C[key] || GATE_C.hold; }

  /* ── Волна прогона: ряд рынка на перспективной сетке ─────────── */
  function smoothAt(d, t) {
    var n = d.length - 1, f = t * n, i = Math.min(n - 1, Math.floor(f)), u = f - i;
    var p0 = d[Math.max(0, i - 1)], p1 = d[i], p2 = d[i + 1], p3 = d[Math.min(n, i + 2)];
    return 0.5 * ((2 * p1) + (-p0 + p2) * u +
      (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u +
      (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u);
  }

  /* Волна умеет рисовать ЛЮБОЙ ряд, не только рыночный: при наведении
     на монету это её собственный ход, и красится он цветом её
     стратегии. Цвета вынесены в переменные — раньше они были вписаны
     в разметку по месту, и перекрасить волну было нечем. */
  function gateWave(w, h, opt) {
    opt = opt || {};
    var d = (opt.series || (O.market || {}).series || []).slice();
    var CA = opt.c || '#ec6f5e';    /* тело, тень, заливка под кривой */
    var CB = opt.c2 || opt.c || '#ffd2ac';  /* хвост кривой и узлы */
    if (d.length < 3) return '';
    /* Поля по краям: кривая не упирается в границу кадра, а
       растворяется маской — иначе она обрывалась о колонку. */
    /* R — поле справа. По умолчанию узкое, но когда под волной стоит
       частокол, справа нужно место под будущее: линия обязана
       кончаться СЕГОДНЯ, дальше рисовать нечего. */
    var L = 26, R = (opt.right || 130), TOP = 46, BASE = h - 42, i, r;
    var max = -Infinity, min = Infinity;
    for (i = 0; i < d.length; i++) {
      if (d[i] > max) max = d[i];
      if (d[i] < min) min = d[i];
    }
    var rng = (max - min) || 1, span = w - L - R;
    var N = 160, ROWS = 13, DX = 5.2, DY = 7.4;

    function px(i2, r2) { return L + i2 / N * span + r2 * DX; }
    function py(i2, r2) {
      var k = 1 - r2 * 0.055;
      return BASE + r2 * DY - ((smoothAt(d, i2 / N) - min) / rng) * (BASE - TOP) * k;
    }
    function row(r2) {
      var s2 = '', i3;
      for (i3 = 0; i3 <= N; i3++) {
        s2 += (i3 ? 'L' : 'M') + px(i3, r2).toFixed(1) + ' ' + py(i3, r2).toFixed(1) + ' ';
      }
      return s2;
    }
    var mesh = '';
    for (r = ROWS; r >= 1; r--) {
      mesh += '<path d="' + row(r) + '" fill="none" stroke="#7d86c8" stroke-opacity="' +
        (0.16 - r * 0.009).toFixed(3) + '" stroke-width="1"/>';
    }
    var ribs = '', c2;
    for (c2 = 0; c2 <= N; c2 += 5) {
      var d2 = '', r3;
      for (r3 = 0; r3 <= ROWS; r3++) {
        d2 += (r3 ? 'L' : 'M') + px(c2, r3).toFixed(1) + ' ' + py(c2, r3).toFixed(1) + ' ';
      }
      ribs += '<path d="' + d2 + '" fill="none" stroke="#7d86c8" ' +
        'stroke-opacity=".08" stroke-width="1"/>';
    }
    var front = row(0), hx = px(N, 0), hy = py(N, 0);
    var fx = px(Math.round(N * 0.66), 0), fy = py(Math.round(N * 0.66), 0);

    return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" ' +
      'role="img" aria-label="ход рынка за ' + d.length + ' дней">' +
      '<defs>' +
        '<linearGradient id="obgWv" x1="0" y1="0" x2="1" y2="0">' +
          '<stop offset="0%" stop-color="#8b93c4"/>' +
          '<stop offset="34%" stop-color="' + CA + '"/>' +
          '<stop offset="72%" stop-color="' + CB + '"/>' +
          '<stop offset="100%" stop-color="' + CB + '"/></linearGradient>' +
        '<linearGradient id="obgUf" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0%" stop-color="' + CA + '" stop-opacity=".2"/>' +
          '<stop offset="100%" stop-color="' + CA + '" stop-opacity="0"/></linearGradient>' +
        '<filter id="obgSh" x="-20%" y="-60%" width="140%" height="260%">' +
          '<feGaussianBlur stdDeviation="16"/></filter>' +
        '<filter id="obgGl" x="-20%" y="-90%" width="140%" height="320%">' +
          '<feGaussianBlur stdDeviation="3" result="q"/>' +
          '<feMerge><feMergeNode in="q"/><feMergeNode in="SourceGraphic"/></feMerge>' +
        '</filter>' +
        '<linearGradient id="obgFadeX" x1="0" y1="0" x2="1" y2="0">' +
          '<stop offset="0%" stop-color="#fff" stop-opacity="0"/>' +
          '<stop offset="7%" stop-color="#fff" stop-opacity="1"/>' +
          '<stop offset="72%" stop-color="#fff" stop-opacity="1"/>' +
          '<stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>' +
        '<mask id="obgMFade"><rect x="0" y="0" width="' + w + '" height="' + h +
          '" fill="url(#obgFadeX)"/></mask>' +
        '<linearGradient id="obgFadeL" x1="0" y1="0" x2="1" y2="0">' +
          '<stop offset="0%" stop-color="#fff" stop-opacity="0"/>' +
          '<stop offset="6%" stop-color="#fff" stop-opacity="1"/>' +
          '<stop offset="84%" stop-color="#fff" stop-opacity="1"/>' +
          '<stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>' +
        '<mask id="obgMLine"><rect x="0" y="0" width="' + w + '" height="' + h +
          '" fill="url(#obgFadeL)"/></mask>' +
      '</defs>' +
      '<g class="obg-mesh" mask="url(#obgMFade)">' + mesh + ribs + '</g>' +
      '<g class="obg-body" mask="url(#obgMFade)">' +
        '<path d="' + front + '" fill="none" stroke="#0f1226" stroke-width="26" ' +
          'stroke-opacity=".55" filter="url(#obgSh)" transform="translate(0,22)"/>' +
        '<path d="' + front + 'L ' + (L + span) + ' ' + BASE + ' L ' + L + ' ' +
          BASE + ' Z" fill="url(#obgUf)"/>' +
        '<path d="' + front + '" fill="none" stroke="' + CA + '" stroke-width="12" ' +
          'stroke-opacity=".3" filter="url(#obgSh)"/>' +
      '</g>' +
      /* Свечение линии — ВТОРАЯ ОБВОДКА, а не фильтр размытия.
         Фильтр на рисующейся линии пересчитывается каждый кадр: сорок
         восемь кадров в секунду вместо шестидесяти, и это видно как
         подёргивание. Широкая полупрозрачная обводка под тонкой даёт
         то же свечение и не стоит ничего — обе рисуются одним штрихом,
         потому что несут один класс. */
      '<g mask="url(#obgMLine)">' +
        '<path class="obg-wv" d="' + front + '" fill="none" stroke="url(#obgWv)" ' +
          'stroke-width="11" stroke-opacity=".16" stroke-linecap="round" ' +
          'stroke-linejoin="round"/>' +
        '<path class="obg-wv" d="' + front + '" fill="none" stroke="url(#obgWv)" ' +
          'stroke-width="6" stroke-opacity=".26" stroke-linecap="round" ' +
          'stroke-linejoin="round"/>' +
        '<path class="obg-wv" d="' + front + '" fill="none" stroke="url(#obgWv)" ' +
          'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>' +
      '</g>' +
      '<g class="obg-node" transform="translate(' + fx.toFixed(1) + ',' +
        fy.toFixed(1) + ')">' +
        '<circle r="30" fill="none" stroke="' + CB + '" stroke-opacity=".26" ' +
          'stroke-dasharray="1.5 6" class="obg-spin"/>' +
        '<circle r="20" fill="none" stroke="' + CB + '" stroke-opacity=".4" ' +
          'stroke-dasharray="1.5 5" class="obg-spin obg-rev"/>' +
        '<circle r="9" fill="none" stroke="' + CB + '" stroke-opacity=".8"/>' +
        '<circle r="3.6" fill="#fff1e2" filter="url(#obgGl)"/>' +
      '</g>' +
      '<g class="obg-head">' +
        '<circle cx="' + hx.toFixed(1) + '" cy="' + hy.toFixed(1) + '" r="17" ' +
          'fill="#ffd2ac" fill-opacity=".1" filter="url(#obgSh)"/>' +
        '<circle cx="' + hx.toFixed(1) + '" cy="' + hy.toFixed(1) + '" r="4.6" ' +
          'fill="#fff1e2" filter="url(#obgGl)"><animate attributeName="r" ' +
          'values="4;6;4" dur="9s" repeatCount="indefinite"/></circle>' +
      '</g></svg>';
  }

  /* ── Строка зала: две недели и точка входа ───────────────────
     Ряд series — ровно 14 суточных точек. Цену входа знаем точно
     (book.px), а ДАТЫ входа в данных нет: поэтому уровень входа —
     сплошной факт (пунктир через всю ширину), а отметка ставится
     там, где ряд ПОСЛЕДНИЙ РАЗ пересёк этот уровень. Выдумывать
     день входа мы не будем. */
  /* Адрес графика собираем ТЕМ ЖЕ способом, что и ссылки кандидата
     в analytics_candidate: BINANCE:<пара>.P — бессрочный контракт.
     Берём готовую пару из данных, а не склеиваем из тикера: у монет
     вроде 1000LUNC пара на бирже пишется не так, как имя на экране. */
  function tvUrl(s) {
    var pair = (s && s.coin) ? s.coin : ((s && s.t ? s.t : '') + 'USDT');
    return 'https://www.tradingview.com/chart/?symbol=BINANCE:' +
           encodeURIComponent(pair) + '.P';
  }

  function railSpark(s, dly) {
    var d = (s.series || []).slice(-14), i;
    if (d.length < 3) return '';
    var W = 150, H = 34, PAD = 3;
    var entry = s.book && s.book.px ? +s.book.px : null;
    var max = -Infinity, min = Infinity;
    for (i = 0; i < d.length; i++) {
      if (d[i] > max) max = d[i];
      if (d[i] < min) min = d[i];
    }
    if (entry !== null) { if (entry > max) max = entry; if (entry < min) min = entry; }
    var rng = (max - min) || 1;
    function X(i2) { return PAD + i2 / (d.length - 1) * (W - PAD * 2); }
    function Y(v) { return H - PAD - (v - min) / rng * (H - PAD * 2); }

    var e = -1;
    if (entry !== null) {
      for (i = d.length - 2; i >= 0; i--) {
        if ((d[i] - entry) * (d[i + 1] - entry) <= 0) { e = i + 1; break; }
      }
      if (e < 0) e = 0;
    }
    var noEntry = e < 0;
    var cut = noEntry ? 0 : e;
    var before = '', after = '';
    for (i = 0; i <= cut; i++) {
      before += (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(d[i]).toFixed(1) + ' ';
    }
    for (i = cut; i < d.length; i++) {
      after += (i === cut ? 'M' : 'L') + X(i).toFixed(1) + ' ' + Y(d[i]).toFixed(1) + ' ';
    }
    var ey = Y(entry === null ? d[cut] : entry), ex = X(cut);
    var pnl = (entry && s.px) ? (s.px / entry - 1) * 100 : 0;
    var col = pnl >= 0 ? '#4fc98a' : '#ec6f5e';

    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" ' +
      'aria-hidden="true">' +
      (noEntry ? '' :
        '<line class="obr-lvl" x1="0" y1="' + ey.toFixed(1) + '" x2="' + W +
        '" y2="' + ey.toFixed(1) + '" stroke="#ffffff" stroke-opacity=".16" ' +
        'stroke-dasharray="2 4" style="animation-delay:' + (dly + 1860) + 'ms"/>') +
      '<path class="obr-ln" d="' + before + '" fill="none" stroke="#8b93c4" ' +
        'stroke-opacity=".38" stroke-width="1.2" stroke-linejoin="round" ' +
        'style="animation-delay:' + dly + 'ms"/>' +
      '<path class="obr-ln" d="' + after + '" fill="none" stroke="' + col + '" ' +
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ' +
        'style="animation-delay:' + (dly + 780) + 'ms"/>' +
      (noEntry ? '' :
        '<circle class="obr-mk" cx="' + ex.toFixed(1) + '" cy="' + ey.toFixed(1) +
        '" r="3.4" fill="none" stroke="#fff" stroke-opacity=".55" ' +
        'style="animation-delay:' + (dly + 900) + 'ms"/>' +
        '<circle class="obr-mk" cx="' + ex.toFixed(1) + '" cy="' + ey.toFixed(1) +
        '" r="1.5" fill="#fff" style="animation-delay:' + (dly + 900) + 'ms"/>') +
      '</svg>';
  }

  /* ── Зал колонкой ── */
  function railList(key) {
    if (key === 'hold') {
      return STARS.filter(function (s) { return s.hold; });
    }
    return groupList(key);
  }

  function paintRail() {
    var host = document.getElementById('obgRail');
    if (!host) return;
    var stg = null, i;
    for (i = 0; i < STAGE.length; i++) {
      if (STAGE[i].key === GATE_KEY) stg = STAGE[i];
    }
    if (!stg) return;
    var col = gcol(GATE_KEY), rows = railList(GATE_KEY);
    /* Остов колонки собираем ОДИН раз, дальше меняем только тело.
       Причина не в экономии: ряд вкладок лежит ВНУТРИ места под них, и
       пересборка всей колонки уничтожала его вместе с местом. После
       переезда вкладки пропадали почти на полсекунды — до тех пор,
       пока центр не соберётся заново и не вернёт их. */
    var slot = document.getElementById('obgTabs');
    var body = document.getElementById('obgBody');
    if (!slot || !body) {
      host.innerHTML = '<div class="obr-tabs" id="obgTabs"></div>' +
                       '<div class="obr-body" id="obgBody"></div>';
      slot = document.getElementById('obgTabs');
      body = document.getElementById('obgBody');
    }
    /* Тело переживает пересборку, значит метку гашения снимаем руками —
       раньше она уходила сама вместе со старым узлом. */
    body.classList.remove('obr-out');

    var out = '<div class="obr-head" style="--c:' + col.c + '">' +
      '<b>' + stg.n + ' · ' + rows.length + '</b></div>' +
      '<div class="obr-find" id="obgFind"><i class="obr-mag"></i>' +
        '<input type="text" id="obgQ" placeholder="поиск по монете" ' +
          'autocomplete="off" spellcheck="false">' +
        '<button class="obr-clr" type="button" id="obgClr" ' +
          'aria-label="очистить">×</button></div>';
    if (!rows.length) {
      body.innerHTML = out +
        '<div class="obr-empty">в этой группе сегодня пусто</div>';
      syncTabs();
      return;
    }
    /* Раскладываем по группам, внутри — своим порядком, и склеиваем
       обратно в одну ленту. ZLIST должен идти ТЕМ ЖЕ порядком, что и
       строки: карточка листает соседей по нему. */
    var buckets = {}, gi, gk;
    for (gi = 0; gi < RAIL_GROUPS.length; gi++) buckets[RAIL_GROUPS[gi].key] = [];
    for (i = 0; i < rows.length; i++) buckets[railGroupOf(rows[i])].push(rows[i]);
    var ordered = [], heads = {};
    for (gi = 0; gi < RAIL_GROUPS.length; gi++) {
      gk = RAIL_GROUPS[gi].key;
      if (!buckets[gk].length) continue;          /* пустую не подписываем */
      buckets[gk].sort(railSortIn(gk));
      heads[ordered.length] = RAIL_GROUPS[gi].n;  /* подпись перед этой строкой */
      ordered = ordered.concat(buckets[gk]);
    }
    rows = ordered;
    /* Карточка листает соседей по ZLIST. Раньше его наполняла только
       стена, поэтому из списка карточка не открывалась вовсе. Теперь
       список сам кладёт туда монеты В ТОМ ЖЕ ПОРЯДКЕ, что и строки. */
    ZLIST = rows.slice();
    /* В строке имя и стратегия. График на такой ширине читался лишь как
       направление, а оно и так было в проценте; сам процент строка не
       считает — ход монеты показывает центр, когда на неё смотрят.
       railSpark оставлен в коде: он ещё пригодится в центре. */
    /* ── Г-15: метки строк — сутки пополам (в бою 29.08) ──
       Правила ночного разбора ONG: тейкер-сдвиг 15%+ между
       половинами (стрелка), переворот дельты со второй половиной
       от трети первой (⟲). Половины считает python в срезе —
       взвешенно по ногам v3.1, без ног средним. Глиф ускорения
       дельты сознательно НЕ добавлен: правило не калибровано. */
    function rowMarks(s) {
      var h = s.cg && s.cg.halves;
      if (!h) return '';
      var out = '';
      if (h.tk1 && h.tk2) {
        var shift = (h.tk2 - h.tk1) / h.tk1;
        if (shift <= -0.15) {
          out += '<x-rm class="dn" title="тейкер съехал вниз: ' +
            h.tk1.toFixed(2) + ' → ' + h.tk2.toFixed(2) +
            ' — покупателя не стало">⭣</x-rm>';
        } else if (shift >= 0.15) {
          out += '<x-rm class="up" title="тейкер вырос: ' +
            h.tk1.toFixed(2) + ' → ' + h.tk2.toFixed(2) + '">⭡</x-rm>';
        }
      }
      if (h.d1 !== undefined && h.d2 !== undefined &&
          h.d1 * h.d2 < 0 && Math.abs(h.d2) >= Math.abs(h.d1) * 0.3) {
        out += '<x-rm class="' + (h.d2 > 0 ? 'up' : 'dn') +
          '" title="дельта перевернулась: ' + money(h.d1) + ' → ' +
          money(h.d2) + '">⟲</x-rm>';
      }
      return out;
    }
    out += '<div class="obr-list">';
    for (i = 0; i < rows.length; i++) {
      var s = rows[i], c = caseOf(s);
      if (heads[i]) {
        out += '<div class="obr-grp" data-grp="1">' + heads[i] + '<s></s></div>';
      }
      out += '<div class="obr-row" data-sym="' + s.t +
        '" data-case="' + c.n + '" style="--c:' + c.c +
        ';--rgb:' + c.rgb + ';animation-delay:' + (i * 165) + 'ms">' +
        '<div><i class="obr-dot"></i>' +
          '<a class="obr-tk" href="' + tvUrl(s) + '" target="_blank" ' +
            'rel="noopener" title="открыть график на TradingView">' +
            /* Первая буква отделена ВСЕГДА, даже когда цвет несёт точка:
               две разметки под два вида разошлись бы при первой правке. */
            '<b>' + String(s.t).charAt(0) + '</b>' + String(s.t).slice(1) +
          '</a>' + delistTag(s) + rowMarks(s) + '</div>' +
        '</div>';
    }
    body.innerHTML = out + '</div><div class="obr-none" id="obgNone">' +
      'ничего не найдено</div>';
    /* Привязку строк зовём ПОСЛЕ отрисовки: раньше она стояла в
       paintHero, который отрабатывает раньше списка, — узлов ещё не
       было, и клик по монете не делал ничего. */
    bindRows(rows);
    bindFind();
    /* На узком экране показываем карточку первой монеты списка сразу:
       наведения на касании нет, а клик по строке открывает полную
       сцену — без этого текст прогона не появлялся вовсе. */
    showLeaderNarrow(rows);
    /* Уход курсора карточку НЕ гасит. Она не всплывающая подсказка, а
       содержимое экрана: её читают, отводя глаза от списка, водят по
       строкам мышью и возвращаются. Сменится она только на другой
       монете — или когда сменится группа, где этой монеты уже нет. */
    /* Список перерисован — значит место под вкладки новое, и переехавшие
       кнопки надо вернуть в него. Без этого смена группы оставляла бы
       вкладки в старом, уже выброшенном узле. */
    syncTabs();
  }

  /* ── Метка делистинга в строке ──
     Стоит ВПЛОТНУЮ к тикеру, а не в столбце хода: делистинг — свойство
     инструмента, а не его движения. Монета с закрывающимся стаканом не
     должна выглядеть как обычная строка списка, даже если ход у неё
     лучший в зале.

     Почему отдельно от разлока: транш можно пересидеть, закрытие
     стакана пересидеть нельзя. Позицию закроют принудительно по цене,
     которую выберет площадка. Поэтому у метки свой цвет и она горит,
     а не тлеет.

     Дефект, из-за которого это появилось (25.08.2026): STORJ стоял в
     зале обычной строкой и держался в списке ЗАРЯЖЕННЫХ НА СЖИМ, а у
     него фьючерсы закрывались принудительным расчётом на следующий
     день. */
  function delistTag(s) {
    var d = s.delist;
    if (!d || !d.level) return '';
    var days = (d.days === null || d.days === undefined) ? null : +d.days;
    var cls = 'obr-dl', txt;
    if (d.level === 'наблюдательная метка') {
      cls += ' obr-dl-w'; txt = 'метка';
    } else if (days !== null && days <= 2) {
      cls += ' obr-dl-x'; txt = days <= 1 ? 'делистинг завтра' : 'делистинг ' + days.toFixed(0) + ' дн';
    } else if (days !== null) {
      txt = 'делистинг ' + days.toFixed(0) + ' дн';
    } else {
      cls += ' obr-dl-x'; txt = 'торги стоят';
    }
    return '<span class="' + cls + '" title="' + (d.why || '').replace(/"/g,'') + '">' +
           txt + '</span>';
  }

  /* Кнопка выхода живёт в разметке ворот и переживает перерисовку
     списка — вешаем один раз, а не на каждую смену группы. */
  (function bindOut() {
    var b = document.getElementById('obgOut');
    if (b) b.onclick = function (e) { e.stopPropagation(); hide(); };
  })();

  /* Фильтр по тикеру И по названию кейса: «топливо» тоже ищется.
     Прячем строки классом, а не перерисовкой — иначе на каждой букве
     заново запускалась бы отрисовка линий. */
  function bindFind() {
    var box = document.getElementById('obgFind');
    var inp = document.getElementById('obgQ');
    var clr = document.getElementById('obgClr');
    var none = document.getElementById('obgNone');
    if (!inp) return;

    function apply() {
      var q = (inp.value || '').trim().toLowerCase();
      var els = document.querySelectorAll('.obr-row'), i, shown = 0;
      for (i = 0; i < els.length; i++) {
        var el = els[i];
        var sym = (el.getAttribute('data-sym') || '').toLowerCase();
        var cs = el.getAttribute('data-case') || '';
        var hit = !q || sym.indexOf(q) >= 0 || cs.indexOf(q) >= 0;
        if (hit) { el.classList.remove('obr-hide'); shown++; }
        else { el.classList.add('obr-hide'); }
      }
      /* Подпись без строк — хуже, чем её отсутствие: она обещает
         раздел, которого в выдаче нет. Прячем вместе со своими. */
      var hs = document.querySelectorAll('.obr-grp'), j, nx, live;
      for (j = 0; j < hs.length; j++) {
        live = false; nx = hs[j].nextElementSibling;
        while (nx && nx.classList.contains('obr-row')) {
          if (!nx.classList.contains('obr-hide')) live = true;
          nx = nx.nextElementSibling;
        }
        if (live) hs[j].classList.remove('obr-hide');
        else hs[j].classList.add('obr-hide');
      }
      if (box) { if (q) box.classList.add('obr-has'); else box.classList.remove('obr-has'); }
      if (none) { if (!shown && q) none.classList.add('obr-on');
                  else none.classList.remove('obr-on'); }
    }
    inp.oninput = apply;
    /* Внутри поля клавиши НАШИ: общий обработчик иначе закрыл бы
       экран на первой же букве. */
    inp.onkeydown = function (e) {
      e.stopPropagation();
      if (e.key === 'Escape') { inp.value = ''; apply(); inp.blur(); }
    };
    if (clr) clr.onclick = function (e) {
      e.stopPropagation(); inp.value = ''; apply(); inp.focus();
    };
  }

  /* Клик по строке — карточка монеты, а не стена: этот экран уже зал. */
  function bindRows(rows) {
    var els = document.querySelectorAll('.obr-row'), i;
    for (i = 0; i < els.length; i++) {
      (function (el, idx) {
        /* Две цели в одной строке: тикер уводит на график, всё
           остальное открывает карточку. Ближняя цель не должна
           перехватывать дальнюю — гасим всплытие на самой ссылке. */
        var tk = el.querySelector('.obr-tk');
        if (tk) tk.onclick = function (e) { e.stopPropagation(); };
        el.onclick = function (e) {
          e.stopPropagation();
          openZoom(rows[idx], idx);
        };
        el.onmouseenter = function () { showCoin(rows[idx]); };
      })(els[i], i);
    }
  }

  /* Ход монеты: от входа, если позиция есть; иначе за две недели. */
  /* ── Порядок списка: по критическому, а не по ходу ──
     Раньше сверху стояли лучшие по проценту. Процент из строки ушёл,
     и порядок стал невидимым; но дело не только в этом. Список читают
     сверху вниз, и первым должно стоять то, что ТОРОПИТ, а не то, что
     радует: закрывающийся стакан, транш на пороге, свежий повод.

     Пороги вынесены наверх и подписаны — их придётся крутить.
     Разлоки: горизонт две недели, дальше монета уходит в «остальное».
     Событие в трёх месяцах не торопит, а место наверху занимает. */
  var RAIL_GROUPS = [
    { key: 'lead',   n: 'лидер прогона' },
    { key: 'delist', n: 'делистинг и метки' },
    { key: 'unlock', n: 'разлоки впереди' },
    { key: 'news',   n: 'поводы и новости' },
    { key: 'deep',   n: 'глубокий откуп' },
    { key: 'rest',   n: 'остальное' }
  ];
  var UNLOCK_HORIZON = 14;   /* дней */
  var DEEP_UP = 200;         /* процентов от дна */

  function railGroupOf(s) {
    /* Лидер прогона идёт первым местом — но ТОЛЬКО в журнале. В книге
       «в работе» и «выходить» место в выборке не значит ничего: там
       порядок задаёт позиция, а не сегодняшний рейтинг.

       Лидер вынимается из своей группы целиком. Срочность при этом не
       теряется: метка делистинга и срок транша остаются на самой
       строке, они не в подписи группы. */
    if (s.lead && GATE_KEY === 'hold') return 'lead';
    if (s.delist && s.delist.level) return 'delist';
    var d = s.unlockDays;
    if (d !== null && d !== undefined && +d <= UNLOCK_HORIZON) return 'unlock';
    /* Поле новостей: {t: заголовок, why: пояснение, at: дата}. Пустое —
       это НЕ «новостей нет», а «мы не смотрели»; для порядка разницы
       нет, но при чтении держать в уме. */
    if (s.news && (s.news.t || s.news.why)) return 'news';
    if (+s.up >= DEEP_UP) return 'deep';
    return 'rest';
  }

  /* Внутри группы порядок задаёт САМА группа, а не общий процент:
     у делистинга и транша это срок, у отката — глубина хода. Общий
     порядок по ходу остаётся там, где торопить нечему. */
  function railSortIn(key) {
    if (key === 'delist') return function (a, b) {
      var x = (a.delist && a.delist.days), y = (b.delist && b.delist.days);
      if (x === null || x === undefined) x = 1e9;
      if (y === null || y === undefined) y = 1e9;
      return x - y;
    };
    if (key === 'unlock') return function (a, b) { return a.unlockDays - b.unlockDays; };
    if (key === 'deep') return function (a, b) { return (+b.up) - (+a.up); };
    return function (a, b) { return pnlOf(b) - pnlOf(a); };
  }

  function pnlOf(s) {
    if (s.book && s.book.px && s.px) return (s.px / s.book.px - 1) * 100;
    var d = (s.series || []);
    if (d.length > 1 && d[0]) return (d[d.length - 1] / d[0] - 1) * 100;
    return 0;
  }

  /* ── Сцена ── */
  function ringsFor(g) {
    /* Первый операнд ОБЯЗАН стоять на строке с return: иначе движок
       сам подставит точку с запятой и функция вернёт пустоту. */
    return '<svg viewBox="0 0 200 200" aria-hidden="true">' +
      '<circle cx="100" cy="100" r="96" fill="none" stroke="rgba(' +
        g.rgb.split(' ').join(',') + ',.28)" stroke-dasharray="2 7" class="obg-spin"/>' +
      '<circle cx="100" cy="100" r="84" fill="none" stroke="rgba(' +
        g.rgb.split(' ').join(',') + ',.5)" stroke-dasharray="2 6" ' +
        'class="obg-spin obg-rev"/>' +
      '<circle cx="100" cy="100" r="72" fill="none" stroke="rgba(' +
        g.rgb.split(' ').join(',') + ',.75)" stroke-width="1.4"/>' +
      '</svg>';
  }

  function gateHint(key, n) {
    if (key === 'take') {
      return n ? { say: 'Есть вход', tail: 'правила предлагают взять' }
               : { say: 'Брать сегодня нечего', tail: 'правила не нашли ни одного входа' };
    }
    if (key === 'exit') {
      return n ? { say: 'Пора выходить', tail: 'позиция просит закрытия' }
               : { say: 'Выходить не из чего', tail: 'ни одна позиция не просит выхода' };
    }
    if (key === 'hold') {
      return { say: 'Журнал держит всё', tail: 'подход без выходов, просто ждём' };
    }
    return n ? { say: 'Позиции в работе', tail: 'ведём по правилам' }
             : { say: 'Книга пуста', tail: 'открытых позиций нет' };
  }

  function money(v) {
    var n = +v || 0, a = Math.abs(n), t = n < 0 ? '−$' : '$';
    if (a >= 1e6) return t + (a / 1e6).toFixed(1) + 'M';
    return t + (a >= 1000 ? (a / 1000).toFixed(1) + 'K' : Math.round(a));
  }
  function pct(v) {
    if (v === null || v === undefined || !isFinite(v)) return '—';
    return (v >= 0 ? '+' : '') + (+v).toFixed(1) + '%';
  }

  var ENTERED = false;
  function paintHero() {
    var host = document.getElementById('obgHero');
    if (!host) return;
    /* Первая отрисовка после открытия — вход, остальные — смена группы. */
    if (ENTERED) {
      host.classList.remove('obg-enter');
      host.classList.add('obg-swap');
    } else {
      host.classList.add('obg-enter');
      host.classList.remove('obg-swap');
      ENTERED = true;
    }
    var g = null, i;
    for (i = 0; i < STAGE.length; i++) {
      if (STAGE[i].key === GATE_KEY) { g = STAGE[i]; }
    }
    if (!g) return;
    var col = gcol(g.key), n = railList(g.key).length;
    /* Спутники строим по ВСЕМ четырём группам, а выбранную помечаем.
       Десктоп прячет помеченную стилем: там её работу делает ядро, и
       вид остаётся прежним. На планшете и телефоне ядра нет — там из
       этих же кнопок собирается ряд вкладок, и выбранная обязана
       быть среди них, иначе не видно, где ты находишься. */
    var sats = '', k, kc, kn;
    for (i = 0; i < STAGE.length; i++) {
      k = STAGE[i]; kc = gcol(k.key); kn = railList(k.key).length;
      sats += '<button class="obg-sat' + (kn ? '' : ' obg-zero') +
        (k.key === GATE_KEY ? ' obg-cur' : '') + '" type="button" ' +
        'data-gkey="' + k.key + '" style="--c:' + kc.c + ';--rgb:' + kc.rgb + '">' +
        '<span class="obg-pill">' + kn + '</span>' +
        '<span class="obg-scap">' + k.n + '</span></button>';
    }
    var h = gateHint(g.key, n);
    var PF = (O.market || {}).portfolios || {};
    var H = PF.hold || {}, T = PF.trade || {};
    host.innerHTML =
      '<div class="obg-hero">' +
        /* Ядро — ПОКАЗАНИЕ, а не кнопка: оно называет выбранную группу.
           Раньше клик по нему уводил в стену карточек, хотя стена и
           есть этот экран — переход был в никуда. */
        '<div class="obg-core">' +
          '<span class="obg-core-in" style="--c:' + col.c +
            ';--rgb:' + col.rgb + '">' +
          '<span class="obg-ring">' + ringsFor(col) +
            '<span class="obg-disc"></span>' +
            '<span class="obg-num">' + n + '</span></span>' +
          '<span class="obg-mark"><i></i><span class="obg-cap">' + g.n +
            '</span><i></i></span>' +
          '<span class="obg-sub">из <b>' + STARS.length + '</b> в журнале</span>' +
          '</span>' +
        '</div>' +
        '<div class="obg-side">' + sats + '</div>' +
      '</div>' +
      '<div class="obg-hint">' +
        '<div class="obg-say">' + h.say + '</div>' +
        '<div class="obg-tail">' + h.tail + '</div>' +
      '</div>' +
      '<div class="obg-panel">' +
        '<div class="obg-up"><span>hold</span><b>' + money(H.value) +
          '<i>' + pct(H.pnlPct) + '</i></b></div>' +
        '<div class="obg-up"><span>по правилам</span><b class="obg-up">' +
          pct(T.pnlPct) + '</b></div>' +
        '<div><span>в работе</span><b>' + money(T.invested) + '</b></div>' +
        '<div class="obg-up"><span>потолок</span><b class="obg-up">' +
          pct(PF.peakPct) + '</b></div>' +
      '</div>';
    var gh = document.getElementById('obgGhost');
    if (gh) gh.innerHTML = n;
    bindGroups();
  }

  /* Привязку зовём после КАЖДОЙ перерисовки: узлы новые.
     Здесь только спутники — переключение группы. Строки списка
     привязывает bindRows, и обязательно после его отрисовки. */
  function bindGroups() {
    var btns = document.querySelectorAll('[data-gkey]'), i;
    for (i = 0; i < btns.length; i++) {
      (function (b) {
        b.onclick = function (e) {
          e.stopPropagation();
          var k = b.getAttribute('data-gkey');
          if (k === GATE_KEY) return;
          switchGroup(k);
        };
      })(btns[i]);
    }
  }

  /* ── Карточка монеты: всё, что известно, одним взглядом ──
     Собирается ТОЛЬКО из непустых полей. Пустое место честнее строки
     с прочерком: прочерк говорит «мы смотрели и там ничего», а у нас
     чаще «мы не смотрели» — это разные вещи, и путать их нельзя.

     Порядок строк — по тому, что перебивает что. Сначала листинг и
     транш: они терминальны. Потом повод и спрос. Потом своя позиция.
     Потом состояние. Числа внизу, потому что их читают вторым
     заходом, а не первым. */
  function dm(iso) {
    var p2 = String(iso || '').split('-');
    return p2.length === 3 ? p2[2] + '.' + p2[1] : '';
  }
  function daysRu(d) {
    if (d === null || d === undefined) return '';
    d = +d;
    if (d <= 0) return 'сегодня';
    if (d === 1) return 'завтра';
    return 'через ' + d + ' дн';
  }
  /* Числа в прозе подсвечиваются. Не украшение: строка «транш 14.8%
     капитализации» читается за долю секунды, если число выделено, и
     за секунду, если нет. Подсвечиваем ТОЛЬКО величины — проценты,
     деньги, кратности, ATR, — и никогда слова. */
  function mark(t) {
    return String(t || '')
      .replace(/(−?\\d[\\d.,]*\\s?(?:%|ATR|×|раз))/g, '<em>$1</em>')
      .replace(/(\\$[\\d.,]+[KMB]?)/g, '<em>$1</em>')
      .replace(/(×\\d[\\d.,]*)/g, '<em>$1</em>');
  }
  /* Цена монеты приходит сырым числом с плавающей точкой: стоп у STORJ
     был 0.04649691666666666. Значащих цифр хватает четырёх — остальное
     не информация, а шум разрядной сетки. */
  function px4(v) {
    var n = +v;
    if (!isFinite(n)) return '';
    if (Math.abs(n) >= 100) return n.toFixed(2);
    if (Math.abs(n) >= 1) return n.toFixed(3);
    return String(+n.toPrecision(4));
  }
  /* Доля капитализации словами. У малых значений целые проценты
     врут: 0.4% и 4% — это разные монеты, а «0%» читается как «нет». */
  /* Сумма коротко: $2.6M, $537K. Прочерк вместо нуля — ноль
     ликвидаций и «не измерено» читаются одинаково, а это разное. */
  function money9(v) {
    var n = +v || 0;
    if (!n) return '—';
    if (n >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return '$' + Math.round(n / 1e3) + 'K';
    return '$' + Math.round(n);
  }

  function fuelPct(v) {
    var p = v * 100;
    if (p >= 10) return Math.round(p) + '%';
    if (p >= 1) return p.toFixed(1) + '%';
    return p.toFixed(2) + '%';
  }

  function cut(t, n) {
    t = String(t || '');
    if (t.length <= n) return t;
    var i = t.lastIndexOf(' ', n);
    return t.slice(0, i > 40 ? i : n) + '…';
  }

  function coinCard(s) {
    var c = caseOf(s), i, nd = 0;
    var ac = (s.act && GATE_C[s.act.group]) || GATE_C.hold;
    var h = '';

    h += '<div class="obc-head obc-anim" style="--nd:' + (nd++) + '">' +
      '<a class="obc-tk" href="' + tvUrl(s) + '" target="_blank" ' +
        'rel="noopener" title="открыть график на TradingView">' + s.t + '</a>' +
      /* Метка фигуры отвечает «что это за монета», а не «когда».
         Когда датчик усилия говорит «отработано», фигура остаётся
         прежней, и карточка читается противоречиво: внизу «сетап
         отработан», вверху топливо в полную силу. Приписка снимает
         противоречие, не трогая ни отбор, ни саму метку. */
      '<span class="obc-cs" style="--c:' + c.c + '">' + c.n +
        (s.effort && s.effort.state === 'spent'
          ? '<i class="obc-spent">ход отработан</i>' : '') + '</span>' +
      (s.act ? '<span class="obc-act" style="--ac:' + ac.c + '">' +
        s.act.act + (s.act.why ? '<s>' + cut(s.act.why, 52) + '</s>' : '') +
        '</span>' : '') + '</div>';

    var why = (s.act && s.act.whyFull && s.act.whyFull[0]) || s.verdict || '';
    if (why) h += '<div class="obc-why obc-anim" style="--nd:' + (nd++) + '">' +
      mark(cut(why, 300)) + '</div>';

    /* ── Факты ── */
    var f = [];
    if (s.delist && s.delist.level) {
      f.push(['#ec6f5e', 'листинг', s.delist.level +
        (s.delist.days === null || s.delist.days === undefined
          ? '' : ' · ' + daysRu(s.delist.days)) +
        (s.delist.why ? ' — ' + cut(s.delist.why, 120) : '')]);
    }
    if (s.unlockDays !== null && s.unlockDays !== undefined) {
      var u = 'транш ' + dm(s.unlockDate) + ' · ' + daysRu(s.unlockDays);
      if (s.unlockPctFloat) u += ' · ' + (+s.unlockPctFloat).toFixed(1) + '% обращения';
      if (s.unlockUsd) u += ' · ' + money(s.unlockUsd);
      u += s.unlockIns ? ' · инсайдерам' : '';
      if (s.unlockRounds && s.unlockRounds.length && s.unlockRounds[0]) {
        u += ' (' + s.unlockRounds.join(', ') + ')';
      }
      /* С-3: дату транша отодвинули. Рынок так не умеет — двигать
         расписание может только организатор. Признак сильный и живёт
         в той же строке, что сам транш: разносить их значило бы
         заставить читателя связывать две строки глазами. */
      if (s.unlockShift && +s.unlockShift.days > 0) {
        u += ' · ДАТУ ДВИГАЛИ на ' + (+s.unlockShift.days) + ' дн' +
             (s.unlockShift.to ? ' (' + dm(s.unlockShift.to) + ')' : '');
      }
      f.push(['#a6b6ff', 'разлок', u]);
    }
    if (s.news && (s.news.t || s.news.why)) {
      f.push(['#ffd678', 'повод', (s.news.t || '') +
        (s.news.why ? ' — ' + cut(s.news.why, 140) : '')]);
    }
    if (s.demand && s.demand.note) {
      f.push(['#4fc98a', 'спрос', (s.demand.label || '') +
        (s.demand.statusRu ? ' · ' + s.demand.statusRu : '') +
        ' — ' + cut(s.demand.note, 150)]);
    }
    /* ── Профиль инструмента: С-7, С-8, С-9 ──
       Не движение, а свойства: кто за монетой, в какой сети и давно
       ли листинг. Три коротких признака в одной строке — порознь
       каждый занял бы строку ради двух слов. */
    var pf = [];
    if (s.organizer) pf.push('организатор ' + s.organizer);
    if (s.chain) pf.push(s.chain);
    if (s.listingDays !== null && s.listingDays !== undefined) {
      pf.push('листинг ' + (+s.listingDays) + ' дн назад');
    }
    if (pf.length) f.push(['#8b93c4', 'профиль', pf.join(' · ')]);

    /* ── Дверь для плеча (26.08) ──
       Разбор BTR, PROM, BMT и STG дал одно общее: перед ходом на
       монете ОТКРЫВАЛИ доступ к плечу. У PROM причина названа прямо —
       листинг фьючерсов MEXC с ×20; у BTR Bitget завёл бессрочный
       с ×50. Чтобы привести чужие деньги, надо сперва открыть дверь,
       через которую они войдут.
       Показываем ЧИСЛОМ, без вердикта: порога у нас нет. */
    if (s.perpAt || s.perpVenue) {
      var dr = [];
      if (s.perpVenue) dr.push(s.perpVenue);
      if (s.perpLev) dr.push('×' + (+s.perpLev));
      if (s.perpDays !== null && s.perpDays !== undefined) {
        dr.push(+s.perpDays === 0 ? 'СЕГОДНЯ' : (+s.perpDays) + ' дн назад');
      } else if (s.perpAt) {
        dr.push(dm(s.perpAt));
      }
      f.push(['#ffd678', 'плечо открыли', dr.join(' · ')]);
    }

    /* ── Плечо: состояние и цена в капитализации ──
       Две величины про одно, поэтому одной строкой. oiState отвечает
       «застряло или разгружено», liqFuel — «сколько его относительно
       размера монеты». По разбору 26.08 второе и есть источник денег
       на ход: у BTR под ценой было больше трёх капитализаций, у PROM
       почти пусто — там плечо сбривают каждым откатом. */
    var lg = [];
    if (s.oiState === 'held') lg.push('застряло');
    else if (s.oiState === 'cleared') lg.push('разгружено');
    else if (s.oiState === 'repeat') lg.push('повторный цикл');
    if (s.liqFuel) {
      var bl = +s.liqFuel.below || 0, ab = +s.liqFuel.above || 0;
      if (bl > 0) lg.push('снизу ' + fuelPct(bl) + ' капитализации');
      if (ab > 0) lg.push('сверху ' + fuelPct(ab));
    }
    if (lg.length) {
      f.push(['#c98ce0', 'плечо', lg.join(' · ') +
        (s.liqFuel ? ' — оценка по модели, не наблюдение' : '')]);
    }

    /* ── Э-9: подписи трёх горизонтов (одобрено 29.08, «заливай
       сразу») ── Тексты карточки говорят о разном времени;
       подписи ДЕНЬ · СЕЙЧАС · ТРЕНД группируют, не меняя слов. */
    f.push(['__hz__', 'день \u00b7 диагноз положения']);
    /* Состояние — вердикт, ему место сразу под кейсом (правка
       владельца 29.08); свод пилюль идёт под ним. */
    var st = [];
    if (s.absorb && s.absorb.note) st.push(s.absorb.note);
    if (s.squeeze && s.squeeze.note) st.push(s.squeeze.note);
    if (s.squeeze && s.squeeze.hotNote) st.push(s.squeeze.hotNote);
    if (s.effort && s.effort.note) st.push(s.effort.note);
    if (s.wyckoffTest && s.wyckoffTest.note) st.push(s.wyckoffTest.note);
    if (st.length) f.push(['#8b93c4', 'состояние', cut(st.slice(0, 2).join(' · '), 220)]);

    /* ── Э-7: свод пометок пилюлями над фактами (одобрен 29.08) ── */
    var dg = [];
    if (s.unlock) {
      var u = s.unlock, uhot = (u.pct >= 10) || (u.ins >= 60 && u.pct >= 2);
      dg.push([uhot ? '#ff8a80' : '#ffd2ac', uhot,
        'разлок <b>' + u.days + ' дн</b> · <b>' + u.pct + '%</b> обращения' +
        (u.ins !== undefined ? ' · инсайдерам <b>' + u.ins + '%</b>' : '') +
        (u.drip ? ' · капля ежедневно' : '')]);
    }
    if (s.klingerLadder) {
      /* Э-8 (одобрено 29.08): лестница шкал — локальный импульс против старших.
         Согласие трёх — сильное чтение, расхождение — само чтение. */
      var L2 = s.klingerLadder;
      function kl(v) { return v === 'up' ? '\u2191' : v === 'dn' ? '\u2193' : v; }
      dg.push(['#8fd6b8', false, 'клингер <b>2ч ' + kl(L2.h2) +
        ' · 4ч ' + kl(L2.h4) + ' · день ' + kl(L2.d1) + '</b>']);
    } else if (s.klinger && (s.klinger.crossUp || s.klinger.above)) {
      dg.push(['#8fd6b8', false, s.klinger.crossUp ?
        'клингер: <b>крест вверх у дна</b>' : 'клингер <b>выше сигнала</b>']);
    }
    if (s.balances && s.balances.chg1dPct) {
      var bp = s.balances.chg1dPct;
      dg.push([bp > 0 ? '#ffd2ac' : '#9fd0e8', bp >= 1,
        (bp > 0 ? 'на биржи за сутки <b>+' : 'с бирж за сутки <b>−') +
        Math.abs(bp).toFixed(1) + '%</b> монет']);
    }
    if (s.absorb) dg.push(['#c9b8ff', false, 'поглощение у дна: <b>' +
      (s.absorb.note || 'продавца съедают') + '</b>']);
    if (dg.length) {
      f.push(['__digest__', dg.map(function (d) {
        /* Собственные теги: тип-селекторы дубля стилей зала бьют по
           div/b/span сильнее любого моего класса — x-pill им чужой. */
        return '<x-pill class="' + (d[1] ? 'hot' : '') +
          '" style="--pc:' + d[0] + '"><x-i></x-i>' +
          d[2].split('<b>').join('<x-b>').split('</b>').join('</x-b>') +
          '</x-pill>';
      }).join('')]);
    }

    f.push(['__hz__', 'сейчас \u00b7 кто жмёт в эти часы']);
    /* ── Э-8 (одобрено 29.08): строка-дивер (разбор графиков 29.08) ──
       Ход за сутки в плюс при отрицательной дельте — цена растёт
       без денег тейкера; ранний признак раздачи из разбора ONG.
       Оба числа уже были в карточке порознь — склейка по имени. */
    if (s.p1d !== undefined && +s.p1d > 1 &&
        s.cg && s.cg.cvdChg !== undefined && +s.cg.cvdChg < 0) {
      f.push(['#f0a878', 'дивер',
        'ход +' + (+s.p1d).toFixed(1) + '% НЕ оплачен дельтой (' +
        money(s.cg.cvdChg) + ' за сутки) — рост без денег']);
    }
    /* ── Э-8 (одобрено 29.08): формы суток мини-рядами — число прячет форму
       (разбор графиков 29.08: рост OI на пампе и удержание после
       читаются только рядом). Дельта из cg.series, OI из oiSpark. */
    function spark(arr, w, h) {
      if (!arr || arr.length < 4) return '';
      var mn = Math.min.apply(null, arr), mx = Math.max.apply(null, arr);
      var sp = (mx - mn) || 1, pts = [];
      for (var q = 0; q < arr.length; q++) {
        pts.push((q / (arr.length - 1) * w).toFixed(1) + ',' +
          (h - (arr[q] - mn) / sp * h).toFixed(1));
      }
      return '<svg class="obg-spk" viewBox="0 0 ' + w + ' ' + h +
        '" width="' + w + '" height="' + h +
        '"><polyline points="' + pts.join(' ') + '"/></svg>';
    }
    var spD = '';
    if (s.cg && s.cg.cvdSpark) {
      spD = spark(s.cg.cvdSpark, 64, 14);
    } else if (s.cg && s.cg.series) {   /* стендовый полный ряд */
      spD = spark(s.cg.series.map(function (b) { return +b.cvd || 0; }),
                  64, 14);
    }
    var spO = s.oiSpark ? spark(s.oiSpark, 64, 14) : '';
    if (spD || spO) {
      f.push(['#8b93c4', 'формы суток',
        (spD ? spD + ' дельта' : '') +
        (spD && spO ? ' \u00b7 ' : '') +
        (spO ? spO + ' плечо' : '')]);
    }
    /* ── Э-8 (одобрено 29.08): крупные сделки (big из интрадея; поля уже
       считались каждый прогон и лежали без показа). ── */
    if (s.bigCount) {
      f.push(['#9fd0e8', 'крупные',
        'за двое суток ' + s.bigCount + ' баров крупняка: покупок ' +
        (s.bigBuys || 0) + ', продаж ' + (s.bigSells || 0) +
        (s.bigMax ? ' · пик размера ×' + s.bigMax : '')]);
    }
    /* Г-15: чем оплачено движение — спот против плеча. Пустой спот у
       перповой монеты — не ошибка, а ответ: ход оплачен плечом. */
    if (s.cg && (s.cg.spotUsd || s.cg.taker)) {
      var pay;
      if (!s.cg.spotUsd) {
        pay = 'спота нет — ход оплачен плечом';
      } else {
        pay = 'спот ' + money(s.cg.spotUsd) +
          (s.cg.spotTaker ? ', тейкер ' + (+s.cg.spotTaker).toFixed(2) : '') +
          (s.cg.taker ? ' · фьюч, тейкер ' + (+s.cg.taker).toFixed(2) : '') +
          /* Г-2: во сколько раз плечо перекрывает спот — дневной
             вопрос из PROMPT_DAILY_NEWS числом по монете. */
          (s.cg.fsRatio ? ' · фьюч к споту ×' + s.cg.fsRatio : '');
      }
      if (s.cg.cvdChg) {
        pay += ' · дельта за сутки ' + (s.cg.cvdChg > 0 ? '+' : '') +
          money(s.cg.cvdChg);
      }
      f.push(['#9fd0e8', 'чем оплачено', pay]);
    }
    /* Ликвидации Coinglass — ФАКТ, а не модель. Держим отдельной
       строкой от «плеча» именно поэтому: наблюдение и оценка не
       должны читаться как одно. */
    if (s.liq24h) {
      var lqs = s.liq24h.note ||
        ('лонгов ' + money(s.liq24h.long || 0) +
         ' против шортов ' + money(s.liq24h.short || 0));
      f.push(['#ec6f5e', 'ликвидации', 'за сутки ' + cut(lqs, 150)]);
    }

    /* Т-1: киты Hyperliquid. Контекст, не сигнал — кит бывает неправ,
       и урок Loracle записан: сорок миллионов на угадывании HYPE. */
    if (s.hlWhales && (s.hlWhales.n || s.hlWhales.note)) {
      f.push(['#7ae8ba', 'киты',
        (s.hlWhales.note || ('лонгов ' + (s.hlWhales.long || 0) +
         ', шортов ' + (s.hlWhales.short || 0))) +
        (s.hlWhales.n ? ' · счетов ' + s.hlWhales.n : '')]);
    }

    /* Т-5: стоп внутри плиты снимут виком, не двигая рынок против
       позиции. Показываем ТОЛЬКО когда попал: молчание и есть «чисто». */
    if (s.stopInPlate && s.stopInPlate.note) {
      f.push(['#ff7d7d', 'стоп', s.stopInPlate.note]);
    }

    if (s.book && s.book.usd) {
      f.push(['#dfe6f2', 'в книге', money(s.book.usd) + ' от ' + px4(s.book.px) +
        ' · ход ' + pct(pnlOf(s))]);
    }
    if (s.exitWhy && s.exitWhy.length) {
      f.push(['#f0a878', 'торопит', cut(s.exitWhy.join(' · '), 160)]);
    }
    if (f.length) {
      /* Обёртка НЕ анимируется: иначе задержки сложились бы, и строки
         внутри поехали бы дважды. Едет каждая строка сама. */
      h += '<div class="obc-facts">';
      for (i = 0; i < f.length; i++) {
        if (f[i][0] === '__hz__') {
          h += '<div class="obc-hz obc-anim" style="--nd:' + (nd++) +
            '">' + f[i][1] + '</div>';
          continue;
        }
        if (f[i][0] === '__digest__') {
          h += '<x-dg>' + f[i][1] + '</x-dg>';
          continue;
        }
        h += '<div class="obc-fact obc-anim" style="--fc:' + f[i][0] +
          ';--nd:' + (nd++) + '">' +
          '<b>' + f[i][1] + '</b><span>' + mark(f[i][2]) + '</span></div>';
      }
      h += '</div>';
    }

    /* ── Числа ── */
    var n = [];
    function num(lab, val, kind) { if (val !== null) n.push([lab, val, kind || '']); }
    /* «Цена», «от дна» и «от пика» из полосы СНЯТЫ (29.08): они
       переехали на график (markCoinWave) — число о линии читается у
       самой линии, а не в таблице под ней. */
    /* Капитализация приходит уже подписанной строкой, вроде «$78M».
       Прочерк в данных означает «не знаем» — такую не показываем вовсе:
       пустое место честнее, чем строка с прочерком. */
    /* Полоса ТРЕМЯ группами (правка владельца 29.08):
       размер | за сутки | цена плеча. Разделитель — служебная
       запись '|', рендер ниже рисует её штрихом. */
    var cg = s.cg || null;
    num('капитализация', (s.cap && s.cap !== '—') ? s.cap : null);
    num('флоат', s.floatPct ? Math.round(s.floatPct) + '%' : null,
        (+s.floatPct < 25 ? 'dn' : ''));
    /* «к норме» = суточный оборот против медианы месяца.
       gsep — первая плитка группы: разделитель рисуется НА ней
       чёрточкой, отдельный элемент ломал счёт детей узкой ветки. */
    num('объём к норме', s.v1d ? '×' + (+s.v1d).toFixed(1) : null,
        (+s.v1d > 3 ? 'up gsep' : 'gsep'));
    if (cg && cg.oiChgPct !== undefined && cg.oiChgPct !== null) {
      num('OI за сутки', pct(cg.oiChgPct), +cg.oiChgPct > 0 ? 'up' : 'dn');
    }
    num('ход за сутки', s.p1d === undefined || s.p1d === null ? null : pct(s.p1d),
        (+s.p1d >= 0 ? 'up' : 'dn'));
    /* Бывший «тейкер»: перевес рыночных покупок над продажами за
       сутки; ×1 — равновесие, ниже — давят продавцы. */
    if (cg && cg.taker) {
      num('покупки к продажам', '×' + (+cg.taker).toFixed(2),
          +cg.taker < 1 ? 'dn' : 'up');
    }
    num('фандинг', s.fund === undefined || s.fund === null ? null : (+s.fund).toFixed(3) + '%',
        (+s.fund < 0 ? 'up gsep' : 'gsep'));
    if (n.length) {
      h += '<div class="obc-nums">';
      for (i = 0; i < n.length && i < 12; i++) {
        h += '<div class="obc-num obc-anim ' + n[i][2] + '" style="--nd:' +
          (nd++) + '"><b>' + n[i][0] + '</b><i>' + n[i][1] + '</i></div>';
      }
      h += '</div>';
    }

    /* ── Что СЧИТАЕТ стратегия. Не прогноз: линии будущей цены здесь
       нет и не будет — считаются уровни от структуры и ожидание по
       прошлым эпизодам журнала. ── */
    var calc = [];
    /* Стоп ВЫШЕ цены — не ошибка знака, а замороженная зона: её
       посчитали при появлении монеты в журнале и с тех пор не
       пересчитывали, а цена успела уйти ниже. Печатать такое числом
       нельзя — оно читается как план, которого нет.
       Правило зоны не трогаем, только называем вещи своими именами. */
    if (s.stop) {
      var pxNow = +s.px || 0;
      if (pxNow > 0 && +s.stop >= pxNow) {
        calc.push('стоп <em>' + px4(s.stop) + '</em> УЖЕ ПРОЙДЕН — ' +
          'цена ниже него на ' + Math.round((1 - pxNow / +s.stop) * 100) +
          '%, зона не пересчитывалась');
      } else {
        calc.push('стоп <em>' + px4(s.stop) + '</em>');
      }
    }
    if (s.levels && s.levels.note) calc.push(s.levels.note);
    if (s.journalExp && s.journalExp.n) {
      /* Один эпизод — это не ожидание, а единичный случай, и подавать
         его как величину нельзя: рядом стоят числа, посчитанные по
         сотням баров. Поэтому при n = 1 меняем и слово, и порядок —
         сначала оговорка, потом число. */
      if (+s.journalExp.n === 1) {
        calc.push('всего <em>один</em> эпизод в журнале, ход был ' +
          pct(s.journalExp.expPct) + ' — не ожидание, а случай');
      } else {
        calc.push('ожидание по журналу <em>' + pct(s.journalExp.expPct) +
          '</em> на ' + s.journalExp.n + ' эпизодах');
      }
    }
    /* Реакция на уровень: отбой значит уровень защитили, закрепление
       за ним — сняли. Это единственное, что отличает «плита впереди»
       от «плита пробита», и без неё уровень читается наполовину. */
    var lvb = (s.levels && s.levels.below) || null;
    var lva = (s.levels && s.levels.above) || null;
    var rc = (lvb && lvb.reaction) || (lva && lva.reaction) || null;
    if (rc && rc.kind) {
      calc.push('реакция на уровень — <em>' + rc.kind + '</em>' +
        (rc.bars_ago !== undefined ? ' ' + rc.bars_ago + ' д назад' : ''));
    }
    /* Согласованность трёх окон: 6ч, сутки, неделя. Верить монете,
       чей ход совпал на всех трёх, — перенос из оценки трейдеров. */
    if (s.aligned && s.aligned.dir) {
      calc.push('три окна согласны — ход <em>' +
        (s.aligned.dir === 'up' ? 'вверх' : 'вниз') + '</em>');
    }
    /* Сколько подкейсов FLOW сработало разом. Победитель показан
       фигурой, а это — сколько ещё с ним согласны. */
    if (s.flowFired && +s.flowFired > 1) {
      calc.push('детекторов согласно <em>' + (+s.flowFired) + '</em>');
    }
    if (calc.length) {
      h += '<div class="obc-hz obc-anim" style="--nd:' + (nd++) +
        '">тренд \u00b7 структура и стратегия</div>' +
        '<div class="obc-calc obc-anim" style="--nd:' + (nd++) + '">' +
        calc.join(' · ') + '</div>';
    }
    return h;
  }

  /* Карточка живёт только там, где освободилось место, и только пока
     курсор на строке. Повторное наведение на ту же монету ничего не
     пересобирает — иначе лесенка играла бы на каждом дрожании мыши. */
  var CARD_SYM = null;
  /* НА УЗКОМ ЭКРАНЕ КАРТОЧКА ПОКАЗЫВАЕТСЯ САМА. Наведения на касании
     нет, а клик по строке открывает полную сцену монеты — значит текст
     прогона на планшете и телефоне не появлялся вовсе. Показываем
     лидера прогона сразу после сборки; выбор строки заменит его. */
  function showLeaderNarrow(list) {
    if (window.innerWidth >= 900) return;
    var lead = null, i;
    for (i = 0; i < list.length; i++) if (list[i] && list[i].lead) { lead = list[i]; break; }
    if (!lead) lead = list[0];
    if (lead) showCoin(lead);
  }
  function showCoin(s) {
    var card = document.getElementById('obgCard');
    var hero = document.getElementById('obgHero');
    if (!card || !hero || !s) return;
    /* На компьютере карточка ждёт, пока ядро уйдёт и освободит место.
       На узком экране ядра нет вовсе, а карточка стоит в потоке между
       волной и списком — ждать нечего, иначе весь текст прогона так и
       не появляется, и остаётся один список. */
    var flow = window.innerWidth < 900;
    if (!flow && !hero.classList.contains('obg-gone')) return;
    if (CARD_SYM === s.t) return;
    CARD_SYM = s.t;
    /* Кнопкам групп нечего делать ПОД карточкой: раннее наведение
       обгоняло таймер гашения, и кнопки просвечивали сквозь
       карточку (скрин владельца 29.08). Флаг TUCKED бережёт от
       повторного полёта. */
    if (window.innerWidth > 900 && !TUCKED) tuckTabs();
    /* место считается от ядра только там, где карточка лежит поверх */
    card.style.top = flow ? '' : hero.offsetTop + 'px';
    card.innerHTML = coinCard(s);
    card.classList.add('obg-on');
    paintWave(s);      /* волна становится ходом этой монеты */
  }
  /* keepWave — для смены группы: там волна и так будет собрана заново,
     своим чередом, когда догорит старая. Без этой оговорки карточка
     тянула волну за собой ПРЯМО В МОМЕНТ КЛИКА: новая линия появлялась
     поверх ещё гаснущей старой, и вся хореография перехода рушилась. */
  /* Место карточки считается от ядра и запоминается один раз. Меняется
     ширина окна — меняется и высота волны, а с ней место ядра; без
     пересчёта карточка уезжала бы на волну или под неё. */
  addEventListener('resize', function () {
    var card = document.getElementById('obgCard');
    var hero = document.getElementById('obgHero');
    if (card && hero && CARD_SYM !== null) {
      card.style.top = window.innerWidth < 900 ? '' : hero.offsetTop + 'px';
    }
  });

  function hideCoin(keepWave) {
    var card = document.getElementById('obgCard');
    if (!card) return;
    if (CARD_SYM === null) return;   /* уже убрана — волну не дёргаем */
    CARD_SYM = null;
    card.classList.remove('obg-on');
    if (!keepWave) { paintWave(); }
  }

  /* Волна пересобирается ЦЕЛИКОМ — только так она рисуется заново.
     Анимация отрисовки играет один раз на узел; чтобы линия пошла с
     начала, нужен новый узел, а не новый класс. Раньше волна строилась
     единожды на весь сеанс, и при смене группы менялось только число
     за ней — оно и щёлкало в одиночку.

     Число вписывает paintHero, поэтому зовём в паре и в этом порядке. */
  /* ── Что стоит на частоколе ──
     У монеты — её собственные сроки. Без наведения — календарь рынка:
     он касается всех, и в этот момент экран говорит про рынок.
     Возвращаем [дней, вид, срочно, заголовок, пояснение]. */
  var PIN_C = {
    dl: ['#ec6f5e', 'rgba(236,111,94,.55)', 'делистинг'],
    un: ['#a6b6ff', 'rgba(166,182,255,.5)', 'разлок'],
    ev: ['#ffd678', 'rgba(255,214,120,.45)', 'событие'],
    pr: ['#7ae8ba', 'rgba(122,232,186,.45)', 'наблюдение']
  };
  function eventsFor(coin) {
    var out = [], i;
    if (coin) {
      if (coin.delist && coin.delist.level && coin.delist.days !== null &&
          coin.delist.days !== undefined) {
        out.push([+coin.delist.days, 'dl', +coin.delist.days <= 2,
          coin.delist.level, coin.delist.why || '']);
      }
      if (coin.unlockDays !== null && coin.unlockDays !== undefined) {
        out.push([+coin.unlockDays, 'un', +coin.unlockDays <= 3,
          'транш ' + dm(coin.unlockDate),
          (coin.unlockPctFloat ? (+coin.unlockPctFloat).toFixed(1) +
            '% обращения' : '') + (coin.unlockIns ? ' · инсайдерам' : '')]);
      }
      if (coin.squeeze && coin.squeeze.charged) {
        out.push([0, 'pr', false, 'заряжен на сжим', coin.squeeze.note || '']);
      }
      return out;
    }
    /* Календарь лежит внутри parts — соседние поля разрешения там же. */
    var prm = (O.market || {}).permission || {};
    var cal = ((prm.parts || {}).calendar || {}).items || [];
    for (i = 0; i < cal.length; i++) {
      var k = cal[i].kind === 'unlock' ? 'un'
            : (cal[i].kind === 'delist' ? 'dl' : 'ev');
      out.push([+cal[i].days || 0, k, !!cal[i].running,
        cal[i].title || '', cal[i].note || '']);
    }
    return out;
  }

  /* Шкала приблизительная НАРОЧНО: сроки транша и делистинга объявляют
     по часовому поясу площадки, а «через 4 дн» — это про день, а не про
     минуту. Точная сетка обещала бы точность, которой нет. */
  var PICKET_DAYS = 21;
  function picket(coin, nowFrac) {
    var ev = eventsFor(coin), i, right = 0.965;
    var span = right - nowFrac;
    function xOf(d) {
      var t = Math.max(0, Math.min(1, (+d) / PICKET_DAYS));
      return (nowFrac + t * span) * 100;
    }
    /* Ярус выбирается по СОСЕДЯМ, а не по порядку в списке. Девять
       событий рынка приходятся на три дня — по очереди они слипались
       в ком. Кладём на первый ярус, где ближайшая точка дальше двух с
       половиной процентов ширины; ближе — этажом выше. */
    ev = ev.slice().sort(function (a, b) { return a[0] - b[0]; });
    var busy = [-99, -99, -99, -99], pins = '';
    for (i = 0; i < ev.length && i < 10; i++) {
      var c = PIN_C[ev[i][1]] || PIN_C.ev, x = xOf(ev[i][0]), lvl = -1, j;
      for (j = 0; j < busy.length; j++) {
        if (x - busy[j] > 2.5) { lvl = j; break; }
      }
      if (lvl < 0) {
        /* Свободного яруса нет — все четыре заняты рядом. Раньше точка
           садилась на последний, ПОВЕРХ уже стоявшей там: две метки
           совпадали до пикселя, и до нижней было не дотянуться мышью.
           Теперь берём ярус, где предыдущая дальше всех, и отодвигаем
           вправо на ширину точки. Сдвиг врёт о сроке меньше чем на
           день — шкала и так приблизительная. */
        var best = 0;
        for (j = 1; j < busy.length; j++) { if (busy[j] < busy[best]) best = j; }
        lvl = best;
        x = Math.max(x, busy[lvl] + 1.4);
      }
      busy[lvl] = x;
      pins += '<div class="obg-pin' + (ev[i][2] ? ' obg-hot' : '') + '" style="left:' +
        x.toFixed(2) + '%;top:' + (15 + lvl * 11) + '%;--pc:' + c[0] +
        ';--pg:' + c[1] + ';--ph:' + (66 - lvl * 11) + 'px;--pd:' + i + '">' +
        '<i></i><s></s><u><b>' + c[2] + ' · ' + daysRu(ev[i][0]) + '</b>' +
        '<em>' + cut(ev[i][3], 70) + '</em>' +
        (ev[i][4] ? '<br>' + cut(ev[i][4], 150) : '') + '</u></div>';
    }
    /* Шкала: сегодня и дальше шагом в три дня. Прошлое подписей не
       имеет — там линия, она и есть подпись. */
    var base = new Date(((O.market || {}).ts || '').slice(0, 10) || Date.now());
    if (isNaN(base.getTime())) { base = new Date(); }
    var MON = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн',
               'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    var ax = '<div class="obg-tick obg-tnow" style="left:' +
      (nowFrac * 100).toFixed(2) + '%"><s></s><b>сегодня</b></div>';
    for (i = 3; i <= PICKET_DAYS; i += 3) {
      var dt = new Date(base.getTime());
      dt.setDate(dt.getDate() + i);
      ax += '<div class="obg-tick" style="left:' + xOf(i).toFixed(2) + '%">' +
        '<s></s><b>' + dt.getDate() + ' ' + MON[dt.getMonth()] + '</b></div>';
    }
    return { pins: pins, axis: ax };
  }

  /* Наведение на точку переносит её текст в общее окно подсказки.
     Копируем содержимое, а не строим заново: разметка уже собрана
     частоколом, и второй сборщик того же текста однажды разошёлся бы
     с первым. Цвет ярлыка берём у самой точки. */
  function bindPins(host) {
    var tip = host.querySelector('.obg-tip');
    var layer = host.querySelector('.obg-pins');
    if (!tip || !layer) return;
    var pins = layer.querySelectorAll('.obg-pin'), i;
    for (i = 0; i < pins.length; i++) {
      (function (pin) {
        pin.onmouseenter = function () {
          var src = pin.querySelector('u');
          if (!src) return;
          tip.innerHTML = src.innerHTML;
          tip.style.setProperty('--pc', pin.style.getPropertyValue('--pc'));
          tip.classList.add('obg-on');
        };
      })(pins[i]);
    }
    /* Гасим на уходе со ВСЕГО слоя точек, а не с каждой: между ярусами
       есть зазоры, и по ним подсказка мигала бы. */
    layer.onmouseleave = function () { tip.classList.remove('obg-on'); };
  }

  /* Поле будущего справа — ОДНО число на волну и метки: второй
     экземпляр разошёлся бы при первой правке. */
  var WAVE_RIGHT = 380;

  /* ── Метки монеты на волне (29.08) ──
     Координаты снимаются С НАРИСОВАННОЙ кривой, а не пересчитываются
     по формуле: сглаживание волны перелетает минимум ряда, и линия
     дна по формуле висела выше видимого низа — поймано глазами на
     прототипе. Пик почти всегда ЗА кадром (серия короче жизни
     монеты), поэтому вместо линии — штрихи вверх и подпись. */
  function markCoinWave(s, host) {
    var svg = host && host.querySelector('svg');
    if (!svg || !s || !s.series) return;
    var front = svg.querySelector('path[stroke^="url"]');
    if (!front || !front.getTotalLength) return;
    var W = 1000, H = 300, L = 26, TOP = 46, EDGE = W - WAVE_RIGHT;
    var len = front.getTotalLength(), yLo = -Infinity, yHi = Infinity,
        pEnd = null, k, pt;
    for (k = 0; k <= 220; k++) {
      pt = front.getPointAtLength(len * k / 220);
      if (pt.x > EDGE + 1) continue;        /* хвост маски не считаем */
      if (pt.y > yLo) yLo = pt.y;
      if (pt.y < yHi) yHi = pt.y;
      if (!pEnd || pt.x > pEnd.x) pEnd = pt;
    }
    if (!pEnd) return;
    /* Цена -> высота: калибровка по ДВУМ точкам самой кривой —
       конец равен текущей цене, низ равен дну (цена / (1 + up)).
       Ряд series для этого не нужен: в бою он нормирован формой
       волны, а не ценами, и калибровка по нему клала опору к
       потолку (кадр владельца 29.08, BLESS). */
    var pxNow = +s.px || 0;
    var lowPx = (s.up !== undefined && s.up !== null && pxNow)
      ? pxNow / (1 + (+s.up) / 100) : null;
    function yOf(p) {
      if (!pxNow || lowPx === null || pxNow === lowPx) return null;
      return pEnd.y + (pxNow - p) / (pxNow - lowPx) * (yLo - pEnd.y);
    }
    var cc = caseOf(s).c;
    var NS = 'http://www.w3.org/2000/svg';
    function ln(x1, y1, x2, y2, dash, op, stroke) {
      var l = document.createElementNS(NS, 'line');
      l.setAttribute('x1', x1); l.setAttribute('y1', y1);
      l.setAttribute('x2', x2); l.setAttribute('y2', y2);
      l.setAttribute('stroke', stroke || '#aab3d8');
      l.setAttribute('stroke-opacity', op);
      l.setAttribute('stroke-width', '1');
      if (dash) l.setAttribute('stroke-dasharray', dash);
      l.setAttribute('class', 'obg-mkln');
      svg.appendChild(l);
    }
    ln(L, yLo, EDGE + 44, yLo, '2 5', '.5');            /* дно      */
    ln(EDGE + 6, pEnd.y, EDGE + 40, pEnd.y, '', '.55', cc); /* цена */
    ln(EDGE + 8, TOP - 14, EDGE + 8, TOP - 34, '2 4', '.45'); /* пик */
    ln(EDGE + 16, TOP - 10, EDGE + 16, TOP - 34, '2 4', '.3');
    function tag(x, y, html, cls) {
      var el = document.createElement('div');
      el.className = 'obg-mk ' + (cls || '');
      el.style.left = (x / W * 100).toFixed(2) + '%';
      el.style.top = (y / H * 100).toFixed(2) + '%';
      el.innerHTML = html;
      host.appendChild(el);
    }
    /* Опора и плита (29.08): рисуются НА графике, строка из карточки
       снята. Уровень за кадром честно не рисуем. */
    /* Поле цены уровня в боевых метриках зовётся price — сверено по
       живому документу 29.08 (стендовое px было именем макета). */
    var lvb = s.levels && s.levels.below && +s.levels.below.price;
    var lva = s.levels && s.levels.above && +s.levels.above.price;
    var yOp = lvb ? yOf(lvb) : null, yPl = lva ? yOf(lva) : null;
    if (yOp !== null && !isFinite(yOp)) yOp = null;
    if (yPl !== null && !isFinite(yPl)) yPl = null;
    if (yOp !== null && (yOp < TOP - 6 || yOp > H - 8)) yOp = null;
    if (yPl !== null && (yPl < TOP - 6 || yPl > H - 8)) yPl = null;
    /* Подписи уровней — ПРЯМО НА ЛИНИЯХ, слева (правка 29.08):
       как на терминале, без шкалы; правое поле остаётся цене, дну и
       пику. Если линия липнет к дну ряда — подпись уходит под неё. */
    /* ── Э-8 (одобрено 29.08): зоны ликвидаций на волне (владелец 29.08: не
       ждать полигон, внедрять и сверять с визуальной картой
       Coinglass). Полоса плотности с подписью топлива; правило
       чтения из analytics_liqmap остаётся: скопление плеча НЕ
       означает, что цена туда пойдёт. */
    if (s.liqZones) {
      for (var zi = 0; zi < s.liqZones.length && zi < 3; zi++) {
        var Z = s.liqZones[zi];
        var zLo = yOf(Z.lo), zHi = yOf(Z.hi);
        if (zLo === null || zHi === null) continue;
        var zt = Math.min(zLo, zHi), zh = Math.abs(zLo - zHi);
        if (zt > H - 8 || zt + zh < TOP - 6) continue;
        var zd = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        zd.setAttribute('x', L); zd.setAttribute('y', Math.max(TOP - 6, zt));
        zd.setAttribute('width', EDGE + 40 - L);
        zd.setAttribute('height', Math.max(3, zh));
        zd.setAttribute('class', 'obg-liqz');
        svg.appendChild(zd);
        tag(L + 8, zt - 6, 'топливо <b>' + money(Z.fuel) + '</b>',
            'obg-mk-lv obg-mk-onln');
      }
    }
    if (yOp !== null) {
      ln(L, yOp, EDGE + 40, yOp, '1 6', '.3');
      tag(L + 8, yOp + (Math.abs(yOp - yLo) < 12 ? 9 : -7),
          'опора <b>' + px4(lvb) + '</b>', 'obg-mk-lv obg-mk-onln');
    }
    if (yPl !== null) {
      ln(L, yPl, EDGE + 40, yPl, '1 6', '.3');
      tag(L + 8, yPl - 7, 'плита <b>' + px4(lva) + '</b>',
          'obg-mk-lv obg-mk-onln');
    }

    /* Общий развод подписей: желаемые высоты, сортировка, зазор.
       Цена главнее — соседи уступают ей, не она им. */
    host.style.setProperty('--mkc', cc);
    var tags = [];
    if (s.ath) {
      tags.push({y: TOP - 24, x: EDGE + 34, cls: 'obg-mk-dim',
        html: '<b>−' + Math.round(+s.ath) + '%</b>от пика' +
              '<span class="obg-mkx"> · выше кадра</span>'});
    }
    if (s.px !== undefined && s.px !== null) {
      tags.push({y: pEnd.y, x: EDGE + 34, cls: 'obg-mk-px', main: true,
        html: '<b>' + px4(s.px) + '</b>сейчас'});
    }
    if (s.up !== undefined && s.up !== null) {
      tags.push({y: yLo - 1, x: EDGE + 34, cls: 'obg-mk-dim',
        html: '<b>+' + Math.round(+s.up) + '%</b>от дна'});
    }
    var GAP = 17;
    tags.sort(function (a, b) { return a.y - b.y; });
    for (k = 1; k < tags.length; k++) {
      if (tags[k].y - tags[k - 1].y < GAP) {
        if (tags[k].main) tags[k - 1].y = tags[k].y - GAP;
        else tags[k].y = tags[k - 1].y + GAP;
      }
    }
    for (k = tags.length - 2; k >= 0; k--) {
      if (tags[k + 1].y - tags[k].y < GAP) tags[k].y = tags[k + 1].y - GAP;
    }
    for (k = 0; k < tags.length; k++) {
      tag(tags[k].x, tags[k].y, tags[k].html, tags[k].cls);
    }
  }

  function paintWave(coin) {
    var inner = document.getElementById('obgInner');
    if (!inner) return;
    var host = inner.querySelector('.obg-wave');
    if (!host) return;
    var opt = null;
    if (coin && coin.series && coin.series.length > 2) {
      var cc = caseOf(coin);
      opt = { series: coin.series, c: cc.c, c2: cc.c };
    }
    /* Наведение — не вход в зал: линия рисуется вчетверо быстрее.
       Шестисекундная церемония на каждое движение мыши была бы пыткой. */
    if (coin) { host.classList.add('obg-quick'); }
    else { host.classList.remove('obg-quick'); }

    /* Поле справа под будущее. Держим его ВСЕГДА — и на рынке, и на
       монете: иначе шкала прыгала бы на каждое наведение. */
    var RIGHT = WAVE_RIGHT, L = 26;
    var nowFrac = (L + (1000 - L - RIGHT)) / 1000;
    if (!opt) { opt = {}; }
    opt.right = RIGHT;
    var pk = picket(coin, nowFrac);

    host.innerHTML = '<div class="obg-ghost" id="obgGhost"></div>' +
                     gateWave(1000, 300, opt) +
                     '<div class="obg-now" style="left:' +
                       (nowFrac * 100).toFixed(2) + '%"></div>' +
                     '<div class="obg-pins">' + pk.pins + '</div>' +
                     '<div class="obg-tip" id="obgTip" style="left:' +
                       (nowFrac * 100 + 1.5).toFixed(2) + '%"></div>';
    var ax = document.getElementById('obgAxis');
    if (ax) { ax.innerHTML = pk.axis; }
    bindPins(host);
    if (coin) { markCoinWave(coin, host); }
    /* Число за волной вписывает paintHero, и при наведении его нет:
       за монетой стоит её ход, а не счёт группы. */
    if (!coin) {
      var gh = document.getElementById('obgGhost');
      var g2 = null, i2;
      for (i2 = 0; i2 < STAGE.length; i2++) {
        if (STAGE[i2].key === GATE_KEY) { g2 = STAGE[i2]; }
      }
      if (gh && g2) { gh.innerHTML = railList(g2.key).length; }
    }
  }

  function openGate() {
    if (!GATE) { bail('ворота не найдены'); return; }
    var inner = document.getElementById('obgInner');
    if (inner) {
      inner.innerHTML = '<div class="obg-wave"></div>' +
                        '<div class="obg-axis" id="obgAxis"></div>' +
                        '<div id="obgHero"></div>' +
                        '<div class="obg-card" id="obgCard"></div>';
      inner.classList.remove('obg-swap');
      inner.classList.remove('obg-swapout');
    }
    /* Сцена собрана заново — карточки больше нет. Не забудь мы про неё,
       и та же монета второй раз не показалась бы: код решил бы, что она
       уже на экране. */
    CARD_SYM = null;
    paintWave();
    ENTERED = false;
    paintHero();
    paintRail();
    pod.classList.add('obp-gated');
    GATE.classList.add('on');
    armTailFade();
  }

  /* Отсчёт до гашения нижнего блока. Таймеры именные и сбрасываются:
     «заново» переигрывает вход с чистого листа, и старый отсчёт не
     должен погасить блок посреди новой сцены. */
  var TAIL_T1 = null, TAIL_T2 = null;
  function armTailFade() {
    var hero = document.getElementById('obgHero');
    if (!hero) return;
    if (TAIL_T1) { clearTimeout(TAIL_T1); }
    if (TAIL_T2) { clearTimeout(TAIL_T2); }
    /* Карточка открыта — герой под ней НЕ воскресает:
       переармирование при смене группы возвращало кнопки в центр
       под карточку (скрин владельца 29.08). Сцена за монетой. */
    if (CARD_SYM !== null && window.innerWidth > 900) {
      hero.classList.add('obg-faded');
      hero.classList.add('obg-gone');
      TUCKED = true;
      return;
    }
    TUCKED = false;
    hero.classList.remove('obg-faded');
    hero.classList.remove('obg-gone');
    TAIL_T1 = setTimeout(function () {
      hero.classList.add('obg-faded');
      /* Ниже 1180 кнопки и так стоят рядом вкладок — своей раскладкой
         узких экранов. Переезжать им некуда, и трогать их нельзя. */
      /* Порог переезда — 900, не 1180 (Г-15, скриншот владельца
         29.08): на 900–1180 работает ДЕСКТОПНАЯ раскладка с гаснущим
         героем, и кнопки без переезда повисали посреди пустого
         центра. Ниже 900 узкая ветка сама ставит кнопки рядом
         вкладок — там переезд не нужен и не зовётся. */
      if (window.innerWidth > 900) tuckTabs();
    }, 10000);
    /* Второй класс ставится ПОСЛЕ гашения — он закрепляет результат,
       чтобы перерисовка не вернула блок. */
    TAIL_T2 = setTimeout(function () { hero.classList.add('obg-gone'); }, 11900);
  }

  /* ── Переезд категорий над список ──
     TUCKED — это состояние, а не разовое действие: список перерисовывается
     при каждой смене группы, и вкладки надо возвращать в новое место.
     Поэтому переезд разделён надвое: syncTabs ставит их куда надо молча,
     tuckTabs делает то же самое, но с полётом, и только один раз. */
  var TUCKED = false;

  /* ── Смена группы в два приёма ──
     Сначала старое гаснет, и только потом собирается новое. Одним
     приёмом это была подмена в один кадр: содержимое менялось целиком
     и разом, отчего экран щёлкал.

     Кнопки в гашение НЕ входят: они не заменяются, а переезжают на
     соседние места. Погасить их значило бы показать подмену вместо
     переезда. Снимок их положения берём в момент пересборки, а не
     сейчас: за время гашения они никуда не сдвинулись, но правило
     «мерить прямо перед сменой» надёжнее.

     Повторный клик посреди гашения не ломает очередь: прежний отсчёт
     сбрасывается, а группу берём последнюю нажатую. */
  /* Сроки РАЗНЫЕ у списка и у центра, и это не прихоть: каждая часть
     пересобирается тогда, когда догорела СВОЯ. Возьми один срок на
     двоих — и та часть, что гаснет дольше, окажется срезана на
     полпути; возьми срок по самой медленной — и список постоит
     пустым лишние полсекунды. */
  var RAIL_T = null, HERO_T = null;
  var RAIL_MS = 440;   /* столько же, сколько гаснут шапка и строки */
  var HERO_MS = 880;   /* столько же, сколько гаснет центр */

  function switchGroup(k) {
    var hero = document.getElementById('obgHero');
    var body = document.getElementById('obgBody');
    if (RAIL_T) { clearTimeout(RAIL_T); }
    if (HERO_T) { clearTimeout(HERO_T); }
    if (body) { body.classList.add('obr-out'); }
    var inner = document.getElementById('obgInner');
    if (inner) {
      inner.classList.remove('obg-swap');
      inner.classList.add('obg-swapout');
    }
    hideCoin(true);   /* монета из прошлой группы к новой не относится */
    /* Кнопка нажатой группы сейчас исчезнет из ряда — провожаем её. */
    var leaving = document.querySelector('.obg-side .obg-sat[data-gkey="' + k + '"]');
    if (leaving) { leaving.classList.add('obg-sat-out'); }
    if (hero && !hero.classList.contains('obg-gone')) {
      /* Вступление снимаем здесь же: пока оно держит конечный кадр,
         прозрачностью элемента распоряжается оно, и гашение не видно. */
      hero.classList.remove('obg-enter');
      hero.classList.remove('obg-swap');
      hero.classList.add('obg-swapout');
    }
    GATE_KEY = k;
    RAIL_T = setTimeout(function () {
      RAIL_T = null;
      paintRail();
    }, RAIL_MS);
    HERO_T = setTimeout(function () {
      HERO_T = null;
      if (hero) { hero.classList.remove('obg-swapout'); }
      if (inner) {
        inner.classList.remove('obg-swapout');
        inner.classList.add('obg-swap');
      }
      /* Снимок берём вплотную к пересборке: к этому времени список уже
         сменился, и место вкладок могло стать другим. */
      var was = tabRects();
      paintWave();
      paintHero();
      syncTabs();      /* центр собран заново — вернуть вкладки на место */
      flipTabs(was);
    }, HERO_MS);
  }

  /* ── Кнопки переезжают, а не переставляются ──
     Ряд собирается заново при каждой смене: выбранная группа из него
     прячется, прежняя возвращается. Узлы новые, поэтому анимировать
     нечего — кнопки просто оказывались на новых местах, и это читалось
     как рывок. Лечится тем же приёмом, что и переезд наверх: помним, где
     кнопка была, и ведём её оттуда.

     Ищем по .obg-side, а не по месту: ряд может стоять и в центре
     (первые десять секунд), и над списком — правило одно на оба случая. */
  function tabRects() {
    var out = {}, els = document.querySelectorAll('.obg-side .obg-sat'), i, r, k;
    for (i = 0; i < els.length; i++) {
      k = els[i].getAttribute('data-gkey');
      r = els[i].getBoundingClientRect();
      if (k && r.width) { out[k] = r; }   /* нулевая ширина = спрятанная */
    }
    return out;
  }

  function flipTabs(was) {
    var els = document.querySelectorAll('.obg-side .obg-sat'), i, el, r, a;
    if (!els.length) return;
    for (i = 0; i < els.length; i++) {
      el = els[i]; r = el.getBoundingClientRect();
      if (!r.width) continue;
      a = was[el.getAttribute('data-gkey')];
      el.style.transition = 'none';
      if (a) {
        el.style.transform = 'translate(' + (a.left - r.left).toFixed(1) + 'px,' +
                             (a.top - r.top).toFixed(1) + 'px)';
      } else {
        /* Этой кнопки в прежнем ряду не было — она была выбранной
           группой. Лететь ей неоткуда, поэтому проступает на месте. */
        el.style.transform = 'scale(.84)';
        el.style.opacity = '0';
      }
    }
    void els[0].offsetWidth;
    for (i = 0; i < els.length; i++) {
      els[i].style.transition =
        'transform .62s cubic-bezier(.4,0,.2,1),opacity .62s ease';
      els[i].style.transform = 'none';
      els[i].style.opacity = '1';
    }
    setTimeout(function () {
      for (var j = 0; j < els.length; j++) {
        els[j].style.transition = '';
        els[j].style.transform = '';
        els[j].style.opacity = '';
      }
    }, 780);
  }

  /* Распорка на место уехавших кнопок.
     Ряд «ядро + кнопки» центрируется ЦЕЛИКОМ. Стоит кнопкам уйти, как
     ядро остаётся одно и перецентровывается — прыгает вправо на
     половину их ширины с зазором. А оно в этот момент ещё видно: гаснет
     полторы секунды. Отсюда и было «перескакивает, потом исчезает».
     Ширина снимается с самих кнопок, а не пишется числом: число
     разъедется от первой же правки стиля. */
  function sideSpacer(side) {
    var ph = document.createElement('div');
    ph.className = 'obg-side-ph';
    ph.style.width = side.offsetWidth + 'px';
    ph.style.flex = '0 0 auto';
    ph.setAttribute('aria-hidden', 'true');
    return ph;
  }

  function syncTabs() {
    if (!TUCKED) return;
    var side = document.querySelector('#obgHero .obg-side');
    var slot = document.getElementById('obgTabs');
    if (!side || !slot) return;
    var row = side.parentNode;
    if (row && !row.querySelector('.obg-side-ph')) {
      row.insertBefore(sideSpacer(side), side);
    }
    /* Прежний ряд убираем ДО переноса. Центр и список пересобираются
       врозь, и без этого в месте вкладок оседали бы два ряда: один от
       прошлой сборки, другой от нынешней. */
    var stale = slot.querySelector('.obg-side');
    if (stale && stale !== side) { slot.removeChild(stale); }
    slot.appendChild(side);
    side.classList.add('obg-tucked');
  }

  function tuckTabs() {
    var side = document.querySelector('#obgHero .obg-side');
    var slot = document.getElementById('obgTabs');
    if (!side || !slot) { TUCKED = true; return; }

    /* Полёт считается по факту: где кнопка была и где оказалась.
       Зашитые координаты разъехались бы на другой ширине окна. */
    var sats = side.querySelectorAll('.obg-sat'), i, was = [], r;
    for (i = 0; i < sats.length; i++) {
      r = sats[i].getBoundingClientRect();
      was.push(r.width ? r : null);   /* скрытая — текущая группа */
    }

    TUCKED = true;
    syncTabs();

    for (i = 0; i < sats.length; i++) {
      if (!was[i]) continue;
      var b = sats[i].getBoundingClientRect();
      if (!b.width) continue;
      /* Разница по ЦЕНТРАМ, а не по левому краю: кнопка на переезде
         становится уже, и по краю она бы прыгнула вбок на старте. */
      var dx = (was[i].left + was[i].width / 2) - (b.left + b.width / 2);
      var dy = (was[i].top + was[i].height / 2) - (b.top + b.height / 2);
      /* И РАЗМЕР тоже едет. Раньше кнопка мгновенно сжималась до
         конечной и только потом летела — вот этот щелчок и был виден.
         Теперь она стартует в прежнюю величину и уменьшается в пути.

         Множитель ОДИН на обе стороны: по ширине кнопка ужимается
         сильнее, чем по высоте, и раздельный масштаб растянул бы текст.
         Берём среднее геометрическое — ошибка делится пополам и глазу
         незаметна, зато буквы не плывут. */
      var k = Math.sqrt((was[i].width / b.width) * (was[i].height / b.height));
      sats[i].style.transition = 'none';
      sats[i].style.transform =
        'translate(' + dx.toFixed(1) + 'px,' + dy.toFixed(1) + 'px) ' +
        'scale(' + k.toFixed(3) + ')';
    }
    /* Без этого браузер схлопнет оба состояния в одно и полёта не будет. */
    void side.offsetWidth;
    for (i = 0; i < sats.length; i++) {
      sats[i].style.transition =
        'transform 1.6s cubic-bezier(.5,0,.2,1) ' + (i * 90) + 'ms';
      sats[i].style.transform = 'none';
    }
    /* Инлайновые правила снимаем после посадки: иначе они переживут
       полёт и заглушат обычные переходы кнопки при наведении. */
    setTimeout(function () {
      for (var j = 0; j < sats.length; j++) {
        sats[j].style.transition = '';
        sats[j].style.transform = '';
      }
    }, 1700 + sats.length * 90);
  }

  /* «Заново» — переиграть вход: сцена собирается с нуля, волна
     рисуется заново. Раньше здесь снималась стена; стены больше нет,
     поэтому осталось только закрыть карточку и пересобрать ворота. */
  function backToGate() {
    closeZoom();
    ZLIST = [];
    bail('');
    openGate();
  }

  var againBtn = document.getElementById('obpAgain');
  if (againBtn) {
    againBtn.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    againBtn.addEventListener('touchstart', function (e) { e.stopPropagation(); },
                              { passive: true });
    againBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      backToGate();
    });
  }

  function show() {
    if (opened) return;
    opened = true;
    /* Небо и шапка — фон под воротами; сам зал живёт в воротах. */
    sky();
    portLine();
    openGate();
    pod.classList.add('on');
  }

  /* Выход один на все способы: кнопка, Esc и любая клавиша ведут
     сюда. Раскрытую карточку закрываем вместе с залом — иначе она
     останется висеть и всплывёт поверх дашборда при следующем
     открытии. */
  var doneSent = false;
  function hide() {
    closeZoom();
    pod.classList.remove('on');
    /* Прокрутку возвращаем в начало: на узком экране зал прокручивается,
       и его остановленная инерция — вторая причина, по которой первые
       касания после закрытия уходили в никуда. */
    pod.scrollTop = 0;

    /* Дальше документ уничтожит оболочка — вместе со сценой, кадрами
       и слушателями. Класс снимается всё равно: между сообщением и
       сменой документа проходит кадр-другой, и без затухания это
       выглядело бы обрывом. */
    if (doneSent) return;
    doneSent = true;
    try {
      window.parent.postMessage(
        { type: 'ob:done', screen: 'podium' }, window.location.origin);
    } catch (e) { /* открыт вне оболочки — просто гаснем */ }
  }

  /* Подсказка по способу ввода. Тип указателя здесь как раз к месту:
     вопрос не в размере экрана, а в том, есть ли мышь и клавиатура.
     На планшете строка про колесо и Esc описывает то, чего у
     человека в руках нет. */
  if (window.matchMedia('(pointer: coarse)').matches) {
    var hintEl = document.getElementById('obpHint');
    if (hintEl) hintEl.textContent = 'смахните · касание по карточке';
  }

  var exitBtn = document.getElementById('obpExit');
  if (exitBtn) {
    /* mousedown гасится до всплытия: на зале висит перетаскивание,
       и без этого нажатие на кнопку уводит сцену вбок. touchstart —
       по той же причине: палец на кнопке иначе начинает вращение, и
       сцена уезжает из-под пальца ещё до отпускания. */
    exitBtn.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    exitBtn.addEventListener('touchstart', function (e) { e.stopPropagation(); },
                             { passive: true });
    exitBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      hide();
    });
  }

  document.addEventListener('keydown', function (e) {
    if (!opened) return;
    /* Печать в поле поиска — не команда экрану. Без этой проверки
       любая буква закрывала бы подиум на первом же нажатии. */
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
              t.isContentEditable)) return;
    /* Открытая карточка забирает клавиатуру себе: у неё свой
       обработчик со стрелками и Escape, и он ловит нажатие РАНЬШЕ
       нашего (перехват). Без этой проверки стрелка листала карточку
       и тем же нажатием прятала весь экран — перелистывание
       выглядело сломанным. Проверяем НОВУЮ карточку, а не старую:
       раньше сверялись со старым зумом, который давно не включается. */
    if (window.OBCARD && window.OBCARD.isOpen && window.OBCARD.isOpen()) return;
    if (zoom.classList.contains('on')) {
      if (e.key === 'Escape') closeZoom();
      return;
    }
    /* Стрелки крутили стену. Стены нет — список листается колесом,
       а любая другая клавиша по-прежнему уводит с экрана. */
    hide();
  });

  /* Показываемся сразу: документ загружен — значит, оболочка уже
     решила, что очередь наша. Ни ожидания чужого экрана, ни
     сторожевого таймера на случай, если тот не открылся, больше не
     нужно: обоих проблем не существует, когда очередь ведёт один
     хозяин, а не каждый участник по-своему. */
  show();
})();
</script>
"""

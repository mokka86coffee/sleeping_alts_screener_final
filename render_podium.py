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
.obg-inner{flex:1;min-width:0;display:flex;flex-direction:column;
  align-items:center;gap:30px;
  animation:obgRise 2.1s cubic-bezier(.2,.75,.3,1) both}
@keyframes obgRise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}

/* ── Волна прогона ── */
.obg-wave{position:relative;width:100%;min-height:300px;isolation:isolate}
.obg-wave svg{position:relative;z-index:1;display:block;width:100%;height:auto;
  max-height:34vh}
/* Призрачное число — нижний слой: лента и сетка идут поверх и режут его. */
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
.obr{width:392px;flex:0 0 auto;height:100%;display:flex;flex-direction:column;
  gap:10px;padding:18px 0}
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
/* Метка делистинга. Янтарь — предупреждение биржи, красный — решение
   принято. Мигание только у срочного: если мигает всё, не мигает
   ничего. */
.obr-dl{display:inline-block;margin-left:7px;padding:1px 6px;border-radius:4px;
  font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;vertical-align:2px;
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

.obr-row{position:relative;display:grid;grid-template-columns:78px 1fr 62px;
  align-items:center;gap:12px;padding:9px 12px 9px 15px;border-radius:11px;
  border:1px solid rgba(255,255,255,.05);cursor:pointer;
  background:linear-gradient(90deg,rgba(var(--rgb),.07),rgba(255,255,255,.012) 42%);
  transition:background .54s,border-color .54s,transform .54s;
  animation:obrRowIn 1.26s cubic-bezier(.2,.75,.3,1) both}
.obr-row:hover{border-color:rgba(var(--rgb),.34);transform:translateX(-3px);
  background:linear-gradient(90deg,rgba(var(--rgb),.13),rgba(255,255,255,.03) 42%)}
/* цвет стратегии — полоса слева */
.obr-row::before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:2px;
  border-radius:2px;background:var(--c);box-shadow:0 0 10px rgba(var(--rgb),.6)}
.obr-tk{font-size:12px;font-weight:500;letter-spacing:.06em;color:#e8ecfb;
  text-decoration:none;cursor:pointer;transition:color .25s}
.obr-tk:hover{color:var(--c);text-decoration:underline;
  text-underline-offset:3px;text-decoration-thickness:1px}
.obr-tk:focus-visible{outline:1px solid var(--c);outline-offset:3px;
  border-radius:3px}
.obr-cs{display:block;margin-top:3px;font-size:7.4px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--c);opacity:.85;white-space:nowrap}
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
#obgHero .obg-hero{animation:obgTextIn 1.32s cubic-bezier(.2,.75,.3,1) both}
#obgHero .obg-hint{animation:obgTextIn 1.32s cubic-bezier(.2,.75,.3,1) both .27s}
#obgHero .obg-panel{animation:obgTextIn 1.32s cubic-bezier(.2,.75,.3,1) both .48s}
.obg-wave .obg-wv{stroke-dasharray:2600;stroke-dashoffset:2600;
  animation:obgWaveDraw 5.7s cubic-bezier(.3,.75,.35,1) .45s both}
.obg-wave .obg-mesh{animation:obgFade 3.6s ease .3s both}
.obg-wave .obg-body{animation:obgFade 3.2s ease 1.6s both}
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
@media (max-width:1180px){
  .obp-gate{padding:0;align-items:stretch;justify-content:flex-start}
  .obg-stage{flex-direction:column;gap:0;height:100%;width:100%;
    align-items:stretch;justify-content:flex-start}

  /* Сцена — не блок с содержимым, а система координат для горизонта.
     Высота её частей задаётся здесь и только здесь. */
  .obg-inner{position:relative;flex:0 0 auto;gap:0;animation:none}

  /* ── Горизонт ── */
  .obg-wave{position:relative;height:56px;min-height:0;overflow:hidden}
  .obg-wave svg{position:absolute;inset:0;width:100%;height:100%;
    max-height:none}
  .obg-ghost{display:none}          /* именно оно уезжало за край */

  /* Счёт едет ПО горизонту: ядро вынимается из потока и ложится
     на ленту. От него остаются число и название группы. */
  #obgHero{position:static;min-height:0;gap:0}
  .obg-hero{position:static;min-height:0;gap:0;display:block}
  .obg-core{position:absolute;left:0;top:0;z-index:4;
    width:auto;min-height:0;height:56px;
    display:flex;align-items:center;padding-left:16px}
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
  .obg-scap{font-size:7.5px;letter-spacing:.2em;text-align:center;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
  .obg-sat.obg-zero{opacity:.42}
  .obg-sat.obg-zero.obg-cur{opacity:.8}

  /* Подсказка молчит: на узком экране каждая строка — это строка
     списка, которой не хватило. */
  .obg-hint{display:none}

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

  /* ── Список забирает остаток и прокручивается внутри себя ── */
  .obr{width:100%;flex:1 1 auto;min-height:0;height:auto;padding:10px 12px 12px}
  .obr-list{max-height:none;flex:1 1 auto;min-height:0;overflow-y:auto}
  .obr-row{min-height:46px}          /* палец, а не курсор */
  .obg-out{top:auto;bottom:14px;right:14px;
    background:rgba(20,22,44,.82);backdrop-filter:blur(6px)}
}

/* Планшет лёжа: ширина вернулась — горизонт, вкладки и сводка уходят
   в левую колонку, список занимает всю правую. */
@media (max-width:1180px) and (min-width:781px) and (orientation:landscape){
  .obg-stage{flex-direction:row}
  .obg-inner{flex:0 0 300px;border-right:1px solid rgba(255,255,255,.07);
    display:flex;flex-direction:column}
  .obg-wave{height:72px}
  .obg-core{height:72px}
  .obg-side{flex-direction:column;padding:12px 12px 0}
  .obg-sat,.obg-sat.obg-cur{flex-direction:row;justify-content:space-between;
    align-items:baseline;padding:8px 11px}
  .obg-scap{text-align:left}
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
  .obg-wave{height:44px}
  .obg-core{height:44px;padding-left:12px}
  .obg-num{font-size:21px}
  .obg-cap{font-size:8px;letter-spacing:.22em}
  .obg-side{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:9px 10px 0}
  .obg-sat,.obg-sat.obg-cur{flex-direction:row;justify-content:space-between;
    align-items:baseline;padding:7px 10px}
  .obg-pill{font-size:15px}
  .obg-scap{text-align:right;font-size:7px}
  .obg-panel{display:grid;grid-template-columns:1fr 1fr;margin:9px 10px 0;
    border:1px solid rgba(255,255,255,.07);border-radius:10px;overflow:hidden}
  .obg-panel > div{border-right:1px solid rgba(255,255,255,.07);
    border-bottom:1px solid rgba(255,255,255,.07)}
  .obg-panel > div:nth-child(2n){border-right:0}
  .obg-panel > div:nth-child(n+3){border-bottom:0}
  .obr{padding:9px 10px 10px}
  .obr-row{grid-template-columns:74px 1fr 62px;min-height:44px}
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
}
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
  /* Пока торговая книга пуста (а она начинается пустой), смотреть в
     ней нечего — зал открывается на HOLD, на том, что реально держим.
     Как только правила что-то ведут, вход переезжает на «выходить».
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
  var GATE_KEY = TRADE_ANY ? 'exit' : 'hold';

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

  function gateWave(w, h) {
    var d = ((O.market || {}).series || []).slice();
    if (d.length < 3) return '';
    /* Поля по краям: кривая не упирается в границу кадра, а
       растворяется маской — иначе она обрывалась о колонку. */
    var L = 26, R = 130, TOP = 46, BASE = h - 42, i, r;
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
          '<stop offset="34%" stop-color="#ec6f5e"/>' +
          '<stop offset="72%" stop-color="#f0a878"/>' +
          '<stop offset="100%" stop-color="#ffd2ac"/></linearGradient>' +
        '<linearGradient id="obgUf" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0%" stop-color="#ec6f5e" stop-opacity=".2"/>' +
          '<stop offset="100%" stop-color="#ec6f5e" stop-opacity="0"/></linearGradient>' +
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
        '<path d="' + front + '" fill="none" stroke="#ec6f5e" stroke-width="12" ' +
          'stroke-opacity=".3" filter="url(#obgSh)"/>' +
      '</g>' +
      '<g mask="url(#obgMLine)">' +
        '<path class="obg-wv" d="' + front + '" fill="none" stroke="url(#obgWv)" ' +
          'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" ' +
          'filter="url(#obgGl)"/>' +
      '</g>' +
      '<g class="obg-node" transform="translate(' + fx.toFixed(1) + ',' +
        fy.toFixed(1) + ')">' +
        '<circle r="30" fill="none" stroke="#ffd2ac" stroke-opacity=".26" ' +
          'stroke-dasharray="1.5 6" class="obg-spin"/>' +
        '<circle r="20" fill="none" stroke="#ffd2ac" stroke-opacity=".4" ' +
          'stroke-dasharray="1.5 5" class="obg-spin obg-rev"/>' +
        '<circle r="9" fill="none" stroke="#ffd2ac" stroke-opacity=".8"/>' +
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
    var withEntry = GATE_KEY === 'trade' || GATE_KEY === 'exit';
    var out = '<div class="obr-head" style="--c:' + col.c + '">' +
      '<b>' + stg.n + ' · ' + rows.length + '</b>' +
      '<span>две недели' + (withEntry ? ' · твх' : '') + '</span></div>' +
      '<div class="obr-find" id="obgFind"><i class="obr-mag"></i>' +
        '<input type="text" id="obgQ" placeholder="поиск по монете" ' +
          'autocomplete="off" spellcheck="false">' +
        '<button class="obr-clr" type="button" id="obgClr" ' +
          'aria-label="очистить">×</button></div>';
    if (!rows.length) {
      host.innerHTML = out + '<div class="obr-empty">в этой группе сегодня пусто</div>';
      return;
    }
    /* Порядок — по ходу от входа, лучшие сверху: список читают
       сверху вниз, и первым должно стоять то, что работает. */
    rows = rows.slice().sort(function (a, b) {
      return (pnlOf(b) - pnlOf(a));
    });
    /* Карточка листает соседей по ZLIST. Раньше его наполняла только
       стена, поэтому из списка карточка не открывалась вовсе. Теперь
       список сам кладёт туда монеты В ТОМ ЖЕ ПОРЯДКЕ, что и строки. */
    ZLIST = rows.slice();
    out += '<div class="obr-list">';
    for (i = 0; i < rows.length; i++) {
      var s = rows[i], c = caseOf(s), p = pnlOf(s);
      out += '<div class="obr-row" data-sym="' + s.t +
        '" data-case="' + c.n + '" style="--c:' + c.c +
        ';--rgb:' + c.rgb + ';animation-delay:' + (i * 165) + 'ms">' +
        '<div><a class="obr-tk" href="' + tvUrl(s) + '" target="_blank" ' +
            'rel="noopener" title="открыть график на TradingView">' + s.t + '</a>' +
          delistTag(s) +
          '<span class="obr-cs">' + c.n + '</span></div>' +
        '<div>' + railSpark(s, i * 165) + '</div>' +
        '<div class="obr-pnl ' + (p >= 0 ? 'obg-up' : 'obg-dn') + '">' +
          (p >= 0 ? '+' : '') + p.toFixed(1) + '%' +
          '<em>' + (s.book && s.book.px ? 'от твх' : 'две недели') + '</em></div>' +
        '</div>';
    }
    host.innerHTML = out + '</div><div class="obr-none" id="obgNone">' +
      'ничего не найдено</div>';
    /* Привязку строк зовём ПОСЛЕ отрисовки: раньше она стояла в
       paintHero, который отрабатывает раньше списка, — узлов ещё не
       было, и клик по монете не делал ничего. */
    bindRows(rows);
    bindFind();
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
      })(els[i], i);
    }
  }

  /* Ход монеты: от входа, если позиция есть; иначе за две недели. */
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

  function paintHero() {
    var host = document.getElementById('obgHero');
    if (!host) return;
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
          GATE_KEY = k;
          paintHero();
          paintRail();
        };
      })(btns[i]);
    }
  }

  function openGate() {
    if (!GATE) { bail('ворота не найдены'); return; }
    var inner = document.getElementById('obgInner');
    if (inner) {
      /* Волна строится ОДИН раз: перестраивать её на каждом переходе
         значило бы каждый раз заново проигрывать её отрисовку. */
      inner.innerHTML =
        '<div class="obg-wave"><div class="obg-ghost" id="obgGhost"></div>' +
          gateWave(1000, 300) + '</div>' +
        '<div id="obgHero"></div>';
    }
    paintHero();
    paintRail();
    pod.classList.add('obp-gated');
    GATE.classList.add('on');
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

"""Сводка утра — ЛИСТАЛКА.

ЧТО ИЗМЕНИЛОСЬ ПРОТИВ ПРЕЖНЕЙ СВОДКИ. Раньше это была одна сцена на
canvas: текст печатался посимвольно поверх дюны, сегмент за сегментом,
и прочитанное уходило безвозвратно. Претензии к ней были такие:
  · всё шло сплошняком, разделов не видно;
  · «и ещё 8» прятало события, среди которых был самый тяжёлый транш;
  · не успел прочитать — назад не вернуться;
  · подробности открывались наведением, а на планшете наведения нет.

Теперь — страницы. Одна мысль на страницу, листаются сами, стрелками
можно вернуться, курсор на листе останавливает ход. Все подробности
видны сразу, без наведения.

ЧТО ОСТАЛОСЬ ПРЕЖНИМ. Контракт с оболочкой: документ живёт в кадре,
ждёт сообщения «показан», по окончании шлёт «доиграл» и гаснет.
Страховочный таймер на случай, если очередь встанет.

ДАННЫЕ. Те же, что у зала: stars и market. Страницы собираются ИЗ НИХ,
а не вшиты в разметку: изменился прогон — изменились страницы.

ИЗОЛЯЦИЯ. Документ сводки несёт в себе ВЕСЬ общий CSS сайта:
render_page.document кладёт render_css.CSS в каждый экран целиком, а в
том файле живут правила прежней сводки на #obBrief и всём, что под ним.
Превью без общего CSS выглядело верно; живая сборка с ним — с чёрным
полем вокруг листа и пустой колонкой событий. Какое именно правило
виновато, отсюда не видно — и не должно быть важно: спорить с общим
файлом по специфичности значит проигрывать при каждой его правке.

Поэтому разметка и стили сводки живут в ТЕНЕВОМ ДЕРЕВЕ (Shadow DOM)
на узле #obfHost: внешние стили внутрь не проходят вовсе, а стили
сводки не выходят наружу. Обёртке #obBrief оставлено одно — класс .on
для затухания из общего файла. Поле вокруг листа рисует сама рамка
своей тенью, а не обёртка. Данные (#obfData) остаются в обычном дереве:
их читает письмо (send_brief_email.load_report_data).

ВЫХОД. Стрелки — на клавиатуре и на экране — листают. Всё остальное
закрывает: клик в любом месте, кроме полосы навигации, и любая клавиша,
кроме стрелок и одиноких модификаторов.
"""

from __future__ import annotations

import json


def render_brief(stars: list[dict], market: dict) -> str:
    """Тело документа сводки. Данные вшиваются, а не читаются из окна."""
    blob = json.dumps({"stars": stars, "market": market},
                      ensure_ascii=False, separators=(",", ":"))
    # Данные идут в <script type="application/json">, а не в присваивание
    # переменной: внутри JSON-блока браузер не разбирает разметку, и
    # последовательность вроде </script> в тексте поля не закроет скрипт
    # раньше времени. Экранируется только сам этот случай.
    safe = blob.replace("</", "<\\/")
    return (BRIEF_HTML
            + f'<script id="obfData" type="application/json">{safe}</script>'
            + BRIEF_JS)


BRIEF_HTML = """
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@200;300;800&family=Playfair+Display:wght@400;500&display=swap" rel="stylesheet">
<div class="obf-host" id="obfHost"></div>
<template id="obfTpl">
<style>
/* ТЕНЕВОЕ ДЕРЕВО. Всё, что ниже, вместе с разметкой клонируется из
   шаблона в shadow root узла #obfHost (см. начало скрипта). Общий CSS
   сайта сюда не достаёт: ни #obBrief div, ни body{color}, ни
   переменные с теми же именами. Единственная связь с внешним документом
   — шрифты: @font-face объявлен снаружи, теневое дерево им пользуется. */
:host{all:initial;display:block}

/* ШРИФТЫ. Montserrat в двух КРАЙНИХ весах — 200 и 800. Между ними
   ничего: контраст тонкого и жирного и есть приём, на нём держится вся
   раскладка. Playfair — антиква для подписей вразрядку.
   Запасные стеки подобраны по РИСУНКУ, а не по имени: Futura и Century
   Gothic — те же геометрические гротески, Didot и Bodoni — та же
   антиква с тонкими засечками. Если сеть закрыта, лист не рассыплется. */
/* Переменные объявлены на самой рамке — узле, который точно есть и
   точно внутри теневого дерева. Снаружи переопределить их некому, а
   всё, что ими пользуется, лежит под рамкой. */
.obf-frame{
  --pg:#8d939c; --bg1:#f2f3f5; --bg2:#c6ccd3;
  --ink:#464c57; --ink2:#6c737f; --mut:#9aa1ab;
  --acc:#e8873f; --up:#4f8a63; --dn:#b5573f;
  --dark:#22262e;
  --sans:'Montserrat',Futura,'Century Gothic','Avenir Next','Trebuchet MS',sans-serif;
  --serif:'Playfair Display',Didot,'Bodoni MT',Georgia,serif;

  /* ЧЕТЫРЕ РЫЧАГА СКОРОСТИ, и они связаны: время стояния страницы
     обязано быть БОЛЬШЕ, чем разбег плюс появление последней строки,
     иначе лист уедет, не дорисовавшись. Биржа не про спешку. */
  --step:1.02s;     /* разбег строк внутри страницы */
  --dur:4.5s;       /* появление одной строки */
  --wipe:3.15s;     /* переход между страницами */
  --dwell:26s;      /* сколько страница стоит сама */

  font-family:var(--sans);font-weight:300;color:var(--ink);

  /* РАМКА САМА СТАВИТ СЕБЯ В ОКНО И САМА РИСУЕТ ПОЛЕ. Раньше отступ и
     серое поле давала обёртка #obBrief — и проигрывала общему CSS:
     обёртка показывала чёрный градиент оболочки, а поле пропадало.
     Теперь рамка закреплена в окне сама (fixed, отступ 26px, ширина до
     1240 по центру), а поле вокруг — её собственная тень на всё окно.
     Обёртка может быть какой угодно: flex, чёрной, без отступов.
     z-index большой намеренно: у прежней сводки в общем CSS могли
     остаться украшения на обёртке (::before/::after, линии) — рамка
     обязана лежать поверх всего, что рисует обёртка. */
  position:fixed;top:26px;right:26px;bottom:26px;left:26px;
  margin:0 auto;max-width:1240px;min-height:600px;z-index:99999;
  box-sizing:border-box;border:14px solid #fff;visibility:visible;
  background:linear-gradient(160deg,var(--bg1),var(--bg2));
  box-shadow:0 0 0 100vmax var(--pg);
  display:grid;grid-template-columns:1fr 322px;overflow:hidden}

/* ── левый лист: колода страниц ── */
.obf-sheet{position:relative;overflow:hidden}
.obf-page{position:absolute;inset:0;padding:30px 46px 88px;
  display:flex;flex-direction:column;visibility:hidden;
  background:linear-gradient(160deg,var(--bg1),var(--bg2))}
.obf-page.on{visibility:visible;z-index:1}

/* ПЕРЕХОД — ДИАГОНАЛЬНЫЙ СРЕЗ. Кадры сходятся косыми гранями: новая
   страница входит клином, а не выцветает. Вперёд клин идёт справа,
   назад — слева, чтобы направление читалось само. */
@keyframes obfInFwd{
  from{clip-path:polygon(125% 0,125% 0,125% 100%,125% 100%)}
  to  {clip-path:polygon(-30% 0,125% 0,125% 100%,0 100%)}
}
@keyframes obfInBack{
  from{clip-path:polygon(-30% 0,-30% 0,-30% 100%,-30% 100%)}
  to  {clip-path:polygon(-30% 0,125% 0,125% 100%,0 100%)}
}
.obf-page.on.fwd {animation:obfInFwd  var(--wipe) cubic-bezier(.22,.61,.36,1)}
.obf-page.on.back{animation:obfInBack var(--wipe) cubic-bezier(.22,.61,.36,1)}

/* УХОД. Уходящий лист лежит ПОВЕРХ входящего и остаётся ПЛОТНЫМ до
   конца: он не растворяется, а съезжает косой гранью и открывает
   следующий. Затухания здесь нет намеренно — с ним текст обеих
   страниц накладывался и читался кашей. */
@keyframes obfOutFwd{
  from{clip-path:polygon(-30% 0,125% 0,125% 100%,0 100%)}
  to  {clip-path:polygon(-30% 0,-30% 0,-30% 100%,-55% 100%)}
}
@keyframes obfOutBack{
  from{clip-path:polygon(-30% 0,125% 0,125% 100%,0 100%)}
  to  {clip-path:polygon(125% 0,125% 0,150% 100%,125% 100%)}
}
.obf-page.out{visibility:visible;z-index:2}
.obf-page.out.fwd {animation:obfOutFwd  calc(var(--wipe) * 1.15) cubic-bezier(.4,0,.5,1) forwards}
.obf-page.out.back{animation:obfOutBack calc(var(--wipe) * 1.15) cubic-bezier(.4,0,.5,1) forwards}

/* ── появление строк ── */
@keyframes obfWedge{
  from{opacity:0;clip-path:polygon(0 0,0 0,0 100%,0 100%);transform:translateX(-14px)}
  to  {opacity:1;clip-path:polygon(0 0,130% 0,130% 100%,0 100%);transform:none}
}
.obf-st{opacity:0}
.obf-page.on .obf-st{animation:obfWedge var(--dur) cubic-bezier(.22,.61,.36,1) forwards;
  animation-delay:calc(var(--i) * var(--step) + .35s)}

/* УХОДЯЩАЯ СТРАНИЦА УДЕРЖИВАЕТ КОНЕЧНОЕ СОСТОЯНИЕ.
   Появление привязано к «.on». Стоило снять этот класс — правило
   переставало действовать, и строки МГНОВЕННО возвращались в
   невидимость: уезжал пустой лист, а глаз читал щелчок. Здесь строки
   остаются на месте, линия дорисована, полоса на всю длину. */
.obf-page.out .obf-st{opacity:1;animation:none;transform:none;
  clip-path:polygon(0 0,130% 0,130% 100%,0 100%)}
.obf-page.out .obf-big .obf-bar{width:80%;animation:none}
.obf-page.out .obf-chart .ln{stroke-dashoffset:0;animation:none}
.obf-page.out .obf-chart .dot{opacity:1;animation:none}

.obf-top{display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid rgba(70,76,87,.16);padding-bottom:14px;flex:0 0 auto}
.obf-logo{display:flex;align-items:center;gap:12px;font-weight:800;
  font-size:12.5px;letter-spacing:.3em}
.obf-logo .o{width:22px;height:22px;border-radius:50%;background:#fff;
  display:grid;place-items:center;color:var(--acc);font-size:14px;
  font-weight:300;line-height:1}
.obf-stamp{font-family:var(--serif);font-size:10.5px;letter-spacing:.3em;
  text-transform:uppercase;color:var(--mut)}

.obf-serif{font-family:var(--serif);font-weight:400;letter-spacing:.44em;
  text-transform:uppercase;color:var(--ink2)}
.obf-mid{flex:1 1 auto;display:flex;flex-direction:column;
  justify-content:center;min-height:0}
.obf-kick{font-size:13px;margin-bottom:18px}

.obf-big{position:relative;display:inline-block;font-weight:800;
  font-size:104px;line-height:.94;letter-spacing:-.015em;align-self:flex-start}
.obf-big .g{position:relative;z-index:2;color:var(--ink)}
.obf-big .obf-bar{position:absolute;left:-16px;top:34px;height:22px;
  background:var(--acc);z-index:1;width:0}
.obf-page.on .obf-big .obf-bar{animation:obfGrow 3.9s cubic-bezier(.22,.61,.36,1) forwards;
  animation-delay:4.05s}
@keyframes obfGrow{to{width:80%}}
.obf-sub{margin-top:22px;font-size:14px;line-height:1.75;max-width:600px;
  color:var(--ink2)}
.obf-sub b{color:var(--ink);font-weight:800}

/* ── ГРАФИК: ЦЕНА, а не объём ──
   Объём после сквиза на 90% бывает огромным и не значит НИЧЕГО, если
   цена не пошла. Поэтому главная линия — цена, объём стоит бледным
   фоном. Вместе они прямо показывают усилие против результата: высокие
   столбики под плоской линией — это «льют, а цена стоит». */
.obf-chart{margin:22px 0 22px;max-width:520px}
.obf-chart svg{display:block;width:100%;height:104px;overflow:visible}
.obf-chart .ln{fill:none;stroke:var(--acc);stroke-width:2;
  stroke-linejoin:round;stroke-linecap:round;
  stroke-dasharray:1400;stroke-dashoffset:1400}
.obf-page.on .obf-chart .ln{animation:obfDraw 5.7s cubic-bezier(.3,.7,.4,1) forwards;
  animation-delay:2.55s}
@keyframes obfDraw{to{stroke-dashoffset:0}}
.obf-chart .dot{fill:var(--acc);opacity:0}
.obf-page.on .obf-chart .dot{animation:obfPop 1.5s ease forwards;animation-delay:7.8s}
@keyframes obfPop{to{opacity:1}}
.obf-chart .bars rect{fill:var(--ink);opacity:.10}
.obf-chart .cap{font-family:var(--serif);font-size:9px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--mut);margin-top:11px;line-height:1.8}

.obf-nums{display:flex;gap:40px;flex-wrap:wrap}
.obf-num{cursor:default}
.obf-num .v{font-weight:200;font-size:34px;line-height:1;color:var(--ink)}
.obf-num .v.acc{color:var(--acc)}
.obf-num .v.up{color:var(--up)} .obf-num .v.dn{color:var(--dn)}
.obf-num .c{font-family:var(--serif);font-size:9px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--mut);margin-top:8px}
/* Подробность видна СРАЗУ: на планшете и телефоне наведения нет, и
   спрятанное там становится недоступным. Обычная приписка — спокойным
   серым, оговорка о качестве данных — акцентом. */
.obf-num .d{font-size:10.5px;color:var(--ink2);line-height:1.5;margin-top:7px;
  max-width:230px}
.obf-num .d.warn{color:var(--acc)}

.obf-pos{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 34px}
.obf-p .r{display:flex;align-items:baseline;gap:10px}
.obf-p .t{font-weight:800;font-size:13px;letter-spacing:.06em;color:var(--ink)}
.obf-p .n{font-weight:200;font-size:19px}
.obf-p .n.up{color:var(--up)} .obf-p .n.dn{color:var(--dn)}
.obf-p .n.acc{color:var(--acc)}
/* Метка лидера прогона — рамкой, а не цветом тикера: цвет тикера уже
   занят под направление хода, и второй смысл на том же месте читался
   бы как оценка монеты. */
.obf-now{font-style:normal;margin-left:9px;padding:1px 7px;border-radius:3px;
  font-family:var(--serif);font-size:7.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--acc);
  border:1px solid rgba(232,135,63,.5);background:rgba(232,135,63,.08)}
.obf-p .d{font-size:10.5px;color:var(--ink2);line-height:1.5;margin-top:4px;
  max-width:290px}

.obf-plain{font-size:15px;line-height:1.8;color:var(--ink2);max-width:620px}
.obf-plain b{color:var(--ink);font-weight:800}
.obf-empty{font-weight:200;font-size:52px;color:var(--mut)}
.obf-tick{display:inline-block;font-weight:800;font-size:14px;
  letter-spacing:.1em;color:var(--ink2);margin:0 20px 8px 0}

/* ── управление ── */
.obf-nav{position:absolute;left:46px;bottom:22px;width:calc(100% - 414px);
  display:flex;align-items:center;gap:16px;z-index:9}
.obf-arrow{width:31px;height:31px;border-radius:50%;background:var(--acc);
  color:#fff;display:grid;place-items:center;font-size:14px;font-weight:300;
  cursor:pointer;user-select:none;flex:0 0 auto;
  transition:opacity .25s,transform .25s}
.obf-arrow:hover{transform:scale(1.09)}
.obf-arrow.off{opacity:.24;cursor:default;transform:none}
.obf-count{font-family:var(--serif);font-size:11px;letter-spacing:.3em;
  color:var(--mut)}
.obf-ticks{display:flex;gap:5px;flex:1 1 auto}
.obf-tk{height:2px;flex:1;background:rgba(70,76,87,.18);cursor:pointer;
  position:relative}
.obf-tk i{position:absolute;inset:0;width:0;background:var(--acc);display:block}
.obf-tk.done i{width:100%}
.obf-tk.now i{animation:obfFill var(--dwell) linear forwards}
@keyframes obfFill{to{width:100%}}
.obf-paused .obf-tk.now i{animation-play-state:paused}
.obf-hint{font-family:var(--serif);font-size:9.5px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--mut);opacity:0;transition:opacity .3s}
.obf-paused .obf-hint{opacity:1}

/* ── тёмная колонка: то, что надвигается ── */
.obf-rail{background:var(--dark);color:#dfe3ea;position:relative;overflow:hidden}
/* Решётка живёт СВОИМ слоем поверх колонки, а не внутри списка: иначе
   она едет вместе с прокруткой. Почти невидима — фактура, не рисунок. */
.obf-mesh{position:absolute;inset:0;opacity:.055;pointer-events:none;z-index:0}
.obf-list{position:absolute;inset:0;padding:28px 20px 22px 24px;z-index:1;
  overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;
  scrollbar-color:rgba(255,255,255,.18) transparent}
.obf-list::-webkit-scrollbar{width:4px}
.obf-list::-webkit-scrollbar-thumb{background:rgba(255,255,255,.18);border-radius:2px}
.obf-list::-webkit-scrollbar-track{background:transparent}
.obf-h{font-family:var(--serif);letter-spacing:.4em;text-transform:uppercase;
  font-size:10px;color:#8d94a2;margin-bottom:18px}
.obf-ev{padding:10px 0;border-bottom:1px solid rgba(255,255,255,.07)}
.obf-ev .w{font-family:var(--serif);font-size:8.5px;letter-spacing:.24em;
  text-transform:uppercase;color:#767e8d;margin-bottom:4px}
.obf-ev .w.now{color:var(--acc)}
.obf-ev .t{font-size:11.3px;line-height:1.42;color:#cfd5df}
.obf-ev .t b{color:#fff;font-weight:800}
.obf-ev .k{font-family:var(--serif);font-size:8px;letter-spacing:.2em;
  text-transform:uppercase;color:#6d7484;margin-left:6px}
.obf-ev .k.book{color:#e88b8b}
.obf-ev .d{font-size:10px;line-height:1.5;color:#8a92a1;margin-top:5px}
.obf-more{margin-top:14px;padding-top:14px;
  border-top:1px solid rgba(255,255,255,.07);font-family:var(--serif);
  font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:#6d7484;
  line-height:1.9}

/* ── узкие экраны ──
   Колонка событий уходит вниз отдельной страницей: в 322 пикселя рядом
   с листом она не помещается, а прятать события нельзя — их видимость
   и была целью. */
/* Страница событий существует ВСЕГДА, но на широком экране скрыта:
   там те же события стоят колонкой справа, и вторая копия была бы
   лишней страницей ни о чём. На узком — наоборот: колонка уходит,
   страница появляется. Прятать события совсем нельзя, ради их
   видимости всё и затевалось. */
.obf-page.narrow{display:none}
@media (max-width:900px){
  .obf-frame{top:12px;right:12px;bottom:12px;left:12px;border-width:8px;
    grid-template-columns:1fr}
  .obf-rail{display:none}
  .obf-page.narrow{display:flex}
  .obf-page .obf-ev{padding:9px 0}
  /* Одиннадцать событий с пояснениями в экран телефона не влезают.
     Сначала я отдал списку overflow:visible — и он полез ВВЕРХ, на
     шапку: середина страницы центрирует содержимое, а содержимое
     оказалось выше самой страницы.
     Здесь список прокручивается ВНУТРИ страницы, а середина
     выравнивает по верху: у длинного списка нет «центра», у него
     есть начало. */
  .obf-page.narrow .obf-mid{justify-content:flex-start}
  .obf-page .obf-list{position:static;padding:0 6px 0 0;
    flex:1 1 auto;min-height:0;overflow-y:auto}

  /* ЦВЕТА ПЕРЕВОРАЧИВАЮТСЯ. Разметка событий одна на два места, а
     места разные: в колонке она лежит на тёмном и набрана светлым, на
     странице — на светлом листе. Без этой правки текст был светлым на
     светлом и почти не читался. */
  .obf-page .obf-h{color:var(--mut)}
  .obf-page .obf-ev{border-bottom-color:rgba(70,76,87,.14)}
  .obf-page .obf-ev .t{color:var(--ink);font-size:13px}
  .obf-page .obf-ev .t b{color:var(--ink);font-weight:800}
  .obf-page .obf-ev .w{color:var(--mut)}
  .obf-page .obf-ev .w.now{color:var(--acc)}
  .obf-page .obf-ev .k{color:var(--mut)}
  .obf-page .obf-ev .k.book{color:var(--dn)}
  .obf-page .obf-ev .d{color:var(--ink2);font-size:11px}
  .obf-page .obf-more{color:var(--mut);border-top-color:rgba(70,76,87,.14)}
  .obf-page .obf-list::-webkit-scrollbar-thumb{background:rgba(70,76,87,.22)}
  .obf-page{padding:22px 26px 78px}
  .obf-big{font-size:64px}
  .obf-nav{left:26px;width:calc(100% - 52px)}
  .obf-nums{gap:26px}
  .obf-pos{grid-template-columns:1fr}
}

/* На телефоне тринадцать полосок в ряд превращаются в мельтешение:
   каждая уже пальца, попасть нельзя, а места они занимают всю строку.
   Оставляем стрелки и счётчик — этого хватает, чтобы понять, где ты
   и как вернуться. */
@media (max-width:560px){
  .obf-ticks{display:none}
  .obf-hint{margin-left:auto}
  .obf-big{font-size:52px}
  .obf-page{padding:18px 20px 74px}
  .obf-nav{left:20px;width:calc(100% - 40px)}
}

@media (prefers-reduced-motion:reduce){
  .obf-page,.obf-page.on .obf-st,.obf-page.on .obf-big .obf-bar,
  .obf-page.on .obf-chart .ln,.obf-page.on .obf-chart .dot,.obf-tk.now i{
    animation:none !important}
  .obf-st{opacity:1}
  .obf-big .obf-bar{width:80%}
  .obf-chart .ln{stroke-dashoffset:0}
  .obf-chart .dot{opacity:1}
}
</style>
<div class="obf-frame">
  <div class="obf-sheet" id="obfSheet"></div>
  <div class="obf-rail">
    <svg class="obf-mesh" viewBox="0 0 322 900" preserveAspectRatio="none">
      <g stroke="#fff" stroke-width="1" fill="none">
        <path d="M0 150 L161 -30 L322 150 L161 330 Z"/>
        <path d="M0 510 L161 330 L322 510 L161 690 Z"/>
        <path d="M0 870 L161 690 L322 870"/>
        <path d="M-40 330 L362 330 M-40 690 L362 690"/>
        <path d="M161 -30 L161 900"/>
      </g>
    </svg>
    <div class="obf-list" id="obfRail"></div>
  </div>
  <div class="obf-nav">
    <div class="obf-arrow" id="obfPrev">&#8592;</div>
    <div class="obf-arrow" id="obfNext">&#8594;</div>
    <div class="obf-count" id="obfCount"></div>
    <div class="obf-ticks" id="obfTicks"></div>
    <div class="obf-hint">пауза &#183; читайте</div>
  </div>
</div>
</template>
"""


BRIEF_JS = """
<script>
(function () {
  var DATA = {};
  try { DATA = JSON.parse(document.getElementById('obfData').textContent); }
  catch (e) { DATA = {}; }
  var ST = DATA.stars || [], M = DATA.market || {};
  /* ЯКОРЬ — ПО ИДЕНТИФИКАТОРУ, как у прежней сводки.
     Я взял класс .ob-brief и, не найдя его, скрипт выходил МОЛЧА:
     страницы оставались скрытыми (без .on), стрелки не слушали
     нажатий, а на экране был чёрный прямоугольник в белой рамке.
     Ошибка тихая и потому дорогая — молчание выглядит как «работает,
     но пусто».
     Теперь берём #obBrief, а если его нет — рамку или тело документа.
     Экран должен показаться в любом случае: сводка, которая не
     нарисовалась, хуже сводки некрасивой. */
  var wrap = document.getElementById('obBrief')
          || document.querySelector('.ob-brief')
          || document.body;

  /* ТЕНЕВОЕ ДЕРЕВО. Разметка и стили лежат в <template> — там они
     инертны, общий CSS документа их не видит. Клонируем в shadow root
     узла #obfHost: с этого момента внешние правила внутрь не проходят.
     Если теневых деревьев в браузере нет (древний движок) — кладём
     разметку прямо в узел, как было; хуже прежнего не станет.
     Нет узла или шаблона — это ошибка сборки, и молчать о ней нельзя. */
  var host = document.getElementById('obfHost');
  var tpl  = document.getElementById('obfTpl');
  if (!host || !tpl || !tpl.content) throw new Error('сводка: нет #obfHost или #obfTpl');
  var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  root.appendChild(tpl.content.cloneNode(true));
  function q(sel){ return root.querySelector(sel); }
  var frame = q('.obf-frame');
  var reduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion:reduce)').matches;

  /* ── помощники ── */
  function num(v){ var n = +v; return isFinite(n) ? n : null; }
  function esc(s){ return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function pct(v, d){ var n = num(v); if (n === null) return '—';
    return (n > 0 ? '+' : '') + n.toFixed(d === undefined ? 1 : d) + '%'; }
  function money(v){ var n = num(v); if (n === null) return '—';
    var a = Math.abs(n);
    if (a >= 1e9) return '$' + (n/1e9).toFixed(1) + 'B';
    if (a >= 1e6) return '$' + (n/1e6).toFixed(1) + 'M';
    if (a >= 1e3) return '$' + Math.round(n/1e3) + 'K';
    return '$' + Math.round(n); }
  function sign(v){ var n = num(v); return n === null ? '' : (n >= 0 ? 'up' : 'dn'); }
  function star(t){ for (var i=0;i<ST.length;i++) if (ST[i].t === t) return ST[i];
    return null; }

  /* Ход позиции считаем ОТ ЦЕНЫ ВХОДА, а не берём готовым: в звезде
     лежит ход от появления в журнале, а в книге — своя цена входа,
     и это разные числа. */
  function bookChg(s){
    var b = s.book || {}, px = num(s.px), en = num(b.px);
    if (px === null || en === null || !en) return null;
    return (px/en - 1) * 100;
  }

  /* ── график: ломаная по ряду ── */
  function linePath(ser, w, h, pad){
    if (!ser || ser.length < 2) return null;
    var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
    var rng = (hi - lo) || 1, out = [], i, x, y;
    for (i = 0; i < ser.length; i++) {
      x = pad + i * (w - 2*pad) / (ser.length - 1);
      y = h - pad - (ser[i] - lo) / rng * (h - 2*pad);
      out.push(x.toFixed(1) + ' ' + y.toFixed(1));
    }
    return { d: 'M' + out.join(' L'),
             lx: (pad + (w - 2*pad)).toFixed(1),
             ly: (h - pad - (ser[ser.length-1] - lo)/rng*(h - 2*pad)).toFixed(1) };
  }
  /* Столбики объёма — по логарифму. При линейной шкале ×1057 придавил
     бы все остальные в ноль, и график стал бы одним столбом. */
  function volBars(rat, w, h, pad){
    if (!rat || !rat.length) return '';
    var lr = rat.map(function(v){ return Math.log10(1 + Math.max(0, +v || 0)); });
    var mx = Math.max.apply(null, lr) || 1;
    var bw = (w - 2*pad)/rat.length - 2, out = [], i, bh, x;
    for (i = 0; i < lr.length; i++) {
      bh = Math.max(1.5, lr[i]/mx * (h - 2*pad - 6));
      x = pad + i * (w - 2*pad)/rat.length;
      out.push('<rect x="' + x.toFixed(1) + '" y="' + (h - pad - bh).toFixed(1) +
               '" width="' + bw.toFixed(1) + '" height="' + bh.toFixed(1) + '"/>');
    }
    return out.join('');
  }
  function chartHTML(ser, rat, cap){
    var W = 520, H = 104, P = 3;
    var lp = linePath(ser, W, H, P);
    if (!lp) return '';
    return '<div class="obf-chart obf-st" style="--i:2">' +
      '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' +
      '<g class="bars">' + volBars(rat, W, H, P) + '</g>' +
      '<path class="ln" d="' + lp.d + '"/>' +
      '<circle class="dot" cx="' + lp.lx + '" cy="' + lp.ly + '" r="4.5"/>' +
      '</svg><div class="cap">' + cap + '</div></div>';
  }

  /* ── строительные кирпичи страницы ── */
  var stamp = (function(){
    var t = M.ts ? new Date(M.ts) : new Date();
    function p(n){ return (n < 10 ? '0' : '') + n; }
    return 'прогон ' + p(t.getDate()) + '.' + p(t.getMonth()+1) +
           ' · ' + p(t.getHours()) + ':' + p(t.getMinutes());
  })();

  function head(right){
    return '<div class="obf-top obf-st" style="--i:0">' +
      '<div class="obf-logo"><span class="o">+</span>СКРИНЕР</div>' +
      '<div class="obf-stamp">' + esc(right || stamp) + '</div></div>';
  }
  function numCell(i, v, cls, cap, det, detWarn){
    return '<div class="obf-num obf-st" style="--i:' + i + '">' +
      '<div class="v' + (cls ? ' ' + cls : '') + '">' + v + '</div>' +
      '<div class="c">' + esc(cap) + '</div>' +
      (det ? '<div class="d' + (detWarn ? ' warn' : '') + '">' + det + '</div>' : '') +
      '</div>';
  }
  function page(title, body, right){
    return '<section class="obf-page">' + head(right) +
      '<div class="obf-mid">' +
      (title ? '<div class="obf-kick obf-serif obf-st" style="--i:1">' +
               esc(title) + '</div>' : '') +
      body + '</div></section>';
  }

  /* ══════════════ СТРАНИЦЫ ══════════════
     Собираются ИЗ ДАННЫХ. Пустой раздел страницу не создаёт: лист с
     одним словом «нет данных» — это потерянные двадцать шесть секунд. */
  var P = M.permission || {}, pp = P.parts || {}, pages = [];

  /* 1 · окно рынка */
  (function(){
    var reasons = [];
    ['btc','funding','oi','cascade','calendar'].forEach(function(k){
      var part = pp[k] || {};
      if (part.warn && part.note) reasons.push(part.note);
    });
    var body =
      '<div class="obf-big obf-st" style="--i:2"><span class="obf-bar"></span>' +
      '<span class="g">' + (P.warnCount || 0) + ' из ' + (P.knownCount || 7) +
      '</span></div>' +
      '<div class="obf-sub obf-st" style="--i:4">' +
      (P.warnCount ? '<b>' + P.warnCount + '</b> предупреждения из ' +
        (P.knownCount || 7) + ' составляющих. ' : 'Явных предупреждений нет. ') +
      (reasons.length ? esc(reasons[0]) + '.' : '') +
      (M.appetite ? ' Аппетит ' + esc(M.appetite).replace('/', ' из ') + '.' : '') +
      '</div>';
    pages.push(page('Окно рынка', body));
  })();

  /* 2 · фон */
  (function(){
    var AS = M.altShare || {}, rs = pp.reservoir || {}, md = M.medians || {};
    var cells = '', i = 2;
    if (AS.d7 !== undefined && AS.d7 !== null) {
      cells += numCell(i++, AS.d7 + '%', '', 'обошли биткоин',
        AS.d7 < 50 ? 'прилив до альтов не дошёл' : 'прилив дошёл до альтов',
        AS.d7 < 50);
    }
    if (rs.share !== undefined && rs.share !== null) {
      /* ВОЗРАСТ РУЧНОГО ЧИСЛА ПЕЧАТАЕТСЯ. Раньше стейблы стояли одним
         и тем же числом четвёртый день, и читалось это как измерение
         сегодняшнего дня. Возраст в данных был — бриф его не печатал. */
      var age = num(rs.ageDays);
      cells += numCell(i++, rs.share + '%', '', 'стейблы к капе',
        age !== null && age > 2 ? 'данным ' + Math.round(age) +
          ' дн · файл не обновлялся' : null, true);
    }
    if (M.dom) cells += numCell(i++, M.dom + '%', '', 'доминация BTC');
    if (md.d7 !== undefined) {
      cells += numCell(i++, pct(md.d7), '', 'медиана за неделю',
        'за сутки ' + pct(md.d1) + ' · за месяц ' + pct(md.d30));
    }
    if (M.sector) {
      var sp = String(M.sector).split(' ');
      cells += numCell(i++, esc(sp[0]), 'acc', 'сектор дня',
        esc(sp.slice(1).join(' ')));
    }
    if (cells) pages.push(page('Фон', '<div class="obf-nums">' + cells + '</div>',
      'фон рынка'));
  })();

  /* 3 · портфели */
  (function(){
    var pf = M.portfolios || {}, jr = M.journal || {}, cells = '', i = 2;
    if (pf.hold && pf.hold.open) {
      cells += numCell(i++, pct(pf.hold.pnlPct), sign(pf.hold.pnlPct),
        'журнал · ' + pf.hold.open + ' позиций',
        'вложено ' + money(pf.hold.invested) + ' · стоит ' +
        money(pf.hold.value) + ' · ' + money(pf.hold.pnl));
    }
    if (pf.trade && pf.trade.open) {
      cells += numCell(i++, pct(pf.trade.pnlPct), sign(pf.trade.pnlPct),
        'трейдинг · ' + pf.trade.open + ' позиций',
        'вложено ' + money(pf.trade.invested) + ' · стоит ' +
        money(pf.trade.value) + ' · ' + money(pf.trade.pnl));
    }
    /* «Лучшая» и «худшая» УБРАНЫ намеренно: минус может быть сквизом
       для снятия плеч с возвратом, а слово «худшая» приговаривает
       монету до того, как ход закончен, и тянет закрыть в минус.
       Осталось только направление. Тикеры одного цвета — красным был
       приговор, а не измерение. */
    if (jr.best) cells += numCell(i++, esc(jr.best.t), '', 'дальше всех вверх',
      pct(jr.best.chg, 1) + ' от входа');
    if (jr.worst) {
      var los = (pf.losers || []).filter(function(x){ return x.t !== jr.worst.t; })
        .slice(0, 3).map(function(x){ return esc(x.t) + ' ' + pct(x.chg, 1); });
      cells += numCell(i++, esc(jr.worst.t), '', 'дальше всех вниз',
        pct(jr.worst.chg, 1) + ' от входа' +
        (los.length ? ' · рядом ' + los.join(', ') : '') + ' · ход не закрыт');
    }
    if (cells) pages.push(page('Портфели', '<div class="obf-nums">' + cells + '</div>',
      'портфели'));
  })();

  /* 4 · лидер */
  (function(){
    var L = M.leader, LC = M.leaderChart || {};
    if (!L || !L.t) return;
    var s = star(L.t) || {};
    var cap = 'ход за две недели' +
      (LC.zone ? ' · зона ' + (+LC.zone).toFixed(5) : '') +
      (LC.stop ? ' · стоп ' + esc(LC.stop) : '') +
      (LC.target ? ' · цель ' + esc(LC.target) : '');
    var body =
      '<div class="obf-big obf-st" style="--i:2"><span class="obf-bar"></span>' +
      '<span class="g">' + esc(L.t) + '</span></div>' +
      chartHTML(LC.series || s.series, null, cap) +
      '<div class="obf-sub obf-st" style="--i:5">Скор <b>' + (L.score || '—') +
      '</b>' + (L.case ? ' · фигура ' + esc(L.case) : '') +
      (LC.horizonDays ? ' · горизонт ' + LC.horizonDays + ' дн' : '') +
      (L.cap ? ' · ' + esc(L.cap) : '') + '.</div>';
    pages.push(page('Лидер', body, 'лидер прогона'));
  })();

  /* 4а · ЛИДЕРЫ ТРЁХ ДНЕЙ
     Кто держался в топе выборки последние трое суток. Считаем по
     hits_by_day, а не по last_seen: last_seen стоит почти у всех
     (59 из 60 в проверенном прогоне) и не фильтрует ничего — монета
     остаётся «виденной», пока она вообще в журнале. Попадания по дням
     отвечают на другой вопрос: сколько РАЗ монета была в топе.

     Зачем страница. Разовое попадание — шум; три дня подряд — то, что
     система выделяет упорно, и это стоит увидеть рядом. Лидер
     СЕГОДНЯШНЕГО прогона помечен отдельно: он в этом списке не самый
     частый, и без метки его не отличить от вчерашних. */
  (function(){
    var lead = (M.leader || {}).t || null;
    /* byDay — МАССИВ за семь дней, свежий день последний, нули
       честные (см. _hits_by_day в analytics_stars). Не словарь с
       датами: сначала я написал разбор словаря, и ветка не сработала
       бы вовсе — молча дала бы пустую страницу.
       Берём три последних дня массива. Дни считаем от конца ряда, а
       не от сегодняшнего числа: ряд уже выровнен по календарю в
       источнике, и второй раз выравнивать его нечем. */
    var rows = ST.map(function(s){
      var by = s.byDay;
      if (!by || !by.length) return null;
      var last3 = by.slice(-3);
      var n = 0, i;
      for (i = 0; i < last3.length; i++) n += (+last3[i] || 0);
      if (!n) return null;
      var names = ['позавчера', 'вчера', 'сегодня'].slice(-last3.length);
      return { t: s.t, n: n,
               days: last3.map(function(v, k){
                 return { d: names[k], v: +v || 0 }; }),
               chg: num(s.chg), cs: s.st || '', cap: s.cap || '' };
    }).filter(Boolean).sort(function(a, b){ return b.n - a.n; });

    if (rows.length < 3) return;
    var top = rows.slice(0, 8);
    /* Лидер прогона обязан быть на странице, даже если по числу
       попаданий он не в первой восьмёрке: страница про него тоже. */
    var has = top.some(function(r){ return r.t === lead; });
    if (lead && !has) {
      var me = rows.filter(function(r){ return r.t === lead; })[0];
      if (me) { top = top.slice(0, 7); top.push(me); }
    }

    var body = '<div class="obf-pos">' + top.map(function(r, k){
      var isLead = r.t === lead;
      var by = r.days.map(function(x){ return x.d + ' ' + x.v; }).join(' · ');
      return '<div class="obf-p obf-st" style="--i:' + (2 + (k >> 1)) + '">' +
        '<div class="r"><span class="t">' + esc(r.t) +
          (isLead ? '<i class="obf-now">лидер прогона</i>' : '') + '</span>' +
        '<span class="n ' + (isLead ? 'acc' : sign(r.chg)) + '">' + r.n +
        '</span></div>' +
        '<div class="d">' + by + (r.cs ? ' · ' + esc(r.cs) : '') +
        (r.chg !== null ? ' · ход ' + pct(r.chg, 0) : '') + '</div></div>';
    }).join('') + '</div>' +
    '<div class="obf-sub obf-st" style="--i:' + (2 + (top.length >> 1) + 1) +
      '">Число справа — <b>сколько раз монета попала в топ выборки</b> за ' +
      'три дня наблюдений. Разовое попадание — шум; повторяющееся — то, ' +
      'что система выделяет упорно.</div>';
    pages.push(page('Лидеры трёх дней', body, 'кто держится'));
  })();

  /* 5 · топ объёма */
  (function(){
    var VC = M.volChart || {}, top = (M.topVol || []).slice(0, 3);
    var lead = M.peakVol || {};
    if (!lead.sym && !top.length) return;
    var ls = star(lead.sym) || {};
    /* ЦЕНА главной линией. Объём после сквиза на 90% бывает огромным и
       не значит ничего — толку от него ноль, если цена не пошла. */
    var ch = '';
    if (ls.series && ls.series.length > 1) {
      var g = (ls.series[ls.series.length-1] / ls.series[0] - 1) * 100;
      ch = chartHTML(ls.series, VC.ratios,
        esc(lead.sym) + ' · цена за две недели, ' + pct(g, 0) + ' · объём фоном');
    }
    var cells = '', i = 3;
    if (lead.sym) cells += numCell(i++, '×' + Math.round(lead.x || 0), 'acc',
      esc(lead.sym), (VC.cap ? esc(VC.cap) : '') +
      (VC.funding ? ' · фандинг ' + (+VC.funding).toFixed(2) + '%' : ''));
    top.forEach(function(v){
      if (v.t === lead.sym) return;
      cells += numCell(i++, '×' + (+v.x).toFixed(1), '', esc(v.t), esc(v.cap || ''));
    });
    pages.push(page('Топ объёма', ch + '<div class="obf-nums">' + cells + '</div>',
      'объём'));
  })();

  /* 6 · брать */
  (function(){
    var take = ST.filter(function(s){
      return (s.act || {}).group === 'take' && (s.act || {}).act === 'брать'; });
    var body;
    if (take.length) {
      body = '<div class="obf-pos">' + take.slice(0, 8).map(function(s, k){
        return '<div class="obf-p obf-st" style="--i:' + (2 + (k >> 1)) + '">' +
          '<div class="r"><span class="t">' + esc(s.t) + '</span>' +
          '<span class="n up">' + esc(s.st || '') + '</span></div>' +
          '<div class="d">' + esc((s.act || {}).why || '') + '</div></div>';
      }).join('') + '</div>';
    } else {
      body = '<div class="obf-empty obf-st" style="--i:2">нечего</div>' +
        '<div class="obf-sub obf-st" style="--i:3">Ни одна монета не прошла ' +
        'порог входа.</div>';
    }
    pages.push(page('Брать', body, 'вход'));
  })();

  /* 7–8 · в работе, плюс и минус отдельно */
  (function(){
    var book = ST.filter(function(s){ return (s.book || {}).usd; })
      .map(function(s){ var c = bookChg(s); return { s: s, c: c }; })
      .filter(function(o){ return o.c !== null; })
      .sort(function(a, b){ return b.c - a.c; });
    if (!book.length) return;
    function block(list, title, right){
      /* ОБЩАЯ ПРИЧИНА ПЕЧАТАЕТСЯ ОДИН РАЗ.
         Событие вроде голосования Solana даёт один и тот же довод всем
         монетам сразу, и в строках он повторялся шесть раз подряд —
         шесть одинаковых абзацев вместо шести разных фактов. Считаем,
         какой довод общий, выносим его над списком, а в строках
         оставляем только то, что у монеты СВОЁ. */
      var cnt = {}, top = null, topN = 0;
      list.forEach(function(o){
        var w = (o.s.act || {}).why; if (!w) return;
        cnt[w] = (cnt[w] || 0) + 1;
        if (cnt[w] > topN) { topN = cnt[w]; top = w; }
      });
      var shared = topN >= 2 ? top : null;
      var body = '<div class="obf-pos">' + list.map(function(o, k){
        var s = o.s, b = s.book || {};
        var det = money(b.usd) + (s.st ? ' · ' + esc(s.st) : '') +
          (b.px ? ' · вход ' + b.px : '');
        var why = (s.act || {}).why;
        if (why && why !== shared) det += ' · ' + esc(why);
        return '<div class="obf-p obf-st" style="--i:' + (2 + (k >> 1)) + '">' +
          '<div class="r"><span class="t">' + esc(s.t) + '</span>' +
          '<span class="n ' + sign(o.c) + '">' + pct(o.c) + '</span></div>' +
          '<div class="d">' + det + '</div></div>';
      }).join('') + '</div>' +
      (shared ? '<div class="obf-sub obf-st" style="--i:' +
        (2 + (list.length >> 1) + 1) + '">Общее для ' + topN +
        ' позиций: ' + esc(shared) + '.</div>' : '');
      pages.push(page(title, body, right));
    }
    var up = book.filter(function(o){ return o.c >= 0; });
    var dn = book.filter(function(o){ return o.c < 0; });
    if (up.length) block(up, 'В работе · плюс', 'в работе · в плюсе');
    if (dn.length) block(dn, 'В работе · минус', 'в работе · в минусе');
  })();

  /* 9 · закрыть */
  (function(){
    var out = ST.filter(function(s){ return (s.act || {}).group === 'exit'; });
    var body = out.length
      ? '<div class="obf-pos">' + out.map(function(s, k){
          return '<div class="obf-p obf-st" style="--i:' + (2 + (k >> 1)) + '">' +
            '<div class="r"><span class="t">' + esc(s.t) + '</span>' +
            '<span class="n dn">' + pct(bookChg(s)) + '</span></div>' +
            '<div class="d">' + esc(s.exitWhy || (s.act || {}).why || '') +
            '</div></div>'; }).join('') + '</div>'
      : '<div class="obf-empty obf-st" style="--i:2">нечего</div>' +
        '<div class="obf-sub obf-st" style="--i:3">Ни одна позиция не дошла ' +
        'до правила выхода.</div>';
    pages.push(page('Закрыть', body, 'выход'));
  })();

  /* 10 · спят */
  (function(){
    var d = M.dormant || [];
    if (!d.length) return;
    var body = '<div class="obf-plain obf-st" style="--i:2">' +
      d.map(function(x){ return '<span class="obf-tick">' + esc(x.t) + '</span>'; })
       .join('') + '</div>' +
      '<div class="obf-sub obf-st" style="--i:3">Ни движения, ни объёма. ' +
      'Держим в выборке — из этого состояния и выходят.</div>';
    pages.push(page('Спят · ' + d.length, body, 'спящие'));
  })();

  /* 11 · итог */
  (function(){
    var size = (P.warnCount || 0) >= 4 ? 'урезанный'
             : (P.warnCount || 0) >= 2 ? 'полный' : 'полный';
    var body =
      '<div class="obf-big obf-st" style="--i:2"><span class="obf-bar"></span>' +
      '<span class="g">' + size + '</span></div>' +
      '<div class="obf-sub obf-st" style="--i:4">Окно рынка ' +
      (P.warnCount || 0) + ' из ' + (P.knownCount || 7) +
      ' — размер по правилу <b>' + size + '</b>.</div>';
    pages.push(page('Итог', body, 'итог прогона'));
  })();

  /* ══════════════ ЧАСТОКОЛ ══════════════
     ВСЕ события, без «и ещё восемь». Прежняя строка показывала три и
     прятала остальные — среди спрятанных оказался самый тяжёлый транш
     списка. Если событий много, резать надо порог попадания, а не
     хвост: тогда решает важность, а не место на экране. */
  function eventsHTML(withHead){
    var cal = pp.calendar || {}, items = cal.items || [];
    var KIND = { delist:'делистинг', unlock:'разлок', risk:'риск',
                 macro:'макро', support:'опора' };
    var html = withHead ? '<div class="obf-h">Впереди</div>' : '';
    /* ПУСТАЯ КОЛОНКА НЕ МОЛЧИТ. Тёмный столбец без единой строки
       читается как «сломалось», а не как «событий нет» — и отличить
       одно от другого с экрана нельзя. Пишем прямо, что случилось:
       календарь не собран или в горизонте пусто. */
    if (!items.length) {
      var why = pp.calendar
        ? 'в горизонте пяти дней ни разлоков, ни делистингов, ни макродат'
        : 'календарь в этом прогоне не собран';
      return html + '<div class="obf-ev"><div class="w">впереди</div>' +
        '<div class="t">событий нет</div><div class="d">' + why + '</div></div>';
    }
    items.forEach(function(e){
      var d = num(e.days);
      var when = e.running ? 'сегодня · идёт'
        : d === 0 ? 'сегодня' : d === 1 ? 'завтра' : 'через ' + d + ' дн';
      var inBook = /МОНЕТА В КНИГЕ|в книге/i.test(e.note || '');
      html += '<div class="obf-ev">' +
        '<div class="w' + (e.running || d === 0 ? ' now' : '') + '">' +
          esc(when) + '</div>' +
        '<div class="t">' + esc(e.title) +
          '<span class="k' + (inBook ? ' book' : '') + '">' +
          esc(inBook ? 'в книге' : (KIND[e.kind] || e.kind || '')) + '</span></div>' +
        (e.note ? '<div class="d">' + esc(String(e.note).slice(0, 190)) +
                  '</div>' : '') +
        '</div>';
    });
    html += '<div class="obf-more">' + items.length + ' ' +
      (items.length === 1 ? 'событие' : items.length < 5 ? 'события' : 'событий') +
      ' · показаны все</div>';
    return html;
  }
  (function(){
    var rail = q('#obfRail');
    if (rail) rail.innerHTML = eventsHTML(true);
    /* Та же разметка — отдельной страницей в конце колоды. На широком
       экране она скрыта стилем, на узком становится единственным
       местом, где события видны. */
    var ev = eventsHTML(false);
    if (ev) {
      pages.push('<section class="obf-page narrow">' + head('впереди') +
        '<div class="obf-mid"><div class="obf-kick obf-serif obf-st" ' +
        'style="--i:1">Впереди</div>' +
        '<div class="obf-list obf-st" style="--i:2">' + ev + '</div></div>' +
        '</section>');
    }
  })();

  /* ══════════════ ЛИСТАЛКА ══════════════ */
  var sheet = q('#obfSheet');
  sheet.innerHTML = pages.join('');
  var all = [].slice.call(sheet.querySelectorAll('.obf-page'));
  /* СЧИТАЕМ ТОЛЬКО ВИДИМЫЕ. Страница событий существует всегда, но
     на широком экране скрыта стилем — если бы листалка считала её,
     на десятой странице был бы шаг в пустоту и счётчик врал бы.
     Спрашиваем сам браузер, а не ширину окна: правило может измениться
     в стилях, и второе место, где та же граница записана числом, рано
     или поздно разойдётся с первым. */
  function shown(){
    return all.filter(function(n){ return getComputedStyle(n).display !== 'none'; });
  }
  var els = shown();
  var ticks = q('#obfTicks');
  var count = q('#obfCount');
  var prev = q('#obfPrev');
  var next = q('#obfNext');
  var nav = q('.obf-nav');

  /* cur = −1, а не 0: защита «не листать на текущую» сравнивает i с cur,
     и при нуле она же блокировала САМЫЙ ПЕРВЫЙ показ — экран
     открывался пустым. Минус один значит «страницы ещё не было». */
  var cur = -1, timer = null, outTimer = null, paused = false, done = false;
  var css = getComputedStyle(frame);
  var WIPE = (parseFloat(css.getPropertyValue('--wipe')) || 3.15) * 1000;
  var DWELL = (parseFloat(css.getPropertyValue('--dwell')) || 26) * 1000;

  var tks = [];
  function buildTicks(){
    ticks.innerHTML = '';
    els.forEach(function(_, i){
      var t = document.createElement('div');
      t.className = 'obf-tk';
      t.innerHTML = '<i></i>';
      /* Полоски кликабельны: если нужное уже позади, не листать по одной. */
      t.onclick = function(){ go(i, i < cur ? 'back' : 'fwd'); };
      ticks.appendChild(t);
    });
    tks = [].slice.call(ticks.children);
  }
  buildTicks();

  /* ПОВОРОТ ПЛАНШЕТА МЕНЯЕТ СОСТАВ КОЛОДЫ: страница событий то
     появляется, то уходит. Пересобираем список и полоски, а место в
     колоде удерживаем по САМОЙ СТРАНИЦЕ, а не по номеру — номера
     сдвигаются, страница остаётся той же. */
  var rezTimer = null;
  window.addEventListener('resize', function(){
    clearTimeout(rezTimer);
    rezTimer = setTimeout(function(){
      var node = cur >= 0 ? els[cur] : null;
      els = shown();
      if (!els.length) return;
      buildTicks();
      var i = node ? els.indexOf(node) : 0;
      if (i < 0) i = Math.min(cur < 0 ? 0 : cur, els.length - 1);
      cur = -1;
      go(i, 'fwd');
    }, 220);
  });

  function go(i, dir){
    if (i < 0 || i >= els.length || i === cur) return;
    dir = dir || 'fwd';
    var old = cur >= 0 ? els[cur] : null;
    if (old) {
      els.forEach(function(q){ q.classList.remove('out'); });
      clearTimeout(outTimer);
      old.classList.remove('on');
      old.classList.add('out', dir);
      outTimer = setTimeout(function(){
        old.classList.remove('out', 'fwd', 'back');
      }, WIPE * 1.15 + 40);
    }
    cur = i;
    var p = els[cur];
    /* Перезапуск анимации: браузер не проигрывает её заново, если класс
       просто вернули. Заставляем пересчитать разметку между снятием и
       возвратом — иначе вторая страница въезжала бы без клина. */
    p.classList.remove('on', 'fwd', 'back');
    void p.offsetWidth;
    p.classList.add('on', dir);
    tks.forEach(function(t, k){
      t.classList.toggle('done', k < cur);
      t.classList.remove('now');
    });
    void tks[cur].offsetWidth;
    tks[cur].classList.add('now');
    count.textContent = (cur + 1) + ' / ' + els.length;
    prev.classList.toggle('off', cur === 0);
    next.classList.toggle('off', cur === els.length - 1);
    arm();
  }

  function arm(){
    clearTimeout(timer);
    if (paused) return;
    if (cur >= els.length - 1) {
      /* Последняя страница стоит дольше и отдаёт экран оболочке сама. */
      timer = setTimeout(close, DWELL * 1.4);
      return;
    }
    timer = setTimeout(function(){ go(cur + 1, 'fwd'); }, DWELL);
  }

  /* Курсор на листе — значит читают: ход стоит, полоска замирает.
     Это и есть ответ на «не успел прочитать»: ловить стрелку не надо. */
  sheet.onmouseenter = function(){
    paused = true; frame.classList.add('obf-paused'); clearTimeout(timer); };
  sheet.onmouseleave = function(){
    paused = false; frame.classList.remove('obf-paused'); arm(); };

  prev.onclick = function(e){ e.stopPropagation(); go(cur - 1, 'back'); };
  next.onclick = function(e){ e.stopPropagation(); go(cur + 1, 'fwd'); };

  /* ВЫХОД: СТРЕЛКИ ЛИСТАЮТ, ВСЁ ОСТАЛЬНОЕ ЗАКРЫВАЕТ.
     Клавиатура: стрелки вправо и вниз — вперёд, влево и вверх — назад.
     Любая другая клавиша закрывает сводку. Исключения две, и обе про
     то, что нажатие не было командой сводке: одинокий модификатор
     (Shift, Ctrl, Alt, Cmd — сам по себе ничего не значит) и сочетание
     с Ctrl или Cmd (это команда браузеру: перезагрузить, открыть
     вкладку, консоль).
     Мышь и палец: клик в любом месте закрывает — на листе, на колонке
     событий, на сером поле. Кроме полосы навигации внизу: стрелки,
     счётчик и полоски листают, и закрывать по ним нельзя.
     Путь события берём составным (composedPath): клик рождается внутри
     теневого дерева, и снаружи его цель видна как узел #obfHost. */
  var MODS = { Shift:1, Control:1, Alt:1, Meta:1, CapsLock:1, NumLock:1,
               ScrollLock:1, Fn:1, FnLock:1, Hyper:1, Super:1, OS:1,
               Dead:1, Unidentified:1 };
  /* До первой страницы ничего не закрываем: клик по окну, пока крутится
     лоадер оболочки, — это не «хватит», а попытка попасть в окно. */
  document.addEventListener('keydown', function(e){
    if (done || cur < 0) return;
    var k = e.key;
    if (k === 'ArrowRight' || k === 'ArrowDown') {
      e.preventDefault(); go(cur + 1, 'fwd'); return; }
    if (k === 'ArrowLeft' || k === 'ArrowUp') {
      e.preventDefault(); go(cur - 1, 'back'); return; }
    if (MODS[k] || e.ctrlKey || e.metaKey) return;
    close();
  });
  document.addEventListener('click', function(e){
    if (done || cur < 0) return;
    var path = e.composedPath ? e.composedPath() : [], n;
    if (!path.length) for (n = e.target; n; n = n.parentNode) path.push(n);
    for (var i = 0; i < path.length; i++) if (path[i] === nav) return;
    close();
  }, true);

  /* ── Выход ──
     Сводка не «закрывается», оставаясь в документе: документ и есть
     сводка. Она сообщает оболочке, что доиграла, и оболочка уничтожает
     этот документ вместе с таймерами. Класс .on снимается всё равно:
     между сообщением и сменой документа проходит кадр-другой, и без
     затухания это выглядело бы обрывом. */
  function close(){
    clearTimeout(timer); clearTimeout(outTimer);
    wrap.classList.remove('on');
    if (done) return;
    done = true;
    try {
      window.parent.postMessage(
        { type: 'ob:done', screen: 'brief' }, window.location.origin);
    } catch (e) { /* открыт вне оболочки — просто гаснем */ }
  }

  /* ПРЕДОХРАНИТЕЛЬ, а не расписание: выход зовёт сама очередь выше.
     Таймер оставлен на случай, если очередь встанет намертво, — с
     запасом на самый длинный сценарий. */
  setTimeout(close, els.length * (DWELL + WIPE * 2) + 30000);

  /* Фокус забираем себе: сводка живёт в iframe, а клавиши приходят
     тому документу, у которого фокус. Без этого первое нажатие уходило
     бы оболочке, и «любая клавиша закрывает» не работало бы, пока по
     сводке не кликнут. */
  function start(){
    if (cur < 0) go(0, 'fwd');
    try { window.focus(); } catch (e) { /* не дали — переживём */ }
  }

  wrap.classList.add('on');
  /* Подстраховка от невидимой сводки. Класс .on гасит прозрачность у
     .ob-brief из общего файла стилей; если якорем оказался другой узел,
     прозрачность может остаться нулевой и экран будет пустым при
     полностью рабочем скрипте. Проверяем ФАКТ видимости, а не наличие
     класса — и снимаем прозрачность руками, если она осталась. */
  setTimeout(function(){
    var ws = getComputedStyle(wrap);
    if (ws.display === 'none') wrap.style.display = 'block';
    if (ws.opacity === '0') {
      wrap.style.opacity = '1';
      wrap.style.pointerEvents = 'auto';
    }
  }, 60);
  if (reduce) {
    /* Без движения листалка не листается сама: показываем первую и
       ждём стрелок. Гасим движение, а не смысл. */
    go(0, 'fwd'); clearTimeout(timer);
  } else if (window.parent === window) {
    setTimeout(start, 400);
  } else {
    window.addEventListener('message', function(e){
      if (e.origin !== window.location.origin) return;
      if (e.data && e.data.type === 'ob:shown') setTimeout(start, 120);
    });
    setTimeout(start, 2500);
  }
})();
</script>
"""

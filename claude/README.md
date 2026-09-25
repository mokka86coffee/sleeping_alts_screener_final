# Папка Claude — контекст и исследования (с 26.09.2026)
Если чат с Claude оборвался: откройте новый и дайте ему эту папку.
- CONTEXT.md — весь контекст: модель рынка владельца, как работать, что стоит сейчас, открытые хвосты. Читать первым.
- research/ — исследования: rules.md (реестр правил со счётом совпадений — главный файл), moves.md (ходы по стадиям),
  exclusion.md, state_probs.md, bots.md, anatomy.csv, episodes.csv и скрипты (запускать .venv/bin/python из корня проекта).
- memory/ — копия памяти Claude (Claude Code держит её в ~/.claude/projects/...; здесь — на случай потери).
Claude обновляет CONTEXT.md и research/ после каждого важного шага.
- settings/ — настройки Claude Code: user-settings.json (~/.claude/settings.json, сейчас пустые {}), skills/ (установленные навыки:
  find-skills). ~/.claude/.claude.json не копируется — там идентификаторы машины и аккаунта, в репозиторий им нельзя.

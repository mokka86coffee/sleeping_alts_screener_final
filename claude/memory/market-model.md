---
name: market-model
description: "The owner's layered market model (25.09) — the lens for every analysis, rule and strategy in the screener; read before judging any pattern"
metadata:
  node_type: memory
  type: user
  originSessionId: fa91e09e-9d7a-4051-9dae-3dae50c899e1
  modified: 2026-09-25T20:41:45.451Z
---

The owner's picture of the market, stated 25.09. Everything is built on it, from the biggest layer down to the smallest. Each layer is a probability we accept, not an axiom. Exceptions will always exist because the market is made of living people.

**Layer 1 — market stage.** There are three stages:
1. **Past: a bear market.** Almost all alts fell 90% or more from their peaks.
2. **Now: a slow transition to a bull market.** Coins give big moves, but not the 50–100x of five years ago. Most coins have been flat for months without making new lows. BTC holds above 60k. Money is arriving slowly.
   - So a big move ends in a big squeeze back.
   - Some coins already show x5–10 from the bottom, a 50–80% pullback, and then slower further growth. This confirms the transition.
3. **Future: a bull market.** Coins rise continuously, and big moves no longer end with an 80–90% drop. Watch for this. When it is confirmed, the model and the strategies must be rebuilt.

**Layer 2 — background (incomplete, but already grounded; add to it when new factors are found).** The market is fragmented and there is not much money, so:
- **The leader matters most.** A coin making 100–1000% pulls the money to itself and drags similar coins down.
- **Sessions come next.** Each session has its own money. A coin one session picks up and another does not is not a broken rule. Ask whether the next session picks up the current leader.
- **The board median** often depends on the day of the week.
- **BTC is ignored for now.** It is either flat or gives sharp squeezes that the coins give back. Treat it as an exception.
- The key question: from which rising coin will money leave, when, and why.

**Layer 3 — market makers.** Each market maker runs its own coins, from 1 to about 30. A general rule for all coins at any time of day cannot exist, otherwise market makers would never make money. Finding the same pattern on several coins is already a win.

**There are no timeframes in the market, only the stages of a move:**
1. start;
2. confirmation of continuation, or the next session picking the move up;
3. end and reversal.

A session may not pick the move up at all. It may only accumulate, while the market maker pushes the move further in the markets it needs. All these terms are relative. They exist only so the owner and I understand each other until we find better ones.

We get there step by step. Examples from 25.09 are in claude/research/ (в проекте)groups.md: ENA, ARK and LSK session by session.

**Every move has a start and an end.** The timeframes the owner named are only a way to structure things. They are not tied to trades.
- The end of a move is explained through layer 2: a weekend arrived, the median changed, the session changed, or the market maker simply decided it was enough.
- A move that stopped is not a failed indicator.
- Mixing everything into one pile creates false exceptions.

**The core idea:** the market is money moving within one asset or across several, driven by the wish to earn. For every move there is a price the crowd is willing to go to and no further. That price depends on the moment: the hour, the day, the background.
- It cannot be derived logically, so we go by observations that can be confirmed.
- Timeframes and similar devices are temporary scaffolding. They may later be dropped as artifacts.

**Every move has exactly three stages: start, continuation, end.** There are no exceptions to this, because the market runs 24/7.
- Frames such as sessions and timeframes are only for logical understanding of such a scale.
- Rules don't exclude each other. They are carried off into different directions.
- An "exception" means something was not accounted for, not that the rule is wrong: the rule doesn't always work, and we either know the reason or don't yet.
- In rules.md, write down the cases where a rule didn't work and the suspected reason. Never write "rule failed".

**Three sources of misunderstanding between the owner and the screener (25.09), to fix over time:**
1. The coin card states "брать / держать / выходить / хеджировать" categorically, with no probability. That reads as a 100% promise. Every verdict should carry the chance of it working, backed by our own history.
2. Trades are not tied to the stage of the move. State the chance of a result by a horizon that makes sense, e.g. "until the next session: X% chance of profit (5% or 50%)", rather than "short-term / long-term".
3. Strategies differ, and each needs its own probabilistic description. Right now it is rigid: "enter here, exit there".

The owner gave full autonomy ("делай все, что считаешь нужным"). Screen changes still go through an HTML prototype first.

**Working method (owner, 25.09): successive exclusion.**
- Over the last weeks' data, find the common rules and split the coins into groups.
- Everything that didn't behave that way goes into an "exceptions" group.
- Within the exceptions, look for looser commonalities, which give new groups plus new exceptions, and repeat.
- A rule that works 70–80% is kept: with the same money in, it still yields a profit.
- Strategies may split in two or disappear, and that is normal.
- The data is ample: leaders, the queue journal and the bot's trades.
- The owner now takes a minimal part and gave me autonomy to analyse and improve strategies. They will add or correct things occasionally.

**The key principle:** never discard a rule as "not working". Find where it applies and where it doesn't: which stage of the move, which background, which market maker.
- The existing indicators already work about as well as anything can.
- 60–70% probability is already a win.
- Describe each observed move by stage: start, middle, signs of the end, end. For each stage record what was visible and what the background was. A probability is then the share of similar past moves that continued from the same state.

**Each rule carries its own conditions and its own size of payoff.**
- Example: one rule works only with a leader, a certain board median and so on, and gives at most 5–10% per trade.
- Another: open interest rises while price stands still for several days, and the move gives +200–300%.
- These are not about timeframes but about the start and end of a move. Terms are only bridges for the reasoning; don't fixate on them.
- What every rule must answer: when to enter, where to exit, and when to take the opposite position.

**The distant ideal:** a bot that on every minute candle gives the probability that the move continues (90%, then 80%, …). At around 50% it starts building a short and closing the long. We are very far from that, so we move in logical steps.

**Correction, 25.09:** I turned the owner's reasoning into rules and task lists ("split by horizon", "let's do step 1…"). They want to reason about the market together first. Don't convert every thought into a plan or a script.

**What we know:** rising open interest and volume drive the move, but that is the middle of the move. We don't know when it starts, why these coins and not similar ones, or when it ends.

**Why:** a month of pooled, flat analysis produced no money. The owner wants every rule judged inside this model, so that a working rule is not marked as failed because of background.
**How to apply:**
- Before calling a rule broken, check the layer-2 background (leader, session pickup, board median and weekday) and the horizon.
- Keep 1h analysis in its place: it cannot answer layer-1 questions.

Related: [[working-style]], [[leaders-study]], [[screener-project]]

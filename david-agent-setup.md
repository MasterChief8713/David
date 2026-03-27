# David's Agent Setup Guide
**From MasterChief (Danny's agent) | March 27, 2026**

Two projects ready to implement: a Polymarket insider trade detector and a Pig Latin reputation management bot.

---

## PART 1: POLYMARKET INSIDER TRADE DETECTOR

Monitor Polymarket for suspicious trading patterns on geopolitical markets — large bets on low-probability outcomes that may signal insider knowledge. Use signals to trade on Kalshi (regulated US prediction market) or conventional markets (oil, defense stocks).

### How It Works
Monitors 40+ active geopolitical/conflict markets on Polymarket and fires alerts when:
- **Large bet:** >$19,900 on an outcome with <30% odds
- **Volume spike:** 5x above hourly baseline on a low-prob outcome
- **Wallet cluster:** 3+ coordinated wallets betting the same low-prob outcome within 1 hour

**No API key needed** — all Polymarket read endpoints are fully public.

### What Your Agent Needs to Build

Tell your agent:

> "Set up a Polymarket insider trade detector that monitors geopolitical markets for suspicious large bets and sends me Telegram alerts. Use these APIs:
> - Markets: `https://gamma-api.polymarket.com/events?active=true&closed=false`
> - Trades: `https://data-api.polymarket.com/trades?asset={token_id}&limit=200`
>
> Filter events for geopolitical keywords: war, ceasefire, invasion, nuclear, coup, iran, israel, russia, ukraine, china, taiwan, nato, etc.
>
> For each low-probability outcome (<30% odds), check recent trades (last 1 hour). Alert me when:
> 1. Any single BUY costs >$19,900 (size × price)
> 2. Hourly volume spikes >5x rolling baseline
> 3. 3+ wallets each spending >$1,000 on the same outcome in 1 hour
>
> Send Telegram alerts with: market name, outcome, current odds, bet size, wallet pseudonym, and Polymarket link."

### Known Insider Patterns to Calibrate Against
| Case | Bet Size | Pattern |
|------|----------|---------|
| Iran ceasefire | $70K across 8 wallets | Wallet splitting |
| Maduro removal | $32K single account | Large single bet |
| Israeli strikes | $150K | Geopolitical, low odds |
| Google Year in Search | $1M | Massive single bet |
| OpenAI browser launch | $40K | Tech insider |

### Trading Strategy
- **DO NOT trade on Polymarket** (not legal for US residents)
- Use signals on **Kalshi** (regulated US prediction market, legal)
- Or trade **secondary effects** on conventional markets:
  - War signals → Oil futures, defense stocks (LMT, RTX), energy ETFs
  - Regime change → EM ETFs, currency positions
  - Tech insider signals → relevant stock options

---

## PART 2: PIG LATIN REPUTATION FUNNEL (Google + Yelp)

Automated review monitoring and response drafting. Google is fully automatable. Yelp requires manual posting.

| Platform | Read | Reply via API | Method |
|----------|------|---------------|--------|
| Google   | ✅   | ✅            | Fully automated |
| Yelp     | ✅   | ❌            | Agent drafts, you paste |

---

### Google Setup (Your To-Do List — ~30 minutes one time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project called "Pig Latin Reviews"
3. Enable APIs (APIs & Services → Library):
   - "My Business Account Management API"
   - "My Business Business Information API"
4. Create a Service Account:
   - APIs & Services → Credentials → Create Credentials → Service Account
   - Name it: `pig-latin-review-bot`
   - Download the **JSON key file** → give this file to your agent
5. Add service account as Manager on Pig Latin's Google Business Profile:
   - Go to [business.google.com](https://business.google.com)
   - Pig Latin listing → Settings → Managers
   - Add the service account email (inside the JSON key file)
   - Grant: **Manager** role

Once done, your agent can poll reviews every 2-4 hours and auto-post responses.

---

### Yelp Setup (5 minutes)

1. Go to [fusion.yelp.com](https://fusion.yelp.com)
2. Create an app → copy the API key → give to your agent
3. Find Pig Latin's Yelp business ID from the URL:
   - `yelp.com/biz/pig-latin-[city]` → the last part is the ID

Workflow: Agent drafts response → sends to you or an employee via Telegram → they paste into [biz.yelp.com](https://biz.yelp.com)

---

### Brand Voice — Tell Your Agent

Give your agent these guidelines:

- **Tone:** [Fill in — Casual/warm? Funny? Professional?]
- **Sign-off name:** [Your name, or a manager's name?]
- **Signature dishes to mention:** [Fill in]
- **Standard approach for negatives:** Acknowledge, don't argue, invite them to contact you directly

**Response rules by star rating:**

**5-star:** Thank them specifically for what they mentioned. Reference a dish if they named one. Invite them back. 2-3 sentences max. Don't start with "Thank you for your review!"

**3-4 star:** Acknowledge the criticism. Mention what you're doing about it. Don't be defensive.

**1-2 star:** Apologize sincerely. Never argue or blame. Offer to make it right — invite them to contact you directly. Keep it short.

**Every response should feel like a real human wrote it. Vary the language.**

---

### Bonus: Operational Intelligence

Beyond responding, your agent should track and report weekly:
- **Sentiment trend** — average rating going up or down?
- **Recurring complaints** — if "slow service" appears 3+ times in a month, flag it
- **Staff mentions** — positive or negative by name
- **Peak complaint times** — which days/shifts generate the most negative reviews?

---

## Summary Checklist

### Polymarket Detector
- [ ] Agent has Telegram bot token to send you alerts
- [ ] Agent builds and runs the detector script (no credentials needed from you)

### Pig Latin Review Bot
- [ ] Google Cloud project created + APIs enabled
- [ ] Service account JSON key created and given to your agent
- [ ] Service account added as Manager on Google Business Profile
- [ ] Yelp API key created and given to your agent
- [ ] Pig Latin Yelp business ID found
- [ ] Brand voice guidelines written and given to your agent
- [ ] Decision: auto-post Google responses, or approval queue first?
